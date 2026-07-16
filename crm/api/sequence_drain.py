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
# Fail-safe: the engine catches step exceptions internally (logs "CRM Sequence
# Runner error") and leaves the enrollment Active-and-due, so before this
# existed a failing send (e.g. Quo out of prepaid credits, Jul 2026) was
# retried forever — flooding the Error Log and then blasting the whole stale
# backlog the moment the upstream problem cleared. Now a due run that advances
# nothing counts as a failure: the drain job stops (so retries happen once per
# drain_due tick, not in a hot loop) and after this many consecutive failures
# the enrollment is Paused and FAILSAFE_NOTIFY is emailed. Resume from the
# sequence's Enrollments list once the cause is fixed.
MAX_CONSECUTIVE_FAILURES = 10
FAILSAFE_NOTIFY = "lance.johnson@groundworkpro.com"


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
		before = (enr.current_step, str(enr.next_run), str(enr.modified))
		_run_core(enrollment)
		frappe.db.commit()
		enr = frappe.get_doc("CRM Sequence Enrollment", enrollment)
		if (enr.current_step, str(enr.next_run), str(enr.modified)) == before:
			# a due run that advanced nothing = the step raised (the engine
			# caught + logged it). Count it and stop this job — the next
			# drain_due tick retries, so failures accrue once a minute.
			if enr.status == "Active":
				_record_failure(enr)
			return
		_reset_failures(enr)


def _record_failure(enr):
	"""Bump the enrollment's consecutive-failure count; pause + notify at the
	threshold. No-ops when the fail_count field isn't provisioned yet, or when
	the sequence is disabled (the engine idles on those by design)."""
	if not frappe.db.has_column("CRM Sequence Enrollment", "fail_count"):
		return
	if not frappe.db.get_value("CRM Sequence", enr.sequence, "enabled"):
		return
	fails = (enr.get("fail_count") or 0) + 1
	if fails < MAX_CONSECUTIVE_FAILURES:
		frappe.db.set_value(
			"CRM Sequence Enrollment", enr.name, "fail_count", fails, update_modified=False
		)
		frappe.db.commit()
		return
	frappe.db.set_value(
		"CRM Sequence Enrollment",
		enr.name,
		{
			"status": "Paused",
			"fail_count": fails,
			"last_log": "{0} PAUSED by fail-safe: step {1} failed {2} runs in a row "
			"(see Error Log). Fix the cause, then set the enrollment back to Active.".format(
				now_datetime(), (enr.current_step or 0) + 1, fails
			),
		},
		update_modified=False,
	)
	frappe.db.commit()
	_notify_pause(enr, fails)


def _reset_failures(enr):
	"""Progress happened — clear the consecutive-failure count (if any)."""
	if enr.get("fail_count"):
		frappe.db.set_value(
			"CRM Sequence Enrollment", enr.name, "fail_count", 0, update_modified=False
		)
		frappe.db.commit()


def _notify_pause(enr, fails):
	"""Email the admin that an enrollment was paused. Never raises — a mail
	failure must not break the drainer."""
	try:
		lead_name = frappe.db.get_value("CRM Lead", enr.lead, "lead_name") or enr.lead
		lead_url = frappe.utils.get_url("/crm/leads/" + enr.lead)
		frappe.sendmail(
			recipients=[FAILSAFE_NOTIFY],
			subject="Sequence paused: {0} — {1}".format(enr.sequence, lead_name),
			message=(
				"<p>The sequence enrollment <b>{0}</b> (<b>{1}</b> for lead "
				'<a href="{2}">{3}</a>) was paused after step {4} failed '
				"{5} runs in a row.</p>"
				"<p>The step's error is in the site's Error Log (\"CRM Sequence "
				"Runner error\"). Fix the cause — e.g. Quo out of prepaid credits — "
				"then set the enrollment back to <b>Active</b> on the sequence's "
				"Enrollments list to resume where it left off, or <b>Stopped</b> "
				"if the queued messages are stale and shouldn't go out.</p>"
			).format(
				enr.name,
				enr.sequence,
				lead_url,
				lead_name,
				(enr.current_step or 0) + 1,
				fails,
			),
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "sequence fail-safe: pause email failed")


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
