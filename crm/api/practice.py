# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Practice comps — the same map as a real lead, sandboxed per person.

The setters price deals on the comps page. This is that page, pointed at a
set of properties Lance picked, with two differences that are the whole point:

  * each person's hides / picks / offer calc live on THEIR attempt, never on
    the CRM Lead — two people can take the same ten-house test and not see
    each other's work, and nothing they do rewrites a live deal
  * a set can carry a time limit (10 properties in 30 minutes), and we record
    how long the whole run and each house took

The map itself is `get_lead_comps` against the source lead, with the lead's
team-wide `comps_hidden` / `comps_selected` swapped out for the attempt's.
Zillow/geocode caches on the source lead may still fill in (`update_modified=
False`); those are not a human edit. Offer saves and underwriting sheets are
refused.

Doctypes (`CRM Practice Set` / `Property` / `Attempt`) come from ops
`scripts/setup_practice.py`. Everything here is `has_doctype`-guarded so the
app deploys before that script runs.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, time_diff_in_seconds

from crm.api.comps import _guard, get_lead_comps

SET = "CRM Practice Set"
PROP = "CRM Practice Property"
ATTEMPT = "CRM Practice Attempt"
SALES_ROLES = ("System Manager", "Sales Manager", "Sales User")
MANAGER_ROLES = ("System Manager", "Sales Manager")
STATUSES = ("In Progress", "Submitted", "Timed Out")


def _available() -> bool:
	return bool(
		frappe.db.exists("DocType", SET)
		and frappe.db.exists("DocType", PROP)
		and frappe.db.exists("DocType", ATTEMPT)
	)


def _is_manager() -> bool:
	return any(role in MANAGER_ROLES for role in frappe.get_roles())


def _assert_manager() -> None:
	if not _is_manager():
		frappe.throw(_("Only a manager can edit practice sets."), frappe.PermissionError)


def _need() -> None:
	_guard()
	if not _available():
		frappe.throw(_("Practice is not set up on this site yet."))


def _now():
	return now_datetime()


def _json(raw) -> dict:
	if not raw:
		return {}
	if isinstance(raw, dict):
		return raw
	try:
		val = json.loads(raw)
		return val if isinstance(val, dict) else {}
	except Exception:
		return {}


def _dump(val) -> str:
	return json.dumps(val, ensure_ascii=False, default=str)


def _user_label(user: str) -> str:
	return frappe.db.get_value("User", user, "full_name") or user


def _set_title(name: str) -> str:
	return frappe.db.get_value(SET, name, "title") or name


def _dt(val) -> str:
	return str(val) if val else ""


def _get_set(name: str):
	if not frappe.db.exists(SET, name):
		frappe.throw(_("Practice set {0} does not exist.").format(name), frappe.DoesNotExistError)
	return frappe.get_doc(SET, name)


def _get_prop(name: str):
	if not frappe.db.exists(PROP, name):
		frappe.throw(_("Practice property {0} does not exist.").format(name), frappe.DoesNotExistError)
	return frappe.get_doc(PROP, name)


def _get_attempt(name: str, *, write: bool = False):
	if not frappe.db.exists(ATTEMPT, name):
		frappe.throw(_("Practice attempt {0} does not exist.").format(name), frappe.DoesNotExistError)
	doc = frappe.get_doc(ATTEMPT, name)
	if write and doc.user != frappe.session.user:
		frappe.throw(_("Not your practice run."), frappe.PermissionError)
	if not write and doc.user != frappe.session.user and not _is_manager():
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	return doc


def _properties(set_name: str) -> list[dict]:
	return frappe.get_all(
		PROP,
		filters={"practice_set": set_name},
		fields=[
			"name",
			"source_lead",
			"lead_name",
			"property_address",
			"property_city",
			"property_state",
			"property_zip",
			"sort_order",
		],
		order_by="sort_order asc, creation asc",
	)


def _elapsed(att) -> int:
	start = get_datetime(att.started_at)
	end = get_datetime(att.finished_at) if att.finished_at else _now()
	if not start:
		return 0
	return max(0, int(time_diff_in_seconds(end, start)))


def _remaining(att) -> int | None:
	limit = int(att.time_limit_min or 0) * 60
	if limit <= 0:
		return None
	return max(0, limit - _elapsed(att))


def _results(att) -> dict:
	return _json(att.results)


def _write_results(att, results: dict) -> None:
	frappe.db.set_value(ATTEMPT, att.name, "results", _dump(results))
	att.results = _dump(results)


def _slot(results: dict, prop: str) -> dict:
	slot = results.get(prop)
	if not isinstance(slot, dict):
		slot = {}
		results[prop] = slot
	slot.setdefault("hidden", [])
	slot.setdefault("selected", [])
	return slot


def _submit(att, *, timed_out: bool = False) -> None:
	if att.status != "In Progress":
		return
	now = _now()
	results = _results(att)
	for slot in results.values():
		if not isinstance(slot, dict):
			continue
		if slot.get("opened_at") and not slot.get("done_at"):
			slot["done_at"] = str(now)
			try:
				slot["duration_seconds"] = max(
					0, int(time_diff_in_seconds(now, get_datetime(slot["opened_at"])))
				)
			except Exception:
				slot["duration_seconds"] = slot.get("duration_seconds") or 0
	frappe.db.set_value(
		ATTEMPT,
		att.name,
		{
			"status": "Timed Out" if timed_out else "Submitted",
			"finished_at": now,
			"results": _dump(results),
		},
	)
	att.status = "Timed Out" if timed_out else "Submitted"
	att.finished_at = now
	att.results = _dump(results)


def _maybe_expire(att):
	if att.status != "In Progress":
		return att
	rem = _remaining(att)
	if rem == 0 and int(att.time_limit_min or 0) > 0:
		_submit(att, timed_out=True)
		return frappe.get_doc(ATTEMPT, att.name)
	return att


def _shape_attempt(att, properties: list[dict] | None = None) -> dict:
	results = _results(att)
	props = properties if properties is not None else _properties(att.practice_set)
	out_props = []
	for p in props:
		slot = results.get(p.name) or {}
		if not isinstance(slot, dict):
			slot = {}
		out_props.append(
			{
				**{k: p.get(k) for k in (
					"name", "source_lead", "lead_name", "property_address",
					"property_city", "property_state", "property_zip", "sort_order",
				)},
				"opened_at": slot.get("opened_at") or "",
				"done_at": slot.get("done_at") or "",
				"duration_seconds": slot.get("duration_seconds"),
				"selected_count": len(slot.get("selected") or []),
				"hidden_count": len(slot.get("hidden") or []),
				"has_offer": bool(slot.get("offer")),
			}
		)
	return {
		"name": att.name,
		"practice_set": att.practice_set,
		"set_title": _set_title(att.practice_set),
		"user": att.user,
		"user_name": _user_label(att.user),
		"status": att.status,
		"started_at": _dt(att.started_at),
		"finished_at": _dt(att.finished_at),
		"time_limit_min": int(att.time_limit_min or 0),
		"elapsed_seconds": _elapsed(att),
		"remaining_seconds": _remaining(att),
		"properties": out_props,
	}


def _shape_set(doc, *, with_properties: bool = False) -> dict:
	n = frappe.db.count(PROP, {"practice_set": doc.name})
	mine = frappe.get_all(
		ATTEMPT,
		filters={"practice_set": doc.name, "user": frappe.session.user},
		fields=["name", "status", "started_at", "finished_at", "time_limit_min"],
		order_by="creation desc",
		limit_page_length=1,
	)
	last = None
	if mine:
		row = mine[0]
		# elapsed needs a full doc only for in-progress; approximate from stamps
		start = get_datetime(row.started_at)
		end = get_datetime(row.finished_at) if row.finished_at else _now()
		elapsed = max(0, int(time_diff_in_seconds(end, start))) if start else 0
		last = {
			"name": row.name,
			"status": row.status,
			"elapsed_seconds": elapsed,
		}
	out = {
		"name": doc.name,
		"title": doc.title,
		"time_limit_min": int(doc.time_limit_min or 0),
		"notes": doc.notes or "",
		"is_active": int(doc.is_active or 0),
		"property_count": n,
		"owner": doc.owner,
		"modified": _dt(doc.modified),
		"my_attempt": last,
	}
	if with_properties:
		out["properties"] = _properties(doc.name)
	return out


# ---------------------------------------------------------------------------------
# Sets
# ---------------------------------------------------------------------------------
@frappe.whitelist()
def list_sets() -> dict:
	"""Active sets for everyone; managers also see paused ones."""
	_guard()
	if not _available():
		return {"available": False, "can_manage": _is_manager(), "sets": []}
	filters: dict[str, Any] = {}
	if not _is_manager():
		filters["is_active"] = 1
	rows = frappe.get_all(
		SET,
		filters=filters,
		fields=["name", "title", "time_limit_min", "notes", "is_active", "owner", "modified"],
		order_by="modified desc",
	)
	return {
		"available": True,
		"can_manage": _is_manager(),
		"sets": [_shape_set(frappe._dict(r)) for r in rows],
	}


@frappe.whitelist()
def get_set(name: str) -> dict:
	_need()
	doc = _get_set(name)
	if not int(doc.is_active or 0) and not _is_manager():
		frappe.throw(_("This practice set is not active."))
	out = _shape_set(doc, with_properties=True)
	out["can_manage"] = _is_manager()
	out["available"] = True
	return out


@frappe.whitelist()
def save_set(
	name: str = "",
	title: str = "",
	time_limit_min: int | str = 0,
	notes: str = "",
	is_active: int | str = 1,
) -> dict:
	_need()
	_assert_manager()
	title = (title or "").strip()
	if not title:
		frappe.throw(_("Give the set a name."))
	try:
		limit = max(0, int(time_limit_min or 0))
	except (TypeError, ValueError):
		limit = 0
	active = 0 if str(is_active) in ("0", "false", "False") else 1
	if name:
		doc = _get_set(name)
		doc.title = title
		doc.time_limit_min = limit
		doc.notes = notes or ""
		doc.is_active = active
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc(
			{
				"doctype": SET,
				"title": title,
				"time_limit_min": limit,
				"notes": notes or "",
				"is_active": active,
			}
		)
		doc.insert(ignore_permissions=True)
	return _shape_set(doc, with_properties=True) | {"can_manage": True, "available": True}


@frappe.whitelist()
def delete_set(name: str) -> dict:
	_need()
	_assert_manager()
	_get_set(name)
	for att in frappe.get_all(ATTEMPT, filters={"practice_set": name}, pluck="name"):
		frappe.delete_doc(ATTEMPT, att, ignore_permissions=True, force=True)
	for prop in frappe.get_all(PROP, filters={"practice_set": name}, pluck="name"):
		frappe.delete_doc(PROP, prop, ignore_permissions=True, force=True)
	frappe.delete_doc(SET, name, ignore_permissions=True, force=True)
	return {"ok": True}


@frappe.whitelist()
def search_leads(q: str = "") -> list[dict]:
	"""Leads with an address, for adding to a set."""
	_need()
	_assert_manager()
	q = (q or "").strip()
	filters = [["property_address", "is", "set"]]
	or_filters = None
	if q:
		like = f"%{q}%"
		or_filters = [
			["lead_name", "like", like],
			["property_address", "like", like],
			["name", "like", like],
		]
	return frappe.get_all(
		"CRM Lead",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "lead_name", "property_address", "property_city", "property_state"],
		order_by="modified desc",
		limit_page_length=20,
	)


@frappe.whitelist()
def add_property(practice_set: str, lead: str) -> dict:
	_need()
	_assert_manager()
	_get_set(practice_set)
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead {0} does not exist.").format(lead), frappe.DoesNotExistError)
	if frappe.db.exists(PROP, {"practice_set": practice_set, "source_lead": lead}):
		frappe.throw(_("That property is already in this set."))
	src = frappe.db.get_value(
		"CRM Lead",
		lead,
		[
			"name",
			"lead_name",
			"property_address",
			"property_city",
			"property_state",
			"property_zip",
		],
		as_dict=True,
	)
	address = (src.property_address or "").strip()
	if not address:
		frappe.throw(_("That lead has no property address to comp."))
	n = frappe.db.count(PROP, {"practice_set": practice_set})
	fields = {
		"doctype": PROP,
		"practice_set": practice_set,
		"source_lead": lead,
		"lead_name": src.lead_name or "",
		"property_address": address,
		"property_city": src.property_city or "",
		"property_state": src.property_state or "",
		"property_zip": src.property_zip or "",
		"sort_order": (n + 1) * 10,
	}
	if frappe.db.has_column("CRM Lead", "property_lat"):
		latlng = frappe.db.get_value(
			"CRM Lead", lead, ["property_lat", "property_lng"], as_dict=True
		)
		if latlng:
			fields["property_lat"] = latlng.property_lat
			fields["property_lng"] = latlng.property_lng
	doc = frappe.get_doc(fields)
	doc.insert(ignore_permissions=True)
	return {
		"name": doc.name,
		"source_lead": doc.source_lead,
		"lead_name": doc.lead_name,
		"property_address": doc.property_address,
		"property_city": doc.property_city,
		"property_state": doc.property_state,
		"property_zip": doc.property_zip,
		"sort_order": doc.sort_order,
	}


@frappe.whitelist()
def remove_property(name: str) -> dict:
	_need()
	_assert_manager()
	_get_prop(name)
	frappe.delete_doc(PROP, name, ignore_permissions=True, force=True)
	return {"ok": True}


@frappe.whitelist()
def reorder_properties(practice_set: str, names: str | list | None = None) -> dict:
	_need()
	_assert_manager()
	_get_set(practice_set)
	if isinstance(names, str):
		names = json.loads(names or "[]")
	names = [str(n) for n in (names or [])]
	existing = {p.name for p in _properties(practice_set)}
	if set(names) != existing:
		frappe.throw(_("Property list does not match this set."))
	for i, name in enumerate(names):
		frappe.db.set_value(PROP, name, "sort_order", (i + 1) * 10)
	return {"ok": True, "properties": _properties(practice_set)}


# ---------------------------------------------------------------------------------
# Attempts
# ---------------------------------------------------------------------------------
@frappe.whitelist()
def start_attempt(practice_set: str) -> dict:
	"""Resume an in-progress run, or start a new one."""
	_need()
	doc = _get_set(practice_set)
	if not int(doc.is_active or 0) and not _is_manager():
		frappe.throw(_("This practice set is not active."))
	props = _properties(practice_set)
	if not props:
		frappe.throw(_("This set has no properties yet."))
	open_ones = frappe.get_all(
		ATTEMPT,
		filters={
			"practice_set": practice_set,
			"user": frappe.session.user,
			"status": "In Progress",
		},
		pluck="name",
		limit_page_length=1,
	)
	if open_ones:
		att = _maybe_expire(_get_attempt(open_ones[0], write=True))
		if att.status == "In Progress":
			return {"available": True, **_shape_attempt(att, props)}
	att = frappe.get_doc(
		{
			"doctype": ATTEMPT,
			"practice_set": practice_set,
			"user": frappe.session.user,
			"status": "In Progress",
			"started_at": _now(),
			"time_limit_min": int(doc.time_limit_min or 0),
			"results": "{}",
		}
	)
	att.insert(ignore_permissions=True)
	return {"available": True, **_shape_attempt(att, props)}


@frappe.whitelist()
def get_attempt(name: str) -> dict:
	_need()
	att = _maybe_expire(_get_attempt(name))
	return {"available": True, "can_manage": _is_manager(), **_shape_attempt(att)}


@frappe.whitelist()
def touch_property(attempt: str, property: str) -> dict:
	"""Start the per-house clock the first time this property is opened."""
	_need()
	att = _maybe_expire(_get_attempt(attempt, write=True))
	if att.status != "In Progress":
		return {"available": True, **_shape_attempt(att)}
	prop = _get_prop(property)
	if prop.practice_set != att.practice_set:
		frappe.throw(_("That property is not in this set."))
	results = _results(att)
	slot = _slot(results, property)
	if not slot.get("opened_at"):
		slot["opened_at"] = str(_now())
		_write_results(att, results)
	return {"available": True, **_shape_attempt(att)}


@frappe.whitelist()
def mark_property_done(attempt: str, property: str) -> dict:
	_need()
	att = _maybe_expire(_get_attempt(attempt, write=True))
	if att.status != "In Progress":
		return {"available": True, **_shape_attempt(att)}
	prop = _get_prop(property)
	if prop.practice_set != att.practice_set:
		frappe.throw(_("That property is not in this set."))
	now = _now()
	results = _results(att)
	slot = _slot(results, property)
	if not slot.get("opened_at"):
		slot["opened_at"] = str(now)
	if not slot.get("done_at"):
		slot["done_at"] = str(now)
		try:
			slot["duration_seconds"] = max(
				0, int(time_diff_in_seconds(now, get_datetime(slot["opened_at"])))
			)
		except Exception:
			slot["duration_seconds"] = 0
		_write_results(att, results)
	return {"available": True, **_shape_attempt(att)}


@frappe.whitelist()
def submit_attempt(attempt: str) -> dict:
	_need()
	att = _maybe_expire(_get_attempt(attempt, write=True))
	if att.status == "In Progress":
		_submit(att, timed_out=False)
		att = frappe.get_doc(ATTEMPT, att.name)
	return {"available": True, **_shape_attempt(att)}


@frappe.whitelist()
def list_results(practice_set: str) -> dict:
	"""Everyone's runs on this set (managers) or just yours."""
	_need()
	_get_set(practice_set)
	filters: dict[str, Any] = {"practice_set": practice_set}
	if not _is_manager():
		filters["user"] = frappe.session.user
	rows = frappe.get_all(
		ATTEMPT,
		filters=filters,
		fields=[
			"name", "user", "status", "started_at", "finished_at",
			"time_limit_min", "results",
		],
		order_by="creation desc",
		limit_page_length=200,
	)
	props = _properties(practice_set)
	n_props = len(props)
	out = []
	for r in rows:
		att = frappe._dict(r)
		# _shape_attempt expects .practice_set
		att.practice_set = practice_set
		shaped = _shape_attempt(att, props)
		done = sum(1 for p in shaped["properties"] if p.get("done_at"))
		opened = sum(1 for p in shaped["properties"] if p.get("opened_at"))
		out.append(
			{
				**{k: shaped[k] for k in (
					"name", "user", "user_name", "status", "started_at",
					"finished_at", "time_limit_min", "elapsed_seconds",
					"remaining_seconds",
				)},
				"done": done,
				"opened": opened,
				"property_count": n_props,
				"properties": shaped["properties"],
			}
		)
	return {
		"available": True,
		"can_manage": _is_manager(),
		"attempts": out,
	}


# ---------------------------------------------------------------------------------
# Comps sandbox
# ---------------------------------------------------------------------------------
@frappe.whitelist()
def get_comps(
	attempt: str,
	property: str,
	radius_mi=None,
	limit=None,
	filters=None,
	auto: int | str = 0,
	include_hidden: int | str = 1,
) -> dict:
	"""The real comps map for this property, with THIS run's hides/picks."""
	_need()
	att = _maybe_expire(_get_attempt(attempt, write=True))
	prop = _get_prop(property)
	if prop.practice_set != att.practice_set:
		frappe.throw(_("That property is not in this set."))
	if not prop.source_lead or not frappe.db.exists("CRM Lead", prop.source_lead):
		frappe.throw(_("The source lead for this property is gone."))
	results = _results(att)
	slot = _slot(results, property)
	if att.status == "In Progress" and not slot.get("opened_at"):
		slot["opened_at"] = str(_now())
		_write_results(att, results)
	data = get_lead_comps(
		prop.source_lead,
		radius_mi=radius_mi,
		limit=limit,
		filters=filters,
		auto=auto,
		include_hidden=include_hidden,
		state={"hidden": slot.get("hidden") or [], "selected": slot.get("selected") or []},
	)
	data["practice"] = True
	data["practice_locked"] = att.status != "In Progress"
	data["offer"] = slot.get("offer")
	data["source_lead"] = prop.source_lead
	return data


@frappe.whitelist()
def set_comp_state(attempt: str, property: str, comp: str, state: str) -> dict:
	_need()
	att = _maybe_expire(_get_attempt(attempt, write=True))
	if att.status != "In Progress":
		frappe.throw(_("This practice run is finished."))
	prop = _get_prop(property)
	if prop.practice_set != att.practice_set:
		frappe.throw(_("That property is not in this set."))
	if state not in ("selected", "hidden", "none"):
		frappe.throw(_("Unknown comp state {0}").format(state))
	results = _results(att)
	slot = _slot(results, property)
	if not slot.get("opened_at"):
		slot["opened_at"] = str(_now())
	hidden = {str(x) for x in (slot.get("hidden") or [])}
	selected = {str(x) for x in (slot.get("selected") or [])}
	comp = str(comp)
	hidden.discard(comp)
	selected.discard(comp)
	if state == "hidden":
		hidden.add(comp)
	elif state == "selected":
		selected.add(comp)
	slot["hidden"] = sorted(hidden)
	slot["selected"] = sorted(selected)
	_write_results(att, results)
	return {"ok": True, "hidden": len(hidden), "selected": len(selected), "state": state}


@frappe.whitelist()
def save_offer(
	attempt: str,
	property: str,
	scenarios=None,
	comps=None,
	subject_sqft=None,
	notes: str = "",
) -> dict:
	"""Store the calc on the attempt. Never writes a Comment on the real lead."""
	_need()
	att = _maybe_expire(_get_attempt(attempt, write=True))
	if att.status != "In Progress":
		frappe.throw(_("This practice run is finished."))
	prop = _get_prop(property)
	if prop.practice_set != att.practice_set:
		frappe.throw(_("That property is not in this set."))
	from crm.api.cash_offer import _comps, _scene, _scene_payload

	if isinstance(scenarios, str):
		scenarios = json.loads(scenarios or "[]")
	if isinstance(comps, str):
		comps = json.loads(comps or "[]")
	sqft = flt(subject_sqft or 0)
	scenes = [s for s in (_scene(x, sqft) for x in (scenarios or [])) if s]
	if not scenes:
		frappe.throw(_("Type a value in at least one scenario first."))
	used = _comps(comps)
	kind = scenes[0]["kind"] if scenes else "cash"
	offer = {
		"kind": kind,
		"sqft": sqft,
		"notes": (notes or "").strip(),
		"scenarios": [_scene_payload(sc) for sc in scenes],
		"comps": used,
	}
	results = _results(att)
	slot = _slot(results, property)
	if not slot.get("opened_at"):
		slot["opened_at"] = str(_now())
	slot["offer"] = offer
	_write_results(att, results)
	return {"ok": True, "offer": offer}
