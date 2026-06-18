"""Real-time driver for CRM Sequence steps (single-driver model).

The sequence engine (`CRM Sequence Runner Core`, a Server Script) advances ONE
step per call. Server Scripts run in a RestrictedPython sandbox with no
`time.sleep` and no delayed enqueue (no rq_scheduler), so they can't honor
seconds-level waits. This module runs in a normal background worker (not
sandboxed): it sleeps the real wait between steps and reuses the engine for the
actual per-step action, so the send logic stays in exactly one place.

Single-driver model — `drain()` is the ONLY thing that advances an enrollment,
and `job_id="seqdrain:<enrollment>"` (deduped via is_job_enqueued, which covers
QUEUED *and* STARTED jobs) guarantees at most one drainer per enrollment ever
runs. That is what makes the cron + drainer handoff race-free: there is never a
second driver that could fire the same step. The old blanket `CRM Sequence
Runner` core-cron is DISABLED so it can't act as a second driver.

Two enqueue paths, both funnelling to the same per-enrollment job_id:
  - `enqueue_for_lead` (CRM Lead doc-event) -> `drain_lead` -> drain, for the
    instant burst the moment a lead enrolls (low latency).
  - `drain_due` (1-min scheduler in hooks.py) -> drain, the backstop that keeps
    sub-minute follow-on steps (e.g. rapid texts after a longer wait) firing
    without being rounded up to the cron tick.

Performance: drainers SLEEP, so they run on a DEDICATED queue (`seqdrain`) with
its own worker container — a sleeping drainer never blocks the main background
queue (emails, ring-alerts, contact sync). Waits longer than LONG_WAIT_SECONDS
are handed back (the drainer returns; `drain_due` re-enqueues it once it is due),
so a single drainer holds its worker for at most ~LONG_WAIT_SECONDS. For higher
lead volume, scale the drain-worker (replicas) or move to delay-based scheduling
(rq_scheduler) to avoid sleeping entirely.
"""

import time

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime
from frappe.utils.background_jobs import is_job_enqueued
from frappe.utils.safe_exec import call_with_form_dict

# dedicated queue so sleeping drainers never block the main background worker
DRAIN_QUEUE = "seqdrain"
# the drainer sleeps waits up to this; longer waits are handed back to drain_due.
# Kept >= the 1-min scheduler interval so every step still fires on time (there
# is always a scheduler tick within this window before a step is due).
LONG_WAIT_SECONDS = 60
# drain_due enqueues an enrollment once it is due within this window. Must be
# <= LONG_WAIT_SECONDS, else a freshly-enqueued drainer would immediately hand
# the step back instead of sleeping for it.
LOOKAHEAD_SECONDS = 60
# safety cap on steps drained in one job (no real sequence chains this many
# sub-minute steps; guards against a misconfigured loop holding a worker open)
MAX_STEPS = 50


def _run_core(enrollment):
	"""Run the API-type engine scoped to one enrollment — exactly what the
	sandbox `run_script("CRM Sequence Runner Core", enrollment=...)` does, so the
	actual send/skip logic stays in the single engine script."""
	call_with_form_dict(
		lambda: frappe.get_doc("Server Script", "CRM Sequence Runner Core").execute_method(),
		{"enrollment": enrollment},
	)


def _enqueue_drain(enrollment):
	"""Enqueue the (single) drainer for an enrollment, on the dedicated queue.
	is_job_enqueued covers QUEUED and STARTED, so a drainer already running for
	this enrollment is never duplicated — the core of the race-free guarantee."""
	job_id = "seqdrain:" + enrollment
	if not is_job_enqueued(job_id):
		frappe.enqueue(
			"crm.api.sequence_drain.drain",
			enrollment=enrollment,
			queue=DRAIN_QUEUE,
			job_id=job_id,
		)


def drain(enrollment):
	"""Worker job (seqdrain queue): drive ONE enrollment through its due steps in
	real time, sleeping each step's real wait. Sole advancer of an enrollment."""
	for _ in range(MAX_STEPS):
		enr = frappe.get_doc("CRM Sequence Enrollment", enrollment)
		if enr.status != "Active":
			return
		if enr.next_run:
			delta = (get_datetime(enr.next_run) - now_datetime()).total_seconds()
			if delta > LONG_WAIT_SECONDS:
				return  # long wait — drain_due re-enqueues this once it is due
			if delta > 0:
				time.sleep(delta)
		_run_core(enrollment)
		frappe.db.commit()


def drain_lead(lead):
	"""Quick job (off the sleeping queue): enqueue a drainer for each Active
	enrollment of a freshly-enrolled lead. Run from a worker (after commit) so the
	enrollment the Sequence Auto Enroll server script creates in the lead's save
	transaction is already visible."""
	for e in frappe.get_all(
		"CRM Sequence Enrollment",
		filters={"lead": lead, "status": "Active"},
		fields=["name"],
	):
		_enqueue_drain(e.name)


def drain_due():
	"""1-min scheduler backstop: enqueue a drainer for every Active enrollment due
	within the lookahead window (or with no next_run yet). Sole periodic driver —
	replaces the old `CRM Sequence Runner` core-cron, which is disabled."""
	soon = add_to_date(now_datetime(), seconds=LOOKAHEAD_SECONDS)
	rows = frappe.get_all(
		"CRM Sequence Enrollment",
		filters={"status": "Active"},
		or_filters=[["next_run", "<=", soon], ["next_run", "is", "not set"]],
		fields=["name"],
	)
	for e in rows:
		_enqueue_drain(e.name)


def enqueue_for_lead(doc, method=None):
	"""CRM Lead after_insert / on_update doc-event: when a lead's source is set or
	changed (the same trigger as auto-enroll), enqueue an instant drainer for it
	after commit. job_id dedupes concurrent saves of the same lead."""
	if doc.source and doc.has_value_changed("source"):
		frappe.enqueue(
			"crm.api.sequence_drain.drain_lead",
			lead=doc.name,
			enqueue_after_commit=True,
			job_id="seqdrain-lead:" + doc.name,
			queue="short",
		)
