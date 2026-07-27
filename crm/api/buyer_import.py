"""Bulk buyer import — paste/CSV -> CRM Buyers, optionally straight onto a
property's Dispo board, optionally split round-robin between reps.

Buyers normally arrive on their own (the InvestorLift scraper + the
address-request webhook). But a rep who buys a cash-buyer list, exports a
county's LLC purchasers, or comes back from a REIA meeting with a spreadsheet
has had no way in — the only route was the one-at-a-time "New buyer" modal.

An import does up to three things:

  1. Creates the buyers we don't already have.
  2. Puts every buyer in the batch — newly created *and* already-existing — on
     the chosen property's Dispo board (a `CRM Lead Buyer` row) at a stage.
  3. Deals the buyers out round-robin between the selected reps as Frappe
     assignments (`_assign` ToDos), so each rep has a list to work.

Deliberate rules, each learned from the lead importer next door:

  * Dedupe is by email → last-10 phone digits → name, the same identity rule
    `_find_buyer` uses everywhere else, so re-importing the same list attaches
    and assigns rather than duplicating.
  * A matched existing buyer is never overwritten. Empty fields get filled in
    (a list that carries an email for a buyer we only had a phone for is a
    gift), but a value someone curated stays put.
  * An already-assigned buyer is never re-assigned. Ownership is not stolen by
    an import, and the round-robin only advances when an assignment actually
    happens, so the reps who do get buyers get an even split.

Nothing here needs an ops script: every field it writes already exists (the
market/Quo fields are `has_field`-guarded anyway).
"""

import re

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as assign_todo

from crm.api.buyers import INTEREST_STAGES, _guard, _has_market_fields, _metros_json
from crm.api.investorlift_ingest import BUYER_DOCTYPE, LEAD_BUYER_DOCTYPE, _last10

LEAD = "CRM Lead"

# Which leads can receive buyers. A deal is only worth marketing once it's
# actually ours, so the picker is "Signed Contract" onwards. Confirmed with
# Lance (2026-07-27): "Contract Sent" (not signed yet) and "Won" (already
# closed) are deliberately out.
PROPERTY_STATUSES = (
	"Signed Contract",
	"Photos & Lockbox In Progress",
	"Needs Listing",
	"Marketing to Buyer",
	"Buyer Assigned",
)

MAX_ROWS_PER_CALL = 500

# fieldname -> label: the only columns an import may write. CRM Buyer's other
# fields (il_buyer_id, quo_contact_id, quo_synced_at, verified, last_active,
# deal_history) are owned by the InvestorLift scraper and the Quo sync — a
# spreadsheet must never be able to set them.
IMPORT_FIELDS = (
	("first_name", "First name"),
	("last_name", "Last name"),
	("buyer_name", "Full name"),
	("phone", "Phone"),
	("email", "Email"),
	("buyer_type", "Buyer type"),
	("buybox", "Buybox"),
	("quo_tags", "Quo tags"),
	("metro", "Metro area"),
)

# filled in on a matched buyer only when our copy is blank
FILLABLE = ("first_name", "last_name", "phone", "email", "buyer_type", "buybox", "quo_tags")
IDENTITY = {"buyer_name", "first_name", "last_name", "phone", "email"}


# ---------------------------------------------------------------- helpers


def _clean(value) -> str:
	"""Spreadsheet cells arrive with float noise ('60085.0' for a ZIP) because
	xlsx stores every number as a double. Trim that back to an integer string,
	otherwise leave the text alone."""
	s = str(value if value is not None else "").strip()
	if re.fullmatch(r"-?\d+\.0+", s):
		s = s.split(".")[0]
	return s


def _valid_email(value: str) -> bool:
	"""Buyer lists routinely put junk in the Email column (alt phone numbers,
	"n/a", several addresses semicolon-separated). An unusable address is
	dropped rather than failing the whole row over a field we don't need."""
	return bool(re.fullmatch(r"[^@\s;,]+@[^@\s;,]+\.[A-Za-z]{2,}", (value or "").strip()))


def _split_name(full: str):
	parts = [p for p in (full or "").split() if p]
	if not parts:
		return "", ""
	return parts[0], " ".join(parts[1:])


def _has_field(field: str) -> bool:
	return frappe.get_meta(BUYER_DOCTYPE).has_field(field)


# ------------------------------------------------------------ properties


@frappe.whitelist()
def get_import_properties():
	"""The property picker: leads under contract / in dispo, newest first.

	Shared by the bulk importer and the single "New buyer" modal, so both
	offer exactly the same set."""
	_guard()
	has_buyers = frappe.db.exists("DocType", LEAD_BUYER_DOCTYPE)
	leads = frappe.get_all(
		LEAD,
		filters={"status": ("in", PROPERTY_STATUSES)},
		fields=["name", "lead_name", "property_address", "property_city", "property_state", "status", "modified"],
		order_by="modified desc",
		limit_page_length=0,
	)
	out = []
	for l in leads:
		label = l.property_address or l.lead_name or l.name
		if l.property_address and l.property_city:
			# manually-entered leads are street-only; webhook leads carry the
			# whole string already (same rule as _full_property_address)
			if l.property_city.lower() not in label.lower():
				label = f"{label}, {l.property_city}"
				if l.property_state:
					label = f"{label} {l.property_state}"
		out.append({
			"lead": l.name,
			"label": label,
			"status": l.status,
			"buyer_count": frappe.db.count(LEAD_BUYER_DOCTYPE, {"lead": l.name}) if has_buyers else 0,
		})
	return out


# ---------------------------------------------------------------- import


def _build_index():
	"""One pass over the (small) buyer table -> email / phone / name indexes.

	`_find_buyer` re-queries per lookup, which is fine for a webhook but means
	a query per row here; a 500-row import would scan the whole table 500
	times. Same identity rules, built once, updated as we insert."""
	by_email, by_phone, by_name = {}, {}, {}
	for b in frappe.get_all(
		BUYER_DOCTYPE, fields=["name", "buyer_name", "phone", "email"], limit_page_length=0
	):
		if b.email:
			by_email.setdefault(b.email.strip().lower(), b.name)
		last10 = _last10(b.phone)
		if last10:
			by_phone.setdefault(last10, b.name)
		# name is the last-resort key only for contact-less rows (see _find_buyer)
		if b.buyer_name and not b.email and not b.phone:
			by_name.setdefault(b.buyer_name.strip().lower(), b.name)
	return by_email, by_phone, by_name


def _fill_gaps(buyer: str, fields: dict):
	"""Fill only what's blank on an existing buyer; never overwrite."""
	current = frappe.db.get_value(BUYER_DOCTYPE, buyer, list(FILLABLE), as_dict=True) or {}
	update = {
		k: v
		for k, v in fields.items()
		if k in FILLABLE and v and not (current.get(k) or "").strip()
	}
	if not update:
		return
	# db.set_value, not doc.save: an import must not fire doc events or bump
	# `modified` and reshuffle every "recently active" buyer list.
	frappe.db.set_value(BUYER_DOCTYPE, buyer, update, update_modified=False)
	if IDENTITY & set(update):
		from crm.api.quo_contacts import enqueue_push

		enqueue_push(buyer)


def _attach(lead: str, buyer: str, stage: str) -> bool:
	"""Put the buyer on the property's board. True when newly attached."""
	if frappe.db.get_value(LEAD_BUYER_DOCTYPE, {"lead": lead, "buyer": buyer}, "name"):
		return False
	frappe.get_doc({
		"doctype": LEAD_BUYER_DOCTYPE,
		"lead": lead,
		"buyer": buyer,
		"interest_stage": stage,
	}).insert(ignore_permissions=True)
	return True


def _assign(buyer: str, user: str) -> bool:
	"""Assign an UNOWNED buyer. True when the assignment was made.

	An import never steals a buyer someone is already working, and the caller
	only advances the round-robin on a True, so the reps who do receive buyers
	still get an even split."""
	current = frappe.parse_json(frappe.db.get_value(BUYER_DOCTYPE, buyer, "_assign") or "[]")
	if current:
		return False
	try:
		assign_todo(
			{"assign_to": [user], "doctype": BUYER_DOCTYPE, "name": buyer},
			ignore_permissions=True,
		)
		return True
	except Exception:
		frappe.log_error(f"buyer_import assign {buyer} -> {user}", frappe.get_traceback())
		return False


@frappe.whitelist()
def import_buyers(rows, lead=None, stage="New", assign_to=None, assign_offset=0):
	"""Create/attach/assign a batch of buyers.

	rows: list of dicts already keyed by the IMPORT_FIELDS names (the frontend
	does the CSV parse + column mapping so the user can eyeball it first).

	lead: optional CRM Lead (a property) every buyer in the batch joins.
	stage: the CRM Lead Buyer interest_stage they land on.
	assign_to / assign_offset: round-robin owners; the offset carries the
	rotation across chunked calls so a 500-row import doesn't restart at the
	first rep every chunk and hand them everything.
	"""
	_guard()

	rows = frappe.parse_json(rows) or []
	if not isinstance(rows, list):
		frappe.throw(_("Invalid rows payload."))
	if len(rows) > MAX_ROWS_PER_CALL:
		frappe.throw(_("Too many rows in one call (max {0}).").format(MAX_ROWS_PER_CALL))

	lead = (lead or "").strip() or None
	if lead and not frappe.db.exists(LEAD, lead):
		frappe.throw(_("Property not found"), frappe.DoesNotExistError)
	if stage not in INTEREST_STAGES:
		stage = "New"

	assignees = [u for u in (frappe.parse_json(assign_to) if assign_to else []) if frappe.db.exists("User", u)]
	assign_i = int(assign_offset or 0)

	has_market = _has_market_fields()
	has_tags = _has_field("quo_tags")

	# metro names are matched, never created: a typo in a spreadsheet column
	# must not add a bogus metro to the Census list everyone else picks from
	metro_by_name = {}
	if has_market and frappe.db.exists("DocType", "CRM Metro Area"):
		for m in frappe.get_all("CRM Metro Area", fields=["name", "metro_name"], limit_page_length=0):
			metro_by_name[(m.metro_name or m.name).strip().lower()] = m.name

	by_email, by_phone, by_name = _build_index()

	created, matched, attached, assigned_counts = [], [], 0, {u: 0 for u in assignees}
	skipped, errors, unmatched_metros, seen = 0, [], set(), set()

	for idx, raw_row in enumerate(rows):
		if not isinstance(raw_row, dict):
			skipped += 1
			continue

		row = {}
		for key, value in raw_row.items():
			v = _clean(value)
			if v:
				row[key] = v

		email = (row.get("email") or "").strip().lower()
		if email and not _valid_email(email):
			email = ""
		phone = (row.get("phone") or "").strip()
		phone_k = _last10(phone)
		if len(phone_k) < 10:
			phone_k = ""

		first = row.get("first_name") or ""
		last = row.get("last_name") or ""
		full = row.get("buyer_name") or ""
		if not first and not last and full:
			first, last = _split_name(full)
		full = full or f"{first} {last}".strip()
		if not full:
			# a nameless row is still a buyer if we can reach them
			full = email or phone or ""

		# no name and no way to reach anyone isn't a buyer
		if not full and not email and not phone_k:
			skipped += 1
			continue

		dedupe_k = email or phone_k or full.lower()
		if dedupe_k in seen:
			skipped += 1
			continue
		seen.add(dedupe_k)

		fields = {
			"buyer_name": full,
			"first_name": first or None,
			"last_name": last or None,
			"phone": phone or None,
			"email": email or None,
			"buyer_type": row.get("buyer_type") or None,
		}
		if has_market:
			fields["buybox"] = row.get("buybox") or None
			metro = (row.get("metro") or "").strip()
			if metro:
				match = metro_by_name.get(metro.lower())
				if match:
					fields["metro_areas"] = _metros_json([match])
				else:
					unmatched_metros.add(metro)
		if has_tags:
			fields["quo_tags"] = row.get("quo_tags") or None

		try:
			existing = (
				(by_email.get(email) if email else None)
				or (by_phone.get(phone_k) if phone_k else None)
				or (by_name.get(full.lower()) if full else None)
			)

			if existing:
				buyer = existing
				_fill_gaps(buyer, fields)
				matched.append(buyer)
			else:
				doc = frappe.get_doc({
					"doctype": BUYER_DOCTYPE,
					**{k: v for k, v in fields.items() if v is not None},
				})
				doc.insert(ignore_permissions=True)
				buyer = doc.name
				created.append(buyer)
				if email:
					by_email.setdefault(email, buyer)
				if phone_k:
					by_phone.setdefault(phone_k, buyer)
				if full and not email and not phone_k:
					by_name.setdefault(full.lower(), buyer)

			if lead and _attach(lead, buyer, stage):
				attached += 1

			if assignees:
				turn_user = assignees[assign_i % len(assignees)]
				if _assign(buyer, turn_user):
					assign_i += 1
					assigned_counts[turn_user] = assigned_counts.get(turn_user, 0) + 1
		except Exception as e:
			errors.append({"row": idx + 1, "error": str(e)[:200]})
			frappe.log_error(f"buyer_import row {idx + 1}", frappe.get_traceback())

	if lead and attached:
		# one emit for the batch, not one per buyer — the Dispo board just
		# refetches, and 200 emits would hammer every open board on the site
		frappe.publish_realtime(
			"crm_il_buyers",
			{"reference_doctype": LEAD, "reference_docname": lead},
			after_commit=True,
		)
	frappe.db.commit()

	return {
		"created": len(created),
		"matched": len(matched),
		"attached": attached,
		"skipped": skipped,
		"assigned": assigned_counts,
		"assign_offset": assign_i,
		"unmatched_metros": sorted(unmatched_metros)[:10],
		"errors": errors[:20],
		"error_count": len(errors),
	}


@frappe.whitelist()
def assign_buyers(buyers, users, assign_offset=0):
	"""Round-robin an explicit set of buyers between users.

	Used by the single "New buyer" modal (one buyer, one user) and available
	for re-dealing a list later."""
	_guard()
	buyers = frappe.parse_json(buyers) or []
	users = [u for u in (frappe.parse_json(users) or []) if frappe.db.exists("User", u)]
	if not buyers or not users:
		return {"assigned": {}, "assign_offset": int(assign_offset or 0)}

	i = int(assign_offset or 0)
	counts = {u: 0 for u in users}
	for b in buyers:
		if not frappe.db.exists(BUYER_DOCTYPE, b):
			continue
		user = users[i % len(users)]
		if _assign(b, user):
			i += 1
			counts[user] += 1
	frappe.db.commit()
	return {"assigned": counts, "assign_offset": i}
