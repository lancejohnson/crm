# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Scratch properties — comps and calcs on a house that is NOT a lead.

A rep wants to price a house they have not bought a lead for: a deal being
scouted, a neighbour of a live lead, a buyer's ask, a "what would we pay for
this" on a drive-by. Until now the only way to open the comps map was to
create a CRM Lead, which put a fake seller on the Kanban, the Today board, the
round robin tally and the dashboard cohort.

`CRM Property` (ops `setup_properties.py`) is a subject WITHOUT any of that. It
carries the same property / cache / comps columns a CRM Lead does, so the
whole comps stack — `get_lead_comps`, hides/picks/types, the sqft override,
Zillow / Redfin / Realtor facts, the BatchData fallback, the offer calculator —
runs against it unchanged. The dispatch is `crm.api.comps.subject_doctype`,
keyed on the `PROP-` name prefix. Saved calcs live on the property itself
(`offer_calcs`, newest first) because there is no activity timeline to post
them to; the latest one seeds the calculator on the next open.

Team-visible on purpose, like practice sets: a comp someone already ran is
worth more to the next person than a private scratchpad would be.
"""

import json

import frappe
from frappe import _
from frappe.utils import now

from crm.api.comps import SCRATCH_DOCTYPE, SCRATCH_PREFIX, _guard

#: How many saved calcs a property keeps. Each is a few KB; nobody re-prices a
#: house twenty-five times, and if they do the early ones are noise.
MAX_OFFERS = 25


def _available() -> bool:
	return bool(frappe.db.exists("DocType", SCRATCH_DOCTYPE))


def _need() -> None:
	if not _available():
		frappe.throw(_("Properties are not set up on this site yet."))


def _get(name: str):
	if not name or not str(name).startswith(SCRATCH_PREFIX) or not frappe.db.exists(
		SCRATCH_DOCTYPE, name
	):
		frappe.throw(_("Property {0} does not exist.").format(name), frappe.DoesNotExistError)
	return frappe.get_doc(SCRATCH_DOCTYPE, name)


def _offers(doc) -> list:
	raw = doc.get("offer_calcs")
	if not raw:
		return []
	try:
		val = json.loads(raw)
	except Exception:
		return []
	return val if isinstance(val, list) else []


def latest_offer(doc):
	"""The most recent saved calc's payload (the calculator's `seed`), or None."""
	offers = _offers(doc)
	return (offers[0].get("offer") or None) if offers else None


def record_offer(name: str, payload: dict, html: str) -> None:
	"""Prepend one saved calc. Called by `cash_offer.save_cash_offer`."""
	doc = _get(name)
	offers = _offers(doc)
	offers.insert(
		0,
		{
			"at": now(),
			"by": frappe.session.user,
			"offer": payload,
			"html": html,
		},
	)
	del offers[MAX_OFFERS:]
	# db.set_value so a saved calc is not a "modified" edit of the address.
	frappe.db.set_value(
		SCRATCH_DOCTYPE, name, "offer_calcs", json.dumps(offers), update_modified=False
	)


def _user_label(user: str) -> str:
	return frappe.db.get_value("User", user, "full_name") or user or ""


def _offer_summary(offer: dict) -> dict:
	"""Kind + headline number for the list page."""
	if not isinstance(offer, dict):
		return {}
	scenes = offer.get("scenarios") or []
	first = scenes[0] if scenes else {}
	return {
		"kind": offer.get("kind") or "cash",
		"offer": first.get("offer"),
		"arv": first.get("arv"),
	}


def _shape(doc, *, with_offers: bool = False) -> dict:
	offers = _offers(doc)
	latest = offers[0] if offers else None
	try:
		selected = json.loads(doc.get("comps_selected") or "[]")
	except Exception:
		selected = []
	out = {
		"name": doc.name,
		"property_address": doc.get("property_address") or "",
		"property_city": doc.get("property_city") or "",
		"property_state": doc.get("property_state") or "",
		"property_zip": doc.get("property_zip") or "",
		"notes": doc.get("notes") or "",
		"owner": doc.owner,
		"owner_name": _user_label(doc.owner),
		"creation": str(doc.creation),
		"modified": str(doc.modified),
		"picked_count": len(selected) if isinstance(selected, list) else 0,
		"offer_count": len(offers),
		"latest_offer": _offer_summary(latest.get("offer")) if latest else None,
		"latest_offer_at": latest.get("at") if latest else None,
		"latest_offer_by": _user_label(latest.get("by")) if latest else None,
	}
	if with_offers:
		out["offers"] = [
			{
				"at": o.get("at"),
				"by": o.get("by"),
				"by_name": _user_label(o.get("by")),
				"html": o.get("html") or "",
				"offer": o.get("offer") or {},
			}
			for o in offers
		]
	return out


def _clean(val) -> str:
	return " ".join(str(val or "").split())


# ---------------------------------------------------------------------------------
# Whitelisted
# ---------------------------------------------------------------------------------
@frappe.whitelist()
def list_properties(q: str = "", mine: int = 0) -> dict:
	"""Every scratch property, newest first. `q` filters on the address."""
	_guard()
	if not _available():
		return {"available": False, "properties": []}
	filters = {}
	if int(mine or 0):
		filters["owner"] = frappe.session.user
	or_filters = None
	q = _clean(q)
	if q:
		like = f"%{q}%"
		or_filters = {
			"property_address": ["like", like],
			"property_city": ["like", like],
			"property_zip": ["like", like],
			"notes": ["like", like],
		}
	names = frappe.get_all(
		SCRATCH_DOCTYPE,
		filters=filters,
		or_filters=or_filters,
		pluck="name",
		order_by="modified desc",
		limit=500,
	)
	return {
		"available": True,
		"properties": [_shape(frappe.get_doc(SCRATCH_DOCTYPE, n)) for n in names],
	}


@frappe.whitelist()
def get_property(name: str) -> dict:
	_guard()
	_need()
	return _shape(_get(name), with_offers=True)


@frappe.whitelist()
def create_property(
	address: str, city: str = "", state: str = "", zip_code: str = "", notes: str = ""
) -> dict:
	"""Add a house to comp. One full address line is fine — `_full_address`
	skips the city/state/zip parts already inside it, so "412 Maple Ave,
	Aurora, MN 55705" with the rest blank geocodes and resolves on Zillow
	exactly like a webhook lead's address does."""
	_guard()
	_need()
	address = _clean(address)
	if not address:
		frappe.throw(_("Type the property address first."))
	doc = frappe.get_doc(
		{
			"doctype": SCRATCH_DOCTYPE,
			"property_address": address,
			"property_city": _clean(city),
			"property_state": _clean(state).upper()[:2] if _clean(state) else "",
			"property_zip": _clean(zip_code),
			"notes": (notes or "").strip(),
		}
	)
	doc.insert()
	return _shape(doc)


@frappe.whitelist()
def update_property(
	name: str, address=None, city=None, state=None, zip_code=None, notes=None
) -> dict:
	"""Edit the address or note. An address change drops every location cache
	(geocode, Zillow facts, BatchData) so the next open looks the new house up
	fresh instead of re-centering on the old parcel."""
	_guard()
	_need()
	doc = _get(name)
	before = (
		doc.get("property_address"),
		doc.get("property_city"),
		doc.get("property_state"),
		doc.get("property_zip"),
	)
	if address is not None:
		address = _clean(address)
		if not address:
			frappe.throw(_("The address cannot be blank."))
		doc.property_address = address
	if city is not None:
		doc.property_city = _clean(city)
	if state is not None:
		doc.property_state = _clean(state).upper()[:2]
	if zip_code is not None:
		doc.property_zip = _clean(zip_code)
	if notes is not None:
		doc.notes = (notes or "").strip()
	after = (
		doc.get("property_address"),
		doc.get("property_city"),
		doc.get("property_state"),
		doc.get("property_zip"),
	)
	if before != after:
		doc.property_lat = None
		doc.property_lng = None
		doc.zillow_facts = ""
		doc.zillow_fetched_at = None
		doc.zillow_zpid = ""
		doc.batchdata_comps = ""
		doc.batchdata_comps_fetched_at = None
	doc.save()
	return _shape(doc, with_offers=True)


@frappe.whitelist()
def delete_property(name: str) -> dict:
	_guard()
	_need()
	doc = _get(name)
	doc.delete()
	return {"ok": True}
