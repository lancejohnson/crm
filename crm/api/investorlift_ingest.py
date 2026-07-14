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


def _find_buyer(email, phone):
	"""Dedupe key: email first (stable per buyer), then last-10 phone digits."""
	if email:
		name = frappe.db.get_value(BUYER_DOCTYPE, {"email": email}, "name")
		if name:
			return name
	if phone:
		last10 = _last10(phone)
		if last10:
			# no SQL LIKE on a computed suffix — scan the small buyer set by digits
			for b in frappe.get_all(BUYER_DOCTYPE, filters={"phone": ("is", "set")}, fields=["name", "phone"]):
				if _last10(b.phone) == last10:
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

	name = _find_buyer(email, phone)
	if name:
		# only overwrite with non-empty values (never blank out on a sparse scrape)
		update = {k: v for k, v in fields.items() if v not in (None, "")}
		if update:
			frappe.db.set_value(BUYER_DOCTYPE, name, update, update_modified=False)
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
				(row.get("email") or "").strip().lower() or None, (row.get("phone") or "").strip() or None
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

	doc = frappe.db.get_value(
		BUYER_DOCTYPE, buyer,
		["name", "buyer_name", "first_name", "last_name", "phone", "email",
		 "verified", "buyer_type", "deal_history", "last_active", "il_buyer_id"],
		as_dict=True,
	)

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
