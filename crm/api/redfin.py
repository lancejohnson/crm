# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Redfin photos — third rung of the gallery ladder, after Zillow and Realtor.

Scraped, free, and effectively unlimited — no RapidAPI subscription. The trick
is that Redfin's photo CDN URLs are fully CONSTRUCTIBLE from data its
unauthenticated endpoint already hands out:

  * `/stingray/api/gis/avm?poly=` (no cookie, no token — the same endpoint
    groundwork-geo's neighbourhood sweep runs on) returns every home in a
    polygon, each carrying `mlsId`, `dataSourceId` and a `photos` RANGE SPEC
    like `"0-10:2,11:3,12-19:2"` — photo indexes with a per-range version.
  * The CDN pattern is then
    `https://ssl.cdn-redfin.com/photo/{ds}/mbmobile/{last3 of MLS}/genMbmob.{MLS}_{i}_{v}.jpg`
    with the `_{i}` part OMITTED for index 0. Verified against live CDN for
    v0/v2/v3, letter and all-numeric MLS ids, and a display-level-5 row —
    every constructed URL returned a real JPEG, hotlinkable with no referer.

The photo-bearing DETAIL endpoints (`aboveTheFold` / `belowTheFold`) are
WAF-gated from datacenter IPs (403), which is why this does not simply fetch
the gallery: the avm sweep is the door that is open.

groundwork-geo is normally the only Redfin caller (the parcel endpoint's WAF
bucket is IP-keyed and shared). This module rides the UNAUTHENTICATED avm
endpoint at trivial volume — third rung only, fired when Zillow AND Realtor
are both empty, result cached 30 days by the comp detail cache — so it does
not meaningfully touch that budget. If Redfin ever WAFs gis/avm too, every
failure path here returns [] and the ladder degrades exactly as before.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.redfin.com"
CDN = "https://ssl.cdn-redfin.com"
TIMEOUT = 20
USER_AGENT = (
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
	"(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

#: Half-size of the lookup box, in degrees (~110m lat / ~85m lng). Big enough
#: that a geocode a house or two off still contains the subject, small enough
#: that the sweep stays tens of rows, not hundreds.
BOX_DEG = 0.001


def _value(home, key):
	"""Redfin wraps many fields as {"value": x, "level": n}. Unwrap safely."""
	v = (home or {}).get(key)
	if isinstance(v, dict):
		return v.get("value")
	return v


def _street_key(text):
	"""Normalized street-line key. merge_key collapses St/Street etc., so the
	ISTL/Zillow spelling and Redfin's `streetLine` land on the same key."""
	from crm.api.zillow_comps import merge_key

	street = str(text or "").split(",")[0].strip()
	return merge_key(street) if street else ""


def _fetch_avm(lat, lng):
	"""Homes in a small box around the point, via the unauthenticated sweep."""
	west, east = lng - BOX_DEG, lng + BOX_DEG
	south, north = lat - BOX_DEG, lat + BOX_DEG
	pts = [(west, south), (east, south), (east, north), (west, north), (west, south)]
	poly = ",".join(f"{x} {y}" for x, y in pts)
	url = f"{BASE}/stingray/api/gis/avm?al=1&poly={urllib.parse.quote(poly)}&v=8"
	req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
	try:
		with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
			text = resp.read().decode("utf-8", "replace")
	except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
		return []
	except Exception:
		import frappe

		frappe.log_error(frappe.get_traceback(), "Redfin: avm sweep failed")
		return []
	if text.startswith("{}&&"):
		text = text[4:]
	try:
		body = json.loads(text)
	except ValueError:
		return []
	return ((body.get("payload") or {}).get("homes")) or []


def _photo_specs(spec):
	"""`"0-10:2,11:3,12-19:2"` -> [(index, version), ...] in index order."""
	out = []
	for part in str(spec or "").split(","):
		part = part.strip()
		if ":" not in part:
			continue
		rng, ver = part.rsplit(":", 1)
		ver = ver.strip()
		try:
			if "-" in rng:
				a, b = rng.split("-", 1)
				indexes = range(int(a), int(b) + 1)
			else:
				indexes = [int(rng)]
		except ValueError:
			continue
		for i in indexes:
			out.append((i, ver))
	out.sort(key=lambda t: t[0])
	return out


def _photo_urls_for(home, limit):
	mls = str(_value(home, "mlsId") or "").strip()
	ds = home.get("dataSourceId")
	specs = _photo_specs(_value(home, "photos"))
	if not mls or ds in (None, "") or not specs:
		return []
	sub = mls[-3:]
	out = []
	for i, v in specs[: int(limit)]:
		name = f"genMbmob.{mls}_{v}.jpg" if i == 0 else f"genMbmob.{mls}_{i}_{v}.jpg"
		out.append(f"{CDN}/photo/{ds}/mbmobile/{sub}/{name}")
	return out


def redfin_photo_urls(address: str, lat=None, lng=None, limit=60):
	"""Address + point -> list of Redfin CDN photo hrefs, or []. Never raises.

	The point finds the neighbourhood; the ADDRESS picks the house. Matching is
	exact on the normalized street line — constructing the neighbour's gallery
	would be worse than returning nothing, so there is deliberately no
	nearest-row fallback.
	"""
	key = _street_key(address)
	try:
		lat, lng = float(lat), float(lng)
	except (TypeError, ValueError):
		return []
	if not key or not lat or not lng:
		return []
	try:
		for home in _fetch_avm(lat, lng):
			if _street_key(_value(home, "streetLine")) == key:
				return _photo_urls_for(home, limit)
	except Exception:
		import frappe

		frappe.log_error(frappe.get_traceback(), "Redfin: photo lookup failed")
	return []
