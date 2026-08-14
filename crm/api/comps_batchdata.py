"""BatchData fallback for leads with no comps in our own inventory.

`CRM Comp` only covers ZIPs iSpeedToLead has fed us. A lead outside them shows an
empty map -- Brooklyn 11230 has literally 0 rows -- so when `get_lead_comps`
finds nothing we buy a small set from BatchData instead.

COST, and why every constant here is what it is
-----------------------------------------------
BatchData bills PER ROW RETURNED, at the sum of the datasets enabled on the
calling token. There are two tokens and they are 21x apart:

    BATCHDATA_API_KEY        all 13 datasets   $0.640/row   <- NOT this one
    BATCHDATA_COMPS_API_KEY  Basic + Comps     $0.030/row   <- this one

So `take: 10` is $0.30 with the comps token and $6.40 with the other. This module
reads `batchdata_comps_key` from site_config and will not fall back to the
expensive key: a silent 21x is not a thing that should be possible.

There is NO /comparables endpoint. The comps mechanism is `property/search` with
a `compAddress` criterion, which returns "similar nearby" properties.

MEASURED, so nobody has to re-derive it
---------------------------------------
* `geoLocation`/`radiusMiles` is **silently ignored** -- it returns HTTP 200 and
  properties from other states. Do not use it. `compAddress` is the only thing
  that actually constrains geography.
* The response is **not** relevance-ordered. Median distance by position on a
  66-row sample: 0.84 / 0.80 / 0.78 / 0.79 / 0.77 mi -- flat. So `take: N` buys
  an arbitrary N, and the ranking below is what turns them into comps.
* Prices are on `sale.lastSale.price`, NOT `deedHistory` (which this token does
  not return at all). Reading deedHistory makes every comp look $0 and is the
  single easiest mistake here.

CACHING IS NOT OPTIONAL. This runs automatically, so without a cache a rep
refreshing the desk five times spends $1.50. If the cache fields are missing the
fallback DISABLES ITSELF rather than billing per page view.
"""

import json
import time

import frappe
import requests

SEARCH_URL = "https://api.batchdata.com/api/v1/property/search"

#: Rows to buy. 10 x $0.030 = $0.30/lead. Raising this is a real cost decision.
TAKE = 10

#: Hard ceiling. Lance: "definitely nothing over 2 mi". compAddress has no radius
#: control and has been observed matching out to ~3mi, so this is enforced here or
#: not at all -- and it DROPS rather than pads: four honest comps beat ten with
#: three from across town.
MAX_MILES = 2.0

#: How many survive ranking and reach the map.
KEEP = 6

CACHE_FIELD = "batchdata_comps"
CACHE_AT_FIELD = "batchdata_comps_at"
CACHE_DAYS = 30

UA = {"User-Agent": "groundwork-crm/1.0 (+groundworkpro.com; comps fallback)"}


def _key():
	"""The CHEAP token only. Never falls back to BATCHDATA_API_KEY."""
	return (frappe.conf.get("batchdata_comps_key") or "").strip()


def _has_cache():
	return frappe.db.has_column("CRM Lead", CACHE_FIELD) and frappe.db.has_column(
		"CRM Lead", CACHE_AT_FIELD
	)


def enabled():
	"""Both a key and somewhere to remember the answer. No cache, no spending."""
	return bool(_key()) and _has_cache()


def _cached(doc):
	raw = doc.get(CACHE_FIELD)
	if not raw:
		return None
	at = doc.get(CACHE_AT_FIELD)
	if at:
		try:
			if frappe.utils.date_diff(frappe.utils.nowdate(), str(at)[:10]) > CACHE_DAYS:
				return None
		except Exception:
			return None
	try:
		return json.loads(raw)
	except Exception:
		return None


def _store(lead, comps):
	"""Cache even an EMPTY result. A lead BatchData has nothing for must not be
	re-bought on every page view -- the negative answer is worth the same $0.30."""
	try:
		frappe.db.set_value(
			"CRM Lead",
			lead,
			{CACHE_FIELD: json.dumps(comps), CACHE_AT_FIELD: frappe.utils.now()},
			update_modified=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "BatchData comps: cache write failed")


def _num(v):
	try:
		f = float(v)
		return f if f else None
	except (TypeError, ValueError):
		return None


def _shape(p, subject_lat, subject_lng, haversine):
	"""One BatchData property -> the same dict shape a CRM Comp row produces, so
	the map and table render it without knowing where it came from."""
	addr = p.get("address") or {}
	bld = p.get("building") or {}
	sale = (p.get("sale") or {}).get("lastSale") or {}
	val = p.get("valuation") or {}

	lat, lng = _num(addr.get("latitude")), _num(addr.get("longitude"))
	if lat is None or lng is None:
		return None
	dist = haversine(subject_lat, subject_lng, lat, lng)
	if dist > MAX_MILES:
		return None

	# Prefer a real recorded sale; fall back to the AVM and say so via `status`.
	price = _num(sale.get("price"))
	status = "sold"
	if not price:
		price = _num(val.get("estimatedValue"))
		status = "estimate"

	street = (addr.get("street") or "").strip()
	if not street:
		return None

	return {
		"name": f"bd:{p.get('_id') or street}",
		"address": street,
		"city": addr.get("city"),
		"state": addr.get("state"),
		"zip": addr.get("zip"),
		"price": price,
		"status": status,
		"lat": lat,
		"lng": lng,
		"bedrooms": _num(bld.get("bedroomCount")),
		"bathrooms": _num(bld.get("bathroomCount")),
		"square_footage": _num(bld.get("livingAreaSquareFeet"))
		or _num(bld.get("totalBuildingAreaSquareFeet")),
		"year_built": _num(bld.get("yearBuilt")),
		"property_type": (p.get("general") or {}).get("propertyTypeDetail"),
		"listed_date": None,
		"removed_date": (sale.get("saleDate") or "")[:10] or None,
		"distance_mi": round(dist, 2),
		"source": "batchdata",
	}


def _score(c, subj):
	"""Lower is better. Distance dominates, shape adjusts.

	BatchData returns no similarity score, so this is the ranking it declines to
	do. Distance is weighted hardest because it is the one thing we can always
	trust: sqft and beds are frequently missing, and a missing fact must not be
	scored as a bad match or every sparse record sinks.
	"""
	score = c["distance_mi"] * 2.0
	s_sqft, c_sqft = subj.get("sqft"), c.get("square_footage")
	if s_sqft and c_sqft:
		score += abs(c_sqft - s_sqft) / max(s_sqft, 1) * 1.5
	s_beds, c_beds = subj.get("beds"), c.get("bedrooms")
	if s_beds and c_beds:
		score += abs(c_beds - s_beds) * 0.3
	s_yr, c_yr = subj.get("year_built"), c.get("year_built")
	if s_yr and c_yr:
		score += min(abs(c_yr - s_yr) / 50.0, 1.0) * 0.3
	if c.get("status") == "estimate":
		score += 0.5  # a real sale outranks an AVM at equal distance
	return score


def fetch(doc, lat, lng, subject_facts=None, force=False):
	"""Comps for a lead our own inventory has none for. Never raises.

	Returns [] when disabled, uncached-and-unbuyable, or genuinely nothing near.
	"""
	if not enabled():
		return []

	if not force:
		hit = _cached(doc)
		if hit is not None:
			return hit

	street = (doc.get("property_address") or "").strip()
	city = (doc.get("property_city") or "").strip()
	state = (doc.get("property_state") or "").strip()
	zipc = (doc.get("property_zip") or "").strip()
	if not (street and (zipc or (city and state))):
		return []

	body = {
		"searchCriteria": {
			"compAddress": {"street": street, "city": city, "state": state, "zip": zipc}
		},
		"options": {"take": TAKE, "skip": 0},
	}

	try:
		r = requests.post(
			SEARCH_URL,
			headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json", **UA},
			json=body,
			timeout=25,
		)
		r.raise_for_status()
		payload = r.json() or {}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "BatchData comps: request failed")
		return []

	props = ((payload.get("results") or {}).get("properties")) or []

	from crm.api.comps import _haversine_mi

	subj = subject_facts or {}
	shaped = []
	for p in props:
		c = _shape(p, lat, lng, _haversine_mi)
		if c:
			shaped.append(c)

	shaped.sort(key=lambda c: _score(c, subj))
	kept = shaped[:KEEP]

	_store(doc.name, kept)
	frappe.logger("comps").info(
		f"BatchData fallback {doc.name}: bought {len(props)} rows "
		f"(~${len(props) * 0.03:.2f}), {len(shaped)} within {MAX_MILES}mi, kept {len(kept)}"
	)
	return kept
