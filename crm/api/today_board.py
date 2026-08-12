# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""The shared **Today** board — the surface the setters actually work from.

The 5am standup DM tells Lance what the day looks like; this is where German and
Exe do it. `crm.api.daily_standup` decides WHO lands on the board (Dennis's
cadence, business-day counting, task suppression — all of it lives there and is
not duplicated here); this module owns what happens to a card afterwards: tick it
Done, Skip it, drag it into a different order.

Division of responsibility, deliberately:

  * the cadence decides what LANDS on the board (generation, once a day)
  * a human owns the card after that (state + order, persisted)

which is why cards are rows rather than a live recomputation. "Done" and
"Skipped" are judgements a person made; recomputing the list would quietly lose
them, or resurrect a card someone had dismissed, the moment a call got logged.
The board also has to hold still while people work it — a list that reshuffles
underneath you is the thing that made the last attempt unusable.

`CRM Today Item` is autonamed `format:{for_date}-{lead}-{call_number}`. A lead
that owes two calls gets two independently actionable cards (call 1 and call 2),
while the call number keeps generation structurally idempotent.
"""

import json
import re
from collections import Counter
from datetime import timedelta

import frappe
from bs4 import BeautifulSoup
from frappe import _
from frappe.utils import escape_html, getdate, now_datetime

from crm.api.daily_standup import (
	build_standup,
	is_business_day,
	previous_business_day,
)

DOCTYPE = "CRM Today Item"
STATES = ("To Call", "Done", "Skipped")

#: What a card records when it is ticked Done. Deliberately five short answers:
#: the modal is a half-second interruption between two calls, and a list nobody
#: can read at a glance gets whatever option is nearest the thumb. "Other" is
#: the escape hatch and is the one answer that must be explained in words.
DONE_OUTCOMES = (
	"Connected",
	"No Answer",
	"Left a Voicemail",
	"Booked an Appointment",
	"Other",
)

#: The default personal priority order. Week-one's two calls are deliberately
#: separated so the first pass can be finished before afternoon follow-ups begin.
PRIORITY_ORDER = ("never", "task", "week1_am", "week1_pm", "weekly", "monthly")
PRIORITY_DEFAULT_KEY = "crm_today_priority_order"


def _priority_key(phase, call_number=1):
	if phase in ("week1", "week1_partial"):
		return "week1_am" if int(call_number or 1) == 1 else "week1_pm"
	return phase if phase in PRIORITY_ORDER else "monthly"


def _priority_order():
	raw = frappe.defaults.get_user_default(PRIORITY_DEFAULT_KEY)
	try:
		stored = json.loads(raw) if isinstance(raw, str) else raw
	except (TypeError, ValueError):
		stored = []
	clean = []
	for key in stored or []:
		if key in PRIORITY_ORDER and key not in clean:
			clean.append(key)
	return clean + [key for key in PRIORITY_ORDER if key not in clean]


def _priority_seed(phase, call_number=1):
	return PRIORITY_ORDER.index(_priority_key(phase, call_number)) * 10000


def _available() -> bool:
	"""The doctype is provisioned by an ops script; degrade quietly if it isn't
	there yet rather than 500-ing every caller."""
	return bool(frappe.db.exists("DocType", DOCTYPE))


def _supports_call_slots() -> bool:
	"""The first Today schema had one row per lead. Keep reads working while the
	idempotent ops setup adds call_number/total_calls and changes autoname."""
	if not _available():
		return False
	meta = frappe.get_meta(DOCTYPE)
	return bool(meta.has_field("call_number") and meta.has_field("total_calls"))


def _row_fields(with_slots=False):
	fields = ["name", "lead", "state", "sort_order", "phase", "reason",
	          "calls_needed", "done_by", "done_at"]
	if with_slots:
		fields += ["call_number", "total_calls"]
	if _supports_outcome():
		fields += ["outcome", "outcome_note"]
	return fields


def _supports_outcome() -> bool:
	"""`outcome`/`outcome_note` are added by the same idempotent ops script that
	provisions the doctype. Degrade quietly if the app is deployed first: the board
	still resolves cards, it just doesn't record why."""
	if not _available():
		return False
	meta = frappe.get_meta(DOCTYPE)
	return bool(meta.has_field("outcome") and meta.has_field("outcome_note"))


def _supports_resolved_stamp() -> bool:
	"""`resolved_at`/`resolved_by` are added by the same idempotent ops script that
	provisions the doctype. Degrade quietly if the app is deployed first."""
	if not _available():
		return False
	meta = frappe.get_meta(DOCTYPE)
	return bool(meta.has_field("resolved_at") and meta.has_field("resolved_by"))


def _log_outcome_comment(card, state, outcome="", outcome_note="", corrected=False):
	"""Write a Today-board disposition onto the lead's own activity timeline.

	The board is where the judgement gets made, but the lead page is where anyone
	later asks "what happened when we called this person?" — so the answer has to
	live there too, not only on a card that scrolls out of the day and is never
	seen again. This is what makes a skip reason survive past 5pm.

	Best-effort by design: a timeline entry is never worth failing a rep's click
	over, so every failure is logged and swallowed.

	Put-backs are deliberately NOT logged. Undoing a mis-click is not a judgement
	about the seller, and a timeline full of "moved back to To Call" would bury the
	entries that are — the same reasoning that keeps the outcome modal from
	interrogating a put-back.
	"""
	if state not in ("Done", "Skipped"):
		return
	lead = card.get("lead") if isinstance(card, dict) else getattr(card, "lead", None)
	if not lead:
		return
	try:
		label = _("Done") if state == "Done" else _("Skipped")
		head = (
			_("Today board — outcome corrected to {0}").format(label)
			if corrected
			else _("Today board — marked {0}").format(label)
		)
		call_no = (card.get("call_number") if isinstance(card, dict) else getattr(card, "call_number", 0)) or 0
		if call_no and int(call_no) > 1:
			head += " " + _("(call {0})").format(int(call_no))
		detail = " · ".join(escape_html(b) for b in (outcome, outcome_note) if b)
		content = "<div><b>{0}</b>{1}</div>".format(
			escape_html(head), "<br>{0}".format(detail) if detail else ""
		)
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Comment",
				"reference_doctype": "CRM Lead",
				"reference_name": lead,
				"content": content,
				"comment_email": frappe.session.user,
				"comment_by": frappe.session.user,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Today outcome comment failed")


def _state_stamps(state, now=None):
	"""The stamp columns that go with a state change, in ONE place.

	Drag and the hover buttons take different code paths (`reorder_today` writes
	with `db.set_value`; `set_today_state` saves the doc), and they were already
	out of step: a card DRAGGED into Skipped never got `resolved_at`, so the
	intraday pulse — which reads exactly that column — saw a rep who works by
	dragging as idle.

	`done_*` stays Done-only: the Today report's "completed by" list, the
	Lance-only activity pulse and the card UI all read it with that meaning.
	`resolved_*` covers Done AND Skipped, because a skip is a real judgement a
	person made. Moving a card back to "To Call" un-resolves it.
	"""
	now = now or now_datetime()
	updates = {}
	if state == "Done":
		updates["done_by"] = frappe.session.user
		updates["done_at"] = now
	else:
		updates["done_by"] = None
		updates["done_at"] = None
	if _supports_resolved_stamp():
		if state == "To Call":
			updates["resolved_by"] = None
			updates["resolved_at"] = None
		else:
			updates["resolved_by"] = frappe.session.user
			updates["resolved_at"] = now
	return updates


def _guard():
	roles = set(frappe.get_roles())
	if not roles & {"System Manager", "Sales Manager", "Sales User"}:
		frappe.throw(_("Not permitted"), frappe.PermissionError)


#: Sentinel for "don't scope to one person" — the whole-team board everyone saw
#: before leads were split between the setters.
ALL_OWNERS = "all"

#: Owner value for a lead nobody owns. Kept selectable rather than hidden: an
#: ownerless lead still owes a call, and if it only ever showed up on a board
#: nobody looks at, it would quietly go uncalled.
UNASSIGNED = ""


def _resolve_owner(owner):
	"""Whose board are we showing? Defaults to your own.

	The board is deliberately NOT permission-scoped — anyone on the sales team can
	look at anyone's list (it is a five-person company, and the standup is read off
	these lists together). Defaulting to your own is what stops it being a wall of
	other people's work.
	"""
	if owner is None:
		return frappe.session.user
	owner = str(owner).strip()
	if owner.lower() == ALL_OWNERS:
		return ALL_OWNERS
	return owner


def _owner_options(rows):
	"""Everyone with cards today, with their card count, for the board switcher.

	Built from the day's cards rather than from the user list so it can't offer a
	board that is empty, and so an unexpected owner (a lead still on the old
	default owner, say) is visible instead of silently unreachable.
	"""
	counts = Counter((r.get("lead_owner") or UNASSIGNED) for r in rows)
	if not counts:
		return []

	emails = [user for user in counts if user]
	names = {}
	if emails:
		names = {
			u.name: u.full_name or u.name
			for u in frappe.get_all(
				"User", filters={"name": ["in", emails]}, fields=["name", "full_name"]
			)
		}

	options = [
		{
			"user": user,
			"full_name": names.get(user) or (user or _("Unassigned")),
			"count": count,
		}
		for user, count in counts.items()
	]
	options.sort(key=lambda o: (not o["user"], -o["count"], o["full_name"]))
	return options


def _expand_legacy_items(day):
	"""Turn an old two-call lead card into two one-call cards, once.

	Existing cards keep their state and relative order. That matters on the day
	the schema is upgraded: an old Done/Skipped card represented the human's
	judgement for the whole lead, so both generated call cards inherit it rather
	than resurrecting work. Names are intentionally not rewritten; the old
	`date-lead` row becomes call 1 and the new formatted row is call 2.
	"""
	if not _supports_call_slots():
		return 0
	rows = frappe.get_all(
		DOCTYPE,
		filters={"for_date": day},
		fields=_row_fields(True),
		order_by="sort_order asc, name asc",
	)
	legacy = [r for r in rows if int(r.calls_needed or 0) > 1]
	if not legacy:
		return 0

	# Preserve the exact visible order while opening integer gaps for sibling
	# call cards. (sort_order is an Int, so fractions are not available.)
	for i, row in enumerate(rows):
		frappe.db.set_value(
			DOCTYPE, row.name, "sort_order", (i + 1) * 10, update_modified=False
		)
		row.sort_order = (i + 1) * 10

	created = 0
	for row in legacy:
		total = max(1, int(row.calls_needed or 1))
		frappe.db.set_value(
			DOCTYPE,
			row.name,
			{"call_number": 1, "total_calls": total, "calls_needed": 1},
			update_modified=False,
		)
		for slot in range(2, total + 1):
			try:
				frappe.get_doc(
					{
						"doctype": DOCTYPE,
						"for_date": day,
						"lead": row.lead,
						"state": row.state,
						"sort_order": row.sort_order + slot - 1,
						"phase": row.phase,
						"reason": row.reason,
						"calls_needed": 1,
						"call_number": slot,
						"total_calls": total,
						"done_by": row.done_by if row.state == "Done" else None,
						"done_at": row.done_at if row.state == "Done" else None,
					}
				).insert(ignore_permissions=True)
				created += 1
			except frappe.DuplicateEntryError:
				# Concurrent first views can both attempt the expansion; autoname is
				# the lock, so the loser simply observes the row the winner inserted.
				pass
	frappe.db.commit()
	_publish(day)
	return created


def _slots_for(row):
	"""Return (slot numbers still owed, total calls represented today).

	Only the first-week cadence is a twice-daily cadence. If the first call was
	logged before the board generated, create only call 2; weekly/monthly/task
	cards remain a single call even if some unrelated call was already logged.
	"""
	if row.phase in ("never", "week1"):
		total = 2
		first = min(total, int(row.calls_today or 0)) + 1
		return range(first, total + 1), total
	return range(1, max(1, int(row.calls_needed or 1)) + 1), max(
		1, int(row.calls_needed or 1)
	)


@frappe.whitelist()
def generate_today(for_date=None):
	"""Manually sync missing cards from the latest cadence/task state.

	Only ever ADDS. Existing cards keep their human-owned state and position, so a
	standup/status/task change can add newly-due work without resurrecting or
	reordering anything the team already judged.
	"""
	_guard()
	return _generate_today(getdate(for_date or now_datetime()))


#: The board's working day ends at 5pm CT. Cards are only ever added to an OPEN
#: board: work that arrives after the close belongs to the next list, not to a
#: day nobody is working any more.
#:
#: This is not a nicety. Measured on prod: German and Exe resolved EVERY card on
#: their boards on both 2026-08-10 and 08-11 — and both days still read as failed
#: streak days, because 20 new leads landed at 23:20–23:57 on the Monday (40
#: cards) and 4 more at 23:33 on the Tuesday (8 cards). Those late cards were the
#: entire unresolved remainder of both days. Nothing is lost by holding them
#: back, either: all 20 and all 4 of those leads appeared on the NEXT day's board
#: anyway, so the late add was pure duplication that only cost the streak.
BOARD_CLOSE_HOUR = 17


def _board_is_closed(day, now=None):
	"""Has this board's working day already ended?

	True after 5pm on the day itself, and for any day already past — materialising
	fresh work onto a board nobody will look at again is the same mistake either
	way. A future day is open: generation for tomorrow is exactly what the nightly
	job does.
	"""
	now = now or now_datetime()
	day, today = getdate(day), getdate(now)
	if day != today:
		return day < today
	return now.hour >= BOARD_CLOSE_HOUR


def _generate_today(day):
	"""Internal sync used by the manual button, hooks, and five-minute safety job."""
	if not _available():
		return {"created": 0, "existing": 0, "due": 0, "available": False}
	day = getdate(day or now_datetime())
	if _board_is_closed(day):
		# Deliberately reported rather than silently skipped: the manual "Sync list"
		# button has to be able to say why it added nothing, or it looks broken.
		return {
			"created": 0,
			"existing": frappe.db.count(DOCTYPE, {"for_date": day}),
			"due": 0,
			"available": True,
			"closed": True,
		}
	data = build_standup(day)
	due = data["setter"]["due"]
	with_slots = _supports_call_slots()
	if with_slots:
		_expand_legacy_items(day)
		existing_rows = frappe.get_all(
			DOCTYPE,
			filters={"for_date": day},
			fields=["name", "lead", "call_number"],
		)
		existing = {(r.lead, int(r.call_number or 1)) for r in existing_rows}
	else:
		existing_rows = frappe.get_all(
			DOCTYPE, filters={"for_date": day}, fields=["name", "lead"]
		)
		existing = {r.lead for r in existing_rows}

	created = 0
	for i, r in enumerate(due):
		if with_slots:
			slots, total = _slots_for(r)
			for slot in slots:
				if (r.name, slot) in existing:
					continue
				try:
					frappe.get_doc(
						{
							"doctype": DOCTYPE,
							"for_date": day,
							"lead": r.name,
							"state": "To Call",
							# Keep the morning and afternoon week-one passes apart.
							# The per-user preference is applied again at read time.
							"sort_order": _priority_seed(r.phase, slot) + (i + 1) * 10,
							"phase": r.phase,
							"reason": r.reason,
							"calls_needed": 1,
							"call_number": slot,
							"total_calls": total,
						}
					).insert(ignore_permissions=True)
					created += 1
					existing.add((r.name, slot))
				except frappe.DuplicateEntryError:
					pass
		elif r.name not in existing:
			seed = _priority_seed(r.phase) + i
			frappe.get_doc(
				{
					"doctype": DOCTYPE,
					"for_date": day,
					"lead": r.name,
					"state": "To Call",
					"sort_order": seed,
					"phase": r.phase,
					"reason": r.reason,
					"calls_needed": r.calls_needed,
				}
			).insert(ignore_permissions=True)
			created += 1
			existing.add(r.name)

	if created:
		frappe.db.commit()
		_publish(day)
	return {
		"created": created,
		"existing": len(existing_rows),
		"due": len(due),
		"available": True,
	}


def enqueue_today_sync(doc=None, method=None):
	"""Queue an add-only sync when a new lead or lead task may create work today.

	Imports can create many leads/tasks in one transaction, so active jobs are
	deduplicated. The five-minute scheduler is the safety net for the narrow race
	where a second commit lands while the deduplicated job is already finishing.
	"""
	try:
		day = getdate(now_datetime())
		if not _available() or not is_business_day(day):
			return
		# A lead that arrives at 11pm is tomorrow's work. Stop here rather than in
		# the job so a late-evening import doesn't queue a sync per commit for a
		# board that will refuse all of them anyway.
		if _board_is_closed(day):
			return
		if doc and doc.doctype == "CRM Lead":
			if method == "on_update" and not doc.has_value_changed("status"):
				return
		elif doc and doc.doctype == "CRM Task":
			if doc.reference_doctype != "CRM Lead" or not doc.reference_docname:
				return
		frappe.enqueue(
			"crm.api.today_board.run_today_sync",
			queue="short",
			job_id=f"today-sync-{day}",
			deduplicate=True,
			enqueue_after_commit=True,
		)
	except TypeError:  # compatibility with older Frappe enqueue signatures
		frappe.enqueue(
			"crm.api.today_board.run_today_sync",
			queue="short",
			enqueue_after_commit=True,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Today board sync enqueue failed")


def run_today_sync():
	"""Worker/scheduler entry: keep today's add-only board current."""
	day = getdate(now_datetime())
	if not is_business_day(day):
		return {"created": 0, "available": _available(), "skipped": "non-business day"}
	if _board_is_closed(day):
		# This job is on `*/5 * * * *` — every five minutes ROUND THE CLOCK, despite
		# what the notes say about business hours. Without this it is the other half
		# of the late-night card problem, alongside the new-lead hook.
		return {"created": 0, "available": _available(), "skipped": "board closed"}
	try:
		return _generate_today(day)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Today board automatic sync failed")
		return {"created": 0, "available": _available(), "error": True}


def _publish(day):
	frappe.publish_realtime("crm_today", {"for_date": str(day)}, after_commit=True)


@frappe.whitelist()
def get_today_board(
	for_date=None, auto_generate=1, status=None, priority=None, signal=None, owner=None
):
	"""Everything the board needs in one call: the cards, plus the lead facts the
	cards display (status, phone, address, and how many calls it has had today so
	a rep can see progress without opening the lead).

	Scoped to ONE person's leads by default (`owner`, defaulting to the caller) so
	each setter works their own list. Pass `owner="all"` for the whole team's
	board, which is what everyone saw before ownership was split."""
	if not _available():
		return {"available": False, "columns": [], "date": None}
	_guard()
	day = getdate(for_date or now_datetime())
	owner = _resolve_owner(owner)

	with_slots = _supports_call_slots()
	if with_slots:
		_expand_legacy_items(day)
	rows = frappe.get_all(
		DOCTYPE,
		filters={"for_date": day},
		fields=_row_fields(with_slots),
		order_by="sort_order asc, name asc",
	)
	# generate on first view so the board works immediately, not only after 5am
	if not rows and int(auto_generate or 0):
		generate_today(day)
		rows = frappe.get_all(
			DOCTYPE,
			filters={"for_date": day},
			fields=_row_fields(with_slots),
			order_by="sort_order asc, name asc",
		)
	if not rows:
		return {
			"available": True,
			"date": str(day),
			"columns": _empty_columns(),
			"priority_order": _priority_order(),
			"status_counts": [],
			"owner": owner,
			"owners": [],
		}

	lead_names = list({r.lead for r in rows})
	leads = {
		l.name: l
		for l in frappe.get_all(
			"CRM Lead",
			filters={"name": ["in", lead_names]},
			fields=["name", "lead_name", "status", "lead_owner", "mobile_no", "phone", "email",
			        "property_address", "property_city", "property_state", "property_zip"],
		)
	}
	calls = frappe.db.sql(
		"""
		select reference_docname n, count(*) c from `tabCRM Call Log`
		where reference_doctype='CRM Lead' and reference_docname in %(names)s
		  and date(creation) = %(d)s
		group by reference_docname
		""",
		{"names": lead_names, "d": day},
		as_dict=True,
	)
	made = {c.n: c.c for c in calls}

	# One open task per lead for the card. Fetch once for the whole board rather
	# than issuing a query per card; due tasks sort before undated tasks.
	task_fields = [
		"name", "reference_doctype", "reference_docname", "title", "description",
		"status", "due_date", "priority", "assigned_to", "creation", "modified",
	]
	task_meta = frappe.get_meta("CRM Task")
	if task_meta.has_field("call_outcome"):
		task_fields.append("call_outcome")
	open_tasks = frappe.get_all(
		"CRM Task",
		filters={
			"reference_doctype": "CRM Lead",
			"reference_docname": ["in", lead_names],
			"status": ["not in", ["Done", "Canceled"]],
		},
		fields=task_fields,
	)
	open_tasks.sort(
		key=lambda task: (
			task.due_date is None,
			task.due_date or "",
			task.creation or "",
		)
	)
	open_task_by_lead = {}
	for task in open_tasks:
		task.pop("creation", None)
		task.pop("modified", None)
		task["is_completed"] = False
		open_task_by_lead.setdefault(task.reference_docname, task)

	# A Done card should show the task the rep just finished, not the next future
	# follow-up. Use the latest task marked Done on this board date; `modified` is
	# the task timeline's existing completion timestamp convention.
	completed_tasks = frappe.get_all(
		"CRM Task",
		filters={
			"reference_doctype": "CRM Lead",
			"reference_docname": ["in", lead_names],
			"status": "Done",
			"modified": [
				"between",
				[f"{day} 00:00:00", f"{day} 23:59:59.999999"],
			],
		},
		fields=task_fields,
		order_by="modified desc",
	)
	completed_task_by_lead = {}
	for task in completed_tasks:
		task.pop("creation", None)
		task["completed_at"] = task.pop("modified", None)
		task["is_completed"] = True
		completed_task_by_lead.setdefault(task.reference_docname, task)

	incoming_by_lead = {}
	if frappe.db.exists("DocType", "Quo Message"):
		incoming = frappe.db.sql(
			"""
			select reference_docname n,
			       max(coalesce(message_date, creation)) last_incoming_text
			from `tabQuo Message`
			where reference_doctype='CRM Lead'
			  and reference_docname in %(names)s
			  and direction='Incoming'
			group by reference_docname
			""",
			{"names": lead_names},
			as_dict=True,
		)
		incoming_by_lead = {row.n: row.last_incoming_text for row in incoming}

	for r in rows:
		l = leads.get(r.lead) or {}
		r["lead_name"] = l.get("lead_name") or r.lead
		r["lead_status"] = l.get("status")
		r["lead_owner"] = l.get("lead_owner") or ""
		r["mobile_no"] = l.get("mobile_no") or l.get("phone")
		r["email"] = l.get("email")
		r["address"] = _address(l)
		r["calls_today"] = made.get(r.lead, 0)
		r["call_number"] = int(r.get("call_number") or 1)
		r["total_calls"] = int(
			r.get("total_calls") or max(1, int(r.get("calls_needed") or 1))
		)
		r["priority_key"] = _priority_key(r.phase, r.call_number)
		# A Done card shows the task the rep just finished. Everywhere else the
		# soonest OPEN task leads — but a task completed today is still shown when
		# there is no open one, so ticking the card's checkbox doesn't make the row
		# vanish and leave the rep no way to undo a mis-click.
		completed_task = completed_task_by_lead.get(r.lead)
		open_task = open_task_by_lead.get(r.lead)
		if r.state == "Done" and completed_task:
			r["task"] = completed_task
		else:
			r["task"] = open_task or completed_task
		r["last_incoming_text"] = incoming_by_lead.get(r.lead)

	# The owner selector lists everyone who has cards today, counted BEFORE the
	# owner filter, so a rep with an empty board can still see whose board has
	# work on it and switch to it.
	owners = _owner_options(rows)
	if owner != ALL_OWNERS:
		rows = [r for r in rows if (r.lead_owner or "") == owner]

	# Everything below this line describes the board you are actually looking at:
	# the status filter counts, the columns and the totals all agree with it.
	status_counts = {}
	for r in rows:
		if r.lead_status:
			status_counts[r.lead_status] = status_counts.get(r.lead_status, 0) + 1
	if status:
		rows = [r for r in rows if r.lead_status == status]
	if priority:
		rows = [r for r in rows if r.priority_key == priority]
	if signal == "incoming":
		rows = [r for r in rows if r.last_incoming_text]
	elif signal == "task":
		rows = [r for r in rows if r.task]

	priority_order = _priority_order()
	priority_rank = {key: i for i, key in enumerate(priority_order)}
	to_call = [r for r in rows if r.state == "To Call"]
	to_call.sort(
		key=lambda r: (
			priority_rank.get(r.priority_key, len(priority_rank)),
			r.sort_order,
			r.name,
		)
	)
	other = [r for r in rows if r.state != "To Call"]
	rows = to_call + other

	cols = _empty_columns()
	by_state = {c["state"]: c for c in cols}
	for r in rows:
		by_state.get(r.state, by_state["To Call"])["items"].append(r)
	for c in cols:
		c["count"] = len(c["items"])
	return {
		"available": True,
		"date": str(day),
		"columns": cols,
		"status_counts": [
			{"status": key, "count": status_counts[key]}
			for key in sorted(status_counts)
		],
		"selected_status": status or "",
		"selected_priority": priority or "",
		"selected_signal": signal or "",
		"priority_order": priority_order,
		"owner": owner,
		"owners": owners,
	}


def _scope_rows_to_owner(rows, owner):
	"""Keep only the cards whose lead belongs to `owner`.

	Ownership is read off the lead at request time rather than stamped onto the
	card. A card stamped at 5am would keep pointing at the old rep for the rest of
	the day the moment a lead was reassigned — and reassignment is exactly what the
	backfill and the round robin do.
	"""
	if not rows:
		return []
	lead_names = list({row.lead for row in rows if row.get("lead")})
	if not lead_names:
		return []
	owners = {
		lead.name: (lead.lead_owner or UNASSIGNED)
		for lead in frappe.get_all(
			"CRM Lead", filters={"name": ["in", lead_names]}, fields=["name", "lead_owner"]
		)
	}
	return [row for row in rows if owners.get(row.lead, UNASSIGNED) == owner]


def _empty_report_day(day):
	return {
		"date": str(getdate(day)),
		"total": 0,
		"done": 0,
		"skipped": 0,
		"remaining": 0,
		"completion_rate": 0,
		"handled_rate": 0,
		"perfect": False,
	}


def _finish_report_day(stats):
	stats["remaining"] = stats["total"] - stats["done"] - stats["skipped"]
	if stats["total"]:
		resolved = stats["done"] + stats["skipped"]
		stats["completion_rate"] = round(resolved * 100 / stats["total"])
		stats["handled_rate"] = stats["completion_rate"]
	stats["perfect"] = bool(stats["total"] and stats["remaining"] == 0)
	return stats


@frappe.whitelist()
def get_today_report(for_date=None, history_days=10, owner=None):
	"""Progress today plus a 100%-resolved business-day streak.

	Both Done and Skipped cards count toward the streak. An unfinished current day
	does not erase the streak earned through the previous business day.

	`owner` scopes the numbers to one person's leads so the progress figures agree
	with the board that is actually on screen — a bar reading 12/87 while the
	visible board holds 30 cards is worse than no bar at all.

	The streak follows that same scope: a rep's streak is now "every card on MY
	board resolved", not the team's (Lance, 2026-08-06). It shipped team-wide as a
	shared artifact, so this deliberately CHANGES what the number means; `scope` in
	the response reports which meaning is in force, and the team streak is still
	what `owner="all"` returns.

	Caveat worth knowing: ownership is read off the lead at request time (see
	`_scope_rows_to_owner`), so a reassigned lead moves its whole history with it.
	A personal streak is therefore a statement about the leads you own NOW, not a
	frozen record of who resolved what on the day.
	"""
	_guard()
	today = getdate(for_date or now_datetime())
	owner = _resolve_owner(owner)
	if not _available():
		return {
			"available": False,
			"today": _empty_report_day(today),
			"recent": [],
			"completed_by": [],
			"streak": {"current": 0, "best": 0, "through": None},
		}

	try:
		history_days = max(5, min(30, int(history_days or 10)))
	except (TypeError, ValueError):
		history_days = 10
	start = today - timedelta(days=370)
	rows = frappe.get_all(
		DOCTYPE,
		filters={"for_date": ["between", [start, today]]},
		fields=["for_date", "state", "done_by", "lead"],
		order_by="for_date asc",
		limit_page_length=50000,
	)

	# Scope EVERY day to the owner, not just today — `by_day` is what the streak is
	# computed from, so this is the one line that makes the streak personal. Done
	# once, up front, so the whole history costs a single extra lead lookup.
	if owner != ALL_OWNERS:
		rows = _scope_rows_to_owner(rows, owner)

	by_day = {}
	for row in rows:
		day = getdate(row.for_date)
		stats = by_day.setdefault(day, _empty_report_day(day))
		stats["total"] += 1
		if row.state == "Done":
			stats["done"] += 1
		elif row.state == "Skipped":
			stats["skipped"] += 1
	for stats in by_day.values():
		_finish_report_day(stats)

	todays_rows = [row for row in rows if getdate(row.for_date) == today]
	today_stats = by_day.get(today, _empty_report_day(today))
	business_dates = sorted(day for day in by_day if is_business_day(day))
	first_day = business_dates[0] if business_dates else today

	# Current streak: an in-progress today is not a failure until the day ends.
	cursor = today
	if not is_business_day(cursor) or not by_day.get(cursor, {}).get("perfect"):
		cursor = previous_business_day(cursor)
	current_streak = 0
	through = None
	while cursor >= first_day:
		stats = by_day.get(cursor)
		if not stats or not stats["perfect"]:
			break
		if through is None:
			through = str(cursor)
		current_streak += 1
		cursor = previous_business_day(cursor)

	# Best streak: missing or imperfect weekdays break the run.
	best_streak = 0
	run = 0
	cursor = first_day
	while cursor <= today:
		if is_business_day(cursor):
			stats = by_day.get(cursor)
			if stats and stats["perfect"]:
				run += 1
				best_streak = max(best_streak, run)
			else:
				run = 0
		cursor += timedelta(days=1)

	scope = "owner" if owner != ALL_OWNERS else "team"
	recent = [by_day[day] for day in sorted(business_dates, reverse=True)[:history_days]]
	recent_total = sum(day["total"] for day in recent)
	recent_resolved = sum(day["done"] + day["skipped"] for day in recent)
	recent_average = round(recent_resolved * 100 / recent_total) if recent_total else 0

	# Credit list follows the same scope as the headline numbers, or the two halves
	# of the same panel would describe different card sets.
	people = Counter(
		row.done_by for row in todays_rows if row.state == "Done" and row.done_by
	)
	user_names = {}
	if people:
		user_names = {
			u.name: u.full_name or u.name
			for u in frappe.get_all(
				"User",
				filters={"name": ["in", list(people)]},
				fields=["name", "full_name"],
			)
		}
	completed_by = [
		{"user": user, "name": user_names.get(user, user), "done": count}
		for user, count in people.most_common()
	]

	return {
		"available": True,
		"today": today_stats,
		"recent": recent,
		"recent_average": recent_average,
		"completed_by": completed_by,
		"streak": {
			"current": current_streak,
			"best": best_streak,
			"through": through,
		},
		"owner": owner,
		# Every figure in this response now describes the same card set, so one scope
		# covers all of them. The keys stay separate because the UI labels them
		# individually and a future divergence shouldn't need a payload change.
		"scope": {"today": scope, "streak": scope, "recent": scope},
		"definition": (
			_("A streak day requires every Today card on your board to be resolved as Done or Skipped.")
			if scope == "owner"
			else _("A streak day requires every Today card to be resolved as Done or Skipped.")
		),
	}


@frappe.whitelist()
def set_today_priority_order(order):
	"""Save this user's cross-device priority order without adding a schema field."""
	_guard()
	if isinstance(order, str):
		try:
			order = json.loads(order)
		except ValueError:
			order = []
	if not isinstance(order, list):
		frappe.throw(_("Invalid priority order."))
	clean = []
	for key in order:
		if key in PRIORITY_ORDER and key not in clean:
			clean.append(key)
	clean += [key for key in PRIORITY_ORDER if key not in clean]
	frappe.defaults.set_user_default(PRIORITY_DEFAULT_KEY, json.dumps(clean))
	return clean


#: trailing country noise that only costs a narrow card its truncation budget
_COUNTRY_TAIL = re.compile(r",\s*(usa|u\.s\.a\.?|united states)\s*$", re.I)


def _address(lead) -> str:
	"""One clean "street, city, ST zip" line for a card.

	Delegates to `agreement._full_property_address` rather than re-deriving the
	rule. A first attempt here compared the raw `property_state` against the
	address, which silently failed on the ~8% of leads whose state is stored
	spelled out ("Minnesota") while the address carries the abbreviation ("MN") —
	producing "611 5th Ave SE, Rochester, MN 55904, USA, Minnesota". The shared
	helper already maps full names to abbreviations and matches the abbreviation
	case-sensitively so "IN" doesn't match the word "in".

	The only thing added on top is dropping a trailing ", USA", which some
	webhook addresses carry and which is pure noise on a narrow card.
	"""
	from crm.api.agreement import _full_property_address

	return _COUNTRY_TAIL.sub("", _full_property_address(lead) or "").strip().rstrip(",")


def _empty_columns():
	return [{"state": s, "items": [], "count": 0} for s in STATES]


def _plain_text(value):
	"""Compact activity previews should never expose stored HTML/JSON markup."""
	if not value:
		return ""
	return BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)


def _recent_lead_activity(lead):
	"""Latest calls, texts, and emails for the compact Today lead view.

	This deliberately excludes FCRM Notes. Intake notes include raw vendor payloads,
	which made the modal show a wall of JSON instead of the seller conversation the
	setter actually needs before calling.
	"""
	activity = []

	call_meta = frappe.get_meta("CRM Call Log")
	call_fields = [
		"name", "type", "from", "to", "duration", "caller", "receiver", "creation",
	]
	for optional in ("custom_ai_summary", "custom_call_class"):
		if call_meta.has_field(optional):
			call_fields.append(optional)
	calls = frappe.get_all(
		"CRM Call Log",
		filters={"reference_doctype": "CRM Lead", "reference_docname": lead},
		fields=call_fields,
		order_by="creation desc",
		limit=10,
	)
	for row in calls:
		outgoing = row.type == "Outgoing"
		activity.append(
			{
				"name": row.name,
				"type": "call",
				"direction": "outgoing" if outgoing else "incoming",
				"title": _("Outgoing call") if outgoing else _("Incoming call"),
				"content": _plain_text(row.get("custom_ai_summary")),
				"when": row.creation,
				"duration": row.duration or 0,
				"classification": row.get("custom_call_class") or "",
				"counterparty": row.get("to") if outgoing else row.get("from"),
			}
		)

	if frappe.db.exists("DocType", "Quo Message"):
		texts = frappe.get_all(
			"Quo Message",
			filters={"reference_doctype": "CRM Lead", "reference_docname": lead},
			fields=["name", "direction", "from", "to", "content", "media", "message_date", "creation"],
			order_by="message_date desc, creation desc",
			limit=10,
		)
		for row in texts:
			outgoing = row.direction == "Outgoing"
			content = _plain_text(row.content)
			if not content and row.media:
				content = _("Attachment")
			activity.append(
				{
					"name": row.name,
					"type": "text",
					"direction": "outgoing" if outgoing else "incoming",
					"title": _("Outgoing text") if outgoing else _("Incoming text"),
					"content": content,
					"when": row.message_date or row.creation,
					"counterparty": row.get("to") if outgoing else row.get("from"),
				}
			)

	emails = frappe.get_all(
		"Communication",
		filters={
			"reference_doctype": "CRM Lead",
			"reference_name": lead,
			"communication_medium": "Email",
		},
		fields=[
			"name", "subject", "content", "sender", "sender_full_name", "recipients",
			"sent_or_received", "communication_date", "creation", "delivery_status",
		],
		order_by="communication_date desc, creation desc",
		limit=10,
	)
	for row in emails:
		outgoing = row.sent_or_received == "Sent"
		activity.append(
			{
				"name": row.name,
				"type": "email",
				"direction": "outgoing" if outgoing else "incoming",
				"title": row.subject or (_("Outgoing email") if outgoing else _("Incoming email")),
				"content": _plain_text(row.content),
				"when": row.communication_date or row.creation,
				"counterparty": row.recipients if outgoing else (row.sender_full_name or row.sender),
				"status": row.delivery_status or "",
			}
		)

	activity.sort(key=lambda item: item["when"], reverse=True)
	return activity[:12]


@frappe.whitelist()
def get_today_lead_snapshot(lead):
	"""A compact, read-only lead view for the Today card modal.

	The full Lead page is intentionally much heavier. Setters need enough context
	to make the call without leaving the queue: contact/property facts, open
	tasks, and recent calls/texts/emails. Every optional field is discovered from
	metadata so an unprovisioned custom field cannot break the board.
	"""
	_guard()
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead not found"), frappe.DoesNotExistError)
	if not frappe.has_permission("CRM Lead", "read", lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	meta = frappe.get_meta("CRM Lead")
	base_fields = [
		"name", "lead_name", "status", "mobile_no", "phone", "email", "source",
		"property_address", "property_city", "property_state", "property_zip",
	]
	optional = [
		"lead_summary", "reason_for_sell", "duration_to_sell", "property_condition",
		"property_occupied_by", "property_type", "bedrooms", "bathrooms",
		"square_footage", "year_built", "asking_price", "best_call_time",
	]
	fields = [f for f in base_fields + optional if f == "name" or meta.has_field(f)]
	doc = frappe.db.get_value("CRM Lead", lead, fields, as_dict=True)

	detail_fields = [
		"reason_for_sell", "duration_to_sell", "property_condition",
		"property_occupied_by", "property_type", "bedrooms", "bathrooms",
		"square_footage", "year_built", "asking_price", "best_call_time", "source",
	]
	details = []
	for fieldname in detail_fields:
		value = doc.get(fieldname)
		if value in (None, ""):
			continue
		field = meta.get_field(fieldname)
		details.append(
			{
				"fieldname": fieldname,
				"label": field.label if field else fieldname.replace("_", " ").title(),
				"value": value,
				"fieldtype": field.fieldtype if field else "Data",
			}
		)

	tasks = frappe.get_all(
		"CRM Task",
		filters={
			"reference_doctype": "CRM Lead",
			"reference_docname": lead,
			"status": ["not in", ["Done", "Canceled"]],
		},
		fields=["name", "title", "description", "status", "due_date", "priority", "assigned_to"],
		order_by="creation asc",
	)
	# Due first (oldest first), undated last — same ordering as the full Lead's
	# pinned To-do block.
	tasks.sort(key=lambda task: (task.due_date is None, task.due_date or ""))

	return {
		"lead": {
			"name": doc.name,
			"lead_name": doc.lead_name or doc.name,
			"status": doc.status,
			"mobile_no": doc.mobile_no or doc.phone,
			"email": doc.email,
			"address": _address(doc),
			"summary": doc.get("lead_summary"),
		},
		"details": details,
		"tasks": tasks,
		"activity": _recent_lead_activity(lead),
	}


@frappe.whitelist()
def set_today_lead_status(item, status, lost_reason=None, lost_notes=None):
	"""Change the CRM Lead status from a Today card.

	Save the full Lead document (rather than using ``db.set_value``) so status
	history, lost-reason validation, task hygiene, and the normal Lead hooks all
	still run. The Today item anchors the request to a card the user can see.
	"""
	_guard()
	if not status or not frappe.db.exists("CRM Lead Status", status):
		frappe.throw(_("Invalid lead status."))

	item_doc = frappe.get_doc(DOCTYPE, item)
	lead = frappe.get_doc("CRM Lead", item_doc.lead)
	lead.check_permission("write")
	if lead.status == status:
		return {"ok": True, "status": status}

	lead.status = status
	if lost_reason is not None:
		lead.lost_reason = lost_reason
	if lost_notes is not None:
		lead.lost_notes = lost_notes
	lead.save()

	# Lead hooks may add newly-due work asynchronously; publish immediately too
	# so every open Today board reflects this status change after commit.
	_publish(item_doc.for_date)
	return {"ok": True, "status": lead.status}


@frappe.whitelist()
def set_today_state(item, state, outcome=None, outcome_note=None):
	"""Tick a card Done / Skipped / back To Call, with what happened.

	Resolving a card is the one moment the rep already has the answer in their
	head, so it is the only moment the answer is cheap to collect — asking later
	means reconstructing thirty calls from memory. A Done card carries one of
	`DONE_OUTCOMES`; a Skipped card carries an open-ended "why" instead, because
	the interesting thing about a skip is precisely the part a fixed list would
	have thrown away.

	Re-submitting the SAME state only rewrites the outcome: correcting a
	mis-click must not restamp `resolved_at`, which the intraday pulse reads as
	"this card was resolved in this half hour".
	"""
	if state not in STATES:
		frappe.throw(_("Invalid state."))
	_guard()

	outcome = (outcome or "").strip()
	outcome_note = (outcome_note or "").strip()
	if state == "Done":
		if outcome and outcome not in DONE_OUTCOMES:
			frappe.throw(_("Invalid call outcome."))
		if outcome == "Other" and not outcome_note:
			frappe.throw(_("Say a little more about what happened."))
	else:
		# "Connected" is a statement about a call that was made. A skipped card is
		# by definition a call that wasn't, so it never carries an outcome.
		outcome = ""
	if state == "To Call":
		outcome_note = ""

	doc = frappe.get_doc(DOCTYPE, item)
	same_state = doc.state == state
	if same_state and not (outcome or outcome_note):
		return {"ok": True, "state": state}

	doc.state = state
	if not same_state:
		for field, value in _state_stamps(state).items():
			setattr(doc, field, value)
	if _supports_outcome():
		doc.outcome = outcome
		doc.outcome_note = outcome_note
	doc.save(ignore_permissions=True)
	# `same_state` here means the rep re-answered an already-resolved card, i.e.
	# corrected a mis-click. Worth its own timeline line: without it the lead keeps
	# showing the answer that was withdrawn.
	_log_outcome_comment(doc, state, outcome, outcome_note, corrected=same_state)
	_publish(doc.for_date)
	return {"ok": True, "state": state, "outcome": outcome, "outcome_note": outcome_note}


@frappe.whitelist()
def reorder_today(order, state=None, for_date=None):
	"""Persist a drag.

	`order` is the list of item names in their new order within one column — the
	client sends the WHOLE column after a drag, which is what vuedraggable hands
	back anyway.

	The whole column is then renumbered in steps of 10. Renumbering only the
	names passed in is not enough: cards are initially seeded at wide priority
	offsets, so writing 10/20/30 onto only the dragged cards can drop them behind
	untouched neighbours. Any name in the column that wasn't passed keeps its relative position
	and is renumbered after the ones that were, so even a partial list leaves the
	column in a sane, predictable total order rather than a corrupted one.
	"""
	_guard()
	if isinstance(order, str):
		order = frappe.parse_json(order)
	if not order:
		return {"ok": True, "moved": 0}

	first = frappe.get_doc(DOCTYPE, order[0])
	day = getdate(for_date) if for_date else first.for_date
	target = state or first.state

	# everything currently in the destination column, in its present order
	column = frappe.get_all(
		DOCTYPE,
		filters={"for_date": day, "state": target},
		fields=["name"],
		order_by="sort_order asc, name asc",
		pluck="name",
	)
	moved = set(order)
	final = list(order) + [n for n in column if n not in moved]

	newly_resolved = []
	for i, name in enumerate(final):
		updates = {"sort_order": (i + 1) * 10}
		if name in moved:
			cur = frappe.db.get_value(DOCTYPE, name, "state")
			if cur != target:
				newly_resolved.append(name)
				# Normally the client has already called `set_today_state` (that is
				# where the outcome is collected), so this branch is the fallback for
				# a drag that skipped it. Stamp it exactly the same way regardless.
				updates["state"] = target
				updates.update(_state_stamps(target))
				if _supports_outcome() and target == "To Call":
					updates["outcome"] = ""
					updates["outcome_note"] = ""
		# db.set_value keeps a 60-card reorder to one cheap write per row; the
		# realtime publish below is what refreshes everyone else's board.
		frappe.db.set_value(DOCTYPE, name, updates, update_modified=False)
	frappe.db.commit()
	# Only the cards this drag actually RESOLVED get a timeline entry, and only on
	# the fallback path — the normal drag already went through `set_today_state`,
	# which logged it with the outcome the rep gave. Logging here too would double
	# every entry.
	for name in newly_resolved:
		card = frappe.db.get_value(DOCTYPE, name, ["lead", "call_number"], as_dict=True)
		if card:
			_log_outcome_comment(card, target)
	_publish(day)
	return {"ok": True, "moved": len(order), "renumbered": len(final)}


@frappe.whitelist()
def clear_today(for_date=None):
	"""Wipe a day's cards so the next view regenerates from scratch. For fixing a
	bad generation; not part of normal use."""
	_guard()
	if not frappe.has_permission(DOCTYPE, "delete"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	day = getdate(for_date or now_datetime())
	names = frappe.get_all(DOCTYPE, filters={"for_date": day}, pluck="name")
	for n in names:
		frappe.delete_doc(DOCTYPE, n, ignore_permissions=True, force=True)
	frappe.db.commit()
	_publish(day)
	return {"deleted": len(names)}
