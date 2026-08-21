# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""When a lead changes hands, the work on it changes hands too.

Ownership genuinely moves now — the round robin deals new leads out, the
backfill redistributed the old ones, and a rep can hand a deal over from the
Today board (`crm.api.today_board.assign_today_leads`). What did NOT move with it
was the work already sitting on the lead:

* **Open tasks kept the old owner.** Sequence call-tasks and hand-written to-dos
  are assigned to whoever owned the lead when they were created. Reassign the
  lead and those tasks stay pointed at the previous rep — who now cannot see the
  lead on their board, so the task is invisible to both of them. It still counts
  as due work in every "due today" list, against a person who is no longer
  supposed to touch it.

* **The old owner stayed assigned to the lead.** `CRM Lead.validate()` already
  shares and assigns the NEW owner on an owner change, but `assign_agent` only
  ever ADDS an assignee — it has no removal half. So a lead that moved twice ends
  up assigned to three people, and the previous owner keeps seeing it in their
  assigned list forever. This is the same double-assignment
  `crm.api.lead_owner_backfill` had to fix up by hand for its bulk run; here it
  is fixed once, for every path that changes an owner.

Two rules keep this from overreaching:

* **Only OPEN tasks move.** A Done or Canceled task is a record of who did it,
  not outstanding work — rewriting it would rewrite history.
* **Only tasks that were following the OLD OWNER move**, i.e. assigned to them or
  assigned to nobody. A task deliberately handed to a third person is a human
  decision and stays with that person.

Everything here is best-effort. A hygiene hook must never be the reason a rep
cannot save a lead, so every failure is logged and swallowed — the same rule
`crm.api.task_hygiene` follows.
"""

import frappe
from frappe.desk.form.assign_to import remove as unassign_todo

LEAD = "CRM Lead"
TASK = "CRM Task"

#: A task in one of these states is still outstanding work and follows the lead.
#: Deliberately spelled out rather than derived as "not Done/Canceled" so a new
#: terminal status added upstream cannot silently start being reassigned.
OPEN_TASK_STATES = ("Backlog", "Todo", "In Progress")


def on_lead_update(doc, method=None):
	"""`CRM Lead` on_update hook: move the lead's open work to its new owner."""
	try:
		if doc.is_new() or not doc.has_value_changed("lead_owner"):
			return
		new_owner = (doc.lead_owner or "").strip()
		if not new_owner:
			# An owner being CLEARED is not a handover. Stripping the old owner's
			# assignment here would leave the lead owned by nobody and assigned to
			# nobody, i.e. invisible on every board — strictly worse than leaving it
			# where it was until someone picks it up.
			return
		before = doc.get_doc_before_save()
		old_owner = ((before.lead_owner if before else "") or "").strip()
		if old_owner == new_owner:
			return
		handover(doc.name, old_owner, new_owner)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Lead owner handover failed")


def handover(lead: str, old_owner: str, new_owner: str) -> dict:
	"""Point the lead's open work at `new_owner` and let `old_owner` go.

	Split out from the hook so a bulk reassignment can call it directly, and so
	it can be exercised from bench without saving a lead.
	"""
	moved = _move_open_tasks(lead, old_owner, new_owner)
	dropped = _drop_stale_assignment(lead, old_owner, new_owner)
	return {"lead": lead, "tasks_moved": moved, "unassigned_old_owner": dropped}


def _move_open_tasks(lead: str, old_owner: str, new_owner: str) -> list[str]:
	"""Reassign the lead's outstanding tasks, leaving finished ones alone."""
	filters = {
		"reference_doctype": LEAD,
		"reference_docname": lead,
		"status": ["in", OPEN_TASK_STATES],
	}
	# An unassigned task followed the lead implicitly, so it moves too; a task
	# assigned to somebody who was never the lead owner was put there by a person
	# and is left alone.
	followers = [old_owner, "", None] if old_owner else ["", None]
	filters["assigned_to"] = ["in", followers]

	moved = []
	for name in frappe.get_all(TASK, filters=filters, pluck="name"):
		try:
			task = frappe.get_doc(TASK, name)
			task.assigned_to = new_owner
			# doc.save() rather than db.set_value on purpose: `CRM Task.validate()`
			# is what unassigns the previous user and creates the new ToDo, and
			# `notify_task_update` is what refreshes every open board and to-do
			# block. A silent column write would move the task on paper only.
			task.save(ignore_permissions=True)
			moved.append(name)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(), f"Could not move task {name} to {new_owner}"
			)
	return moved


def _drop_stale_assignment(lead: str, old_owner: str, new_owner: str) -> bool:
	"""Remove the previous owner's automatic assignment from the lead itself.

	Only ever the previous *owner*: anyone else on the lead was put there by a
	person, and this is not the place to overrule them. The new owner's share and
	assignment are already handled by `CRM Lead.validate()`.
	"""
	if not old_owner or old_owner == new_owner:
		return False
	current = frappe.parse_json(frappe.db.get_value(LEAD, lead, "_assign") or "[]")
	if old_owner not in current:
		return False
	try:
		unassign_todo(LEAD, lead, old_owner)
		return True
	except Exception:
		frappe.log_error(
			frappe.get_traceback(), f"Could not unassign {old_owner} from {lead}"
		)
		return False
