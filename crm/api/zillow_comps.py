# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Refresh ISTL comps against Zillow — area search + per-pin lookup.

The pooled `CRM Comp` index is ISTL's RentCast-derived last *asks*, frozen when
the marketplace lead was scraped. It ages. This module is the freshness layer:

  A. One circle search for RecentlySold and one for ForSale
     (`coordinates=lon lat,diameter`, diameter = 2× radius miles). Cached 7 days
     per rounded center so two leads on the same block share the spend.
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
PIN_REFRESH_CAP = 5
#: Don't spend a /property call on an ISTL pin that already looks current.
PIN_STALE_DAYS = 90
SOLD_IN_LAST = "12m"
AREA_CACHE_VERSION = 3  # v1 ZIP, v2 polygon box, v3 coordinates circle
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
	}


def _search(coordinates, status_type, sold_in_last=None):
	params = {
		"coordinates": coordinates,
		"status_type": status_type,
		"sort": "Newest",
		"page": 0,
	}
	if sold_in_last:
		params["soldInLast"] = sold_in_last
	body = zillow_api._request("/search", params, f"Zillow: {status_type} search failed")
	if not isinstance(body, dict):
		return None
	# A bad coordinates string comes back as `{errors: ["wrong format"]}`. A
	# street-address `location` comes back as `{zpid}`. Neither is an area result.
	if "props" not in body:
		return []
	kind = "sale" if status_type == "ForSale" else "sold"
	rows = []
	for prop in body.get("props") or []:
		shaped = _shape_search(prop, kind)
		if shaped:
			rows.append(shaped)
	return rows


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

	rows = _search(coordinates, status_type, sold_in_last)
	if rows is None:
		return [], False
	_cache_set(key, rows)
	return rows, False


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

	def _stale(row):
		if row.get("source") == "zillow" or not row.get("address"):
			return False
		# Still listed in ISTL: it may have sold. Off-market and recent: A already
		# covered the ZIP's newest sales, so a /property here rarely pays off.
		if str(row.get("status") or "").lower() == "active":
			return True
		removed = str(row.get("removed_date") or "")[:10]
		if not removed:
			return True
		try:
			return frappe.utils.date_diff(today, removed) >= PIN_STALE_DAYS
		except Exception:
			return True

	candidates = [r for r in rows if _stale(r)]
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
		if changed:
			if facts.get("sqft") and not row.get("square_footage"):
				row["square_footage"] = facts["sqft"]
			if facts.get("year_built") and not row.get("year_built"):
				row["year_built"] = facts["year_built"]
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
