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

`CRM Today Item` is autonamed `format:{for_date}-{lead}`, so (date, lead) is
structurally unique and generation can run as often as it likes without ever
duplicating a card.
"""

import frappe
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


def _guard():
	roles = set(frappe.get_roles())
	if not roles & {"System Manager", "Sales Manager", "Sales User"}:
		frappe.throw(_("Not permitted"), frappe.PermissionError)


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

	existing = set(
		frappe.get_all(DOCTYPE, filters={"for_date": day}, pluck="lead")
	)
	created = 0
	for i, r in enumerate(due):
		if r.name in existing:
			continue
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

	if created:
		frappe.db.commit()
		_publish(day)
	return {"created": created, "existing": len(existing), "due": len(due), "available": True}


def _publish(day):
	frappe.publish_realtime("crm_today", {"for_date": str(day)}, after_commit=True)


@frappe.whitelist()
def get_today_board(for_date=None, auto_generate=1):
	"""Everything the board needs in one call: the cards, plus the lead facts the
	cards display (status, phone, address, and how many calls it has had today so
	a rep can see progress without opening the lead)."""
	if not _available():
		return {"available": False, "columns": [], "date": None}
	_guard()
	day = getdate(for_date or now_datetime())

	rows = frappe.get_all(
		DOCTYPE,
		filters={"for_date": day},
		fields=["name", "lead", "state", "sort_order", "phase", "reason",
		        "calls_needed", "done_by", "done_at"],
		order_by="sort_order asc, name asc",
	)
	# generate on first view so the board works immediately, not only after 5am
	if not rows and int(auto_generate or 0):
		generate_today(day)
		rows = frappe.get_all(
			DOCTYPE,
			filters={"for_date": day},
			fields=["name", "lead", "state", "sort_order", "phase", "reason",
			        "calls_needed", "done_by", "done_at"],
			order_by="sort_order asc, name asc",
		)
	if not rows:
		return {"available": True, "date": str(day), "columns": _empty_columns()}

	leads = {
		l.name: l
		for l in frappe.get_all(
			"CRM Lead",
			filters={"name": ["in", [r.lead for r in rows]]},
			fields=["name", "lead_name", "status", "mobile_no", "property_address",
			        "property_city", "property_state"],
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
		r["mobile_no"] = l.get("mobile_no")
		r["address"] = _address(l)
		r["calls_today"] = made.get(r.lead, 0)

	cols = _empty_columns()
	by_state = {c["state"]: c for c in cols}
	for r in rows:
		by_state.get(r.state, by_state["To Call"])["items"].append(r)
	for c in cols:
		c["count"] = len(c["items"])
	return {"available": True, "date": str(day), "columns": cols}


def _address(lead) -> str:
	"""Street + city + state, appending each part only when it isn't already in
	the address string.

	Webhook/imported leads carry a fully-qualified `property_address` ("4526
	Domingo Dr, Corpus Christi, TX 78416") while manually-entered ones are
	street-only with separate city/state fields. Blindly joining all three
	produced "...TX 78416, corpus christi, TX", which then ate the card's
	truncation budget. Same rule as agreement._full_property_address.
	"""
	out = (lead.get("property_address") or "").strip()
	for part in (lead.get("property_city"), lead.get("property_state")):
		part = (part or "").strip()
		if part and part.lower() not in out.lower():
			out = f"{out}, {part}" if out else part
	return out


def _empty_columns():
	return [{"state": s, "items": [], "count": 0} for s in STATES]


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
