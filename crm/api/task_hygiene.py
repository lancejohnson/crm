# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Close out follow-up tasks when a lead stops being workable.

A lead that goes Dead Lead / Lost keeps whatever open follow-up tasks it had.
Nothing ever retired them, so they sat in the To-do block and in every
"due today" list forever. Measured on prod 2026-08-03: **25 open tasks on Dead
Leads** (the oldest due 2026-06-22), which was a quarter of the entire
due-or-overdue task backlog. Working that list meant calling dead leads — the
same disease that made the old iSpeedToLead digest useless ("the due list had
33 leads, but most were Dead Lead").

Two entry points:

  * `on_lead_update` — a `CRM Lead` on_update hook. When a lead moves INTO a
    dead status, its open tasks are canceled.
  * `backfill_terminal_tasks` — a bench-executable sweep for the ones already
    sitting there. Dry-run by default.

Design notes
------------
* **Keyed on `CRM Lead Status.type == "Lost"`, not on status names.** Both
  "Dead Lead" and "Lost" are type Lost, so this keeps working if a status is
  renamed or a new dead status ("Not Interested", "Do Not Call") is added. The
  previous report broke precisely because it hardcoded a guessed status list.
* **Won is deliberately NOT included.** A won deal can still carry legitimate
  closing tasks. To include it, add "Won" to `TERMINAL_TYPES`.
* **Canceled, never deleted.** The task stays on the timeline (struck through)
  so the history of what was planned survives.
* **A hygiene failure must never block the lead save.** The whole hook body is
  wrapped — worst case the tasks stay open and the backfill catches them.
* Tasks are canceled via `doc.save()` rather than `db.set_value` so
  `CRM Task.on_update` fires and publishes `crm_task_update`, which is what
  refreshes the open Kanban badge and the Activity to-do block live.
"""

import frappe

#: `CRM Lead Status.type` values that mean "stop working this lead".
TERMINAL_TYPES = ("Lost",)

#: `CRM Task.status` values that are still outstanding.
OPEN_TASK_STATUSES = ("Backlog", "Todo", "In Progress")


def is_terminal_status(status: str) -> bool:
	"""True if this lead status means the lead is dead (type Lost)."""
	if not status:
		return False
	try:
		return frappe.get_cached_value("CRM Lead Status", status, "type") in TERMINAL_TYPES
	except Exception:
		return False


def cancel_open_tasks(lead: str, doctype: str = "CRM Lead") -> list[str]:
	"""Cancel every open task on `lead`. Returns the task names canceled."""
	tasks = frappe.get_all(
		"CRM Task",
		filters={
			"reference_doctype": doctype,
			"reference_docname": lead,
			"status": ["in", OPEN_TASK_STATUSES],
		},
		pluck="name",
	)
	canceled = []
	for name in tasks:
		try:
			task = frappe.get_doc("CRM Task", name)
			task.status = "Canceled"
			task.save(ignore_permissions=True)
			canceled.append(name)
		except Exception:
			frappe.log_error(
				title="task_hygiene: could not cancel task",
				message=f"task={name} lead={lead}\n{frappe.get_traceback()}",
			)
	return canceled


def on_lead_update(doc, method=None):
	"""CRM Lead on_update hook — retire open tasks when a lead goes dead.

	Gated on `has_value_changed("status")` so this is a single in-memory check
	on the overwhelmingly common save, and so re-saving an already-dead lead
	does not keep re-running (and cannot resurrect-then-recancel a task a human
	deliberately reopened).
	"""
	try:
		if not doc.has_value_changed("status"):
			return
		if not is_terminal_status(doc.status):
			return
		cancel_open_tasks(doc.name, doc.doctype)
	except Exception:
		# Never let hygiene break a status change.
		frappe.log_error(
			title="task_hygiene: on_lead_update failed",
			message=f"lead={getattr(doc, 'name', '?')}\n{frappe.get_traceback()}",
		)


@frappe.whitelist()
def backfill_terminal_tasks(dry_run=1, limit=None):
	"""Cancel open tasks already sitting on dead leads.

	Dry-run by default — pass `dry_run=0` to actually write:

	    bench --site <site> execute crm.api.task_hygiene.backfill_terminal_tasks \\
	        --kwargs '{"dry_run": 1}'
	"""
	if isinstance(dry_run, str):
		dry_run = dry_run not in ("0", "false", "False", "")
	dry_run = bool(int(dry_run)) if not isinstance(dry_run, bool) else dry_run

	dead = frappe.get_all(
		"CRM Lead Status", filters={"type": ["in", TERMINAL_TYPES]}, pluck="name"
	)
	if not dead:
		return {"dead_statuses": [], "leads": 0, "tasks": 0, "dry_run": dry_run, "detail": []}

	rows = frappe.get_all(
		"CRM Task",
		filters={"reference_doctype": "CRM Lead", "status": ["in", OPEN_TASK_STATUSES]},
		fields=["name", "title", "status", "due_date", "reference_docname"],
		order_by="due_date asc",
	)
	lead_status = {}
	detail = []
	for r in rows:
		lead = r.reference_docname
		if lead not in lead_status:
			lead_status[lead] = frappe.db.get_value("CRM Lead", lead, "status")
		if lead_status[lead] not in dead:
			continue
		detail.append(
			{
				"task": r.name,
				"title": r.title,
				"task_status": r.status,
				"due_date": str(r.due_date) if r.due_date else None,
				"lead": lead,
				"lead_status": lead_status[lead],
			}
		)
		if limit and len(detail) >= int(limit):
			break

	if not dry_run:
		for d in detail:
			try:
				task = frappe.get_doc("CRM Task", d["task"])
				task.status = "Canceled"
				task.save(ignore_permissions=True)
			except Exception:
				d["error"] = frappe.get_traceback(with_context=False)[-300:]
				frappe.log_error(
					title="task_hygiene: backfill could not cancel task",
					message=f"task={d['task']}\n{frappe.get_traceback()}",
				)
		frappe.db.commit()

	return {
		"dead_statuses": dead,
		"leads": len({d["lead"] for d in detail}),
		"tasks": len(detail),
		"dry_run": dry_run,
		"detail": detail,
	}
