# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Refresh ISTL comps against Zillow — area search + per-pin lookup.

The pooled `CRM Comp` index is ISTL's RentCast-derived last *asks*, frozen when
the marketplace lead was scraped. It ages. This module is the freshness layer:

  A. Circle search for every RecentlySold in the last 2 years AND every
     ForSale (`coordinates=lon lat,diameter`, diameter = 2× radius miles).
     Pages through `totalPages`; a window over RapidAPI's 800-result ceiling
     binary-splits on price (devproppy `fetch_all_zillow_properties`). Cached 7 days per rounded
     center so two leads on the same block share the spend.
  B. `/property` on the nearest stale ISTL pins (capped) so a house ISTL still
     has as an 8-month-old ask can pick up the sale Zillow recorded last week.

Street-address `/search` returns `{zpid}` only. ZIP is the wrong geography.
`polygon` is a box (corners sit at 2.83 mi). `coordinates` is the true circle
(measured: `d=4` → solds out to 1.99 mi). `dateSold` is epoch-ms.

Every path degrades softly: a Zillow outage or a quota-reserve hit leaves the
ISTL set untouched. BatchData stays the last resort for a truly empty map.
"""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone

import frappe

from crm.api import zillow as zillow_api

AREA_HIT_DAYS = 7
AREA_MISS_DAYS = 1
PIN_CACHE_DAYS = 30
PIN_REFRESH_CAP = 12
#: Don't spend a /property call on an ISTL pin that already looks current.
PIN_STALE_DAYS = 90
SOLD_IN_LAST = "24m"
#: RapidAPI's own ceiling per query — same number devproppy stops at. Past this
#: the API silently repeats page 1, so we binary-split the price range instead
#: (devproppy `fetch_all_zillow_properties`). Each half recurses if still >800.
MAX_SEARCH_RESULTS = 800
MAX_SPLIT_DEPTH = 6
#: Hard stop on RapidAPI calls for one circle+status so a dense metro cannot
#: spend the shared quota on a single comps open. 40 pages ≈ 1,600 rows.
MAX_SEARCH_CALLS = 40
AREA_CACHE_VERSION = 6  # v4 paged to 800; v5 price-splits past 800; v6 keeps imgSrc
PIN_CACHE_VERSION = 1

_SUFFIXES = {
	"street": "st",
	"avenue": "ave",
	"boulevard": "blvd",
	"drive": "dr",
	"road": "rd",
	"lane": "ln",
	"court": "ct",
	"place": "pl",
	"terrace": "ter",
	"circle": "cir",
	"highway": "hwy",
	"parkway": "pkwy",
	"trail": "trl",
}


def _cache_get(key, ttl_days):
	"""Read a `{t, data}` blob. No Redis TTL — see zillow.py's cache GOTCHA."""
	try:
		rec = frappe.cache().get_value(key)
	except Exception:
		return None
	if not isinstance(rec, dict) or "data" not in rec:
		return None
	try:
		age = time.time() - float(rec.get("t") or 0)
	except (TypeError, ValueError):
		return None
	if age > float(ttl_days) * 86400:
		return None
	return rec["data"]


def _cache_set(key, data):
	try:
		frappe.cache().set_value(key, {"t": time.time(), "data": data})
	except Exception:
		pass


def _ymd(value):
	"""Zillow dateSold is epoch-ms; priceHistory dates are YYYY-MM-DD. One shape."""
	if value in (None, ""):
		return None
	if isinstance(value, str):
		s = value.strip()
		if len(s) >= 10 and s[4] == "-" and s[7] == "-":
			return s[:10]
		try:
			value = float(s)
		except (TypeError, ValueError):
			return None
	try:
		n = float(value)
	except (TypeError, ValueError):
		return None
	if n > 1e12:
		n /= 1000.0
	if n <= 0:
		return None
	try:
		return datetime.fromtimestamp(n, tz=timezone.utc).strftime("%Y-%m-%d")
	except (OverflowError, OSError, ValueError):
		return None


def _newer(a, b):
	"""True when date string `a` is strictly after `b`. Missing `b` → yes."""
	if not a:
		return False
	if not b:
		return True
	return str(a)[:10] > str(b)[:10]


def _comps():
	# Late import: comps.py calls this module from get_lead_comps, so a top-level
	# import of address_key / _haversine_mi would cycle.
	from crm.api import comps as comps_mod

	return comps_mod


def merge_key(address: str) -> str:
	"""address_key after collapsing Street/Avenue/… so ISTL and Zillow collide.

	ISTL writes `3362 N 22nd St`; Zillow search writes `3362 N 22nd STREET`.
	The CRM Comp docname is the ISTL form, so a raw address_key miss would
	duplicate the pin instead of refreshing it.
	"""
	norm = re.sub(r"\s+", " ", (address or "").strip().lower())
	parts = []
	for word in re.split(r"([^a-z0-9]+)", norm):
		parts.append(_SUFFIXES.get(word, word))
	return _comps().address_key("".join(parts))


def _ll_key(lat, lng):
	if lat is None or lng is None:
		return None
	try:
		return (round(float(lat), 4), round(float(lng), 4))
	except (TypeError, ValueError):
		return None


def _coordinates(lat, lng, radius_mi) -> str:
	"""RapidAPI `/search` circle: `lon lat,diameter` (miles, 0–99).

	Diameter is 2× the comps radius so a 2-mile map is `d=4`. Measured: `d=4`
	around a St Paul point returned RecentlySold pins out to 1.99 mi. Rounded
	to 4 decimals (~11 m) so two leads on the same block share the cache.
	"""
	diameter = max(1, min(99, int(round(float(radius_mi) * 2))))
	return f"{round(float(lng), 4)} {round(float(lat), 4)},{diameter}"


def _shape_search(prop, kind):
	"""One RapidAPI search prop → the row shape `get_lead_comps` already emits."""
	if not isinstance(prop, dict):
		return None
	addr = (prop.get("address") or "").strip()
	lat = zillow_api._num(prop.get("latitude"))
	lng = zillow_api._num(prop.get("longitude"))
	price = zillow_api._num(prop.get("price"))
	zpid = prop.get("zpid")
	if not addr or lat is None or lng is None or not price or not zpid:
		return None

	sold = _ymd(prop.get("dateSold"))
	dom = zillow_api._num(prop.get("daysOnZillow"))
	home = str(prop.get("propertyType") or "").strip().upper()
	active = kind == "sale"
	return {
		"name": f"zillow::{zpid}",
		"address": addr,
		"city": "",
		"state": "",
		"zip": "",
		"lat": lat,
		"lng": lng,
		"price": price,
		"status": "Active" if active else "Inactive",
		"listed_date": None if not active else None,
		"removed_date": None if active else sold,
		"days_on_market": int(dom) if dom is not None else None,
		"days_old": None,
		"bedrooms": zillow_api._num(prop.get("bedrooms")),
		"bathrooms": zillow_api._num(prop.get("bathrooms")),
		"square_footage": zillow_api._num(prop.get("livingArea")),
		"year_built": None,
		"property_type": zillow_api.HOME_TYPES.get(home) or (home.title().replace("_", " ") or None),
		"source": "zillow",
		"zpid": str(zpid),
		# The search response already carries a listing thumbnail. Keeping it is the
		# whole reason the tray can show a photo per comp for NOTHING: the alternative
		# is `/property?address=` per house, which is one billed call each. Measured
		# on a St Paul 2-mile RecentlySold page: imgSrc present on 41 of 41 rows.
		"photo": (prop.get("imgSrc") or "").strip(),
	}


def _search_params(coordinates, status_type, sold_in_last=None, min_price=None, max_price=None, sort="Newest", page=1):
	params = {
		"coordinates": coordinates,
		"status_type": status_type,
		"sort": sort,
		"page": page,
	}
	if sold_in_last:
		params["soldInLast"] = sold_in_last
	if min_price is not None:
		params["minPrice"] = int(min_price)
	if max_price is not None:
		params["maxPrice"] = int(max_price)
	return params


def _get(coordinates, status_type, sold_in_last=None, min_price=None, max_price=None, sort="Newest", page=1):
	"""One RapidAPI /search. None on quota-reserve or a bad body."""
	left = zillow_api.quota_remaining()
	if left is not None and left <= zillow_api.QUOTA_RESERVE:
		return None
	params = _search_params(
		coordinates, status_type, sold_in_last, min_price, max_price, sort, page
	)
	body = zillow_api._request(
		"/search", params, f"Zillow: {status_type} {sort} p{page} failed"
	)
	if not isinstance(body, dict) or "props" not in body:
		return None
	return body


def _price_edge(coordinates, status_type, sold_in_last, min_price, max_price, high):
	"""Cheapest or dearest price in this window. One extra call, like devproppy."""
	sort = "Price_High_Low" if high else "Price_Low_High"
	body = _get(
		coordinates, status_type, sold_in_last, min_price, max_price, sort=sort, page=1
	)
	if not body:
		return None
	for prop in body.get("props") or []:
		n = zillow_api._num(prop.get("price"))
		if n:
			return int(n)
	return None


def _collect_pages(coordinates, status_type, sold_in_last, min_price, max_price, first_body, budget):
	"""Page through one price window that is already known to be ≤800."""
	kind = "sale" if status_type == "ForSale" else "sold"
	rows = []
	seen = set()
	try:
		total_pages = max(1, int(first_body.get("totalPages") or 1))
	except (TypeError, ValueError):
		total_pages = 1
	bodies = [first_body]
	page = 2
	while page <= total_pages and budget["n"] < MAX_SEARCH_CALLS:
		body = _get(
			coordinates, status_type, sold_in_last, min_price, max_price, page=page
		)
		budget["n"] += 1
		if body is None:
			break
		bodies.append(body)
		page += 1
	for body in bodies:
		for prop in body.get("props") or []:
			shaped = _shape_search(prop, kind)
			if not shaped or shaped.get("zpid") in seen:
				continue
			seen.add(shaped["zpid"])
			rows.append(shaped)
	complete = page > total_pages
	return rows, complete


def _search_window(coordinates, status_type, sold_in_last=None, min_price=None, max_price=None, depth=0, budget=None):
	"""One circle (optionally price-sliced). Splits when totalResultCount > 800."""
	if budget is None:
		budget = {"n": 0}
	if budget["n"] >= MAX_SEARCH_CALLS or depth > MAX_SPLIT_DEPTH:
		return [], False

	body = _get(coordinates, status_type, sold_in_last, min_price, max_price, page=1)
	budget["n"] += 1
	if body is None:
		return None, False

	try:
		count = int(body.get("totalResultCount") or 0)
	except (TypeError, ValueError):
		count = 0

	if count > MAX_SEARCH_RESULTS and depth < MAX_SPLIT_DEPTH:
		lo = min_price if min_price is not None else _price_edge(
			coordinates, status_type, sold_in_last, min_price, max_price, high=False
		)
		hi = max_price if max_price is not None else _price_edge(
			coordinates, status_type, sold_in_last, min_price, max_price, high=True
		)
		budget["n"] += int(min_price is None) + int(max_price is None)
		# No prices → cannot split (non-disclosure solds). Page this window's 800.
		if lo and hi and int(lo) < int(hi):
			mid = (int(lo) + int(hi)) // 2
			low_rows, low_ok = _search_window(
				coordinates, status_type, sold_in_last, int(lo), mid, depth + 1, budget
			)
			high_rows, high_ok = _search_window(
				coordinates, status_type, sold_in_last, mid, int(hi), depth + 1, budget
			)
			seen, out = set(), []
			for row in (low_rows or []) + (high_rows or []):
				zpid = row.get("zpid")
				if not zpid or zpid in seen:
					continue
				seen.add(zpid)
				out.append(row)
			return out, bool(low_ok and high_ok)

	return _collect_pages(
		coordinates, status_type, sold_in_last, min_price, max_price, body, budget
	)


def _search(coordinates, status_type, sold_in_last=None):
	"""All solds/listings in the circle. Price-splits when a window exceeds 800.

	`complete` is False when we stopped early (quota, call budget, a mid-run
	error). Those must not be cached for a week or we hide the rest of the circle.
	"""
	rows, complete = _search_window(coordinates, status_type, sold_in_last)
	if rows is None:
		return None, False
	return rows, complete


def _area_cached(coordinates, status_type, sold_in_last=None):
	digest = hashlib.md5(
		f"{coordinates}|{status_type}|{sold_in_last or ''}".encode()
	).hexdigest()[:12]
	key = f"zillow_area:v{AREA_CACHE_VERSION}:{digest}"
	hit = _cache_get(key, AREA_HIT_DAYS)
	if hit is not None:
		return hit, True
	# A remembered miss uses the short TTL so an outage does not lock a circle
	# out for a week, but also does not re-bill every modal open.
	miss = _cache_get(key, AREA_MISS_DAYS)
	if miss is not None:
		return miss, True

	rows, complete = _search(coordinates, status_type, sold_in_last)
	if rows is None:
		return [], False
	if complete:
		_cache_set(key, rows)
	return rows, complete


def area_comps(lat, lng, radius_mi):
	"""RecentlySold + ForSale inside a distance circle. Empty list on any failure."""
	if lat is None or lng is None or not zillow_api._api_key():
		return {"sold": [], "for_sale": [], "location": "", "cached": True}
	coords = _coordinates(float(lat), float(lng), float(radius_mi))
	sold, sold_cached = _area_cached(coords, "RecentlySold", SOLD_IN_LAST)
	sale, sale_cached = _area_cached(coords, "ForSale")
	return {
		"sold": sold or [],
		"for_sale": sale or [],
		"location": f"{radius_mi:.2f}mi",
		"cached": bool(sold_cached and sale_cached),
	}


def _pin_facts(address):
	"""Cached `/property` normalize for one ISTL pin. None on miss/failure."""
	if not address:
		return None
	key = f"zillow_pin:v{PIN_CACHE_VERSION}:{_comps().address_key(address)}"
	hit = _cache_get(key, PIN_CACHE_DAYS)
	if hit is not None:
		return hit or None

	raw = zillow_api.property_details(address)
	facts = zillow_api._normalize(raw) if raw else None
	# Cache the empty answer too — same lesson as subject facts.
	_cache_set(key, facts or {})
	return facts


def _apply_facts(existing, incoming):
	"""Zillow's shape wins. ISTL sqft is the listing/tax figure and is what
	Dennis just caught disagreeing with the Zillow page — we used to keep it
	whenever it was already set, so a merge that updated the SALE left the
	wrong living area on the pin.
	"""
	for key in ("square_footage", "bedrooms", "bathrooms", "year_built"):
		val = incoming.get(key)
		if val:
			existing[key] = val


def _apply_sale(row, price, date):
	row["price"] = price or row.get("price")
	row["removed_date"] = date
	row["status"] = "Inactive"
	row["source"] = "zillow"
	row["zillow_refreshed"] = True


def _apply_listing(row, price, days_on_market):
	row["price"] = price or row.get("price")
	row["status"] = "Active"
	if days_on_market is not None:
		row["days_on_market"] = int(days_on_market)
	row["source"] = "zillow"
	row["zillow_refreshed"] = True


def _index(rows):
	by_key, by_ll = {}, {}
	for row in rows:
		by_key[merge_key(row.get("address") or "")] = row
		ll = _ll_key(row.get("lat"), row.get("lng"))
		if ll:
			by_ll.setdefault(ll, row)
	return by_key, by_ll


def _find(row, by_key, by_ll):
	hit = by_key.get(merge_key(row.get("address") or ""))
	if hit:
		return hit
	ll = _ll_key(row.get("lat"), row.get("lng"))
	return by_ll.get(ll) if ll else None


def _merge_one(existing, incoming, today):
	"""Update `existing` from a Zillow row when Zillow is actually newer."""
	# A photo is not "newer" data, it is data the pooled index simply never had, so
	# it rides along on ANY match rather than waiting for a price/date to change.
	# This is what gives ISTL-origin pins a thumbnail without a per-address call.
	if incoming.get("photo") and not existing.get("photo"):
		existing["photo"] = incoming["photo"]
	if incoming.get("zpid") and not existing.get("zpid"):
		existing["zpid"] = incoming["zpid"]
	# Facts ride on ANY match, same as the photo: Zillow livingArea is the
	# number on the page Dennis is looking at. Leaving ISTL's figure in place
	# because a price didn't change is how sold comps showed the wrong sqft.
	_apply_facts(existing, incoming)
	if incoming.get("status") == "Active":
		# A live Zillow listing is more current than an ISTL ask, even if ISTL
		# also thought it was active — the ask may have moved.
		if existing.get("status") != "Active" or existing.get("source") != "zillow":
			_apply_listing(existing, incoming.get("price"), incoming.get("days_on_market"))
			existing["recency_days"] = _comps()._recency_days(existing, today)
			return "updated"
		return None
	if _newer(incoming.get("removed_date"), existing.get("removed_date")):
		_apply_sale(existing, incoming.get("price"), incoming.get("removed_date"))
		existing["recency_days"] = _comps()._recency_days(existing, today)
		return "updated"
	return None


def refresh_pins(rows, cap=PIN_REFRESH_CAP):
	"""B: `/property` the nearest ISTL-origin pins. Mutates `rows`. Returns counts."""
	today = frappe.utils.today()
	checked = updated = 0

	def _needs_zillow_shape(row):
		# Any pin still wearing ISTL facts — those are the listing/tax numbers
		# that disagree with the Zillow page. Zillow-origin rows already carry
		# livingArea from /search.
		return bool(row.get("address") and row.get("source") != "zillow")

	candidates = [r for r in rows if _needs_zillow_shape(r)]
	candidates.sort(key=lambda r: r.get("distance_mi") or 99)
	for row in candidates[: max(0, int(cap))]:
		facts = _pin_facts(row["address"])
		checked += 1
		if not facts:
			continue
		sale = facts.get("last_sale") or {}
		sale_date = _ymd(sale.get("date"))
		home = str(facts.get("home_status") or "").strip().upper()
		changed = False
		if sale_date and _newer(sale_date, row.get("removed_date")):
			_apply_sale(row, sale.get("price"), sale_date)
			changed = True
		elif home in {"FOR_SALE", "PENDING", "CONTINGENT", "COMING_SOON"}:
			listing = facts.get("last_listing") or {}
			_apply_listing(row, listing.get("price") or facts.get("zestimate"), None)
			changed = True
		# Shape from /property, even when the sale date did not move — same
		# reason as _merge_one. Blank-only used to preserve ISTL's listing sqft.
		if facts.get("sqft"):
			row["square_footage"] = facts["sqft"]
			changed = True
		if facts.get("beds"):
			row["bedrooms"] = facts["beds"]
			changed = True
		if facts.get("baths"):
			row["bathrooms"] = facts["baths"]
			changed = True
		if facts.get("year_built"):
			row["year_built"] = facts["year_built"]
			changed = True
		if changed:
			row["recency_days"] = _comps()._recency_days(row, today)
			updated += 1
	return {"checked": checked, "updated": updated}


def apply(doc, out, lat, lng, radius):
	"""A then B. Mutates `out`. Returns a small status dict for the UI."""
	info = {
		"used": False,
		"added": 0,
		"updated": 0,
		"sold": 0,
		"for_sale": 0,
		"pins_checked": 0,
		"location": "",
		"cached": True,
		"reason": None,
		# The subject's OWN listing is usually inside its own search radius. We throw
		# the row away (a house is not a comp for itself) but its thumbnail is the
		# subject photo, free — the alternative is a billed `/property` lookup for a
		# picture we were already handed.
		"subject_photo": "",
	}
	if lat is None or lng is None:
		info["reason"] = "no_subject"
		return info
	if not zillow_api._api_key():
		info["reason"] = "not_configured"
		return info

	today = frappe.utils.today()
	self_keys = {merge_key(doc.get("property_address") or ""), merge_key(_comps()._full_address(doc))}
	self_keys.discard(merge_key(""))
	area = area_comps(lat, lng, radius)
	info["location"] = area.get("location") or ""
	info["cached"] = bool(area.get("cached"))
	incoming = []
	for row in (area.get("sold") or []) + (area.get("for_sale") or []):
		dist = _comps()._haversine_mi(lat, lng, row["lat"], row["lng"])
		if dist > radius:
			continue
		if merge_key(row.get("address") or "") in self_keys:
			if row.get("photo") and not info["subject_photo"]:
				info["subject_photo"] = row["photo"]
			continue
		row = dict(row)
		row["distance_mi"] = round(dist, 2)
		row["selected"] = False
		row["hidden"] = False
		row["recency_days"] = _comps()._recency_days(row, today)
		incoming.append(row)
		if row["status"] == "Active":
			info["for_sale"] += 1
		else:
			info["sold"] += 1

	by_key, by_ll = _index(out)
	for row in incoming:
		existing = _find(row, by_key, by_ll)
		if existing:
			if _merge_one(existing, row, today) == "updated":
				info["updated"] += 1
			continue
		out.append(row)
		by_key[merge_key(row.get("address") or "")] = row
		ll = _ll_key(row.get("lat"), row.get("lng"))
		if ll:
			by_ll[ll] = row
		info["added"] += 1

	pins = refresh_pins(out)
	info["pins_checked"] = pins["checked"]
	info["updated"] += pins["updated"]
	info["used"] = bool(info["added"] or info["updated"] or info["sold"] or info["for_sale"] or info["pins_checked"])
	return info
