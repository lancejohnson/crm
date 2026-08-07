# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Subject-property facts from Zillow, for the comps map.

Why this exists
---------------
The comps map compares a lead against nearby sales, but until now it could barely
describe the lead itself. The two sources it had are both weak:

  * the lead's own iSpeedToLead fields are pick-list LABELS, not numbers
    ("3 Bedroom", "1000 - 2000", "1900-1950"), so a "similar" filter built from
    them is a wide guess;
  * the property's own row in our comp inventory carries real numbers, but only
    ~5% of leads have one, and its price is the last ASK, not a sale.

Zillow answers both. `/property?address=` resolves our ordinary address strings
and returns real beds / baths / living area / year built / type / coordinates,
plus `priceHistory` — which contains genuine `event: "Sold"` rows sourced from
Public Record. That is an actual transaction with a date, which is what a rep
means by "what did it last sell for".

Cost and caching
----------------
This is a metered RapidAPI plan (57,000 requests/month). One lookup per lead is
plenty, so the normalized result is cached on the lead and only refetched past
CACHE_DAYS or when explicitly forced. Everything is `has_field`-guarded, so the
app is safe to deploy before the ops script adds the cache fields — it just
refetches each time until they exist.

Every failure path is soft. A Zillow outage, a quota exhaustion or an address
Zillow cannot resolve must degrade the popup back to the older sources, never
break the comps map.
"""

import json

import frappe
from frappe import _

HOST = "us-property-market1.p.rapidapi.com"
BASE = f"https://{HOST}"

#: Property facts barely move; a sale a week old is still news next month.
CACHE_DAYS = 30
TIMEOUT = 20

#: Zillow's enum -> the vocabulary our comp inventory uses, so the subject's type
#: can be fed straight into the comps "Type" filter and actually match.
#: (Measured comp values: Single Family, Townhouse, Condo, Multi-Family,
#: Manufactured, Land, Apartment.)
HOME_TYPES = {
	"SINGLE_FAMILY": "Single Family",
	"TOWNHOUSE": "Townhouse",
	"CONDO": "Condo",
	"CONDOMINIUM": "Condo",
	"MULTI_FAMILY": "Multi-Family",
	"MANUFACTURED": "Manufactured",
	"MOBILE": "Manufactured",
	"LOT": "Land",
	"LAND": "Land",
	"VACANT_LAND": "Land",
	"APARTMENT": "Apartment",
}

CACHE_FIELDS = ("zillow_facts", "zillow_fetched_at", "zillow_zpid")


def _num(v):
	"""Zillow uses null for unknown; it also hands back strings like '1,438 sqft'."""
	if v is None or v == "":
		return None
	if isinstance(v, (int, float)):
		return float(v)
	try:
		import re

		m = re.search(r"-?[\d,]+(?:\.\d+)?", str(v))
		return float(m.group().replace(",", "")) if m else None
	except Exception:
		return None


def _has_cache() -> bool:
	return all(frappe.db.has_column("CRM Lead", f) for f in CACHE_FIELDS)


def _api_key():
	return frappe.conf.get("rapidapi_zillow_key") or ""


def _fetch(address: str):
	"""One address -> Zillow's raw property blob, or None. Never raises."""
	import urllib.parse
	import urllib.request

	key = _api_key()
	if not key or not address:
		return None
	url = f"{BASE}/property?" + urllib.parse.urlencode({"address": address})
	req = urllib.request.Request(
		url, headers={"x-rapidapi-key": key, "x-rapidapi-host": HOST}
	)
	try:
		with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
			return json.loads(resp.read().decode("utf-8", "replace"))
	except Exception:
		# Quota exhaustion, an unresolvable address, an outage — all of them mean
		# "no Zillow facts today", never "break the comps map".
		frappe.log_error(frappe.get_traceback(), "Zillow: property lookup failed")
		return None


def _price_history(raw):
	"""Split priceHistory into the last real SALE and the last LISTING event.

	GOTCHA — the top-level `dateSold` / `lastSoldPrice` are null even on homes
	whose priceHistory plainly contains Sold rows (verified on prod addresses), so
	the history is the only reliable source. `event` is a display string, hence
	the lowercase compare rather than an equality test on a code.
	"""
	events = raw.get("priceHistory") or []
	sale = listing = None
	for e in events:  # newest first as returned
		if not isinstance(e, dict):
			continue
		kind = str(e.get("event") or "").strip().lower()
		price, date = _num(e.get("price")), e.get("date")
		if not date:
			continue
		if sale is None and kind == "sold":
			sale = {"price": price, "date": date, "source": e.get("source")}
		elif listing is None and "list" in kind:
			# "Listed for sale" / "Listing removed" both describe the ask.
			listing = {
				"price": price,
				"date": date,
				"event": e.get("event"),
				"source": e.get("source"),
			}
		if sale and listing:
			break
	return sale, listing


def _normalize(raw):
	"""Zillow's blob -> the small, flat shape the comps map actually consumes."""
	if not isinstance(raw, dict) or not raw.get("zpid"):
		return None
	reso = raw.get("resoFacts") or {}
	sale, listing = _price_history(raw)

	home_type = str(raw.get("homeType") or "").strip().upper()
	# GOTCHA — on an off-market home `price` mirrors taxAssessedValue rather than
	# any list price (verified: Macon price 6005 == taxAssessedValue 6005). It is
	# deliberately NOT surfaced as a price.
	return {
		"zpid": raw.get("zpid"),
		"beds": _num(raw.get("bedrooms")),
		"baths": _num(raw.get("bathrooms")),
		"sqft": _num(raw.get("livingArea") or raw.get("livingAreaValue")),
		"year_built": _num(raw.get("yearBuilt")),
		"property_type": HOME_TYPES.get(home_type) or (home_type.title().replace("_", " ") or None),
		"lot_size": reso.get("lotSize") or None,
		"lat": _num(raw.get("latitude")),
		"lng": _num(raw.get("longitude")),
		"zestimate": _num(raw.get("zestimate")),
		"rent_zestimate": _num(raw.get("rentZestimate")),
		"tax_assessed_value": _num(reso.get("taxAssessedValue") or raw.get("taxAssessedValue")),
		"last_sale": sale,
		"last_listing": listing,
		"home_status": raw.get("homeStatus"),
		"address": raw.get("streetAddress"),
	}


def _cached(doc):
	if not _has_cache() or not doc.get("zillow_facts"):
		return None
	fetched = doc.get("zillow_fetched_at")
	if fetched:
		try:
			if frappe.utils.date_diff(frappe.utils.nowdate(), str(fetched)[:10]) > CACHE_DAYS:
				return None
		except Exception:
			pass
	try:
		return json.loads(doc.get("zillow_facts"))
	except Exception:
		return None


def _store(doc, facts):
	if not _has_cache():
		return
	try:
		frappe.db.set_value(
			"CRM Lead", doc.name,
			{
				"zillow_facts": json.dumps(facts) if facts else "",
				"zillow_fetched_at": frappe.utils.now(),
				"zillow_zpid": str((facts or {}).get("zpid") or ""),
			},
			# A cached lookup is not a human edit; same rule as the geocode cache.
			update_modified=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Zillow: caching facts failed")


def facts_for_lead(doc, force=False):
	"""Normalized Zillow facts for a lead, cached. Returns None when unavailable.

	`doc` is a CRM Lead document. Safe to call on every comps-map open: past the
	first fetch this is a JSON parse off a column.
	"""
	if not force:
		hit = _cached(doc)
		if hit is not None:
			return hit
	if not _api_key():
		return None

	from crm.api.comps import _full_address

	raw = _fetch(_full_address(doc))
	facts = _normalize(raw) if raw else None
	# Cache negatives too, so an address Zillow cannot resolve is not re-fetched
	# (and re-billed) on every single modal open.
	_store(doc, facts or {})
	return facts


@frappe.whitelist()
def refresh_lead_facts(lead):
	"""Force a re-fetch for one lead (whitelisted so a button can offer it)."""
	from crm.api.comps import _guard

	_guard()
	doc = frappe.get_doc("CRM Lead", lead)
	facts = facts_for_lead(doc, force=True)
	return {"ok": bool(facts), "facts": facts}
