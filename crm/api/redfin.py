# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Redfin photos — third rung of the gallery ladder, after Zillow and Realtor.

Zillow remains the comps source; Realtor (apivex) is the first photo fallback.
This is the last resort for a house neither of them has pictures of — Redfin
runs its own MLS deals, so its gallery sometimes survives where the other two
are empty. One address lookup + one detail fetch, on an explicit gallery open,
only when the ladder above already came up with ≤1 image, and the result rides
the same 30-day detail cache as everything else.

Provider: "Redfin.com Data" (ntd119) on RapidAPI, on the SAME account key as
the Zillow provider (`rapidapi_zillow_key`) — RapidAPI keys are per-account,
quotas per-API, so this spends its own 100 req/month Basic allowance (2 calls
per lookup ≈ 50 lookups) and cannot eat the Zillow budget. Redfin itself
hard-blocks direct API access (CloudFront bot detection, datacenter AND
residential — measured 403 both ways), which is why this goes through a
provider at all. Absent the key or the subscription, silent no-op.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

HOST = "redfin-com-data.p.rapidapi.com"
TIMEOUT = 20
CONF_KEY = "rapidapi_zillow_key"


def _api_key():
	import frappe

	return (frappe.conf.get(CONF_KEY) or "").strip()


def _get(path, params, key):
	url = f"https://{HOST}{path}?" + urllib.parse.urlencode(params)
	req = urllib.request.Request(url, headers={"x-rapidapi-key": key, "x-rapidapi-host": HOST})
	try:
		with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
			return json.loads(resp.read().decode("utf-8", "replace"))
	except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
		# Includes 403 (not subscribed), 429 (2/s rate limit or the monthly cap)
		# and every network failure: a missing fallback is never worth an error.
		return None
	except Exception:
		import frappe

		frappe.log_error(frappe.get_traceback(), "Redfin: request failed")
		return None


def _property_url(address, key):
	"""Address string -> Redfin property URL path, or None."""
	body = _get("/properties/auto-complete", {"query": address}, key)
	if not isinstance(body, dict):
		return None
	for section in body.get("data") or []:
		for row in section.get("rows") or []:
			url = (row.get("url") or "").strip()
			# Only a concrete home page ("/home/<id>") is an address match;
			# city/neighborhood rows also come back and must never be fetched.
			if "/home/" in url:
				return url
	return None


def redfin_photo_urls(address: str, limit=60):
	"""Address -> list of Redfin CDN photo hrefs, or []. Never raises."""
	addr = (address or "").strip()
	key = _api_key()
	if not addr or not key:
		return []
	url = _property_url(addr, key)
	if not url:
		return []
	body = _get("/properties/detail-by-url", {"url": "https://www.redfin.com" + url}, key)
	if not isinstance(body, dict):
		return []
	media = (((body.get("data") or {}).get("aboveTheFold") or {}).get("mediaBrowserInfo")) or {}
	out = []
	for photo in media.get("photos") or []:
		if not isinstance(photo, dict):
			continue
		urls = photo.get("photoUrls") or {}
		href = (urls.get("fullScreenPhotoUrl") or urls.get("nonFullScreenPhotoUrl") or "").strip()
		if href.startswith("http") and href not in out:
			out.append(href)
		if len(out) >= int(limit):
			break
	return out
