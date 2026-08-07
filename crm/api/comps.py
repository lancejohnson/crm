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

Filters, and why they arrive PRE-SET
------------------------------------
An unfiltered radius dump is not a comp set — it is every roof within two miles,
and on a dense ZIP that is 200 pins of condos and mansions around a 900 sqft
bungalow. So the map opens with the filters already set AROUND THIS PROPERTY:
recent, and similar in beds / baths / size / age / type.

The hard part is that a tight, honest filter often matches nothing — our comp
inventory is a pooled area index, not a curated per-lead set. Silently showing an
empty map would be the worst outcome, and silently showing everything would be a
lie about fit. So `_preset_tiers` is a LADDER: the tightest tier that still yields
a usable set wins, and the response says which tier was used and whether it had to
loosen, so the UI can tell the user plainly rather than pretending.
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

#: How many matches make a tier "usable". Below this you are not comping, you are
#: reading anecdotes, so the ladder loosens instead of presenting 2 pins as an
#: answer. Five is the smallest set a reviewer can see a middle in.
MIN_USABLE_COMPS = 5

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
# Subject property facts
# ---------------------------------------------------------------------------------
#: iSpeedToLead ships the subject's details as pick-list LABELS, not numbers.
#: Measured across all 764 prod leads, the entire vocabulary is:
#:   bedrooms   "3 Bedroom", "More than 5"
#:   bathrooms  "1.5 Bathroom", "More than 3", "None"
#:   square_footage "1000 - 2000", "5000+", "0 - 500"
#:   year_built "1900-1950", "2010-2022"
_RE_RANGE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:-|\u2013|to)\s*(\d+(?:\.\d+)?)\s*$", re.I)
_RE_PLUS = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*\+\s*$")
_RE_MORE = re.compile(r"more\s*than\s*(\d+(?:\.\d+)?)", re.I)
_RE_NUM = re.compile(r"(\d+(?:\.\d+)?)")


def _parse_band(value):
	"""One pick-list label -> (lo, hi, exact) in real numbers, or None.

	Returns the INTERVAL the source actually named, not a midpoint. "1000 - 2000"
	is a 2x band; collapsing it to 1500 would invent precision the data does not
	have and would then be widened again by a tolerance, compounding the fiction.
	`exact` says the source named a single value, which is what lets the preset be
	tight when we really know and loose when we are guessing.
	"""
	if value is None:
		return None
	text = str(value).strip()
	if not text or text.lower() in ("none", "n/a", "na", "not provided", "unknown", "0"):
		return None

	m = _RE_RANGE.match(text)
	if m:
		lo, hi = float(m.group(1)), float(m.group(2))
		return (min(lo, hi), max(lo, hi), False)
	# "5000+" / "More than 5" are open-ended: no upper bound, and NOT exact.
	m = _RE_PLUS.match(text) or _RE_MORE.search(text)
	if m:
		return (float(m.group(1)), None, False)
	m = _RE_NUM.search(text)
	if m:
		n = float(m.group(1))
		return (n, n, True)
	return None


def _band_mid(band):
	"""A single number to DISPLAY for a band (never used to filter)."""
	if not band:
		return None
	lo, hi = band[0], band[1]
	return lo if hi is None else (lo + hi) / 2.0


def _band_label(band, unit=""):
	if not band:
		return None
	lo, hi = band[0], band[1]

	def n(v):
		return str(int(v)) if float(v).is_integer() else f"{v:g}"

	if hi is None:
		return f"{n(lo)}+{unit}"
	if lo == hi:
		return f"{n(lo)}{unit}"
	return f"{n(lo)}–{n(hi)}{unit}"


def _self_listing(doc):
	"""The subject's OWN row in the comp inventory, if we happen to hold one.

	Present for ~5% of leads (13 of a 250-lead prod sample): a lead we bought was
	often scraped while it was itself on the market. When it exists it is the best
	thing we have about the property — real numbers instead of pick-list bands,
	plus what it last listed for and when it left the market.

	NOTE it is looked up by the same deterministic address_key the importer names
	rows with, so this is an exact-address match, never a fuzzy one.
	"""
	if not _available():
		return None
	candidates = []
	street = (doc.get("property_address") or "").strip()
	if street:
		candidates.append(street)
	full = _full_address(doc)
	if full and full != street:
		candidates.append(full)
	for addr in candidates:
		row = frappe.db.get_value(
			DOCTYPE, address_key(addr),
			["name", "address", "price", "status", "listed_date", "removed_date",
			 "days_on_market", "bedrooms", "bathrooms", "square_footage",
			 "year_built", "property_type"],
			as_dict=True,
		)
		if row:
			for key in ("listed_date", "removed_date"):
				if row.get(key):
					row[key] = str(row[key])
			return row
	return None


def _subject_facts(doc):
	"""Everything we can honestly say about the subject, best source first.

	1. its own listing in the comp inventory (real numbers, and a last list price)
	2. the iSpeedToLead pick-list fields on the lead (bands)
	3. the BatchData tax pull (assessed value / annual tax), already on the lead

	Every fact carries the source it came from, because "3 bd" from a listing and
	"3 bd" from a seller-typed web form are not the same claim.
	"""
	listing = _self_listing(doc)
	facts = {"source": {}}

	def take(key, lead_field, listing_field=None, unit=""):
		listing_val = (listing or {}).get(listing_field or lead_field)
		if listing_val:  # importer coerces missing numerics to 0, so 0 == unknown
			band = (float(listing_val), float(listing_val), True)
			facts["source"][key] = "listing"
		else:
			band = _parse_band(doc.get(lead_field))
			if band:
				facts["source"][key] = "lead"
		facts[f"{key}_band"] = list(band[:2]) if band else None
		facts[f"{key}_exact"] = bool(band[2]) if band else False
		facts[key] = _band_mid(band)
		facts[f"{key}_label"] = _band_label(band, unit)

	take("beds", "bedrooms")
	take("baths", "bathrooms")
	take("sqft", "square_footage")
	take("year_built", "year_built")

	ptype = (listing or {}).get("property_type") or None
	facts["property_type"] = ptype
	if ptype:
		facts["source"]["property_type"] = "listing"

	# What it last asked, and when it left the market. Deliberately NOT called a
	# sale price: this inventory carries the last LIST price, and going off-market
	# is not a confirmed close. The UI repeats that caveat rather than burying it.
	if listing:
		facts["last_listing"] = {
			"price": listing.get("price") or None,
			"status": listing.get("status"),
			"listed_date": listing.get("listed_date"),
			"removed_date": listing.get("removed_date"),
			"days_on_market": listing.get("days_on_market") or None,
		}
		facts["self_comp_key"] = listing.get("name")
	else:
		facts["last_listing"] = None
		facts["self_comp_key"] = None

	# Straight off the lead — seller-stated or BatchData, both already displayed
	# elsewhere on the page, so the popup is not inventing a new source of truth.
	facts["condition"] = (doc.get("property_condition") or "").strip() or None
	for key in ("assessed_value", "annual_tax", "asking_price"):
		val = doc.get(key)
		if isinstance(val, str):
			val = val.strip()
			val = val if val and val.lower() not in ("not provided", "none", "n/a") else None
		facts[key] = val or None
	return facts


# ---------------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------------
def _num(v):
	try:
		n = float(v)
	except (TypeError, ValueError):
		return None
	return n if math.isfinite(n) else None


def _is_active(status) -> bool:
	"""Exact match — a substring test would read "Inactive" as active."""
	return str(status or "").strip().lower() == "active"


def _recency_days(row, today):
	"""Days since this comp last said anything about the market.

	An off-market comp is dated by when it LEFT (the transaction); a live one by
	when it listed. Same rule the map's fade uses, so a comp that looks fresh can
	never be filtered out as stale, or vice versa.
	"""
	if _is_active(row.get("status")):
		if row.get("listed_date"):
			return max(0, frappe.utils.date_diff(today, row["listed_date"]))
		dom = _num(row.get("days_on_market"))
		return dom if dom is not None else None
	if row.get("removed_date"):
		return max(0, frappe.utils.date_diff(today, row["removed_date"]))
	age = _num(row.get("days_old"))
	if age is not None and age > 0:
		return age
	if row.get("listed_date"):
		return max(0, frappe.utils.date_diff(today, row["listed_date"]))
	return None


def _coerce_filters(filters):
	"""Accept a dict or a JSON string (frappe hands whitelisted args either way)."""
	if not filters:
		return None
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except Exception:
			return None
	return filters if isinstance(filters, dict) else None


def _matches(row, f, today):
	"""Does one comp pass the filter set? Unknown values never silently fail.

	The importer coerces a missing number to 0, so 0 means "not known", not "zero
	bedrooms". A comp with an unknown year built is not evidence that it fails a
	year filter — excluding it would quietly drop real sales for missing metadata,
	so an unknown passes and the pin carries no claim about that fact.
	"""
	status = f.get("status")
	if status == "sold" and _is_active(row.get("status")):
		return False
	if status == "active" and not _is_active(row.get("status")):
		return False

	within = _num(f.get("within_days"))
	if within:
		days = _recency_days(row, today)
		if days is not None and days > within:
			return False

	for key, field in (
		("beds", "bedrooms"), ("baths", "bathrooms"),
		("sqft", "square_footage"), ("year", "year_built"), ("price", "price"),
	):
		val = _num(row.get(field))
		if not val:  # 0 / None == unknown
			continue
		lo, hi = _num(f.get(f"{key}_min")), _num(f.get(f"{key}_max"))
		if lo is not None and val < lo:
			return False
		if hi is not None and val > hi:
			return False

	types = f.get("property_types")
	if types:
		if isinstance(types, str):
			types = [types]
		wanted = {str(t).strip().lower() for t in types if str(t).strip()}
		if wanted:
			actual = str(row.get("property_type") or "").strip().lower()
			if actual and actual not in wanted:
				return False
	return True


def _widen(band, pct=None, flat=None, floor=None):
	"""Grow an interval by a fraction of it and/or a flat amount.

	The band is the SOURCE's interval, so widening a wide band stays wide: a
	seller who said "1000 - 2000 sqft" gets a looser filter than a listing that
	said 1406, which is the correct amount of confidence in each.
	"""
	if not band:
		return None, None
	lo, hi = band[0], band[1]
	span = (hi - lo) if hi is not None else 0
	base = hi if hi is not None else lo
	pad = 0.0
	if pct:
		pad += base * pct
	if flat:
		pad += flat
	lo_out = max(floor, lo - pad) if floor is not None else lo - pad
	hi_out = None if hi is None else hi + pad
	return round(lo_out, 2), (None if hi_out is None else round(hi_out, 2))


def _preset_tiers(facts, radius):
	"""Filters pre-set around THIS property, tightest first.

	Each tier is a complete filter set, not a delta, so what the UI shows is
	exactly what ran. The ladder exists because a strict "recent and similar"
	filter genuinely matches nothing on plenty of leads — our comps are a pooled
	area index, not a curated per-lead set — and an empty map with no explanation
	is worse than a loose one that says so.
	"""
	beds, baths = facts.get("beds_band"), facts.get("baths_band")
	sqft, year = facts.get("sqft_band"), facts.get("year_built_band")
	ptype = facts.get("property_type")
	has_shape = any((beds, baths, sqft, year))

	tiers = []

	def tier(key, label, within, b_pad, ba_pad, sq_pct, yr_pad, use_type):
		f = {"status": "all", "within_days": within, "radius_mi": radius}
		if b_pad is not None:
			f["beds_min"], f["beds_max"] = _widen(beds, flat=b_pad, floor=0)
		if ba_pad is not None:
			f["baths_min"], f["baths_max"] = _widen(baths, flat=ba_pad, floor=0)
		if sq_pct is not None:
			f["sqft_min"], f["sqft_max"] = _widen(sqft, pct=sq_pct, floor=0)
		if yr_pad is not None:
			f["year_min"], f["year_max"] = _widen(year, flat=yr_pad)
		if use_type and ptype:
			f["property_types"] = [ptype]
		tiers.append({"key": key, "label": label, "filters": f})

	if has_shape:
		tier("similar", _("Recent · similar"), 180, 1, 1, 0.25, 20, True)
		tier("wider", _("Last year · similar"), 365, 1, 1, 0.35, 30, True)
		tier("loose", _("Last 2 years · loosely similar"), 730, 2, None, 0.50, None, False)
	else:
		# Nothing is known about the subject, so "similar" has no meaning here and
		# pretending otherwise would filter on air. Recency is still real.
		tier("recent", _("Recent"), 180, None, None, None, None, False)
		tier("wider", _("Last year"), 365, None, None, None, None, False)
		tier("loose", _("Last 2 years"), 730, None, None, None, None, False)
	tiers.append({
		"key": "all",
		"label": _("Everything nearby"),
		"filters": {"status": "all", "radius_mi": radius},
	})
	return tiers


# ---------------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------------
@frappe.whitelist()
def get_lead_comps(lead, radius_mi=None, limit=None, filters=None, auto=0):
	"""Comps near a lead, nearest first, with the subject's real position.

	The bounding box is a cheap indexed pre-filter; haversine then trims the
	corners of that box to a true circle. Doing it the other way round would mean
	a full-table distance computation over every comp we hold.

	`filters` is the explicit filter set (the user has touched the controls).
	With none, and `auto`, the filters are DERIVED from the subject and walked down
	`_preset_tiers` until a tier yields a usable set — the response reports which
	tier that was so the UI can say so out loud.

	`auto` defaults OFF so this stays byte-compatible for any caller that predates
	the filters: no argument means the old "everything in radius" answer. Presets
	are opt-in by a caller that knows how to show and explain them, which is what
	lets this deploy independently of the frontend.
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
	subject = {"lat": lat, "lng": lng} if lat is not None else None
	if subject:
		# The facts the subject pin shows when clicked. Merged onto the same dict the
		# map already reads for lat/lng, so no caller has to learn a second shape.
		subject.update(_subject_facts(doc))
	base = {
		"lead": lead,
		"address": _full_address(doc),
		"subject": subject,
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
	# Explicit >=/<= rather than `between`: Frappe's `between` operator routes
	# through get_between_date_filter and treats its bounds as DATES, which turns a
	# numeric bounding box into malformed SQL.
	rows = frappe.get_all(
		DOCTYPE,
		filters=[
			[DOCTYPE, "lat", ">=", lat - dlat],
			[DOCTYPE, "lat", "<=", lat + dlat],
			[DOCTYPE, "lng", ">=", lng - dlng],
			[DOCTYPE, "lng", "<=", lng + dlng],
		],
		fields=[
			"name", "address", "city", "state", "zip", "lat", "lng", "price", "status",
			"listed_date", "removed_date", "days_on_market", "days_old",
			"bedrooms", "bathrooms", "square_footage", "year_built", "property_type",
		],
		limit_page_length=5000,
	)

	today = frappe.utils.today()
	self_key = (subject or {}).get("self_comp_key")
	out = []
	for row in rows:
		if row.lat is None or row.lng is None:
			continue
		# The subject's own listing is not a comparable for itself. It sits at
		# distance 0 and used to render as a pill directly under the subject dot,
		# quietly inflating the count and comping the house against itself.
		if self_key and row.name == self_key:
			continue
		dist = _haversine_mi(lat, lng, row.lat, row.lng)
		if dist > radius:
			continue
		row = dict(row)
		row["distance_mi"] = round(dist, 2)
		# Computed while the dates are still dates, and returned so the client can
		# show "3 mo ago" without re-deriving "recent" a second, divergent way.
		row["recency_days"] = _recency_days(row, today)
		# Dates are returned raw; the client derives the recency fade so the map and
		# any future report can't disagree about what "recent" means.
		for key in ("listed_date", "removed_date"):
			if row.get(key):
				row[key] = str(row[key])
		out.append(row)

	out.sort(key=lambda r: r["distance_mi"])
	base["total_in_radius"] = len(out)

	explicit = _coerce_filters(filters)
	if explicit is not None:
		# The user drove the controls: run exactly what they asked for, even if it
		# matches nothing. Quietly widening someone's deliberate filter is how a
		# tool stops being trusted.
		matched = [r for r in out if _matches(r, explicit, today)]
		base["filters"] = explicit
		base["preset"] = None
		base["relaxed"] = False
	elif int(auto or 0):
		tiers = _preset_tiers(base["subject"] or {}, radius)
		matched, chosen = [], tiers[-1]
		for t in tiers:
			hits = [r for r in out if _matches(r, t["filters"], today)]
			# Take the first tier that clears the bar. A looser tier is a superset,
			# so this is the tightest usable set by construction.
			if len(hits) >= MIN_USABLE_COMPS:
				matched, chosen = hits, t
				break
			if t is tiers[-1]:
				matched, chosen = hits, t
		base["filters"] = chosen["filters"]
		base["preset"] = {"key": chosen["key"], "label": chosen["label"]}
		# "Relaxed" means we could NOT honour the recent-and-similar default, which
		# is the thing the user has to be told rather than left to infer from a map
		# full of comps that do not resemble the subject.
		base["relaxed"] = chosen["key"] != tiers[0]["key"]
		base["fell_through"] = chosen["key"] == "all"
	else:
		matched = out
		base["filters"] = {"status": "all", "radius_mi": radius}
		base["preset"] = None
		base["relaxed"] = False

	base["total_matched"] = len(matched)
	base["comps"] = matched[:cap]
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
	# Frappe declares Int/Float/Currency columns NOT NULL, but plenty of comps are
	# missing a year built or a lot size. Coerce to 0 rather than dropping the row:
	# a comp with an unknown year is still a valid sale at a known price and place,
	# and 0 is falsy so the popup simply omits the fact instead of printing "0".
	NUMERIC = {
		"lat", "lng", "price", "days_on_market", "days_old",
		"bedrooms", "bathrooms", "square_footage", "year_built", "correlation",
	}
	# Dates stay nullable (a live listing has no removal date); text stays "".
	NULLABLE = {"listed_date", "removed_date"}

	def cell(col, value):
		if value is None:
			return None if col in NULLABLE else (0 if col in NUMERIC else "")
		return value
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
			rows.append([key, key, now, now, user, user] + [cell(c, rec.get(c)) for c in cols])
			stats["written"] += 1
			if len(rows) >= int(chunk):
				flush(rows)
				rows = []
	flush(rows)
	stats["ok"] = True
	stats["dry_run"] = bool(dry_run)
	stats["total_in_db"] = frappe.db.count(DOCTYPE) if not dry_run else None
	return stats
