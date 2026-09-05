# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Reserve the owner of a lead BEFORE the vendor's webhook creates it.

Why this exists
---------------
LeadMarket is where a lead is chosen and bought, but the CRM Lead is created by
the vendor's own webhook (iSpeedToLead hits `ispeed-to-lead` the instant the
charge clears), ownerless, and the rotation in `lead_round_robin` stamps a
setter. So "Dennis, this one is yours" cannot be said at insert time by the
system that knows it — unless it says it *in advance*, here.

A reservation is "the next iSpeedToLead lead published at <ms> (ZIP <z>) belongs
to <user>". The desk writes one at Buy-click via `reserve()`; the
`before_insert` hook (`lead_round_robin.assign_round_robin_owner`) consults
`reserved_owner_for(doc)` before it rotates. The lead is therefore BORN with the
right owner: no post-hoc reassignment, no double `_assign`, no sequence
auto-enroll under the wrong person, and no dependency on LeadMarket being up at
the moment the webhook lands — an absent reservation just means the rotation
decides, exactly as today.

The match key
-------------
Pre-purchase, the marketplace feed exposes no street address or phone — only
city / ZIP and the lead's `published_date` (epoch ms). The webhook payload
carries the same instant as `lead_published_date` (ISO), verified identical to
the millisecond on production (order 6a99ab5f…, 2026-09-04). The ops webhook
script copies it onto `CRM Lead.vendor_published_date`; that plus `source` (and
ZIP when both sides have one) is the key. Both sides normalise to epoch-ms
strings so ISO-vs-epoch formatting can never make a real match miss.

Races, and why none of them lose a lead
---------------------------------------
* Reservation lands AFTER the webhook (slow call, checkout tab already open):
  `reserve()` also looks for a matching lead already created inside the TTL and
  moves it with `lead_owner_backfill._reassign` — the one reassign path in this
  codebase that also drops the previous automatic assignment. Early or late,
  the reservation wins; LeadMarket never touches `lead_owner` itself.
* Two people click Buy with different picks: upsert per marketplace lead id,
  last click wins, and `status()` shows who reserved it for whom.
* Vendor retries the webhook: a reservation is NOT consumed on first match — it
  stays live for its TTL, so a duplicate insert lands on the same person
  instead of falling into the rotation.

Everything here is has-doctype / has-column guarded so the app deploys before
the ops script (`scripts/setup_lead_owner_reservation.py`) and does nothing
until it has run. Nothing in the insert path may raise: a misrouted lead beats
a lost lead, so the hook-facing functions swallow and log.
"""

import datetime
import re

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

LEAD = "CRM Lead"
DOCTYPE = "CRM Lead Owner Reservation"
PUBLISHED_FIELD = "vendor_published_date"

#: How long a reservation waits for its purchase. Buy-click to Stripe receipt is
#: seconds; a day covers "opened checkout, came back after lunch".
DEFAULT_TTL_HOURS = 24
#: Unmatched reservations older than this are pruned on the next reserve().
PRUNE_AFTER_DAYS = 14

ROLES = ("System Manager", "Sales Manager", "Sales User")


# ---------------------------------------------------------------------------
# Availability + key normalisation
# ---------------------------------------------------------------------------


def available() -> bool:
	"""True once the ops script has created the doctype and the lead column."""
	return bool(frappe.db.exists("DocType", DOCTYPE)) and frappe.db.has_column(
		LEAD, PUBLISHED_FIELD
	)


def published_ms(value) -> str | None:
	"""Epoch milliseconds as a string, from any of the shapes the two systems use:
	epoch ms (int / numeric string), ISO 8601 with Z or offset, or a datetime.
	None when there is nothing usable. String on purpose — it's a match key, not
	a number, and a Data column compares it exactly."""
	if value is None or value == "":
		return None
	if isinstance(value, datetime.datetime):
		if value.tzinfo is None:
			value = value.replace(tzinfo=datetime.timezone.utc)
		return str(int(value.timestamp() * 1000))
	s = str(value).strip()
	if re.fullmatch(r"\d{10,13}", s):
		n = int(s)
		return str(n if len(s) == 13 else n * 1000)
	try:
		dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
	except ValueError:
		return None
	if dt.tzinfo is None:
		dt = dt.replace(tzinfo=datetime.timezone.utc)
	return str(int(dt.timestamp() * 1000))


def _zip5(value) -> str | None:
	digits = re.sub(r"\D", "", str(value or ""))
	return digits[:5] if len(digits) >= 5 else None


def _enabled_user(user: str | None) -> str | None:
	user = (user or "").strip()
	if user and frappe.db.get_value("User", user, "enabled"):
		return user
	return None


# ---------------------------------------------------------------------------
# The hook side: who does this incoming lead belong to?
# ---------------------------------------------------------------------------


def find_live(source: str | None, published, zip_code=None) -> dict | None:
	"""The newest unexpired reservation for this (source, published-ms) — and
	ZIP, when both sides carry one. None if nothing matches."""
	ms = published_ms(published)
	if not (source and ms):
		return None
	rows = frappe.get_all(
		DOCTYPE,
		filters={
			"source": source,
			"published_ms": ms,
			"expires_on": [">", now_datetime()],
		},
		fields=["name", "lead_owner", "property_zip", "marketplace_lead_id", "requested_by"],
		order_by="modified desc",
		limit=5,
	)
	z = _zip5(zip_code)
	for row in rows:
		rz = _zip5(row.get("property_zip"))
		if z and rz and z != rz:
			continue
		return row
	return None


def reserved_owner_for(doc) -> str | None:
	"""Called by the before_insert hook. Never raises."""
	try:
		if not available():
			return None
		row = find_live(doc.get("source"), doc.get(PUBLISHED_FIELD), doc.get("property_zip"))
		if not row:
			return None
		owner = _enabled_user(row.get("lead_owner"))
		if not owner:
			return None
		doc.flags.lead_reservation = row["name"]
		return owner
	except Exception:
		frappe.log_error("Lead owner reservation lookup failed", frappe.get_traceback())
		return None


def stamp_matched_lead(doc, method=None):
	"""`CRM Lead` after_insert: record which lead a reservation produced, so the
	desk can confirm the purchase landed where it was pointed. Never raises."""
	try:
		name = getattr(doc.flags, "lead_reservation", None)
		if not name:
			return
		frappe.db.set_value(
			DOCTYPE,
			name,
			{"matched_lead": doc.name, "matched_on": now_datetime(), "previous_owner": None},
			update_modified=False,
		)
	except Exception:
		frappe.log_error("Lead owner reservation stamp failed", frappe.get_traceback())


# ---------------------------------------------------------------------------
# The desk side: reserve / release / status
# ---------------------------------------------------------------------------


def _late_match(res: dict) -> dict | None:
	"""A lead that already arrived for this reservation — the webhook beat the
	reserve call. Move it to the reserved owner and stamp the match. Returns
	{lead, previous_owner} or None."""
	since = add_to_date(now_datetime(), hours=-int(res["ttl_hours"]))
	filters = {
		"source": res["source"],
		PUBLISHED_FIELD: ["is", "set"],
		"creation": [">=", since],
	}
	candidates = frappe.get_all(
		LEAD,
		filters=filters,
		fields=["name", "lead_owner", PUBLISHED_FIELD, "property_zip"],
		order_by="creation desc",
		limit=50,
	)
	z = _zip5(res.get("property_zip"))
	for lead in candidates:
		if published_ms(lead.get(PUBLISHED_FIELD)) != res["published_ms"]:
			continue
		lz = _zip5(lead.get("property_zip"))
		if z and lz and z != lz:
			continue
		previous = lead.get("lead_owner")
		if previous != res["lead_owner"]:
			from crm.api.lead_owner_backfill import _reassign

			_reassign(lead["name"], previous, res["lead_owner"])
		frappe.db.set_value(
			DOCTYPE,
			res["name"],
			{
				"matched_lead": lead["name"],
				"matched_on": now_datetime(),
				"previous_owner": previous if previous != res["lead_owner"] else None,
			},
			update_modified=False,
		)
		return {"lead": lead["name"], "previous_owner": previous}
	return None


def _prune():
	"""Old, never-matched reservations are noise; matched ones are the audit
	trail and stay."""
	cutoff = add_to_date(now_datetime(), days=-PRUNE_AFTER_DAYS)
	for name in frappe.get_all(
		DOCTYPE,
		filters={"matched_lead": ["is", "not set"], "expires_on": ["<", cutoff]},
		pluck="name",
		limit=200,
	):
		frappe.delete_doc(DOCTYPE, name, ignore_permissions=True, force=True)


def _row(name: str) -> dict:
	d = frappe.db.get_value(
		DOCTYPE,
		name,
		[
			"name", "source", "lead_owner", "marketplace_lead_id", "published_ms",
			"property_zip", "requested_by", "expires_on", "matched_lead", "matched_on",
			"previous_owner", "modified",
		],
		as_dict=True,
	)
	if d and d.get("matched_lead"):
		d["matched_owner"] = frappe.db.get_value(LEAD, d["matched_lead"], "lead_owner")
	return d


@frappe.whitelist()
def reserve(
	source,
	lead_owner,
	marketplace_lead_id,
	published_date,
	zip=None,
	requested_by=None,
	ttl_hours=DEFAULT_TTL_HOURS,
):
	"""Point the next lead matching (source, published_date[, zip]) at `lead_owner`.

	Upserts on `marketplace_lead_id`, so a second click for the same lead simply
	replaces the first. If the lead already arrived (webhook won the race) it is
	moved right now. Returns the reservation row, with `matched_lead` set when a
	lead exists for it.
	"""
	frappe.only_for(ROLES)
	if not available():
		frappe.throw(_("Lead owner reservations are not set up on this site."))

	source = (source or "").strip()
	if not source:
		frappe.throw(_("source is required"))
	owner = _enabled_user(lead_owner)
	if not owner:
		frappe.throw(_("{0} is not an enabled CRM user").format(lead_owner))
	ms = published_ms(published_date)
	if not ms:
		frappe.throw(_("published_date is required (epoch ms or ISO 8601)"))
	marketplace_lead_id = (marketplace_lead_id or "").strip()
	if not marketplace_lead_id:
		frappe.throw(_("marketplace_lead_id is required"))
	try:
		ttl = max(1, int(ttl_hours or DEFAULT_TTL_HOURS))
	except (TypeError, ValueError):
		ttl = DEFAULT_TTL_HOURS

	values = {
		"source": source,
		"lead_owner": owner,
		"marketplace_lead_id": marketplace_lead_id,
		"published_ms": ms,
		"property_zip": _zip5(zip),
		"requested_by": (requested_by or frappe.session.user or "")[:140],
		"expires_on": add_to_date(now_datetime(), hours=ttl),
	}
	name = frappe.db.get_value(DOCTYPE, {"marketplace_lead_id": marketplace_lead_id}, "name")
	if name:
		existing = frappe.db.get_value(DOCTYPE, name, ["matched_lead"], as_dict=True)
		if existing and existing.get("matched_lead"):
			# Already produced a lead: a new pick is a reassignment of THAT lead,
			# not a new reservation. Do it the same way a late match would.
			values["matched_lead"] = existing["matched_lead"]
			frappe.db.set_value(DOCTYPE, name, values, update_modified=True)
			current = frappe.db.get_value(LEAD, existing["matched_lead"], "lead_owner")
			if current != owner:
				from crm.api.lead_owner_backfill import _reassign

				_reassign(existing["matched_lead"], current, owner)
				frappe.db.set_value(
					DOCTYPE, name, "previous_owner", current, update_modified=False
				)
			return _row(name)
		frappe.db.set_value(DOCTYPE, name, values, update_modified=True)
	else:
		doc = frappe.get_doc({"doctype": DOCTYPE, **values})
		doc.insert(ignore_permissions=True)
		name = doc.name

	_late_match({**values, "name": name, "ttl_hours": ttl})
	try:
		_prune()
	except Exception:
		frappe.log_error("Lead owner reservation prune failed", frappe.get_traceback())
	return _row(name)


@frappe.whitelist()
def release(marketplace_lead_id):
	"""Withdraw a reservation so the rotation decides. A reservation that has
	already produced a lead is left alone — releasing it would not (and must
	not) un-own that lead."""
	frappe.only_for(ROLES)
	if not available():
		return {"released": False, "reason": "not set up"}
	name = frappe.db.get_value(
		DOCTYPE, {"marketplace_lead_id": (marketplace_lead_id or "").strip()}, "name"
	)
	if not name:
		return {"released": False, "reason": "none"}
	if frappe.db.get_value(DOCTYPE, name, "matched_lead"):
		return {"released": False, "reason": "already matched", **_row(name)}
	frappe.delete_doc(DOCTYPE, name, ignore_permissions=True, force=True)
	return {"released": True}


@frappe.whitelist()
def status(marketplace_lead_ids):
	"""Reservation rows for a batch of marketplace lead ids (JSON list or CSV),
	keyed by id. Read-only; what LeadMarket mirrors onto its cards."""
	frappe.only_for(ROLES)
	if not available():
		return {}
	ids = marketplace_lead_ids
	if isinstance(ids, str):
		ids = frappe.parse_json(ids) if ids.strip().startswith("[") else ids.split(",")
	ids = [str(i).strip() for i in (ids or []) if str(i).strip()]
	if not ids:
		return {}
	out = {}
	for name, mid in frappe.get_all(
		DOCTYPE,
		filters={"marketplace_lead_id": ["in", ids]},
		fields=["name", "marketplace_lead_id"],
		as_list=True,
	):
		out[mid] = _row(name)
	return out
