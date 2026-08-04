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
from frappe.utils import getdate, now_datetime

from crm.api.daily_standup import (
	build_standup,
	is_business_day,
	previous_business_day,
)

DOCTYPE = "CRM Today Item"
STATES = ("To Call", "Done", "Skipped")

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
	return fields


def _guard():
	roles = set(frappe.get_roles())
	if not roles & {"System Manager", "Sales Manager", "Sales User"}:
		frappe.throw(_("Not permitted"), frappe.PermissionError)


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


def _generate_today(day):
	"""Internal sync used by the manual button, hooks, and five-minute safety job."""
	if not _available():
		return {"created": 0, "existing": 0, "due": 0, "available": False}
	day = getdate(day or now_datetime())
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
	try:
		return _generate_today(day)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Today board automatic sync failed")
		return {"created": 0, "available": _available(), "error": True}


def _publish(day):
	frappe.publish_realtime("crm_today", {"for_date": str(day)}, after_commit=True)


@frappe.whitelist()
def get_today_board(for_date=None, auto_generate=1, status=None, priority=None, signal=None):
	"""Everything the board needs in one call: the cards, plus the lead facts the
	cards display (status, phone, address, and how many calls it has had today so
	a rep can see progress without opening the lead)."""
	if not _available():
		return {"available": False, "columns": [], "date": None}
	_guard()
	day = getdate(for_date or now_datetime())

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
		}

	lead_names = list({r.lead for r in rows})
	leads = {
		l.name: l
		for l in frappe.get_all(
			"CRM Lead",
			filters={"name": ["in", lead_names]},
			fields=["name", "lead_name", "status", "mobile_no", "phone", "email", "property_address",
			        "property_city", "property_state", "property_zip"],
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
		r["mobile_no"] = l.get("mobile_no") or l.get("phone")
		r["email"] = l.get("email")
		r["address"] = _address(l)
		r["calls_today"] = made.get(r.lead, 0)
		r["call_number"] = int(r.get("call_number") or 1)
		r["total_calls"] = int(
			r.get("total_calls") or max(1, int(r.get("calls_needed") or 1))
		)
		r["priority_key"] = _priority_key(r.phase, r.call_number)
		r["task"] = (
			completed_task_by_lead.get(r.lead)
			if r.state == "Done" and completed_task_by_lead.get(r.lead)
			else open_task_by_lead.get(r.lead)
		)
		r["last_incoming_text"] = incoming_by_lead.get(r.lead)

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
	}


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
def get_today_report(for_date=None, history_days=10):
	"""Team progress today plus a 100%-resolved business-day streak.

	Both Done and Skipped cards count toward the streak. An unfinished current day
	does not erase the streak earned through the previous business day.
	"""
	_guard()
	today = getdate(for_date or now_datetime())
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
		fields=["for_date", "state", "done_by"],
		order_by="for_date asc",
		limit_page_length=50000,
	)

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

	recent = [by_day[day] for day in sorted(business_dates, reverse=True)[:history_days]]
	recent_total = sum(day["total"] for day in recent)
	recent_resolved = sum(day["done"] + day["skipped"] for day in recent)
	recent_average = round(recent_resolved * 100 / recent_total) if recent_total else 0

	people = Counter(row.done_by for row in rows if getdate(row.for_date) == today and row.state == "Done" and row.done_by)
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
		"definition": _("A streak day requires every Today card to be resolved as Done or Skipped."),
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
def set_today_state(item, state):
	"""Tick a card Done / Skipped / back To Call."""
	if state not in STATES:
		frappe.throw(_("Invalid state."))
	_guard()
	doc = frappe.get_doc(DOCTYPE, item)
	if doc.state == state:
		return {"ok": True, "state": state}
	doc.state = state
	if state == "Done":
		doc.done_by = frappe.session.user
		doc.done_at = now_datetime()
	else:
		doc.done_by = None
		doc.done_at = None
	doc.save(ignore_permissions=True)
	_publish(doc.for_date)
	return {"ok": True, "state": state}


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

	for i, name in enumerate(final):
		updates = {"sort_order": (i + 1) * 10}
		if name in moved:
			cur = frappe.db.get_value(DOCTYPE, name, "state")
			if cur != target:
				updates["state"] = target
				if target == "Done":
					updates["done_by"] = frappe.session.user
					updates["done_at"] = now_datetime()
				elif cur == "Done":
					updates["done_by"] = None
					updates["done_at"] = None
		# db.set_value keeps a 60-card reorder to one cheap write per row; the
		# realtime publish below is what refreshes everyone else's board.
		frappe.db.set_value(DOCTYPE, name, updates, update_modified=False)
	frappe.db.commit()
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
