# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Comparable sales around a lead's property — the "View comps" map.

Ported from the LeadMarket (istl-buyer) comps view, with one deliberate change:
LeadMarket can only ever draw an ESTIMATED subject location, because iSpeedToLead
gates the real address until you buy the lead, so it plots the centroid of the comp
cloud. We own these leads, so we know the actual parcel — the map centers on the
subject's real geocoded address and the comps arrange themselves around it.

Where the data comes from
-------------------------
The comps themselves are iSpeedToLead's (RentCast-derived) comparables, imported
from the marketplace inventory by `import_comps_file`. They carry a full street
address but no coordinates, so the importer ships them pre-geocoded.

Two layers, because exact-per-lead coverage is thin:
  * a lead we BOUGHT and whose marketplace record we still hold has its own comps
  * everything else is served from the pooled AREA inventory — every comp we have
    anywhere near the subject, which covers ~92% of our leads

The pooled layer is what makes this useful today: matching a CRM lead back to its
marketplace record only works for the ~9% we scraped while they were still for
sale (see `crm.api.comps.LINKAGE_NOTE`).

Recency is a first-class signal, not decoration: a sale from last month says more
about today's value than one from last year, so the UI fades a comp by staleness.
The raw dates are returned untouched and the fade is computed client-side, so the
map and any future report can't disagree about what "recent" means.
"""

import hashlib
import json
import math
import re
import urllib.parse
import urllib.request

import frappe
from frappe import _

DOCTYPE = "CRM Comp"
SALES_ROLES = ("System Manager", "Sales Manager", "Sales User")

#: Default search radius. Two miles is what LeadMarket's rings top out at, and in
#: practice a comp further away than that is arguing about a different market.
DEFAULT_RADIUS_MI = 2.0
#: Hard cap on returned pins. A dense metro ZIP can hold 700+ comps; past ~200
#: the map is an unreadable wall of pills and the payload starts to hurt.
MAX_COMPS = 200

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
UA = {"User-Agent": "groundwork-crm/1.0 (+groundworkpro.com; comps map)"}

LINKAGE_NOTE = (
	"CRM Lead.vendor_lead_id holds the iSpeedToLead ORDER id, not the lead id. "
	"The lead id lives at order.lead._id in GET /orders/all."
)


def _guard():
	if not any(role in SALES_ROLES for role in frappe.get_roles()):
		frappe.throw(_("Not permitted."), frappe.PermissionError)


def _available() -> bool:
	"""False until the ops setup script has run. Everything degrades to 'no comps'."""
	return bool(frappe.db.exists("DocType", DOCTYPE))


def address_key(address: str) -> str:
	"""Deterministic, collision-free docname for one property address.

	Deterministic so a re-import updates the same row instead of duplicating it;
	the md5 tail is what keeps two addresses that slugify identically (or that get
	truncated to the same 100 chars) from colliding on a `unique` field.
	"""
	norm = re.sub(r"\s+", " ", (address or "").strip().lower())
	slug = re.sub(r"[^a-z0-9]+", "-", norm).strip("-")[:100]
	return f"{slug}-{hashlib.md5(norm.encode()).hexdigest()[:8]}"


def _haversine_mi(lat1, lng1, lat2, lng2):
	r = 3958.7613
	p1, p2 = math.radians(lat1), math.radians(lat2)
	dp = math.radians(lat2 - lat1)
	dl = math.radians(lng2 - lng1)
	a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
	return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------------
# Subject property geocoding
# ---------------------------------------------------------------------------------
def _full_address(doc) -> str:
	"""Street + city + state + zip, skipping anything already inside the street line.

	Webhook leads arrive with the whole address in `property_address`; hand-entered
	ones are street-only with the rest in separate fields. Same rule the agreement
	builder uses, and for the same reason: a bare "123 Main St" geocodes to the
	wrong state.
	"""
	parts = [(doc.get("property_address") or "").strip()]
	for key in ("property_city", "property_state", "property_zip"):
		val = (doc.get(key) or "").strip()
		if val and val.lower() not in parts[0].lower():
			parts.append(val)
	return ", ".join(p for p in parts if p)


def _census_geocode(address: str):
	"""One address -> (lat, lng), or None. Free, US-only, no API key."""
	qs = urllib.parse.urlencode(
		{"address": address, "benchmark": "Public_AR_Current", "format": "json"}
	)
	req = urllib.request.Request(f"{CENSUS_URL}?{qs}", headers=UA)
	try:
		with urllib.request.urlopen(req, timeout=20) as resp:
			body = json.loads(resp.read().decode("utf-8", "replace"))
		matches = (body.get("result") or {}).get("addressMatches") or []
		if not matches:
			return None
		coords = matches[0].get("coordinates") or {}
		return float(coords["y"]), float(coords["x"])
	except Exception:
		# A geocoder outage must not take the lead page with it.
		frappe.log_error(frappe.get_traceback(), "Comps: subject geocode failed")
		return None


def _subject_point(doc):
	"""The lead's real position, geocoded once and cached on the lead.

	Cached because the Census geocoder is free but slow (~1s), and this runs every
	time someone opens the modal. `update_modified=False` so caching a coordinate
	never looks like somebody edited the lead.
	"""
	has_cache = frappe.db.has_column("CRM Lead", "property_lat")
	if has_cache and doc.get("property_lat") and doc.get("property_lng"):
		return float(doc.property_lat), float(doc.property_lng), True

	address = _full_address(doc)
	if not address:
		return None, None, False
	point = _census_geocode(address)
	if not point:
		return None, None, False
	if has_cache:
		try:
			frappe.db.set_value(
				"CRM Lead", doc.name,
				{"property_lat": point[0], "property_lng": point[1]},
				update_modified=False,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Comps: caching subject point failed")
	return point[0], point[1], False


# ---------------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------------
@frappe.whitelist()
def get_lead_comps(lead, radius_mi=None, limit=None):
	"""Comps near a lead, nearest first, with the subject's real position.

	The bounding box is a cheap indexed pre-filter; haversine then trims the
	corners of that box to a true circle. Doing it the other way round would mean
	a full-table distance computation over every comp we hold.
	"""
	_guard()
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead {0} does not exist.").format(lead), frappe.DoesNotExistError)
	doc = frappe.get_doc("CRM Lead", lead)

	try:
		radius = max(0.25, min(10.0, float(radius_mi or DEFAULT_RADIUS_MI)))
	except (TypeError, ValueError):
		radius = DEFAULT_RADIUS_MI
	try:
		cap = max(1, min(MAX_COMPS, int(limit or MAX_COMPS)))
	except (TypeError, ValueError):
		cap = MAX_COMPS

	lat, lng, cached = _subject_point(doc)
	base = {
		"lead": lead,
		"address": _full_address(doc),
		"subject": {"lat": lat, "lng": lng} if lat is not None else None,
		"radius_mi": radius,
		"cached_point": cached,
		"comps": [],
		"available": _available(),
	}
	if not base["available"]:
		base["message"] = _("Comps have not been imported yet.")
		return base
	if lat is None:
		base["message"] = _("Could not locate this property's address on the map.")
		return base

	# 1 degree of latitude is ~69 miles; longitude shrinks with the cosine of it.
	dlat = radius / 69.0
	cos_lat = max(math.cos(math.radians(lat)), 0.01)
	dlng = radius / (69.0 * cos_lat)
	rows = frappe.get_all(
		DOCTYPE,
		filters={
			"lat": ["between", [lat - dlat, lat + dlat]],
			"lng": ["between", [lng - dlng, lng + dlng]],
		},
		fields=[
			"name", "address", "city", "state", "zip", "lat", "lng", "price", "status",
			"listed_date", "removed_date", "days_on_market", "days_old",
			"bedrooms", "bathrooms", "square_footage", "year_built", "property_type",
		],
		limit_page_length=5000,
	)

	out = []
	for row in rows:
		if row.lat is None or row.lng is None:
			continue
		dist = _haversine_mi(lat, lng, row.lat, row.lng)
		if dist > radius:
			continue
		row = dict(row)
		row["distance_mi"] = round(dist, 2)
		# Dates are returned raw; the client derives the recency fade so the map and
		# any future report can't disagree about what "recent" means.
		for key in ("listed_date", "removed_date"):
			if row.get(key):
				row[key] = str(row[key])
		out.append(row)

	out.sort(key=lambda r: r["distance_mi"])
	base["total_in_radius"] = len(out)
	base["comps"] = out[:cap]
	return base


# ---------------------------------------------------------------------------------
# Import (bench-executable)
# ---------------------------------------------------------------------------------
@frappe.whitelist()
def import_comps_file(path, dry_run=1, chunk=2000):
	"""Bulk-load geocoded comps from a JSONL file produced by the build script.

	Raw SQL upsert rather than `doc.insert()`: this is ~37k rows of immutable
	reference data, and the ORM path costs minutes plus a Version row apiece for an
	audit trail nobody will read. `ON DUPLICATE KEY UPDATE` keyed on the
	deterministic address_key is what makes a re-import idempotent.

	    bench execute crm.api.comps.import_comps_file \\
	        --kwargs '{"path": "/tmp/comps_geocoded.jsonl", "dry_run": 0}'
	"""
	dry_run = int(dry_run)
	if not _available():
		return {"ok": False, "error": f"{DOCTYPE} doctype does not exist — run setup_comps.py"}

	cols = [
		"address", "city", "state", "zip", "lat", "lng", "price", "status",
		"listed_date", "removed_date", "days_on_market", "days_old",
		"bedrooms", "bathrooms", "square_footage", "year_built", "property_type",
		"correlation", "source_lead",
	]
	seen, rows, stats = set(), [], {"read": 0, "skipped": 0, "written": 0}

	def flush(batch):
		if not batch or dry_run:
			return
		placeholders = ", ".join(["(" + ", ".join(["%s"] * (len(cols) + 6)) + ")"] * len(batch))
		flat = []
		for r in batch:
			flat.extend(r)
		updates = ", ".join(f"`{c}`=VALUES(`{c}`)" for c in cols)
		frappe.db.sql(
			f"""INSERT INTO `tab{DOCTYPE}`
			    (`name`, `address_key`, `creation`, `modified`, `owner`, `modified_by`, {', '.join(f'`{c}`' for c in cols)})
			    VALUES {placeholders}
			    ON DUPLICATE KEY UPDATE {updates}, `modified`=VALUES(`modified`)""",
			flat,
		)
		frappe.db.commit()

	now = frappe.utils.now()
	user = frappe.session.user or "Administrator"
	with open(path) as fh:
		for line in fh:
			line = line.strip()
			if not line:
				continue
			stats["read"] += 1
			try:
				rec = json.loads(line)
			except Exception:
				stats["skipped"] += 1
				continue
			if rec.get("lat") is None or rec.get("lng") is None or not rec.get("address"):
				stats["skipped"] += 1
				continue
			key = address_key(rec["address"])
			if key in seen:          # same address twice in one file
				stats["skipped"] += 1
				continue
			seen.add(key)
			rows.append([key, key, now, now, user, user] + [rec.get(c) for c in cols])
			stats["written"] += 1
			if len(rows) >= int(chunk):
				flush(rows)
				rows = []
	flush(rows)
	stats["ok"] = True
	stats["dry_run"] = bool(dry_run)
	stats["total_in_db"] = frappe.db.count(DOCTYPE) if not dry_run else None
	return stats
