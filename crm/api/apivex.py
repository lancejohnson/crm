# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Apivex Realtor photos — gallery fallback when Zillow only has one picture.

Zillow remains the comps source (search, facts, priceHistory). Off-market solds
often come back with a single Zillow frame; Realtor's listing photos stay up
longer. This module is that hole and nothing else: one call, on an explicit
gallery open, only when Zillow already returned ≤1 image.

Key: site_config `apivex_api_key`. Absent, this is a silent no-op.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

HOST = "api.apivex.com"
BASE = f"https://{HOST}"
TIMEOUT = 20
CONF_KEY = "apivex_api_key"


def _api_key():
	import frappe

	return (frappe.conf.get(CONF_KEY) or "").strip()


def realtor_photo_urls(address: str, limit=60):
	"""Address -> list of Realtor CDN hrefs, or []. Never raises."""
	addr = (address or "").strip()
	key = _api_key()
	if not addr or not key:
		return []
	params = urllib.parse.urlencode({"address": addr})
	url = f"{BASE}/realtor/property/photos?{params}"
	req = urllib.request.Request(
		url,
		headers={
			"x-apivex-key": key,
			"Accept": "application/json",
		},
	)
	try:
		with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
			body = json.loads(resp.read().decode("utf-8", "replace"))
	except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
		return []
	except Exception:
		import frappe

		frappe.log_error(frappe.get_traceback(), "Apivex: realtor photos failed")
		return []
	return _hrefs(body, limit)


def _hrefs(body, limit):
	rows = body
	if isinstance(body, dict):
		rows = body.get("photos") or body.get("data") or body.get("results") or []
	if not isinstance(rows, list):
		return []
	out = []
	for row in rows:
		href = ""
		if isinstance(row, str):
			href = row
		elif isinstance(row, dict):
			href = (row.get("href") or row.get("url") or "").strip()
		if href.startswith("http") and href not in out:
			out.append(href)
		if len(out) >= int(limit):
			break
	return out
