"""Status gating for CRM Sequences.

A sequence can name the lead statuses it runs in (`CRM Sequence.lead_statuses`,
one per line — the same shape as `auto_enroll_sources`; ops
`setup_sequence_statuses.py` adds the column). Empty means "any status", which
is exactly the pre-existing behaviour, so deploying this changes nothing until
someone edits a sequence.

The moment a lead leaves the set — a rep moves it to Follow Up, Underwriting,
Dead — every Active enrollment of a gated sequence is **Paused**, not Stopped:
the rep can Resume from the sequence's Enrollments list if the move was a
mis-click, and `last_log` says why it stopped. Nothing auto-resumes when a lead
returns to an included status; resuming a stale text run is a human decision.

Two enforcement points, both in app code so the sandboxed engine is untouched:

- `on_lead_update` (CRM Lead on_update hook) pauses at the moment of the status
  change, so the enrollment table reflects it immediately.
- `check_before_step` runs inside the drainer before every step, as the safety
  net for any status write that bypassed the hook (`db.set_value` paths) and for
  a lead that was already outside the set when it was enrolled by hand.
"""

import frappe
from frappe.utils import now_datetime

FIELD = "lead_statuses"


def _supported() -> bool:
	try:
		return frappe.db.has_column("CRM Sequence", FIELD)
	except Exception:
		return False


def parse_statuses(raw) -> frozenset | None:
	"""One status per line; blank → None (= any status). Pure."""
	names = [line.strip() for line in (raw or "").splitlines() if line.strip()]
	return frozenset(names) if names else None


def allowed_statuses(sequence) -> frozenset | None:
	if not _supported():
		return None
	return parse_statuses(frappe.db.get_value("CRM Sequence", sequence, FIELD))


def status_excluded(allowed, status) -> bool:
	"""Pure: True when the sequence names statuses and this one is not among them."""
	return allowed is not None and (status or "") not in allowed


def _pause(enrollment_name, reason):
	frappe.db.set_value(
		"CRM Sequence Enrollment",
		enrollment_name,
		{
			"status": "Paused",
			"last_log": "{0} auto-paused: {1}".format(now_datetime(), reason),
		},
		update_modified=False,
	)


def pause_excluded_enrollments(lead, status, reason=None) -> list:
	"""Pause every Active enrollment of `lead` whose sequence does not include
	`status`. Returns the enrollment names paused. Never raises."""
	paused = []
	try:
		if not _supported():
			return paused
		rows = frappe.get_all(
			"CRM Sequence Enrollment",
			filters={"lead": lead, "status": "Active"},
			fields=["name", "sequence"],
		)
		for row in rows:
			if status_excluded(allowed_statuses(row.sequence), status):
				_pause(
					row.name,
					reason or "lead status '{0}' is not one this sequence runs in".format(status),
				)
				paused.append(row.name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "sequence_status: pause failed")
	return paused


def on_lead_update(doc, method=None):
	"""CRM Lead on_update: a status move out of a sequence's set pauses it."""
	try:
		if not doc.has_value_changed("status"):
			return
	except Exception:
		return
	pause_excluded_enrollments(
		doc.name,
		doc.status,
		reason="lead moved to '{0}', which this sequence does not run in".format(doc.status),
	)


def check_before_step(enr) -> bool:
	"""Drainer guard: True if the enrollment may run its next step. Pauses it
	(and returns False) when the lead's current status is outside the set."""
	try:
		allowed = allowed_statuses(enr.sequence)
		if allowed is None:
			return True
		status = frappe.db.get_value("CRM Lead", enr.lead, "status")
		if not status_excluded(allowed, status):
			return True
		_pause(enr.name, "lead status '{0}' is not one this sequence runs in".format(status))
		frappe.db.commit()
		return False
	except Exception:
		frappe.log_error(frappe.get_traceback(), "sequence_status: step guard failed")
		return True
