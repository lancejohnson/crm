# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Subject-property facts from Zillow, for the comps map.

Why this exists
---------------
The comps map compares a lead against nearby sales, but until now it could barely
describe the lead itself. The two sources it had are both weak:

  * the lead's own iSpeedToLead fields are pick-list LABELS, not numbers
    ("3 Bedroom", "1000 - 2000", "1900-1950"), so a "similar" filter built from
    them is a wide guess;
  * the property's own row in our comp inventory carries real numbers, but only
    ~5% of leads have one, and its price is the last ASK, not a sale.

Zillow answers both. `/property?address=` resolves our ordinary address strings
and returns real beds / baths / living area / year built / type / coordinates,
plus `priceHistory` — which contains genuine `event: "Sold"` rows sourced from
Public Record. That is an actual transaction with a date, which is what a rep
means by "what did it last sell for".

Cost, and the SHARED key
------------------------
OUR spend here is small: one lookup per lead, cached 30 days, so ~764 leads is a
few hundred requests a month even if every lead is opened.

The plan itself is a RapidAPI "Ultra" tier, 57,000 requests per billing cycle,
renewing on the 14th (anniversary-billed, not the 1st). That ceiling is NOT our
budget though — **the key is shared**. `istl-buyer/src/zillow_api.py` runs a
background ZIP-market job against the identical key (Infisical exposes it twice,
as `RAPIDAPI_ZILLOW_API_KEY` and `ZILLOW_RAPIDAPI_KEY` — verified byte-identical),
and it is the heavy consumer: 8,414 of 57,000 were already spent the day this
shipped, ~350/day, against ~10 from the CRM.

That job stops at `QUOTA_RESERVE = 5_000` remaining, commented "leave headroom
for the other Zillow-backed app that shares this RapidAPI key" — that app is now
us. So the CRM may use the band istl-buyer deliberately refuses to touch, but it
keeps its own smaller floor so a runaway loop here can never zero the account for
both apps.

One lookup per lead is plenty, so the normalized result is cached on the lead and
only refetched past CACHE_DAYS or when explicitly forced. Everything is
`has_field`-guarded, so the app is safe to deploy before the ops script adds the
cache fields — it just refetches each time until they exist.

Every failure path is soft. A Zillow outage, a quota exhaustion or an address
Zillow cannot resolve must degrade the popup back to the older sources, never
break the comps map.
"""

import json
import time

import frappe
from frappe import _

HOST = "us-property-market1.p.rapidapi.com"
BASE = f"https://{HOST}"

#: Property facts barely move; a sale a week old is still news next month.
CACHE_DAYS = 30
TIMEOUT = 20

#: Stop fetching once the SHARED plan is this close to empty. Deliberately far
#: below istl-buyer's 5,000 reserve: that reserve exists to leave room for THIS
#: app, so matching it would strand 5,000 requests neither app is willing to
#: spend. Below this floor the comps map degrades to its older fact sources
#: rather than taking the last of a budget the ZIP-market job may still need.
QUOTA_RESERVE = 500
#: RapidAPI reports remaining quota on every response, so caching it briefly
#: makes the guard free — and it reflects the OTHER app's spending too.
#:
#: GOTCHA — this is stored WITHOUT `expires_in_sec`, and freshness is judged from
#: a timestamp we store alongside it. `frappe.cache().get_value()` memoizes a MISS
#: as None into the per-request `frappe.local.cache`, while
#: `set_value(..., expires_in_sec=...)` writes only to Redis — so the poisoned
#: local None then shadows the value that is demonstrably sitting in Redis, and
#: the guard silently never fires. (`get_value(..., expires=True)` does NOT help;
#: it checks the local dict first regardless.) Storing with no TTL populates the
#: local cache too, which overwrites the poisoned entry.
_QUOTA_KEY = "zillow_quota_remaining"
_QUOTA_TTL = 900

#: Zillow's enum -> the vocabulary our comp inventory uses, so the subject's type
#: can be fed straight into the comps "Type" filter and actually match.
#: (Measured comp values: Single Family, Townhouse, Condo, Multi-Family,
#: Manufactured, Land, Apartment.)
HOME_TYPES = {
	"SINGLE_FAMILY": "Single Family",
	"TOWNHOUSE": "Townhouse",
	"CONDO": "Condo",
	"CONDOMINIUM": "Condo",
	"MULTI_FAMILY": "Multi-Family",
	"MANUFACTURED": "Manufactured",
	"MOBILE": "Manufactured",
	"LOT": "Land",
	"LAND": "Land",
	"VACANT_LAND": "Land",
	"APARTMENT": "Apartment",
}

CACHE_FIELDS = ("zillow_facts", "zillow_fetched_at", "zillow_zpid")


def _num(v):
	"""Zillow uses null for unknown; it also hands back strings like '1,438 sqft'."""
	if v is None or v == "":
		return None
	if isinstance(v, (int, float)):
		return float(v)
	try:
		import re

		m = re.search(r"-?[\d,]+(?:\.\d+)?", str(v))
		return float(m.group().replace(",", "")) if m else None
	except Exception:
		return None


def _has_cache() -> bool:
	return all(frappe.db.has_column("CRM Lead", f) for f in CACHE_FIELDS)


def _api_key():
	return frappe.conf.get("rapidapi_zillow_key") or ""


def quota_remaining():
	"""Last known remaining requests on the SHARED plan, or None if unknown.

	Taken from the response headers of our most recent call, so it also reflects
	whatever istl-buyer's ZIP job has spent since — which is the point.
	"""
	try:
		rec = frappe.cache().get_value(_QUOTA_KEY)
		if not isinstance(rec, dict):
			return None
		# Expiry enforced here rather than by Redis — see the GOTCHA on _QUOTA_KEY.
		if time.time() - float(rec.get("t") or 0) > _QUOTA_TTL:
			return None
		return int(rec["n"])
	except Exception:
		return None


def _store_quota(n):
	"""Remember what RapidAPI last said was left. Called only on a real thread."""
	if n is None:
		return
	try:
		frappe.cache().set_value(_QUOTA_KEY, {"n": int(n), "t": time.time()})
	except Exception:
		pass


#: A throttled call is a TRANSIENT refusal, not an answer, and dropping one is
#: expensive twice over: the page's ~40 comps vanish from the map, and the circle
#: is then marked incomplete so the week-long cache is never written and the next
#: open re-pays for everything. One patient retry is far cheaper than either.
_RETRY_STATUS = {429, 500, 502, 503, 504}
_RETRY_BACKOFF = 1.5


def _raw_get(key: str, path: str, params: dict, retries: int = 1):
	"""One RapidAPI GET with NO Frappe involvement. -> (body, remaining, error).

	Deliberately pure: this is the only thing `fetch_many` runs on a worker thread,
	and `frappe.local` is a thread-local proxy — a worker has no site, no database
	connection and no cache, so touching `frappe.conf`, `frappe.cache()` or
	`frappe.log_error` from one raises instead of degrading. The key, the quota
	guard, the quota update and the error logging all stay on the calling thread.
	"""
	import urllib.error
	import urllib.parse
	import urllib.request

	url = f"{BASE}{path}?" + urllib.parse.urlencode(params)
	req = urllib.request.Request(
		url, headers={"x-rapidapi-key": key, "x-rapidapi-host": HOST}
	)
	try:
		with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
			body = json.loads(resp.read().decode("utf-8", "replace"))
			try:
				remaining = int(resp.headers.get("X-RateLimit-Requests-Remaining"))
			except (TypeError, ValueError):
				remaining = None
			return body, remaining, None
	except urllib.error.HTTPError as e:
		if retries > 0 and e.code in _RETRY_STATUS:
			# Plain `time.sleep` is safe here precisely because this function touches
			# nothing but the socket — it parks one worker thread, not the request.
			time.sleep(_RETRY_BACKOFF)
			return _raw_get(key, path, params, retries - 1)
		import traceback

		return None, None, traceback.format_exc()
	except Exception:
		import traceback

		return None, None, traceback.format_exc()


def _quota_blocked(path: str):
	"""True when the SHARED plan is too close to empty to spend anything here."""
	left = quota_remaining()
	if left is None or left > QUOTA_RESERVE:
		return False
	frappe.log_error(
		f"Zillow quota reserve reached ({left} left <= {QUOTA_RESERVE}); skipping "
		f"{path}. Key is shared with istl-buyer's ZIP-market job.",
		"Zillow: quota reserve",
	)
	return True


def _request(path: str, params: dict, error_title: str):
	"""One guarded RapidAPI GET, or None. Every caller degrades softly."""
	key = _api_key()
	if not key or not params:
		return None

	# Yield the last of a shared budget rather than spend it: both subject facts and
	# an on-demand comp gallery are optional, whereas istl-buyer's batch job cannot
	# degrade at all. This check runs before EACH request, so a property lookup that
	# lands on the reserve does not spend one more request fetching its photos.
	if _quota_blocked(path):
		return None

	body, remaining, error = _raw_get(key, path, params)
	_store_quota(remaining)
	if error:
		frappe.log_error(error, error_title)
		return None
	return body


#: How many RapidAPI calls may be in flight at once for one page load.
#:
#: Every call here is ~1.35s of pure network wait, and they were being made one
#: after another: a 2-mile comps circle is ~30 calls, which measured 40.5s on
#: production while the CPU did nothing. Threads are the right tool precisely
#: because the work is I/O — each one blocks in `urlopen` with the GIL released.
#:
#: FOUR, and that number is measured, not guessed. Nineteen pages fetched eight
#: at a time came back with THIRTEEN failures — `HTTP 429: Too Many Requests` —
#: which is worse than being slow, because each dropped page silently removes ~40
#: comps from the map. Sweeping the same eight calls across worker counts:
#:
#:   1 -> 8/8 in 9.5s    3 -> 8/8 in 3.3s    6 -> 8/8 in 2.2s
#:   2 -> 8/8 in 5.0s    4 -> 8/8 in 2.2s    8 -> 7/8 in 1.6s + a 429
#:
#: Four is where the curve flattens: it is the full 4.3x speedup, six buys
#: literally nothing on top of it, and eight starts losing data. The key is also
#: SHARED with istl-buyer's ZIP job, so the limit we are near is not ours alone.
FETCH_WORKERS = 4


def fetch_many(specs, error_title="Zillow: batch request failed", workers=FETCH_WORKERS):
	"""Run several independent RapidAPI GETs at once. [(path, params)] -> [body|None].

	Results come back in the order asked for, with `None` in the slot of anything
	that failed, so a caller can tell a partial answer from a complete one and
	decide whether it is safe to cache.

	The quota is checked ONCE, before the batch, rather than before each call as the
	serial path does: the whole point is that these are in flight together, so there
	is no "before" to check in between. The reserve is 500 and a batch is at most a
	few dozen, so the floor still cannot be crossed by more than one batch.
	"""
	from concurrent.futures import ThreadPoolExecutor

	specs = list(specs or [])
	if not specs:
		return []
	key = _api_key()
	if not key or _quota_blocked(specs[0][0]):
		return [None] * len(specs)

	with ThreadPoolExecutor(max_workers=max(1, min(int(workers), len(specs)))) as pool:
		results = list(pool.map(lambda s: _raw_get(key, s[0], s[1]), specs))

	# Back on the request thread, where Frappe is usable again.
	remaining = [r for _, r, _ in results if r is not None]
	if remaining:
		# The LOWEST reading is the truthful one: the responses raced, so the
		# smallest number is the furthest the plan actually got drawn down.
		_store_quota(min(remaining))
	errors = [e for _, _, e in results if e]
	if errors:
		# One log line for the batch, not one per call: a Zillow outage would
		# otherwise write 30 identical tracebacks per page load.
		frappe.log_error(
			f"{len(errors)} of {len(specs)} calls failed.\n\n{errors[0]}", error_title
		)
	return [body for body, _, _ in results]


def _fetch(address: str):
	"""One address -> Zillow's raw property blob, or None. Never raises."""
	if not address:
		return None
	return _request("/property", {"address": address}, "Zillow: property lookup failed")


def property_details(address: str):
	"""Raw details for an explicitly opened comp. Kept separate from lead caching."""
	return _fetch(address)


def property_photos(zpid):
	"""Raw `/photos` response for a Zillow property id, or None on any failure."""
	if not zpid:
		return None
	body = _request("/photos", {"zpid": zpid}, "Zillow: photo lookup failed")
	# RapidAPI can report endpoint errors inside an HTTP-200 JSON body. Treat only
	# the documented list shape as success; `{status:'error', errors:[…]}` must get
	# the short retry cache rather than hiding photos for 30 days.
	return body if isinstance(body, dict) and isinstance(body.get("photos"), list) else None


def _price_history(raw):
	"""Split priceHistory into the last real SALE and the last LISTING event.

	GOTCHA — the top-level `dateSold` / `lastSoldPrice` are null even on homes
	whose priceHistory plainly contains Sold rows (verified on prod addresses), so
	the history is the only reliable source. `event` is a display string, hence
	the lowercase compare rather than an equality test on a code.
	"""
	events = raw.get("priceHistory") or []
	sale = listing = None
	for e in events:  # newest first as returned
		if not isinstance(e, dict):
			continue
		kind = str(e.get("event") or "").strip().lower()
		price, date = _num(e.get("price")), e.get("date")
		if not date:
			continue
		if sale is None and kind == "sold":
			sale = {"price": price, "date": date, "source": e.get("source")}
		elif listing is None and "list" in kind:
			# "Listed for sale" / "Listing removed" both describe the ask.
			listing = {
				"price": price,
				"date": date,
				"event": e.get("event"),
				"source": e.get("source"),
			}
		if sale and listing:
			break
	return sale, listing


#: Kept per priceHistory event, and no more. This is CACHED for 30 days, so it is
#: the raw material every later question is answered from.
_HISTORY_FIELDS = ("date", "event", "price", "source", "postingIsRental")


def _slim_history(raw):
	"""The part of `priceHistory` worth keeping. Cached INSTEAD of a parse of it.

	Caching the raw events rather than `sale_history.parse()`'s output is a
	deliberate trade, and it was made after getting it the other way round first:

	  * a parser fix is then FREE. The first version cached the parse, so
	    discovering that a chain must not span a rental (15256 Edmore Dr was
	    reporting 1,115 days to sell) meant every cached property had to be
	    re-fetched -- one billed call each -- to correct a pure arithmetic bug.
	  * ages cannot go stale. Two of the parse's numbers are relative to today, so
	    a cached parse quietly drifts by up to a month. Parsing on read means the
	    answer is always computed against the date being asked about.

	The cost is a few hundred bytes per property, against a payload we already keep
	photos and coordinates in.
	"""
	out = []
	for e in (raw or {}).get("priceHistory") or []:
		if not isinstance(e, dict) or not e.get("date"):
			continue
		out.append({k: e.get(k) for k in _HISTORY_FIELDS})
	return out


def _normalize(raw):
	"""Zillow's blob -> the small, flat shape the comps map actually consumes."""
	if not isinstance(raw, dict) or not raw.get("zpid"):
		return None
	reso = raw.get("resoFacts") or {}
	sale, listing = _price_history(raw)

	home_type = str(raw.get("homeType") or "").strip().upper()
	# GOTCHA — on an off-market home `price` mirrors taxAssessedValue rather than
	# any list price (verified: Macon price 6005 == taxAssessedValue 6005). It is
	# deliberately NOT surfaced as a price.
	return {
		"zpid": raw.get("zpid"),
		"beds": _num(raw.get("bedrooms")),
		"baths": _num(raw.get("bathrooms")),
		"sqft": _num(raw.get("livingArea") or raw.get("livingAreaValue")),
		"year_built": _num(raw.get("yearBuilt")),
		"property_type": HOME_TYPES.get(home_type) or (home_type.title().replace("_", " ") or None),
		"lot_size": reso.get("lotSize") or None,
		"lat": _num(raw.get("latitude")),
		"lng": _num(raw.get("longitude")),
		"zestimate": _num(raw.get("zestimate")),
		"rent_zestimate": _num(raw.get("rentZestimate")),
		"tax_assessed_value": _num(reso.get("taxAssessedValue") or raw.get("taxAssessedValue")),
		"last_sale": sale,
		"last_listing": listing,
		"home_status": raw.get("homeStatus"),
		"address": raw.get("streetAddress"),
		# Carried so a lead whose facts we already paid for can show its own photo
		# without a second call. Leads cached before this shipped simply have no key
		# and fall back to the area search's self-match, which is also free.
		"cover_photo": raw.get("imgSrc") or "",
		# The SAME `priceHistory` we already pay for, kept so time-on-market and flips
		# can be derived later for free. Parsed on READ, never here -- see _slim_history.
		"price_history": _slim_history(raw),
	}


def normalize_detail(raw):
	"""Zillow's large property blob -> the useful facts in a comp detail panel."""
	if not isinstance(raw, dict) or not raw.get("zpid"):
		return None
	reso = raw.get("resoFacts") or {}
	sale, listing = _price_history(raw)
	home_type = str(raw.get("homeType") or "").strip().upper()
	status = str(raw.get("homeStatus") or "").strip().upper()
	# Zillow's top-level `price` is an assessed value on many off-market homes.
	# Only call it an asking price while the property is actually marketed.
	asking_statuses = {"FOR_SALE", "FOR_RENT", "PENDING", "CONTINGENT", "COMING_SOON"}
	url = raw.get("url") or ""
	if url.startswith("/"):
		url = "https://www.zillow.com" + url
	address = raw.get("address") if isinstance(raw.get("address"), dict) else {}

	def text_list(value):
		if isinstance(value, list):
			return ", ".join(str(v) for v in value if v)
		return str(value or "")

	return {
		"zpid": raw.get("zpid"),
		"address": raw.get("streetAddress") or address.get("streetAddress"),
		"city": raw.get("city") or address.get("city"),
		"state": raw.get("state") or address.get("state"),
		"zip": raw.get("zipcode") or address.get("zipcode"),
		"beds": _num(raw.get("bedrooms")),
		"baths": _num(raw.get("bathrooms")),
		"sqft": _num(raw.get("livingArea") or raw.get("livingAreaValue")),
		"year_built": _num(raw.get("yearBuilt")),
		"property_type": HOME_TYPES.get(home_type) or (home_type.title().replace("_", " ") or None),
		"lot_size": reso.get("lotSize") or None,
		"home_status": raw.get("homeStatus"),
		"asking_price": _num(raw.get("price")) if status in asking_statuses else None,
		"zestimate": _num(raw.get("zestimate")),
		"rent_zestimate": _num(raw.get("rentZestimate")),
		"hoa_fee": _num(raw.get("monthlyHoaFee") or reso.get("hoaFee")),
		"parking": text_list(reso.get("parkingFeatures")),
		"heating": text_list(reso.get("heating")),
		"cooling": text_list(reso.get("cooling")),
		"description": raw.get("description") or "",
		"last_sale": sale,
		"last_listing": listing,
		# A rep who has opened the photos is the one most likely to be asking "why did
		# this sell for that?", so the history rides along here too -- raw, and parsed
		# on read for the same two reasons `_slim_history` explains.
		"price_history": _slim_history(raw),
		"zillow_url": url,
		"cover_photo": raw.get("imgSrc") or "",
		"photo_count": int(_num(raw.get("photoCount")) or 0),
	}


def photo_urls(raw, limit=60):
	"""Choose one useful Zillow CDN URL per photo, preferring ~1152px JPEGs."""
	if not isinstance(raw, dict):
		return []
	out = []
	for photo in raw.get("photos") or []:
		sources = (photo or {}).get("mixedSources") or {}
		options = sources.get("jpeg") or sources.get("webp") or []
		options = [o for o in options if isinstance(o, dict) and o.get("url")]
		if not options:
			continue
		# Big enough to inspect without pulling the largest 1536px image into a
		# modal. If all variants are smaller/larger, take the nearest useful one.
		under = [o for o in options if float(o.get("width") or 0) <= 1152]
		chosen = max(under or options, key=lambda o: float(o.get("width") or 0))
		if chosen["url"] not in out:
			out.append(chosen["url"])
		if len(out) >= int(limit):
			break
	return out


# Bumped when `_normalize` starts carrying a field worth re-fetching a lead for.
# A cached blob without every key here is treated as stale, which spends ONE
# lookup per lead and then rides the normal 30-day cache. Cheaper than the
# alternative it replaces (a per-comp `/property` call just to get a picture),
# and self-limiting because the refetch rewrites the cache with the key present.
REQUIRED_FACT_KEYS = ("cover_photo", "price_history")


def _cached(doc):
	if not _has_cache() or not doc.get("zillow_facts"):
		return None
	fetched = doc.get("zillow_fetched_at")
	if fetched:
		try:
			if frappe.utils.date_diff(frappe.utils.nowdate(), str(fetched)[:10]) > CACHE_DAYS:
				return None
		except Exception:
			pass
	try:
		hit = json.loads(doc.get("zillow_facts"))
	except Exception:
		return None
	# A remembered negative is `{}` and must stay a cheap negative — re-fetching it
	# for a missing key would re-bill every unresolvable address on every open.
	if hit and any(k not in hit for k in REQUIRED_FACT_KEYS):
		return None
	return hit


def _store(doc, facts):
	if not _has_cache():
		return
	try:
		frappe.db.set_value(
			"CRM Lead", doc.name,
			{
				"zillow_facts": json.dumps(facts) if facts else "",
				"zillow_fetched_at": frappe.utils.now(),
				"zillow_zpid": str((facts or {}).get("zpid") or ""),
			},
			# A cached lookup is not a human edit; same rule as the geocode cache.
			update_modified=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Zillow: caching facts failed")


def facts_for_lead(doc, force=False):
	"""Normalized Zillow facts for a lead, cached. Returns None when unavailable.

	`doc` is a CRM Lead document. Safe to call on every comps-map open: past the
	first fetch this is a JSON parse off a column.
	"""
	if not force:
		hit = _cached(doc)
		if hit is not None:
			return hit
	if not _api_key():
		return None

	from crm.api.comps import _full_address

	raw = _fetch(_full_address(doc))
	facts = _normalize(raw) if raw else None
	# Cache negatives too, so an address Zillow cannot resolve is not re-fetched
	# (and re-billed) on every single modal open.
	_store(doc, facts or {})
	return facts


@frappe.whitelist()
def refresh_lead_facts(lead):
	"""Force a re-fetch for one lead (whitelisted so a button can offer it)."""
	from crm.api.comps import _guard

	_guard()
	doc = frappe.get_doc("CRM Lead", lead)
	facts = facts_for_lead(doc, force=True)
	return {"ok": bool(facts), "facts": facts}
