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

import re

import frappe
from bs4 import BeautifulSoup
from frappe import _
from frappe.utils import getdate, now_datetime

from crm.api.daily_standup import build_standup

DOCTYPE = "CRM Today Item"
STATES = ("To Call", "Done", "Skipped")

#: seeds sort_order so the board opens in cadence priority — never-called first.
#: Gaps of 100 leave room to drag between two cards without renumbering the world.
_PHASE_SEED = {"never": 0, "week1": 100, "week1_partial": 150, "weekly": 200,
               "monthly": 300, "task": 400}


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
	"""Materialise today's cards from the cadence.

	Only ever ADDS. An existing card is left completely alone — its state and its
	position are human decisions, and a second run (5am job, manual refresh, first
	page load) must not overwrite them. A lead that stops being due does NOT get
	its card removed either: it was on today's list when the day started, and
	silently retracting work is how a board loses trust.
	"""
	if not _available():
		return {"created": 0, "existing": 0, "available": False}
	_guard()
	day = getdate(for_date or now_datetime())

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
							# `due` is already cadence-sorted. Tens leave call 1/2
							# adjacent and room to drag without immediate ties.
							"sort_order": (i + 1) * 10 + slot - 1,
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
			seed = _PHASE_SEED.get(r.phase, 500) + i
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


def _publish(day):
	frappe.publish_realtime("crm_today", {"for_date": str(day)}, after_commit=True)


@frappe.whitelist()
def get_today_board(for_date=None, auto_generate=1, status=None):
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
		return {"available": True, "date": str(day), "columns": _empty_columns()}

	leads = {
		l.name: l
		for l in frappe.get_all(
			"CRM Lead",
			filters={"name": ["in", [r.lead for r in rows]]},
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
		{"names": [r.lead for r in rows], "d": day},
		as_dict=True,
	)
	made = {c.n: c.c for c in calls}

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

	status_counts = {}
	for r in rows:
		if r.lead_status:
			status_counts[r.lead_status] = status_counts.get(r.lead_status, 0) + 1
	if status:
		rows = [r for r in rows if r.lead_status == status]

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
	}


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
	names passed in is not enough: cards are seeded at cadence-priority offsets
	(never-called at 0-99, week 1 at 100+, and so on), so writing 10/20/30 onto
	three dragged cards drops them *behind* untouched neighbours that still sit at
	3, 4, 5. Any name in the column that wasn't passed keeps its relative position
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
