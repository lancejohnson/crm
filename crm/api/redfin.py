# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Redfin photos — third rung of the gallery ladder, via redfin-scraper-api.

The CRM does not talk to Redfin. redfin-scraper-api (formerly groundwork-geo)
owns the one Redfin client on this egress IP — the WAF budget is IP-keyed, so
several apps each running their own scraper would collectively exhaust it with
nobody able to tell which one did (that service's CLAUDE.md, "Why this is a
service and not a library"). The first cut of this module scraped Redfin's avm
endpoint directly from the CRM; it worked, and it was still the wrong place
for the traffic to live.

The service constructs CDN photo URLs from its rate-limited avm sweep (the
photo-bearing detail endpoints are WAF-403 from the box; see geo/photos.py in
the redfin-scraper-api repo for the URL scheme and its verification). One GET
per lookup, fired only when Zillow AND Realtor are both empty, result cached
30 days by the comp detail cache.

Config-gated like crm/api/geo.py: reads `redfin_scraper_url` (pre-rename
fallback `geo_service_url`); absent both, every call is a silent no-op and
the ladder degrades exactly as before.
"""

import requests

TIMEOUT = 15


def _base_url():
	from crm.api.geo import _base_url as geo_base

	return geo_base()


def redfin_photo_urls(address: str, lat=None, lng=None, limit=60):
	"""Address + point -> list of Redfin CDN photo hrefs, or []. Never raises.

	The point finds the neighbourhood; the address picks the house (exact
	normalized street-line match, service-side — no nearest-row fallback,
	because the neighbour's gallery is worse than nothing).
	"""
	base = _base_url()
	addr = (address or "").strip()
	try:
		lat, lng = float(lat), float(lng)
	except (TypeError, ValueError):
		return []
	if not base or not addr or not lat or not lng:
		return []
	try:
		r = requests.get(
			f"{base}/photos",
			params={"address": addr, "lat": lat, "lng": lng, "limit": int(limit)},
			timeout=TIMEOUT,
		)
		r.raise_for_status()
		body = r.json() or {}
	except Exception:
		import frappe

		frappe.log_error(frappe.get_traceback(), "Redfin: geo /photos failed")
		return []
	photos = body.get("photos") or []
	return [p for p in photos if isinstance(p, str) and p.startswith("http")][: int(limit)]
