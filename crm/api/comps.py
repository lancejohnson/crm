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
The comps themselves are iSpeedToLead's (RentCast-derived) last *asks*, imported
from the LeadMarket inventory by `import_comps_file`. ISTL uses RentCast internally;
we never call the RentCast API. They carry a full street address but no
coordinates, so the importer ships them pre-geocoded.

On every map open we then ask Zillow whether anything is more recent: a ZIP-level
RecentlySold + ForSale search (A), and `/property` on the nearest ISTL pins (B).
See `crm.api.zillow_comps`. BatchData remains the last resort when the pooled
index is empty even after that.

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

#: Default recency window for OFF-MARKET comps. A sale older than a year is a
#: different market, so the preset never reaches further back than this until the
#: ladder is forced to. Active listings are deliberately exempt — see `_matches`.
DEFAULT_WITHIN_DAYS = 365

#: Clicking a comp can spend two shared RapidAPI requests (property + photos), so
#: keep the normalized result rather than paying again every time another setter
#: opens the same house. A failed/partial lookup gets a short retry window.
DETAIL_CACHE_SECONDS = 30 * 24 * 60 * 60
DETAIL_RETRY_SECONDS = 60 * 60
DETAIL_CACHE_VERSION = 1

#: Per-lead, TEAM-WIDE record of which comps a human hid or picked. Not per-user:
#: a junk comp is junk for everyone, and "the comps we used" is a deal artifact
#: the next person to open the lead needs to see.
HIDDEN_FIELD = "comps_hidden"
SELECTED_FIELD = "comps_selected"

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

	1. ZILLOW (`crm.api.zillow`) — real numbers for beds/baths/sqft/year/type, and a
	   genuine last SALE out of priceHistory's Public Record rows
	2. its own listing in the comp inventory (real numbers, but a last ASK, and
	   present for only ~5% of leads)
	3. the iSpeedToLead pick-list fields on the lead (bands, not numbers)
	4. the BatchData tax pull (assessed value / annual tax), already on the lead

	Every fact carries the source it came from, because "3 bd" from Zillow, from a
	listing record, and typed into a web form by a motivated seller are not the same
	claim — and the preset filters widen according to which one it is.
	"""
	listing = _self_listing(doc)
	zillow = None
	try:
		from crm.api import zillow as zillow_api

		zillow = zillow_api.facts_for_lead(doc)
	except Exception:
		# A third-party lookup must never take the comps map down with it.
		frappe.log_error(frappe.get_traceback(), "Comps: Zillow facts failed")
	facts = {"source": {}}

	def take(key, lead_field, listing_field=None, zillow_key=None, unit=""):
		z = (zillow or {}).get(zillow_key or key)
		listing_val = (listing or {}).get(listing_field or lead_field)
		if z:
			band = (float(z), float(z), True)
			facts["source"][key] = "zillow"
		elif listing_val:  # importer coerces missing numerics to 0, so 0 == unknown
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

	# Each fact falls through INDEPENDENTLY: Zillow returns null for a fact it lacks
	# (measured — a home with bathrooms but no bedrooms), so picking one source for
	# the whole set would throw away good data from the others.
	take("beds", "bedrooms")
	take("baths", "bathrooms")
	take("sqft", "square_footage", zillow_key="sqft")
	take("year_built", "year_built")

	z_type = (zillow or {}).get("property_type")
	ptype = z_type or (listing or {}).get("property_type") or None
	facts["property_type"] = ptype
	if ptype:
		facts["source"]["property_type"] = "zillow" if z_type else "listing"

	# The headline: what it actually SOLD for, and when. A Public Record transaction
	# out of Zillow's priceHistory is a far stronger claim than the comp inventory's
	# last ask, so it is kept separate and labelled a sale rather than folded in.
	facts["last_sale"] = (zillow or {}).get("last_sale") or None
	facts["zestimate"] = (zillow or {}).get("zestimate") or None
	facts["rent_zestimate"] = (zillow or {}).get("rent_zestimate") or None
	facts["lot_size"] = (zillow or {}).get("lot_size") or None
	facts["zpid"] = (zillow or {}).get("zpid") or None
	facts["has_zillow"] = bool(zillow)
	# May be "" here: leads cached before `cover_photo` was carried have no key.
	# `get_lead_comps` fills the gap from the area search's self-match afterwards,
	# so neither path spends a request on a picture.
	facts["cover_photo"] = (zillow or {}).get("cover_photo") or ""

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
	# BatchData's assessed value costs $0.10 a pull and is only fetched on demand;
	# Zillow ships one with the facts we already have, so it fills the gap for free.
	if not facts.get("assessed_value") and (zillow or {}).get("tax_assessed_value"):
		facts["assessed_value"] = zillow["tax_assessed_value"]
		facts["source"]["assessed_value"] = "zillow"
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

	# Recency gates OFF-MARKET comps ONLY. A sale from three years ago is a
	# different market, but a house that has sat on the market for 18 months is
	# live evidence about what is being asked TODAY — dropping it for being "old"
	# would hide exactly the stale listings that tell you the area is not moving.
	within = _num(f.get("within_days"))
	if within and not _is_active(row.get("status")):
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

	# The window opens at 12 months and STAYS there while the shape loosens: a
	# poorly-matching sale from this year beats a well-matching one from 2022, so
	# similarity is spent before recency is.
	if has_shape:
		tier("similar", _("Last 12 months · similar"), DEFAULT_WITHIN_DAYS, 1, 1, 0.25, 20, True)
		tier("wider", _("Last 12 months · wider"), DEFAULT_WITHIN_DAYS, 1, 1, 0.35, 30, True)
		tier("loose", _("Last 2 years · loosely similar"), 730, 2, None, 0.50, None, False)
	else:
		# Nothing is known about the subject, so "similar" has no meaning here and
		# pretending otherwise would filter on air. Recency is still real.
		tier("recent", _("Last 12 months"), DEFAULT_WITHIN_DAYS, None, None, None, None, False)
		tier("loose", _("Last 2 years"), 730, None, None, None, None, False)
	tiers.append({
		"key": "all",
		"label": _("Everything nearby"),
		"filters": {"status": "all", "radius_mi": radius},
	})
	return tiers


# ---------------------------------------------------------------------------------
# Human judgement: hidden / selected comps
# ---------------------------------------------------------------------------------
def _state_supported() -> bool:
	"""False until the ops script adds the fields; everything degrades quietly."""
	return frappe.db.has_column("CRM Lead", HIDDEN_FIELD) and frappe.db.has_column(
		"CRM Lead", SELECTED_FIELD
	)


def _load_list(doc, field):
	raw = doc.get(field)
	if not raw:
		return []
	try:
		val = json.loads(raw)
		return [str(x) for x in val] if isinstance(val, list) else []
	except Exception:
		return []


def _comp_state(doc):
	"""(hidden, selected) as sets of comp docnames for this lead."""
	if not _state_supported():
		return set(), set()
	return set(_load_list(doc, HIDDEN_FIELD)), set(_load_list(doc, SELECTED_FIELD))


@frappe.whitelist()
def set_comp_state(lead, comp, state):
	"""Mark one comp as `selected`, `hidden`, or `none` for this lead.

	Deliberately TEAM-WIDE rather than per-user: a comp that is obviously not
	comparable is wrong for everyone, and the set someone actually priced the deal
	on is a deal artifact the next person needs to see, not a private view setting.

	The two states are mutually exclusive — picking a comp you hid un-hides it,
	which is the only sane reading of the two clicks.
	"""
	_guard()
	if state not in ("selected", "hidden", "none"):
		frappe.throw(_("Unknown comp state {0}").format(state))
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead {0} does not exist.").format(lead), frappe.DoesNotExistError)
	if not _state_supported():
		return {"ok": False, "error": "comps_hidden/comps_selected fields are missing"}

	doc = frappe.get_doc("CRM Lead", lead)
	hidden, selected = _comp_state(doc)
	comp = str(comp)
	hidden.discard(comp)
	selected.discard(comp)
	if state == "hidden":
		hidden.add(comp)
	elif state == "selected":
		selected.add(comp)

	# db.set_value, not doc.save: this is a view judgement on a lead, and running
	# the whole CRM Lead save path (SLA, hooks, assignment) for it would be absurd.
	frappe.db.set_value(
		"CRM Lead", lead,
		{
			HIDDEN_FIELD: json.dumps(sorted(hidden)),
			SELECTED_FIELD: json.dumps(sorted(selected)),
		},
		update_modified=False,
	)
	return {"ok": True, "hidden": len(hidden), "selected": len(selected), "state": state}


# ---------------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------------
def _detail_cache_key(comp):
	return f"crm:comp-detail:v{DETAIL_CACHE_VERSION}:{comp}"


def _shape_detail(row):
	"""Fetch and normalize one comp only after a person explicitly opens it."""
	from crm.api import zillow as zillow_api

	if str(row.get("name") or "").startswith("zillow::"):
		zpid = str(row.name).split("::", 1)[1]
		raw = zillow_api._request("/property", {"zpid": zpid}, "Zillow: zpid lookup failed")
	else:
		raw = zillow_api.property_details(row.address)
	details = zillow_api.normalize_detail(raw) if raw else None
	photo_raw = zillow_api.property_photos(details.get("zpid")) if details else None
	photos = zillow_api.photo_urls(photo_raw)
	if details and details.get("cover_photo") and not photos:
		photos = [details["cover_photo"]]

	comp = dict(row)
	for key in ("listed_date", "removed_date"):
		if comp.get(key):
			comp[key] = str(comp[key])
	return {
		"available": bool(details),
		"comp": comp,
		"details": details,
		"photos": photos,
		"photos_available": photo_raw is not None,
		"message": "" if details else _("Zillow details are unavailable for this property."),
	}


@frappe.whitelist()
def get_comp_details(lead, comp):
	"""On-demand Zillow facts + scrollable photos for one comp.

	The compact Today view already has the comparison facts from `CRM Comp`; this
	endpoint is deliberately lazy so merely opening a lead never spends one or two
	third-party calls PER HOUSE. Results are cached by the immutable comp name for
	30 days. Access remains sales-role gated and the lead anchor must be real.
	"""
	_guard()
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead {0} does not exist.").format(lead), frappe.DoesNotExistError)
	if not _available():
		return {"available": False, "comp": None, "details": None, "photos": []}

	if str(comp).startswith("zillow::"):
		# Area-search pins are not CRM Comp rows. _shape_detail looks them up by zpid.
		row = frappe._dict({"name": comp, "address": ""})
	else:
		row = frappe.db.get_value(
			DOCTYPE,
			comp,
			[
				"name", "address", "city", "state", "zip", "price", "status",
				"listed_date", "removed_date", "days_on_market", "days_old",
				"bedrooms", "bathrooms", "square_footage", "year_built", "property_type",
			],
			as_dict=True,
		)
	if not row:
		frappe.throw(_("Comparable property {0} does not exist.").format(comp), frappe.DoesNotExistError)

	key = _detail_cache_key(comp)
	cached = frappe.cache().get_value(key)
	if isinstance(cached, dict):
		return {**cached, "cached": True}

	result = _shape_detail(row)
	result["cached"] = False
	# A complete photo response is stable property data. A quota/outage partial is
	# useful now but should retry soon rather than hiding photos for a month.
	ttl = DETAIL_CACHE_SECONDS if result.get("available") and result.get("photos_available") else DETAIL_RETRY_SECONDS
	frappe.cache().set_value(key, result, expires_in_sec=ttl)
	# Do not read the cache again in this request: Frappe memoizes cache misses in
	# `frappe.local.cache`, and an expiring set does not replace that local miss.
	return result


@frappe.whitelist()
def get_lead_comps(lead, radius_mi=None, limit=None, filters=None, auto=0, include_hidden=0):
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
		# Comps a human discarded. Never merged into `comps` — see the pool filter
		# below. Present as [] so the client can render it without a guard.
		"discarded": [],
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
	hidden, selected = _comp_state(doc)
	base["selected"] = sorted(selected)
	base["hidden"] = sorted(hidden)
	base["state_supported"] = _state_supported()
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
		row["source"] = row.get("source") or "istl"
		# The pooled index holds no imagery. The key exists from the start so the
		# client never has to special-case its absence; the Zillow merge fills it in
		# for any pin it can match, and the rest render a placeholder.
		row.setdefault("photo", "")
		row["selected"] = row["name"] in selected
		row["hidden"] = row["name"] in hidden
		# Computed while the dates are still dates, and returned so the client can
		# show "3 mo ago" without re-deriving "recent" a second, divergent way.
		row["recency_days"] = _recency_days(row, today)
		# Dates are returned raw; the client derives the recency fade so the map and
		# any future report can't disagree about what "recent" means.
		for key in ("listed_date", "removed_date"):
			if row.get(key):
				row[key] = str(row[key])
		out.append(row)

	# ISTL asks go stale. Check Zillow for newer sales/listings around the
	# subject, and refresh the nearest ISTL pins' sale dates, before we count
	# or filter. Soft: an outage leaves `out` as the pooled index.
	try:
		from crm.api import zillow_comps

		base["zillow"] = zillow_comps.apply(doc, out, lat, lng, radius)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Comps: Zillow refresh failed")
		base["zillow"] = {"used": False, "reason": "error"}

	# Subject photo, cheapest source first: the facts we already cached, else the
	# self-match the area search threw away. Both are free; neither is worth a
	# billed lookup, so an unmatched subject simply shows no photo.
	if base.get("subject") is not None and not base["subject"].get("cover_photo"):
		base["subject"]["cover_photo"] = (base.get("zillow") or {}).get("subject_photo") or ""

	for row in out:
		row["selected"] = row["name"] in selected
		row["hidden"] = row["name"] in hidden

	out.sort(key=lambda r: r["distance_mi"])

	# BatchData only when BOTH sources failed to produce a priced sale:
	#   no ISTL pins in radius, AND Zillow RecentlySold came back with no prices
	#   (non-disclosure). Zillow for-sale listings do not count — an ask is not
	#   a sale. ISTL last-asks DO count: if the pool has anything, we do not spend.
	istl = [r for r in out if r.get("source") == "istl"]
	zillow_solds = [
		r for r in out
		if r.get("price")
		and r.get("source") == "zillow"
		and str(r.get("status") or "").lower() != "active"
	]
	if istl:
		base["fallback"] = {"source": "batchdata", "used": False, "reason": "istl_has_comps"}
	elif zillow_solds:
		base["fallback"] = {"source": "batchdata", "used": False, "reason": "zillow_has_prices"}
	else:
		base["fallback"] = _batchdata_fallback(doc, base, merge_into=out)
		out.sort(key=lambda r: r["distance_mi"])

	base["total_in_radius"] = len(out)

	# A comp a human hid is gone from every count and every tier decision — leaving
	# it in the pool would let junk keep a tier "usable" and suppress the widening
	# that the rep actually needs.
	hidden_here = [r for r in out if r["hidden"]]
	base["hidden_count"] = len(hidden_here)
	# ALWAYS removed from the pool, whatever the caller asked for. `include_hidden`
	# used to merge them back in here, which quietly let discarded junk keep a tier
	# "usable" and suppress the widening the rep needed. Discards now travel in
	# their own list so the tray can gray them out and offer an undo without ever
	# touching the ladder, the counts, or what gets underwritten.
	out = [r for r in out if not r["hidden"]]
	if int(include_hidden or 0):
		base["discarded"] = sorted(hidden_here, key=lambda r: r["distance_mi"])[:cap]

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

	# An explicit human pick outranks any derived filter: a comp someone marked as
	# one they are pricing off must not vanish because the preset later tightened.
	# Same principle as the Today board — the machine decides what LANDS, the human
	# owns it afterwards.
	if selected:
		seen = {r["name"] for r in matched}
		pinned = [r for r in out if r["selected"] and r["name"] not in seen]
		if pinned:
			matched = sorted(matched + pinned, key=lambda r: r["distance_mi"])
	base["selected_count"] = sum(1 for r in matched if r["selected"])

	base["total_matched"] = len(matched)
	base["comps"] = matched[:cap]
	return base


def _batchdata_fallback(doc, base, merge_into=None):
	"""Fill an empty comps map from BatchData. Returns a small status dict.

	Split out so the paid path is one obvious, greppable place rather than an inline
	branch someone later widens by accident.
	"""
	from crm.api import batchdata_comps

	if not batchdata_comps.available():
		return {"source": "batchdata", "used": False, "reason": "not_configured"}

	try:
		comps = batchdata_comps.fetch_for_lead(doc)
	except Exception:
		# A comps map that renders without the fallback beats a 500 on lead detail.
		frappe.log_error(frappe.get_traceback(), "BatchData comps fallback failed")
		return {"source": "batchdata", "used": False, "reason": "error"}

	if not comps:
		return {"source": "batchdata", "used": True, "count": 0}

	lat, lng = base["subject"]["lat"], base["subject"]["lng"]
	for c in comps:
		c["distance_mi"] = round(_haversine_mi(lat, lng, c["lat"], c["lng"]), 2)
		c["selected"] = False
		c["hidden"] = False
		# BatchData sells records, not imagery.
		c.setdefault("photo", "")
		c["recency_days"] = _recency_days(c, frappe.utils.today())

	# BatchData applies no radius and returns no similarity score, so both are ours
	# to impose. Drop first: a comp 2.8mi away is not a comp here, and padding the
	# list with one is worse than showing five.
	comps = [c for c in comps if c["distance_mi"] <= batchdata_comps.MAX_MILES]

	# Then rank on shape, not just proximity. Distance still dominates because it is
	# the one fact always present; sqft and beds are frequently missing, and a
	# missing fact must not score as a bad match or every sparse row sinks.
	subj = base.get("subject") or {}
	s_sqft, s_beds, s_year = subj.get("sqft"), subj.get("beds"), subj.get("year_built")

	def _fit(c):
		score = c["distance_mi"] * 2.0
		if s_sqft and c.get("square_footage"):
			score += abs(c["square_footage"] - s_sqft) / max(s_sqft, 1) * 1.5
		if s_beds and c.get("bedrooms"):
			score += abs(c["bedrooms"] - s_beds) * 0.3
		if s_year and c.get("year_built"):
			score += min(abs(c["year_built"] - s_year) / 50.0, 1.0) * 0.3
		return score

	comps.sort(key=_fit)
	comps = comps[: batchdata_comps.KEEP]
	comps.sort(key=lambda r: r["distance_mi"])

	if merge_into is not None:
		try:
			from crm.api.zillow_comps import merge_key
		except Exception:
			merge_key = lambda a: (a or "").strip().lower()
		seen = {merge_key(r.get("address") or "") for r in merge_into}
		for c in comps:
			k = merge_key(c.get("address") or "")
			if k in seen:
				continue
			seen.add(k)
			merge_into.append(c)
	else:
		# Pre-merge callers (none left) still get a standalone list.
		base["comps"] = comps
		base["total_matched"] = len(comps)
		base["total_in_radius"] = len(comps)
	return {
		"source": "batchdata",
		"used": True,
		"count": len(comps),
		"basis": batchdata_comps.WINDOW_LABEL,
	}


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
