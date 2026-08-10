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

Cost, and the SHARED key
------------------------
OUR spend here is small: one lookup per lead, cached 30 days, so ~764 leads is a
few hundred requests a month even if every lead is opened.

The plan itself is a RapidAPI "Ultra" tier, 57,000 requests per billing cycle,
renewing on the 14th (anniversary-billed, not the 1st). That ceiling is NOT our
budget though — **the key is shared**. `istl-buyer/src/zillow_api.py` runs a
background ZIP-market job against the identical key (Infisical exposes it twice,
as `RAPIDAPI_ZILLOW_API_KEY` and `ZILLOW_RAPIDAPI_KEY` — verified byte-identical),
and it is the heavy consumer: 8,414 of 57,000 were already spent the day this
shipped, ~350/day, against ~10 from the CRM.

That job stops at `QUOTA_RESERVE = 5_000` remaining, commented "leave headroom
for the other Zillow-backed app that shares this RapidAPI key" — that app is now
us. So the CRM may use the band istl-buyer deliberately refuses to touch, but it
keeps its own smaller floor so a runaway loop here can never zero the account for
both apps.

One lookup per lead is plenty, so the normalized result is cached on the lead and
only refetched past CACHE_DAYS or when explicitly forced. Everything is
`has_field`-guarded, so the app is safe to deploy before the ops script adds the
cache fields — it just refetches each time until they exist.

Every failure path is soft. A Zillow outage, a quota exhaustion or an address
Zillow cannot resolve must degrade the popup back to the older sources, never
break the comps map.
"""

import json
import time

import frappe
from frappe import _

HOST = "us-property-market1.p.rapidapi.com"
BASE = f"https://{HOST}"

#: Property facts barely move; a sale a week old is still news next month.
CACHE_DAYS = 30
TIMEOUT = 20

#: Stop fetching once the SHARED plan is this close to empty. Deliberately far
#: below istl-buyer's 5,000 reserve: that reserve exists to leave room for THIS
#: app, so matching it would strand 5,000 requests neither app is willing to
#: spend. Below this floor the comps map degrades to its older fact sources
#: rather than taking the last of a budget the ZIP-market job may still need.
QUOTA_RESERVE = 500
#: RapidAPI reports remaining quota on every response, so caching it briefly
#: makes the guard free — and it reflects the OTHER app's spending too.
#:
#: GOTCHA — this is stored WITHOUT `expires_in_sec`, and freshness is judged from
#: a timestamp we store alongside it. `frappe.cache().get_value()` memoizes a MISS
#: as None into the per-request `frappe.local.cache`, while
#: `set_value(..., expires_in_sec=...)` writes only to Redis — so the poisoned
#: local None then shadows the value that is demonstrably sitting in Redis, and
#: the guard silently never fires. (`get_value(..., expires=True)` does NOT help;
#: it checks the local dict first regardless.) Storing with no TTL populates the
#: local cache too, which overwrites the poisoned entry.
_QUOTA_KEY = "zillow_quota_remaining"
_QUOTA_TTL = 900

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


def quota_remaining():
	"""Last known remaining requests on the SHARED plan, or None if unknown.

	Taken from the response headers of our most recent call, so it also reflects
	whatever istl-buyer's ZIP job has spent since — which is the point.
	"""
	try:
		rec = frappe.cache().get_value(_QUOTA_KEY)
		if not isinstance(rec, dict):
			return None
		# Expiry enforced here rather than by Redis — see the GOTCHA on _QUOTA_KEY.
		if time.time() - float(rec.get("t") or 0) > _QUOTA_TTL:
			return None
		return int(rec["n"])
	except Exception:
		return None


def _remember_quota(headers):
	try:
		raw = headers.get("X-RateLimit-Requests-Remaining")
		if raw is not None:
			frappe.cache().set_value(_QUOTA_KEY, {"n": int(raw), "t": time.time()})
	except Exception:
		pass


def _request(path: str, params: dict, error_title: str):
	"""One guarded RapidAPI GET, or None. Every caller degrades softly."""
	import urllib.parse
	import urllib.request

	key = _api_key()
	if not key or not params:
		return None

	# Yield the last of a shared budget rather than spend it: both subject facts and
	# an on-demand comp gallery are optional, whereas istl-buyer's batch job cannot
	# degrade at all. This check runs before EACH request, so a property lookup that
	# lands on the reserve does not spend one more request fetching its photos.
	left = quota_remaining()
	if left is not None and left <= QUOTA_RESERVE:
		frappe.log_error(
			f"Zillow quota reserve reached ({left} left <= {QUOTA_RESERVE}); skipping "
			f"{path}. Key is shared with istl-buyer's ZIP-market job.",
			"Zillow: quota reserve",
		)
		return None

	url = f"{BASE}{path}?" + urllib.parse.urlencode(params)
	req = urllib.request.Request(
		url, headers={"x-rapidapi-key": key, "x-rapidapi-host": HOST}
	)
	try:
		with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
			body = json.loads(resp.read().decode("utf-8", "replace"))
			_remember_quota(resp.headers)
			return body
	except Exception:
		frappe.log_error(frappe.get_traceback(), error_title)
		return None


def _fetch(address: str):
	"""One address -> Zillow's raw property blob, or None. Never raises."""
	if not address:
		return None
	return _request("/property", {"address": address}, "Zillow: property lookup failed")


def property_details(address: str):
	"""Raw details for an explicitly opened comp. Kept separate from lead caching."""
	return _fetch(address)


def property_photos(zpid):
	"""Raw `/photos` response for a Zillow property id, or None on any failure."""
	if not zpid:
		return None
	body = _request("/photos", {"zpid": zpid}, "Zillow: photo lookup failed")
	# RapidAPI can report endpoint errors inside an HTTP-200 JSON body. Treat only
	# the documented list shape as success; `{status:'error', errors:[…]}` must get
	# the short retry cache rather than hiding photos for 30 days.
	return body if isinstance(body, dict) and isinstance(body.get("photos"), list) else None


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


def normalize_detail(raw):
	"""Zillow's large property blob -> the useful facts in a comp detail panel."""
	if not isinstance(raw, dict) or not raw.get("zpid"):
		return None
	reso = raw.get("resoFacts") or {}
	sale, listing = _price_history(raw)
	home_type = str(raw.get("homeType") or "").strip().upper()
	status = str(raw.get("homeStatus") or "").strip().upper()
	# Zillow's top-level `price` is an assessed value on many off-market homes.
	# Only call it an asking price while the property is actually marketed.
	asking_statuses = {"FOR_SALE", "FOR_RENT", "PENDING", "CONTINGENT", "COMING_SOON"}
	url = raw.get("url") or ""
	if url.startswith("/"):
		url = "https://www.zillow.com" + url
	address = raw.get("address") if isinstance(raw.get("address"), dict) else {}

	def text_list(value):
		if isinstance(value, list):
			return ", ".join(str(v) for v in value if v)
		return str(value or "")

	return {
		"zpid": raw.get("zpid"),
		"address": raw.get("streetAddress") or address.get("streetAddress"),
		"city": raw.get("city") or address.get("city"),
		"state": raw.get("state") or address.get("state"),
		"zip": raw.get("zipcode") or address.get("zipcode"),
		"beds": _num(raw.get("bedrooms")),
		"baths": _num(raw.get("bathrooms")),
		"sqft": _num(raw.get("livingArea") or raw.get("livingAreaValue")),
		"year_built": _num(raw.get("yearBuilt")),
		"property_type": HOME_TYPES.get(home_type) or (home_type.title().replace("_", " ") or None),
		"lot_size": reso.get("lotSize") or None,
		"home_status": raw.get("homeStatus"),
		"asking_price": _num(raw.get("price")) if status in asking_statuses else None,
		"zestimate": _num(raw.get("zestimate")),
		"rent_zestimate": _num(raw.get("rentZestimate")),
		"hoa_fee": _num(raw.get("monthlyHoaFee") or reso.get("hoaFee")),
		"parking": text_list(reso.get("parkingFeatures")),
		"heating": text_list(reso.get("heating")),
		"cooling": text_list(reso.get("cooling")),
		"description": raw.get("description") or "",
		"last_sale": sale,
		"last_listing": listing,
		"zillow_url": url,
		"cover_photo": raw.get("imgSrc") or "",
		"photo_count": int(_num(raw.get("photoCount")) or 0),
	}


def photo_urls(raw, limit=60):
	"""Choose one useful Zillow CDN URL per photo, preferring ~1152px JPEGs."""
	if not isinstance(raw, dict):
		return []
	out = []
	for photo in raw.get("photos") or []:
		sources = (photo or {}).get("mixedSources") or {}
		options = sources.get("jpeg") or sources.get("webp") or []
		options = [o for o in options if isinstance(o, dict) and o.get("url")]
		if not options:
			continue
		# Big enough to inspect without pulling the largest 1536px image into a
		# modal. If all variants are smaller/larger, take the nearest useful one.
		under = [o for o in options if float(o.get("width") or 0) <= 1152]
		chosen = max(under or options, key=lambda o: float(o.get("width") or 0))
		if chosen["url"] not in out:
			out.append(chosen["url"])
		if len(out) >= int(limit):
			break
	return out


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
