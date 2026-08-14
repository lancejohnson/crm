"""Does one of our disposition buyers work this lead's area?

Two national buyers publish where they operate, so a lead in their footprint has
a likely exit before we ever call it. `crm/api/data/dispo_buyers.json` is a
snapshot of both, generated from the istl-buyer repo (see build_dispo_buyers.py
beside it) -- the scraping, the CBSA expansion and the FIPS crosswalk all live
there, and the CRM carries only the finished lookup tables.

    new_western  "Yes - NW city" | "Nearby - NW county" | "No"
    keyglee      "Yes - KG operating" | "Sold out - KG" | "No"

Both keep TWO positive levels rather than one, and the split is the whole point:
one of them is the company's own published claim and the other is our inference.
Collapsing them would quietly promote a guess to a fact.

  * New Western publishes a CITY list. A city on it is their claim; a lead
    merely in the same COUNTY as a listed city is us guessing at their metro buy
    box; and between those sits asserted coverage -- markets they demonstrably
    run (an office page that resolves, their own market taxonomy) but do not
    list, hand-evidenced upstream.
  * KeyGlee publishes only map polygons, approximated upstream by the
    territory's CBSA. Their real territories run 1.0x-4.9x that, so this
    UNDER-claims -- a "No" may be wrong, a "Yes" is safe. Note also that their
    map's raw status "Available" means a franchise is OPERATING, not one that is
    for sale; upstream already flips it, and this file inherits the flipped
    value.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata

import frappe

NW_CITY = "Yes - NW city"
# Coverage New Western has evidence for (an office page that resolves, their own
# market taxonomy) but does not publish on the locations page. Stronger than our
# county inference -- it is a market they actually run -- but still not their
# published city list, so it keeps its own value rather than being laundered
# into NW_CITY. Las Vegas and Tucson are the live examples.
NW_MARKET = "Yes - NW market"
NW_COUNTY = "Nearby - NW county"
KG_OPERATING = "Yes - KG operating"
KG_SOLD_OUT = "Sold out - KG"
NO = "No"

_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "dispo_buyers.json")
_DATA = None

# Leads do not agree on how to write a state: 19 of them store "Texas" or
# "Indiana" where the rest store "TX"/"IN". Truncating to two characters turns
# "Texas" into "TE" and silently matches nothing, so full names are mapped
# before any truncation happens.
_STATE_NAMES = {
	"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
	"california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
	"district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
	"idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
	"kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
	"massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
	"missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
	"new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
	"north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
	"oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
	"south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
	"utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
	"west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}

_ABBR = {"st": "saint", "ste": "sainte", "ft": "fort", "mt": "mount"}
_SUFFIX = re.compile(
	r"\s+(county|parish|borough|census area|municipality|city and borough|city)$"
)


def _norm(s) -> str:
	"""Lowercase, de-accent, de-punctuate, expand St/Ft/Mt.

	The NFKD fold has to happen BEFORE non-alphanumerics are stripped or an
	accented letter is deleted rather than folded: "Dona Ana" survives, but
	"Dona Ana" written with an enye became "doaana" and matched nothing. That
	was a real miss on a live Las Cruces lead.
	"""
	if not s:
		return ""
	s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
	s = s.lower().replace("&", " and ")
	s = re.sub(r"[.'`]", "", s)
	s = re.sub(r"[^a-z0-9]+", " ", s).strip()
	return " ".join(_ABBR.get(p, p) for p in s.split())


def _state(s) -> str:
	raw = (str(s or "")).strip()
	if not raw:
		return ""
	return _STATE_NAMES.get(raw.lower(), raw.upper()[:2])


def _county_keys(name, state) -> list:
	"""Candidate keys for a county, most-specific first.

	A lead writes the bare name -- "Virginia Beach", not "Virginia Beach City" --
	so the county form is tried first and the INDEPENDENT CITY form second. The
	order matters and the fallback is not a shortcut for dropping the C/N flag
	entirely: Virginia has both a Richmond County and a Richmond city, and a
	lead saying "Richmond" means the county, which the first key finds. Only
	when no county of that name exists in that state (Virginia Beach, Chesapeake,
	Danville) does the city become the sole candidate. 30 live leads, all of them
	Virginia independent cities, were resolving to nothing before this.
	"""
	st = _state(state)
	if not name or not st:
		return []
	n = _SUFFIX.sub("", " " + _norm(name)).strip().replace(" ", "")
	if not n:
		return []
	return [f"{n}|N|{st}", f"{n}|C|{st}"]


def _load() -> dict:
	global _DATA
	if _DATA is None:
		try:
			with open(_DATA_FILE) as fh:
				_DATA = json.load(fh)
		except Exception:
			# A missing or unreadable snapshot must degrade to "we don't know",
			# never take a board down. Every caller treats {} as no coverage.
			frappe.log_error(title="dispo_buyers dataset unavailable")
			_DATA = {"new_western": {}, "keyglee": {}}
	return _DATA


def resolve(city=None, state=None, county=None) -> dict:
	"""(city, state, county) -> both buyers' verdicts.

	Returns the two status strings plus the market that answered, ready to be
	rendered. Everything is "No" when the state is unknown: there are 40
	Madisons, and guessing which one is worse than saying nothing.
	"""
	data = _load()
	st = _state(state)
	out = {
		"new_western": NO,
		"new_western_market": None,
		"keyglee": NO,
		"keyglee_market": None,
	}
	if not st:
		return out

	nw = data.get("new_western") or {}
	city_key = f"{_norm(city).replace(' ', '')}|{st}"
	market = (nw.get("cities") or {}).get(city_key)
	if market:
		out["new_western"] = NW_CITY
		out["new_western_market"] = market
	else:
		asserted = set(nw.get("asserted") or ())
		for key in _county_keys(county, st):
			market = (nw.get("counties") or {}).get(key)
			if market:
				out["new_western"] = NW_MARKET if key in asserted else NW_COUNTY
				out["new_western_market"] = market
				break

	kg = (data.get("keyglee") or {}).get("counties") or {}
	for key in _county_keys(county, st):
		hit = kg.get(key)
		if hit:
			out["keyglee"] = hit[1] or NO
			out["keyglee_market"] = hit[0]
			break

	return out


def summary(city=None, state=None, county=None) -> dict | None:
	"""The compact shape the Kanban card and lead page render.

	None when neither buyer covers the area, so the caller can omit the field
	entirely rather than shipping "No" for every lead on the board.
	"""
	r = resolve(city, state, county)
	badges = []
	if r["new_western"] != NO:
		badges.append({
			"buyer": "nw",
			"market": r["new_western_market"],
			# "strong" is what fills a badge in: the company's own claim about
			# where it buys. Asserted coverage counts -- it is a market they run --
			# while a bare county match stays outlined, because that guess is ours.
			"strong": r["new_western"] in (NW_CITY, NW_MARKET),
			"status": r["new_western"],
		})
	if r["keyglee"] != NO:
		badges.append({
			"buyer": "kg",
			"market": r["keyglee_market"],
			"strong": r["keyglee"] == KG_OPERATING,
			"status": r["keyglee"],
		})
	return badges or None


@frappe.whitelist()
def get_dispo_buyers(city=None, state=None, county=None):
	"""Whitelisted single-lead lookup, for surfaces that hold a lead not a card."""
	return resolve(city, state, county)
