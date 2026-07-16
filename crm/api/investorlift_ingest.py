"""Ingest InvestorLift buyer-board rows into CRM Buyer + CRM Lead Buyer.

The buyer board lives at `investorlift.ai/deals/{property_id}` — a Next.js RSC app
with no REST API and a reCAPTCHA login, so it can't be crcommed like the admin API
(Tier 1). Instead an ops Playwright worker (`../frappe-crm-deploy`,
`scripts/investorlift_scrape.py`) loads a human-seeded session, reads the rendered
DOM per deal, and POSTs the parsed buyer rows here.

This endpoint is the CRM side: for each scraped buyer it upserts a global
**CRM Buyer** (deduped by email → phone) and a per-property **CRM Lead Buyer**
relationship (the Dispo-board row), resolving the lead from `il_property_id`. The
board's column becomes the `interest_stage`; type tags, verified, deal history,
direction, and last-active are mirrored on. Buyer↔us texts/calls are NOT ingested
here — once a buyer's phone is on a CRM Buyer, their Quo conversation already shows
in our own timeline.
"""

import json
import re

import requests

import frappe
from frappe import _
from frappe.utils import now_datetime

BUYER_DOCTYPE = "CRM Buyer"
LEAD_BUYER_DOCTYPE = "CRM Lead Buyer"

# board column label -> CRM Lead Buyer.interest_stage option
COLUMN_TO_STAGE = {
	"new leads": "New",
	"new lead": "New",
	"attempted to contact": "Attempted to Contact",
	"not interested": "Not Interested",
	"interested": "Interested",
	"offer made": "Offer Made",
}

MANAGER_ROLES = ("System Manager", "Sales Manager")


def _guard():
	if not any(r in MANAGER_ROLES for r in frappe.get_roles()):
		frappe.throw(_("Not permitted to ingest InvestorLift buyers."), frappe.PermissionError)


def _last10(number):
	return "".join(ch for ch in (number or "") if ch.isdigit())[-10:]


def _find_buyer(email, phone, name=None):
	"""Dedupe key: email first (stable per buyer), then last-10 phone digits.
	Last resort: exact name match against a buyer that has NO email and NO phone —
	those rows only come from the address-request webhook when the contact lookup
	failed (e.g. Marcel Cohen), so an enrichment pass should merge into them
	rather than create a duplicate."""
	if email:
		buyer = frappe.db.get_value(BUYER_DOCTYPE, {"email": email}, "name")
		if buyer:
			return buyer
	if phone:
		last10 = _last10(phone)
		if last10:
			# no SQL LIKE on a computed suffix — scan the small buyer set by digits
			for b in frappe.get_all(BUYER_DOCTYPE, filters={"phone": ("is", "set")}, fields=["name", "phone"]):
				if _last10(b.phone) == last10:
					return b.name
	if name:
		want = name.strip().lower()
		if want:
			for b in frappe.get_all(
				BUYER_DOCTYPE,
				filters={"email": ("is", "not set"), "phone": ("is", "not set")},
				fields=["name", "buyer_name"],
			):
				if (b.buyer_name or "").strip().lower() == want:
					return b.name
	return None


def _upsert_buyer(row):
	"""Create/update a CRM Buyer from a scraped row; return its name."""
	email = (row.get("email") or "").strip().lower() or None
	phone = (row.get("phone") or "").strip() or None
	full_name = (row.get("name") or "").strip() or (email or phone or "Unknown")
	tags = row.get("tags") or []
	buyer_type = ", ".join(t for t in tags if t) if tags else None

	fields = {
		"buyer_name": full_name,
		"first_name": row.get("first_name"),
		"last_name": row.get("last_name"),
		"phone": phone,
		"email": email,
		"verified": 1 if row.get("verified") else 0,
		"buyer_type": buyer_type,
		"deal_history": row.get("deal_history"),
		"last_active": row.get("last_active_at"),  # optional ISO; may be None
	}
	if row.get("il_buyer_id"):
		fields["il_buyer_id"] = str(row["il_buyer_id"])

	name = _find_buyer(email, phone, full_name)
	if name:
		# only overwrite with non-empty values (never blank out on a sparse scrape)
		update = {k: v for k, v in fields.items() if v not in (None, "")}
		if update:
			frappe.db.set_value(BUYER_DOCTYPE, name, update, update_modified=False)
			# db.set_value fires no doc events — push identity changes to Quo here
			if {"buyer_name", "first_name", "last_name", "phone", "email"} & set(update):
				from crm.api.quo_contacts import enqueue_push

				enqueue_push(name)
		return name

	doc = frappe.get_doc({"doctype": BUYER_DOCTYPE, **{k: v for k, v in fields.items() if v is not None}})
	doc.insert(ignore_permissions=True)
	return doc.name


def _upsert_relationship(lead, buyer, row):
	"""Create/update the per-property CRM Lead Buyer row."""
	stage = COLUMN_TO_STAGE.get((row.get("column") or "").strip().lower())
	direction = (row.get("direction") or "").strip().capitalize()
	if direction not in ("Inbound", "Outbound"):
		direction = None

	existing = frappe.db.get_value(LEAD_BUYER_DOCTYPE, {"lead": lead, "buyer": buyer}, "name")
	vals = {
		"interest_stage": stage,
		"direction": direction,
		"message_count": row.get("note_count") or 0,
		"last_active": row.get("last_active_at"),
	}
	vals = {k: v for k, v in vals.items() if v not in (None, "")}
	if existing:
		if vals:
			frappe.db.set_value(LEAD_BUYER_DOCTYPE, existing, vals, update_modified=False)
		return existing, False
	doc = frappe.get_doc({"doctype": LEAD_BUYER_DOCTYPE, "lead": lead, "buyer": buyer, **vals})
	doc.insert(ignore_permissions=True)
	return doc.name, True


@frappe.whitelist()
def ingest_deal_buyers(il_property_id, buyers):
	"""Upsert a deal's scraped buyer rows. `buyers` = JSON list of row dicts:
	{name, first_name?, last_name?, phone, email, verified, tags[], deal_history,
	 direction, column, note_count?, last_active_at?, il_buyer_id?}."""
	_guard()
	if isinstance(buyers, str):
		buyers = json.loads(buyers)
	il_property_id = str(il_property_id).strip()

	# resolve the lead this property maps to (Tier-1 link)
	lead = frappe.db.get_value("CRM Lead", {"il_property_id": il_property_id}, "name")
	if not lead:
		return {"ok": False, "error": f"no CRM Lead linked to il_property_id {il_property_id}"}

	created_buyers = updated_buyers = created_rels = 0
	for row in buyers or []:
		try:
			existed = _find_buyer(
				(row.get("email") or "").strip().lower() or None,
				(row.get("phone") or "").strip() or None,
				(row.get("name") or "").strip() or None,
			)
			buyer = _upsert_buyer(row)
			if existed:
				updated_buyers += 1
			else:
				created_buyers += 1
			_, is_new = _upsert_relationship(lead, buyer, row)
			if is_new:
				created_rels += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"IL buyer ingest failed for {row.get('email') or row.get('name')}")

	frappe.db.commit()
	# live-refresh the lead's Dispo board
	frappe.publish_realtime(
		"crm_il_buyers",
		{"reference_doctype": "CRM Lead", "reference_docname": lead},
		after_commit=True,
	)
	return {
		"ok": True,
		"lead": lead,
		"buyers_created": created_buyers,
		"buyers_updated": updated_buyers,
		"relationships_created": created_rels,
		"total": len(buyers or []),
		"synced_at": str(now_datetime()),
	}


@frappe.whitelist()
def get_linked_properties():
	"""[{lead, il_property_id}] for every lead linked to an IL property — the
	scraper's work-list (which deal boards to scrape)."""
	_guard()
	if not frappe.get_meta("CRM Lead").has_field("il_property_id"):
		return []
	return frappe.get_all(
		"CRM Lead",
		filters={"il_property_id": ("is", "set")},
		fields=["name as lead", "il_property_id"],
	)


# --------------------------------------------------------------------------- #
# real-time "new buyer requested an address" — webhook-driven (NOT polling)
# --------------------------------------------------------------------------- #
# InvestorLift texts us a notification the moment a buyer requests an address; that
# text is delivered to our Quo line → the OpenPhone `message.received` webhook →
# Sequence Events Log. An after_insert hook on that log (crm/hooks.py) fires
# `on_sequence_event`, which parses the (self-contained) notification and pulls the
# buyer onto the right property's board in real time. Two notification shapes:
#   "New buyer signed up: <name>, <email>, <phone>"
#   "Hi <rep>. <name> sent an address request for <full property address>"
_NEW_BUYER_RE = re.compile(
	r"New buyer signed up:\s*(?P<name>.+?),\s*(?P<email>[^,\s]+@[^,\s]+)\s*,\s*(?P<phone>[+\d().\-\s]+?)\s*$",
	re.I,
)
_ADDR_REQ_RE = re.compile(
	r"(?:hi\s+[^.]+\.\s*)?(?P<name>.+?)\s+sent an address request for\s+(?P<addr>.+?)\.?\s*$",
	re.I,
)


def on_sequence_event(doc, method=None):
	"""after_insert on Sequence Events Log — pull a buyer when an InvestorLift
	address-request notification lands (real-time, webhook-driven)."""
	if (doc.get("event_type") or "") != "message.received":
		return
	try:
		obj = (json.loads(doc.get("payload") or "{}").get("data") or {}).get("object") or {}
	except (ValueError, TypeError):
		return
	m = _ADDR_REQ_RE.search(obj.get("text") or "")
	if not m:
		return
	try:
		_handle_address_request(m.group("name").strip(), m.group("addr").strip())
	except Exception:
		frappe.log_error(frappe.get_traceback(), "IL address-request webhook failed")


def _lookup_signup(buyer_name):
	"""Grab email/phone from the paired 'New buyer signed up' notification (arrives
	seconds before the address request), so we create the buyer with full contact."""
	want = (buyer_name or "").strip().lower()
	for r in frappe.get_all(
		"Sequence Events Log", filters={"event_type": "message.received"},
		fields=["payload"], order_by="creation desc", limit_page_length=40,
	):
		try:
			o = (json.loads(r.payload or "{}").get("data") or {}).get("object") or {}
		except (ValueError, TypeError):
			continue
		mm = _NEW_BUYER_RE.search(o.get("text") or "")
		if mm and mm.group("name").strip().lower() == want:
			return mm.group("email").strip(), mm.group("phone").strip()
	return None, None


def _inquiry_contact(il_property_id, buyer_name):
	"""Look up an address-requester's contact info from the IL admin API: the
	property's inquiries carry a customer_id; the customer record has the email +
	SMS phone (+ verified). Returns {} on any failure — callers degrade to the
	name-only row the webhook used to create."""
	from crm.api import investorlift as il

	want = (buyer_name or "").strip().lower()
	if not (want and il_property_id):
		return {}
	try:
		token = il.get_token()
		h = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
		inquiries = requests.get(
			f"{il.API_BASE}/properties/{il_property_id}/inquiries",
			params={"per_page": 100}, headers=h, timeout=25,
		).json().get("data", [])
		for inq in inquiries:
			cid = inq.get("customer_id")
			if not cid:
				continue
			c = requests.get(f"{il.API_BASE}/customers/{cid}", headers=h, timeout=20).json()
			cust = c.get("data") if isinstance(c, dict) and "data" in c else c
			if not isinstance(cust, dict):
				continue
			if (cust.get("full_name") or "").strip().lower() != want:
				continue
			return {
				"email": cust.get("email") or inq.get("from_email"),
				"phone": (cust.get("unsubscribe_sms_data") or {}).get("phone") or inq.get("from_phone"),
				"verified": bool(cust.get("is_id_verified")),
				"il_buyer_id": cid,
			}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "IL inquiry-contact lookup failed")
	return {}


def _handle_address_request(buyer_name, address):
	from crm.api import investorlift as il

	# match the notified address to a linked lead (normalized street|zip key)
	key = il._addr_key(*il._split_address(address))
	if not key:
		return
	lead = None
	for l in frappe.get_all(
		"CRM Lead",
		filters={"il_property_id": ("is", "set"), "property_address": ("is", "set")},
		fields=["name", "property_address"],
	):
		if il._addr_key(*il._split_address(l.property_address)) == key:
			lead = l.name
			break
	if not lead:
		frappe.log_error(f"no linked lead for address '{address}'", "IL address-request")
		return

	email, phone = _lookup_signup(buyer_name)
	row = {"name": buyer_name, "email": email, "phone": phone, "direction": "Inbound", "column": "NEW LEADS"}
	if not (email and phone):
		# no paired signup text (buyer signed up long ago / >40 events back) —
		# pull contact info from the IL API instead (the Marcel Cohen case)
		extra = _inquiry_contact(frappe.db.get_value("CRM Lead", lead, "il_property_id"), buyer_name)
		if extra:
			row["email"] = row["email"] or extra.get("email")
			row["phone"] = row["phone"] or extra.get("phone")
			row["verified"] = extra.get("verified")
			row["il_buyer_id"] = extra.get("il_buyer_id")
	buyer = _upsert_buyer(row)
	_upsert_relationship(lead, buyer, row)
	frappe.db.commit()
	frappe.publish_realtime(
		"crm_il_buyers", {"reference_doctype": "CRM Lead", "reference_docname": lead}, after_commit=True
	)


@frappe.whitelist()
def pull_new_inquiries():
	"""Manual backfill/reconciliation (the webhook is the live path): for each linked
	property, poll `/api/properties/{id}/inquiries`, resolve each requester's customer,
	and upsert a CRM Buyer (il_buyer_id=customer id) + a CRM Lead Buyer (New/Inbound).
	Idempotent — reconciles with scraper/webhook buyers by email; realtime-refreshes."""
	if frappe.session.user != "Administrator" and not any(
		r in MANAGER_ROLES for r in frappe.get_roles()
	):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	if not frappe.get_meta("CRM Lead").has_field("il_property_id"):
		return {"ok": False, "reason": "not provisioned"}

	from crm.api import investorlift as il

	try:
		token = il.get_token()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "IL inquiries: token failed")
		return {"ok": False, "reason": "auth"}
	h = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

	leads = frappe.get_all(
		"CRM Lead", filters={"il_property_id": ("is", "set")}, fields=["name", "il_property_id"]
	)
	created, touched = 0, set()
	for lead in leads:
		pid = str(lead.il_property_id).strip()
		try:
			inquiries = requests.get(
				f"{il.API_BASE}/properties/{pid}/inquiries", params={"per_page": 100}, headers=h, timeout=25
			).json().get("data", [])
		except Exception:
			continue
		for inq in inquiries:
			cid = inq.get("customer_id")
			if not cid:
				continue
			# already pulled onto this board? (fast path once il_buyer_id is stamped)
			existing = frappe.db.get_value(BUYER_DOCTYPE, {"il_buyer_id": str(cid)}, "name")
			if existing and frappe.db.exists(LEAD_BUYER_DOCTYPE, {"lead": lead.name, "buyer": existing}):
				continue
			try:
				c = requests.get(f"{il.API_BASE}/customers/{cid}", headers=h, timeout=20).json()
			except Exception:
				continue
			cust = c.get("data") if isinstance(c, dict) and "data" in c else c
			if not isinstance(cust, dict):
				continue
			row = {
				"name": cust.get("full_name"),
				"email": cust.get("email") or inq.get("from_email"),
				"phone": (cust.get("unsubscribe_sms_data") or {}).get("phone") or inq.get("from_phone"),
				"verified": bool(cust.get("is_id_verified")),
				"il_buyer_id": cid,
				"direction": "Inbound",
				"column": "NEW LEADS",
			}
			try:
				buyer = _upsert_buyer(row)
				_, is_new = _upsert_relationship(lead.name, buyer, row)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"IL inquiry pull failed for customer {cid}")
				continue
			if is_new:
				created += 1
				touched.add(lead.name)
		frappe.db.commit()

	for ln in touched:
		frappe.publish_realtime(
			"crm_il_buyers", {"reference_doctype": "CRM Lead", "reference_docname": ln}, after_commit=True
		)
	return {"ok": True, "new_buyers": created}


@frappe.whitelist()
def get_dispo_properties():
	"""Active-dispo properties (leads linked to an IL property) for the Dispo page
	property switcher: [{lead, label, il_property_id, il_status, buyer_count}]."""
	if not any(r in ("System Manager", "Sales Manager", "Sales User") for r in frappe.get_roles()):
		frappe.throw(_("Only sales users can view dispo."), frappe.PermissionError)
	if not frappe.get_meta("CRM Lead").has_field("il_property_id"):
		return []
	leads = frappe.get_all(
		"CRM Lead",
		filters={"il_property_id": ("is", "set")},
		fields=["name", "lead_name", "property_address", "il_property_id", "il_status", "modified"],
		order_by="modified desc",
		limit_page_length=0,
	)
	has_buyers = frappe.db.exists("DocType", LEAD_BUYER_DOCTYPE)
	out = []
	for l in leads:
		out.append({
			"lead": l.name,
			"label": l.property_address or l.lead_name or l.name,
			"il_property_id": l.il_property_id,
			"il_status": l.il_status,
			"buyer_count": frappe.db.count(LEAD_BUYER_DOCTYPE, {"lead": l.name}) if has_buyers else 0,
		})
	return out


@frappe.whitelist()
def get_buyer(buyer):
	"""A buyer's profile + every deal (property) they've engaged with — the buyer page."""
	if not any(r in ("System Manager", "Sales Manager", "Sales User") for r in frappe.get_roles()):
		frappe.throw(_("Only sales users can view buyers."), frappe.PermissionError)
	if not frappe.db.exists(BUYER_DOCTYPE, buyer):
		frappe.throw(_("Buyer not found"), frappe.DoesNotExistError)

	fields = ["name", "buyer_name", "first_name", "last_name", "phone", "email",
	          "verified", "buyer_type", "deal_history", "last_active", "il_buyer_id"]
	if frappe.get_meta(BUYER_DOCTYPE).has_field("metro_areas"):
		fields += ["metro_areas", "buybox"]
	if frappe.get_meta(BUYER_DOCTYPE).has_field("quo_tags"):
		fields += ["quo_tags"]
	doc = frappe.db.get_value(BUYER_DOCTYPE, buyer, fields, as_dict=True)
	from crm.api.buyers import _parse_metros

	doc["metros"] = _parse_metros(doc.get("metro_areas"))

	deals = []
	rels = frappe.get_all(
		LEAD_BUYER_DOCTYPE,
		filters={"buyer": buyer},
		fields=["name", "lead", "interest_stage", "direction", "last_active", "message_count"],
		order_by="modified desc",
	)
	for r in rels:
		info = frappe.db.get_value(
			"CRM Lead", r.lead, ["lead_name", "property_address", "il_property_id"], as_dict=True
		) or {}
		deals.append({
			"lead": r.lead,
			"label": info.get("property_address") or info.get("lead_name") or r.lead,
			"il_property_id": info.get("il_property_id"),
			"interest_stage": r.interest_stage,
			"direction": r.direction,
			"last_active": r.last_active,
			"message_count": r.message_count,
		})

	doc["deals"] = deals
	return doc


def _e164(number):
	"""Best-effort E164 for a US buyer phone ('(313) 502-6343' → '+13135026343')."""
	d = "".join(c for c in (number or "") if c.isdigit())
	if len(d) == 10:
		return "+1" + d
	if len(d) == 11 and d.startswith("1"):
		return "+" + d
	return ("+" + d) if d else ""


@frappe.whitelist()
def get_buyer_conversation(buyer):
	"""Texts with a buyer, time-sorted — read from the stored **Quo Message**
	rows referenced to the buyer (the sequence-events webhook mirrors buyer
	texts now, and ops `backfill_buyer_texts.py` covered history), so the
	thread is fast, complete, carries MMS media, and refreshes live via the
	`quo_message` realtime event. Calls are NOT fetched here — they come from
	CRM Call Log via crm.api.buyers.get_buyer_calls, which carries recordings
	+ transcripts and renders with the lead timeline's CallArea card."""
	if not any(r in ("System Manager", "Sales Manager", "Sales User") for r in frappe.get_roles()):
		frappe.throw(_("Only sales users can view buyer activity."), frappe.PermissionError)
	phone = frappe.db.get_value(BUYER_DOCTYPE, buyer, "phone")
	e164 = _e164(phone)
	if not frappe.db.exists("DocType", "Quo Message"):
		return {"phone": e164 or None, "items": []}

	from zoneinfo import ZoneInfo

	from frappe.utils import get_datetime, get_system_timezone

	from crm.api.sms import _media, _sender_map

	rows = frappe.get_all(
		"Quo Message",
		filters={"reference_doctype": BUYER_DOCTYPE, "reference_docname": buyer},
		fields=["name", "direction", "from", "to", "content", "media", "status",
		        "message_date", "creation"],
		order_by="message_date asc, creation asc",
		limit_page_length=0,
	)
	senders = _sender_map()
	tz = ZoneInfo(get_system_timezone())
	items = []
	for m in rows:
		out = m.direction == "Outgoing"
		sender = senders.get(_last10(m.get("from"))) if out else None
		at = m.message_date or m.creation
		items.append({
			"kind": "text",
			"direction": "outgoing" if out else "incoming",
			"text": m.content or "",
			"media": _media(m.get("media")),
			"at": at,
			"at_epoch": get_datetime(at).replace(tzinfo=tz).timestamp() if at else 0,
			"line": (sender.full_name if sender else None) or m.get("from"),
		})
	return {"phone": e164 or None, "items": items}


@frappe.whitelist()
def get_deal_buyers(lead):
	"""CRM Lead Buyer rows for a lead, grouped for the Dispo board / debugging."""
	if not frappe.has_permission("CRM Lead", "read", lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.db.exists("DocType", LEAD_BUYER_DOCTYPE):
		return []
	return frappe.get_all(
		LEAD_BUYER_DOCTYPE,
		filters={"lead": lead},
		fields=[
			"name", "buyer", "buyer_name", "interest_stage", "direction",
			"phone", "buyer_type", "deal_history", "verified", "last_active", "message_count",
		],
		order_by="interest_stage asc, modified desc",
		limit_page_length=0,
	)
