# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""BatchData comps — the fallback for leads our pooled index cannot cover.

Why this exists
---------------
`crm.api.comps` serves a POOLED AREA INDEX of iSpeedToLead/RentCast comparables.
It covers most of the book, but not all of it: sampling the 45 most recent leads,
**8 (18%) returned zero comps** — Albany/Brooklyn/Rochester NY, High Point and
Glade Valley NC, Avondale AZ, Newnan GA, Warsaw MO. Those reps open the map and
get nothing at all, which is the one outcome `comps.py` set out to avoid.

This module fills exactly that hole and nothing else. It is a FALLBACK, not a
second opinion: if the local index returned anything, we do not spend money here.

Deliberately NOT gated on non-disclosure states
-----------------------------------------------
The original ask was "use this where pricing doesn't show up", on the theory that
Texas comps lack sale prices. That was checked and is false: all 67,679 CRM Comp
rows carry a price, TX included at 100%, and TX has our BEST coverage (~168 comps
per lead vs ~26 for MN). Four TX leads returned 200 / 107 / 13 / 158 comps, all
priced. The real gap is **zero coverage**, and it is geography-agnostic — none of
the eight empty leads above are in a non-disclosure state. So the trigger is
"the local index gave us nothing", not "which state is this".

What it costs
-------------
Billing is PER ROW RETURNED at the sum of the datasets enabled on the token. The
`comps` token (Basic Property Data + Comparable Properties) measured at
**$0.03/row**, verified by wallet-balance deltas. At `take=10` that is **$0.30**
per lead that would otherwise show an empty map. ~18% of leads x ~417/mo, if every
one were opened, is ~$22/mo — and the cache below means each lead is paid for once,
ever.

The sale-date window is applied SERVER-SIDE (`sale.lastSaleDate.minDate/maxDate`),
so we only pay for rows already inside it rather than buying 25 and discarding the
stale ones. Measured: 24% cheaper for the same answer.

Caching, including the empty answer
-----------------------------------
Same rule the Zillow cache learned the hard way: **a miss is cached too.** An
address BatchData cannot match would otherwise be re-billed on every modal open.
Stored on the lead with `update_modified=False`, because a cached lookup is not a
human edit.
"""

import json
import time
import urllib.error
import urllib.request

import frappe
from frappe import _

API_BASE = "https://api.batchdata.com/api/v1"

#: Cheap, purpose-built token: Basic Property Data + Comparable Properties ONLY.
#: Do NOT point this at the general BatchData key — that one carries all 13
#: datasets and bills $0.64/row, 21x more, for data this feature never reads.
CONF_KEY = "batchdata_comps_api_key"

#: Lance's call: "pull the most similar five-ten". Ten is the top of that range
#: and still only $0.30. take=25 was tried (better median $/sf on one Brooklyn
#: lead) and then capped back — we are billed per row returned, so 25 is $0.75
#: on a fallback that already only fires when ISTL and Zillow solds both failed.
#: KEEP still ranks down to 6 for the map; take is only how many we BUY.
DEFAULT_TAKE = 10

#: Hard ceiling on how far a "comp" may be. `compAddress` has NO radius control
#: and has been observed matching out to ~3mi, so this is enforced by us or not at
#: all. It DROPS rather than pads: four honest comps beat ten with three from
#: across town.
MAX_MILES = 2.0

#: How many survive ranking and reach the map.
KEEP = 6

#: Two years, not one. Measured on a real San Antonio subject: a 12-month window
#: left 3 usable comps and read ~4% low, while 2 years gave 9-11 and converged.
#: "No limit" is also wrong — decade-old sales drag the median down.
SALE_WINDOW_DAYS = 730

#: Shown to the rep in the provenance banner. Says only the WINDOW — both callers
#: already say "recorded sales", and repeating it read as
#: "recorded sales from BatchData (recorded sales, last 2 years)".
WINDOW_LABEL = "last 2 years"

#: Cache fields on CRM Lead. Absent until the ops script adds them, in which case
#: the whole feature degrades quietly — same contract as `comps._state_supported`.
CACHE_FIELD = "batchdata_comps"
CACHE_STAMP_FIELD = "batchdata_comps_fetched_at"

#: A found answer is stable — comps do not un-sell. A MISS is re-checked sooner,
#: because "no comparable sales yet" is a statement about time, not about the
#: property, and a new subdivision gets its first sales eventually.
HIT_TTL_DAYS = 90
MISS_TTL_DAYS = 14

HTTP_TIMEOUT = 20


def _api_key() -> str:
	return frappe.conf.get(CONF_KEY) or ""


def _cache_supported() -> bool:
	return frappe.db.has_column("CRM Lead", CACHE_FIELD) and frappe.db.has_column(
		"CRM Lead", CACHE_STAMP_FIELD
	)


def available() -> bool:
	"""True when this fallback can actually run. Callers degrade quietly."""
	return bool(_api_key())


# ---------------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------------
def _cached(doc):
	"""Prior answer for this lead, or None when there is nothing usable on file."""
	if not _cache_supported() or not doc.get(CACHE_FIELD):
		return None
	try:
		payload = json.loads(doc.get(CACHE_FIELD))
	except Exception:
		return None
	if not isinstance(payload, dict):
		return None

	age_days = (time.time() - float(payload.get("t") or 0)) / 86400.0
	ttl = HIT_TTL_DAYS if payload.get("comps") else MISS_TTL_DAYS
	if age_days > ttl:
		return None
	return payload


def _store(doc, comps):
	if not _cache_supported():
		return
	payload = {"t": time.time(), "comps": comps}
	try:
		frappe.db.set_value(
			"CRM Lead",
			doc.name,
			{
				CACHE_FIELD: json.dumps(payload),
				CACHE_STAMP_FIELD: frappe.utils.now(),
			},
			# A cached lookup is not a human edit — same rule as the geocode and
			# Zillow caches, so `modified` keeps meaning "a person touched this".
			update_modified=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "BatchData comps: cache write failed")


# ---------------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------------
def _post(path, body):
	req = urllib.request.Request(
		API_BASE + path,
		data=json.dumps(body).encode(),
		headers={
			"Authorization": "Bearer {0}".format(_api_key()),
			"Content-Type": "application/json",
		},
	)
	with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
		return json.loads(resp.read().decode())


def _window():
	today = frappe.utils.getdate()
	since = frappe.utils.add_days(today, -SALE_WINDOW_DAYS)
	return str(since), str(today)


def _num(v):
	try:
		n = float(v)
	except (TypeError, ValueError):
		return None
	return n if n == n else None  # NaN guard


def _shape(row, idx):
	"""Normalize one BatchData property into the row shape `comps.py` already emits.

	Returning the SAME keys means the map, the table and the pill grammar all work
	untouched — this is a data source swap, not a UI feature.
	"""
	addr = row.get("address") or {}
	bld = row.get("building") or {}
	sale = ((row.get("sale") or {}).get("lastSale")) or {}
	price = _num(sale.get("price"))
	sold = str(sale.get("saleDate") or "")[:10] or None

	street = addr.get("street") or ""
	city = addr.get("city") or ""
	state = addr.get("state") or ""
	zipc = addr.get("zip") or ""
	label = ", ".join([p for p in (street, city, "{0} {1}".format(state, zipc).strip()) if p])

	return {
		# Namespaced so it can never collide with a real CRM Comp docname, and so
		# `set_comp_state` (which writes docnames) visibly does not apply to these.
		"name": "batchdata::{0}".format(row.get("_id") or idx),
		"address": label,
		"lat": _num(addr.get("latitude")),
		"lng": _num(addr.get("longitude")),
		"price": price,
		# BatchData returns recorded/closed sales, so these are never live listings.
		"status": "Inactive",
		# And unlike the pooled ISTL index, these genuinely ARE closed transactions,
		# so they earn the word "sold" rather than the weaker "off-market".
		"listing_state": "sold",
		"listed_date": None,
		"removed_date": sold,
		"days_on_market": None,
		"days_old": None,
		"bedrooms": _num(bld.get("bedroomCount")),
		"bathrooms": _num(bld.get("bathroomCount")),
		"square_footage": _num(bld.get("livingAreaSquareFeet")),
		"year_built": _num(bld.get("yearBuilt")),
		"property_type": (row.get("general") or {}).get("propertyTypeDetail"),
		# Provenance. The UI can badge these as bought-in rather than pooled, and
		# anyone reading the payload can tell where a number came from.
		"source": "batchdata",
	}


def fetch_for_lead(doc, take=DEFAULT_TAKE, force=False):
	"""Comps for a lead from BatchData, cached. Returns [] when unavailable.

	Never raises: a comps map that renders without the fallback is a far better
	outcome than a 500 on a lead detail page.
	"""
	if not available():
		return []

	if not force:
		hit = _cached(doc)
		if hit is not None:
			return hit.get("comps") or []

	street = (doc.get("property_address") or "").split(",")[0].strip()
	city = (doc.get("property_city") or "").strip()
	state = (doc.get("property_state") or "").strip()
	zipc = str(doc.get("property_zip") or "").strip()
	if not street or not (zipc or (city and state)):
		return []

	since, until = _window()
	body = {
		"searchCriteria": {
			"compAddress": {"street": street, "city": city, "state": state, "zip": zipc},
			# minDate/maxDate is the ONLY accepted shape here. min/max, start/end,
			# from/to, gte/lte and ISO datetimes all fail with "Invalid Date", and
			# an unrecognised key is SILENTLY IGNORED — which would mean paying for
			# stale rows and never being told.
			"sale": {"lastSaleDate": {"minDate": since, "maxDate": until}},
		},
		"options": {"take": int(take), "skip": 0},
	}

	try:
		raw = _post("/property/search", body)
	except urllib.error.HTTPError as e:
		detail = ""
		try:
			detail = e.read().decode()[:200]
		except Exception:
			pass
		# 403 means two very different things on this API and they need different
		# human responses: an empty wallet is an ops problem, a scope problem is a
		# token problem. Say which.
		if e.code == 403 and "insufficient balance" in detail.lower():
			frappe.log_error(detail, "BatchData comps: WALLET EMPTY - top up to re-enable")
			# The Error Log is where this went to die: 24 of these accumulated over a
			# week while reps' tax pulls failed and nobody knew. Tell a person.
			try:
				from crm.api import batchdata_wallet

				batchdata_wallet.report_wallet_empty("comps fallback")
			except Exception:
				frappe.log_error(frappe.get_traceback(), "BatchData comps: alert failed")
		else:
			frappe.log_error(detail, "BatchData comps: HTTP {0}".format(e.code))
		return []
	except Exception:
		frappe.log_error(frappe.get_traceback(), "BatchData comps: request failed")
		return []

	rows = ((raw.get("results") or {}).get("properties")) or []
	comps = [_shape(r, i) for i, r in enumerate(rows)]
	# Only rows we can actually place on a map and price are worth showing; the
	# rest still cost us, which is why the window is applied server-side.
	comps = [c for c in comps if c["lat"] is not None and c["lng"] is not None and c["price"]]

	# Cached even when empty — otherwise an unmatched address is re-billed on every
	# single modal open.
	_store(doc, comps)
	return comps
