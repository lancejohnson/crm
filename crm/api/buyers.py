"""Buyer directory — manually create/edit buyer leads (beyond InvestorLift ingest).

Buyers live on the ops doctype **CRM Buyer** (created by setup_investorlift.py);
setup_buyer_directory.py adds `metro_area` (Link → CRM Metro Area) + `buybox`
(Small Text, free-form until buybox search is structured). This module is the
manual-management side: the /buyers directory list, create (deduped against the
scraper/webhook buyers by email → phone), edit, and metro-area creation.
"""

import json
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import get_datetime, get_system_timezone

from crm.api.investorlift_ingest import BUYER_DOCTYPE, LEAD_BUYER_DOCTYPE, _find_buyer, _last10

SALES_ROLES = ("System Manager", "Sales Manager", "Sales User")

# fields a user may set on create/edit (identity + market; IL sync owns the rest)
EDITABLE_FIELDS = (
	"first_name", "last_name", "phone", "email",
	"buyer_type", "metro_areas", "buybox", "deal_history", "verified",
	"quo_tags",  # Quo (OpenPhone) contact tags — synced two-way with Quo
)

# an edit to any of these re-pushes the buyer's Quo contact
QUO_PUSH_FIELDS = {"first_name", "last_name", "buyer_name", "phone", "email", "quo_tags"}


def _guard():
	if not any(r in SALES_ROLES for r in frappe.get_roles()):
		frappe.throw(_("Only sales users can manage buyers."), frappe.PermissionError)


def _has_market_fields():
	return frappe.get_meta(BUYER_DOCTYPE).has_field("metro_areas")


def _metros_json(value):
	"""Normalize a metro_areas input (list or JSON string) to a stored JSON
	string, or None when empty. Metro names contain commas, hence JSON."""
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except (ValueError, TypeError):
			value = [value] if value.strip() else []
	metros = [m.strip() for m in (value or []) if isinstance(m, str) and m.strip()]
	return json.dumps(metros) if metros else None


def _parse_metros(raw):
	try:
		val = json.loads(raw or "[]")
		return val if isinstance(val, list) else []
	except (ValueError, TypeError):
		return []


@frappe.whitelist()
def get_buyers(search=None, metro=None):
	"""The /buyers directory: every CRM Buyer + deal count + the area they're
	active in (their metro if set, else the cities of the properties they've
	engaged with)."""
	_guard()
	if not frappe.db.exists("DocType", BUYER_DOCTYPE):
		return []

	fields = ["name", "buyer_name", "first_name", "last_name", "phone", "email",
	          "buyer_type", "verified", "deal_history", "last_active", "il_buyer_id", "modified"]
	if _has_market_fields():
		fields += ["metro_areas", "buybox"]
	if frappe.get_meta(BUYER_DOCTYPE).has_field("quo_tags"):
		fields += ["quo_tags"]

	filters = []
	if metro and _has_market_fields():
		# metro_areas is a JSON array of names — match the quoted element
		filters.append(["metro_areas", "like", f'%{json.dumps(metro)}%'])

	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = [
			["buyer_name", "like", like],
			["phone", "like", like],
			["email", "like", like],
		]

	buyers = frappe.get_all(
		BUYER_DOCTYPE, filters=filters, or_filters=or_filters, fields=fields,
		order_by="modified desc", limit_page_length=0,
	)

	# engaged-deal counts + cities per buyer (one pass over the small rel table)
	deal_count, cities = {}, {}
	if frappe.db.exists("DocType", LEAD_BUYER_DOCTYPE):
		rels = frappe.get_all(LEAD_BUYER_DOCTYPE, fields=["buyer", "lead"], limit_page_length=0)
		lead_city = {}
		lead_names = list({r.lead for r in rels})
		if lead_names and frappe.get_meta("CRM Lead").has_field("property_city"):
			for l in frappe.get_all(
				"CRM Lead", filters={"name": ("in", lead_names)},
				fields=["name", "property_city", "property_state"], limit_page_length=0,
			):
				if l.property_city:
					city = l.property_city.strip().title()
					state = (l.property_state or "").strip()
					lead_city[l.name] = f"{city}, {state}" if state else city
		for r in rels:
			deal_count[r.buyer] = deal_count.get(r.buyer, 0) + 1
			c = lead_city.get(r.lead)
			if c:
				cities.setdefault(r.buyer, set()).add(c)

	for b in buyers:
		b["deal_count"] = deal_count.get(b.name, 0)
		metros = _parse_metros(b.get("metro_areas"))
		b["metros"] = metros
		b["active_in"] = " · ".join(metros) or ", ".join(sorted(cities.get(b.name, [])))
	return buyers


@frappe.whitelist()
def create_buyer(first_name, last_name=None, phone=None, email=None,
                 buyer_type=None, metro_areas=None, buybox=None, quo_tags=None):
	"""Create a buyer manually. Dedupes against existing buyers (email → phone);
	on a duplicate, returns it instead of creating so the UI can open it."""
	_guard()
	first_name = (first_name or "").strip()
	if not first_name:
		frappe.throw(_("First name is required."))
	last_name = (last_name or "").strip()
	email = (email or "").strip().lower() or None
	phone = (phone or "").strip() or None

	existing = _find_buyer(email, phone)
	if existing:
		return {
			"ok": False,
			"duplicate": existing,
			"buyer_name": frappe.db.get_value(BUYER_DOCTYPE, existing, "buyer_name"),
		}

	doc = frappe.get_doc({
		"doctype": BUYER_DOCTYPE,
		"buyer_name": f"{first_name} {last_name}".strip(),
		"first_name": first_name,
		"last_name": last_name or None,
		"phone": phone,
		"email": email,
		"buyer_type": (buyer_type or "").strip() or None,
		**({"metro_areas": _metros_json(metro_areas), "buybox": (buybox or "").strip() or None}
		   if _has_market_fields() else {}),
		**({"quo_tags": (quo_tags or "").strip() or None}
		   if frappe.get_meta(BUYER_DOCTYPE).has_field("quo_tags") else {}),
	})
	doc.insert()
	return {"ok": True, "buyer": doc.name}


@frappe.whitelist()
def update_buyer(buyer, updates):
	"""Edit a buyer's identity/market fields (whitelist-filtered)."""
	_guard()
	if isinstance(updates, str):
		updates = json.loads(updates)
	if not frappe.db.exists(BUYER_DOCTYPE, buyer):
		frappe.throw(_("Buyer not found"), frappe.DoesNotExistError)

	meta = frappe.get_meta(BUYER_DOCTYPE)
	vals = {}
	for k, v in (updates or {}).items():
		if k not in EDITABLE_FIELDS or not meta.has_field(k):
			continue
		if k == "metro_areas":
			vals[k] = _metros_json(v)
			continue
		if isinstance(v, str):
			v = v.strip()
		vals[k] = v if v not in ("", None) else None
	if "email" in vals and vals["email"]:
		vals["email"] = vals["email"].lower()

	# keep the display name in sync when the name parts change
	if "first_name" in vals or "last_name" in vals:
		first = vals.get("first_name", frappe.db.get_value(BUYER_DOCTYPE, buyer, "first_name")) or ""
		last = vals.get("last_name", frappe.db.get_value(BUYER_DOCTYPE, buyer, "last_name")) or ""
		full = f"{first} {last}".strip()
		if full:
			vals["buyer_name"] = full

	if vals:
		frappe.db.set_value(BUYER_DOCTYPE, buyer, vals)
		# db.set_value fires no doc events — push identity/tag changes to Quo here
		if QUO_PUSH_FIELDS & set(vals):
			from crm.api.quo_contacts import enqueue_push

			enqueue_push(buyer)
	return {"ok": True}


INTEREST_STAGES = ("New", "Attempted to Contact", "Not Interested", "Interested", "Offer Made")


@frappe.whitelist()
def add_buyer_to_lead(lead, buyer, stage="New"):
	"""Manually put a buyer on a deal's Dispo board (deals = leads in this CRM):
	creates the CRM Lead Buyer relationship if it doesn't exist yet."""
	_guard()
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead not found"), frappe.DoesNotExistError)
	if not frappe.db.exists(BUYER_DOCTYPE, buyer):
		frappe.throw(_("Buyer not found"), frappe.DoesNotExistError)
	if stage not in INTEREST_STAGES:
		stage = "New"

	existing = frappe.db.get_value(LEAD_BUYER_DOCTYPE, {"lead": lead, "buyer": buyer}, "name")
	if existing:
		return {"ok": True, "existing": True}

	frappe.get_doc({
		"doctype": LEAD_BUYER_DOCTYPE,
		"lead": lead,
		"buyer": buyer,
		"interest_stage": stage,
	}).insert()
	frappe.publish_realtime(
		"crm_il_buyers",
		{"reference_doctype": "CRM Lead", "reference_docname": lead},
		after_commit=True,
	)
	return {"ok": True, "existing": False}


@frappe.whitelist()
def get_buyer_calls(buyer):
	"""CRM Call Log rows for a buyer (matched by last-10 phone digits against
	from/to), shaped exactly like the lead Activity timeline's call entries
	(parse_call_log adds _caller/_receiver/_duration) so the buyer page renders
	them with the same CallArea card — recording, Playback (waveform +
	transcript + comments), AI summary and all. `at_epoch` is a true UTC epoch
	for merging with the live-fetched Quo texts client-side."""
	_guard()
	phone = frappe.db.get_value(BUYER_DOCTYPE, buyer, "phone")
	last10 = _last10(phone)
	if not last10:
		return []

	from crm.fcrm.doctype.crm_call_log.crm_call_log import parse_call_log

	calls = frappe.get_all(
		"CRM Call Log",
		or_filters=[
			["from", "like", f"%{last10}"],
			["to", "like", f"%{last10}"],
		],
		fields=[
			"name", "caller", "receiver", "from", "to", "duration",
			"start_time", "end_time", "status", "type", "recording_url", "creation",
		],
		order_by="creation asc",
		limit_page_length=0,
	)
	tz = ZoneInfo(get_system_timezone())
	buyer_name = frappe.db.get_value(BUYER_DOCTYPE, buyer, "buyer_name")
	out = []
	for c in calls:
		c = parse_call_log(c)
		# the buyer isn't a CRM Contact, so the phone→contact lookup says "Unknown";
		# show the buyer's name on their side of the call instead
		side = "_receiver" if c.get("type") == "Outgoing" else "_caller"
		if c.get(side) and c[side].get("label") in (None, "", "Unknown"):
			c[side]["label"] = buyer_name
		c["at_epoch"] = get_datetime(c["creation"]).replace(tzinfo=tz).timestamp()
		out.append(c)
	return out


@frappe.whitelist()
def get_metro_areas():
	"""All metros for the directory filter dropdown."""
	_guard()
	if not frappe.db.exists("DocType", "CRM Metro Area"):
		return []
	return frappe.get_all("CRM Metro Area", fields=["name", "metro_name", "state"],
	                      order_by="metro_name asc", limit_page_length=0)


@frappe.whitelist()
def create_metro_area(metro_name, state=None):
	"""Create a metro (the Link control's Create New)."""
	_guard()
	metro_name = (metro_name or "").strip()
	if not metro_name:
		frappe.throw(_("Metro name is required."))
	if frappe.db.exists("CRM Metro Area", metro_name):
		return {"name": metro_name}
	doc = frappe.get_doc({
		"doctype": "CRM Metro Area",
		"metro_name": metro_name,
		"state": (state or "").strip() or None,
	})
	doc.insert()
	return {"name": doc.name}
