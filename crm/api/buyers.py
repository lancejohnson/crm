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
from frappe.utils import get_datetime, get_system_timezone, now_datetime

from crm.api.investorlift_ingest import BUYER_DOCTYPE, LEAD_BUYER_DOCTYPE, _find_buyer, _last10

SALES_ROLES = ("System Manager", "Sales Manager", "Sales User")

# fields a user may set on create/edit (identity + market; IL sync owns the rest)
EDITABLE_FIELDS = (
	"first_name", "last_name", "phone", "email",
	"buyer_type", "metro_areas", "buybox", "buybox_cities",
	"buybox_property_types", "deal_history", "verified",
	"quo_tags",  # Quo (OpenPhone) contact tags — synced two-way with Quo
)

JSON_LIST_FIELDS = {"metro_areas", "buybox_cities", "buybox_property_types"}

# an edit to any of these re-pushes the buyer's Quo contact
QUO_PUSH_FIELDS = {"first_name", "last_name", "buyer_name", "phone", "email", "quo_tags"}


def _guard():
	if not any(r in SALES_ROLES for r in frappe.get_roles()):
		frappe.throw(_("Only sales users can manage buyers."), frappe.PermissionError)


def _has_market_fields():
	return frappe.get_meta(BUYER_DOCTYPE).has_field("metro_areas")


def _json_list(value):
	"""Normalize a JSON-list field while preserving commas inside values."""
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except (ValueError, TypeError):
			value = [value] if value.strip() else []
	items = []
	for item in value or []:
		if not isinstance(item, str) or not item.strip():
			continue
		item = item.strip()
		if item not in items:
			items.append(item)
	return items


def _json_list_value(value):
	items = _json_list(value)
	return json.dumps(items, ensure_ascii=False) if items else None


def _metros_json(value):
	"""Backwards-compatible spelling used by buyer-import callers."""
	return _json_list_value(value)


def _parse_metros(raw):
	"""Backwards-compatible parser used by the directory and ingest API."""
	return _json_list(raw)


@frappe.whitelist()
def get_buyers(search=None, metro=None, property=None, import_list=None):
	"""The /buyers directory: every CRM Buyer + deal count + the area they're
	active in (their metro if set, else the cities of the properties they've
	engaged with).

	`property` is a CRM Lead name (a dispo property) — when given, the list is
	restricted to the buyers engaged on that property (CRM Lead Buyer rows).

	`import_list` is a buyer import list name (CRM Buyer.import_lists is a JSON
	array of names) — when given, only buyers tagged with that list."""
	_guard()
	if not frappe.db.exists("DocType", BUYER_DOCTYPE):
		return []

	fields = ["name", "buyer_name", "first_name", "last_name", "phone", "email",
	          "buyer_type", "verified", "deal_history", "last_active", "il_buyer_id", "modified"]
	if _has_market_fields():
		fields += ["metro_areas", "buybox"]
		for fieldname in ("buybox_cities", "buybox_property_types"):
			if frappe.get_meta(BUYER_DOCTYPE).has_field(fieldname):
				fields.append(fieldname)
	if frappe.get_meta(BUYER_DOCTYPE).has_field("quo_tags"):
		fields += ["quo_tags"]

	filters = []
	if metro and _has_market_fields():
		# metro_areas is a JSON array of names — match the quoted element
		filters.append(["metro_areas", "like", f'%{json.dumps(metro)}%'])
	if import_list and frappe.get_meta(BUYER_DOCTYPE).has_field("import_lists"):
		# same quoted-JSON-element LIKE as metros; ensure_ascii=False because the
		# stored value is written that way (an em-dash in a list name must match)
		filters.append(["import_lists", "like", f'%{json.dumps(import_list, ensure_ascii=False)}%'])
	stage_by_buyer = {}
	if property and frappe.db.exists("DocType", LEAD_BUYER_DOCTYPE):
		# restrict to buyers engaged on this property (the CRM Lead Buyer rel table)
		# and capture each buyer's interest_stage on it (the per-property status), so
		# the UI can show status + let the user avoid texting "Not Interested" buyers.
		stage_by_buyer = {
			r.buyer: r.interest_stage for r in frappe.get_all(
				LEAD_BUYER_DOCTYPE, filters={"lead": property},
				fields=["buyer", "interest_stage"], limit_page_length=0,
			) if r.buyer
		}
		if not stage_by_buyer:
			return []
		filters.append(["name", "in", list(stage_by_buyer)])

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
		if stage_by_buyer:
			# per-property interest stage (only present when filtered by property)
			b["interest_stage"] = stage_by_buyer.get(b.name)
	return buyers


@frappe.whitelist()
def create_buyer(first_name, last_name=None, phone=None, email=None,
                 buyer_type=None, metro_areas=None, buybox=None, quo_tags=None,
                 buybox_cities=None, buybox_property_types=None):
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
		**({
			"metro_areas": _metros_json(metro_areas),
			"buybox": (buybox or "").strip() or None,
			**({"buybox_cities": _json_list_value(buybox_cities)}
			   if frappe.get_meta(BUYER_DOCTYPE).has_field("buybox_cities") else {}),
			**({"buybox_property_types": _json_list_value(buybox_property_types)}
			   if frappe.get_meta(BUYER_DOCTYPE).has_field("buybox_property_types") else {}),
		} if _has_market_fields() else {}),
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
		if k in JSON_LIST_FIELDS:
			vals[k] = _json_list_value(v)
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

# Canonical per-property rejection reasons. Keep the values in sync with
# frontend/src/utils/buyerRejectionReasons.js so the board's icons and the
# server-side validation cannot drift.
NOT_INTERESTED_REASONS = (
	"Pricing",
	"Not buying in this location",
	"Not currently in the market",
	"Daisy chainer",
	"Does not buy deal type",
	"Property condition",
	"No longer buying",
	"Other",
)


def _not_interested_reasons(value):
	"""Normalize and validate the JSON multi-select sent by the Dispo board."""
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except (TypeError, ValueError):
			value = [value]
	if not isinstance(value, (list, tuple)):
		frappe.throw(_("Not interested reasons must be a list."))

	items = []
	for item in value:
		if not isinstance(item, str) or not item.strip():
			continue
		item = item.strip()
		if item not in NOT_INTERESTED_REASONS:
			frappe.throw(_("Invalid not interested reason: {0}").format(item))
		if item not in items:
			items.append(item)
	if not items:
		frappe.throw(_("Select at least one reason."))
	return items


@frappe.whitelist()
def move_buyer_stage(relationship, stage, reasons=None, note=None):
	"""Move one buyer relationship to another Dispo-board column.

	Moving to Not Interested also stores structured, per-property reasons. The
	same endpoint updates reasons on an already-Not-Interested card, so corrections
	remain atomic with the relationship row and publish the usual realtime event.
	"""
	_guard()
	if stage not in INTEREST_STAGES:
		frappe.throw(_("Invalid buyer stage."))
	if not frappe.db.exists(LEAD_BUYER_DOCTYPE, relationship):
		frappe.throw(_("Buyer relationship not found"), frappe.DoesNotExistError)

	doc = frappe.get_doc(LEAD_BUYER_DOCTYPE, relationship)
	if not doc.has_permission("write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	updates = {}
	meta = frappe.get_meta(LEAD_BUYER_DOCTYPE)
	if stage == "Not Interested":
		if not meta.has_field("not_interested_reasons"):
			frappe.throw(_("Not interested reasons are not configured yet."))
		selected = _not_interested_reasons(reasons)
		note = (note or "").strip()
		if len(note) > 1000:
			frappe.throw(_("The note must be 1,000 characters or fewer."))
		updates = {
			"not_interested_reasons": json.dumps(selected, ensure_ascii=False),
			"not_interested_note": note or None,
			"not_interested_by": frappe.session.user,
			"not_interested_at": now_datetime(),
		}
	else:
		# Reasons describe the buyer's current per-property stage. Clear them when
		# the buyer leaves Not Interested so an InvestorLift-origin move back into
		# that column cannot surface stale CRM reasons from an earlier decision.
		for fieldname in (
			"not_interested_reasons", "not_interested_note",
			"not_interested_by", "not_interested_at",
		):
			if meta.has_field(fieldname) and doc.get(fieldname):
				updates[fieldname] = None

	if doc.interest_stage == stage and not updates:
		return {"ok": True, "stage": stage}

	doc.interest_stage = stage
	for fieldname, value in updates.items():
		if doc.meta.has_field(fieldname):
			setattr(doc, fieldname, value)
	doc.save()
	frappe.publish_realtime(
		"crm_il_buyers",
		{"reference_doctype": "CRM Lead", "reference_docname": doc.lead},
		after_commit=True,
	)
	return {
		"ok": True,
		"stage": stage,
		**({"reasons": selected, "note": note} if stage == "Not Interested" else {}),
	}


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
def get_buybox_cities():
	"""Distinct property cities already in CRM, plus cities saved on buyers.

	The picker still allows a custom city, so the existing lead set is a useful
	starting vocabulary rather than a gate.
	"""
	_guard()
	cities = {}
	if frappe.get_meta("CRM Lead").has_field("property_city"):
		for row in frappe.get_all(
			"CRM Lead",
			filters={"property_city": ["is", "set"]},
			fields=["property_city", "property_state"],
			limit_page_length=0,
		):
			city = (row.property_city or "").strip().title()
			state = (row.property_state or "").strip()
			state = state.upper() if len(state) <= 3 else state.title()
			label = f"{city}, {state}" if state else city
			if label:
				cities.setdefault(label.lower(), label)

	meta = frappe.get_meta(BUYER_DOCTYPE)
	if meta.has_field("buybox_cities"):
		for raw in frappe.get_all(
			BUYER_DOCTYPE, fields=["buybox_cities"], limit_page_length=0
		):
			for city in _json_list(raw.get("buybox_cities")):
				cities.setdefault(city.lower(), city)

	return [{"label": value, "value": value} for value in sorted(cities.values())]


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
