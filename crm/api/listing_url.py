# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Turn a listing URL into a street address — Zillow, Redfin, Realtor, Auction.com.

A rep scouting a house usually has the listing open, not the address typed
out. Every one of these sites puts the address in the URL slug, so the
address can be read off the link with no API call and no key:

  zillow.com/homedetails/3820-N-Illinois-St-Indianapolis-IN-46208/1023_zpid/
  redfin.com/IN/Indianapolis/3820-N-Illinois-St-46208/home/1023
  realtor.com/realestateandhomes-detail/3820-N-Illinois-St_Indianapolis_IN_46208_M10-23
  auction.com/details/3820-n-illinois-st-indianapolis-in-46208-1023-e_12345/

Redfin and Realtor delimit street / city / state explicitly. Zillow and
Auction.com hand back ONE hyphenated run (`street-city-state-zip`), and the
street/city split is a heuristic: the last street-suffix word ("St", "Ave",
"Rd" …) in the run ends the street, with any unit token after it ("Unit-2",
"Apt-B", "#4") kept on the street side. When no suffix is found the address
is returned unsplit — "3820 N Illinois St Indianapolis, IN 46208" still
geocodes and still resolves on Zillow; only the display loses a comma.

Pure: no frappe import, so it unit-tests without a bench
(`crm/tests/unit_test_listing_url.py`).
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

SUPPORTED = ("zillow.com", "redfin.com", "realtor.com", "auction.com")

#: Words that end a street line. Lower-case, matched against a slug token.
STREET_SUFFIXES = {
	"st", "street", "ave", "avenue", "av", "rd", "road", "dr", "drive", "ln", "lane",
	"blvd", "boulevard", "ct", "court", "cir", "circle", "way", "pl", "place", "ter",
	"terrace", "trl", "trail", "pkwy", "parkway", "hwy", "highway", "loop", "run",
	"pike", "path", "pass", "row", "sq", "square", "xing", "crossing", "bnd", "bend",
	"cv", "cove", "pt", "point", "ridge", "rdg", "hts", "heights", "holw", "hollow",
	"vly", "valley", "mnr", "manor", "ext", "aly", "alley", "byp", "bypass", "cres",
	"crescent", "expy", "expressway", "fwy", "freeway", "gdns", "gardens", "grv",
	"grove", "is", "island", "jct", "junction", "lndg", "landing", "mdws", "meadows",
	"ml", "mill", "mtn", "mountain", "orch", "orchard", "plz", "plaza", "shr", "shore",
	"spg", "spring", "spgs", "springs", "sta", "station", "trce", "trace", "tpke",
	"turnpike", "vw", "view", "vlg", "village", "walk", "wall", "xrd", "crossroad",
}
#: Tokens that begin a unit designator and, with the token after them, stay on
#: the street side of the split.
UNIT_WORDS = {"unit", "apt", "ste", "suite", "lot", "bldg", "fl", "floor", "rm", "spc", "trlr"}
DIRECTIONALS = {"n", "s", "e", "w", "ne", "nw", "se", "sw"}
STATE_RE = re.compile(r"^[a-z]{2}$", re.I)
ZIP_RE = re.compile(r"^\d{5}$")


def _title(token: str) -> str:
	"""Slug token → display: 'illinois' → 'Illinois', 'n' → 'N', '5th' → '5th'."""
	if not token:
		return token
	low = token.lower()
	if low in DIRECTIONALS:
		return low.upper()
	if low[0].isdigit():
		return low  # 5th, 42nd, 1a
	if low == "mc" or low.startswith("mc") and len(low) > 3:
		return "Mc" + low[2:].capitalize()
	return low[0].upper() + low[1:]


def _words(slug: str) -> str:
	return " ".join(_title(t) for t in slug.split("-") if t)


def _split_street_city(tokens: list[str]) -> tuple[str, str]:
	"""(street, city) from one hyphen run. City may be '' when no suffix is found."""
	low = [t.lower() for t in tokens]
	cut = None
	for i, t in enumerate(low):
		if t in STREET_SUFFIXES and i > 0:
			cut = i + 1
	if cut is None:
		return " ".join(_title(t) for t in tokens), ""
	# A directional right after the suffix ("St-W") is a post-directional and
	# stays on the street — cities spelled with a bare "W" are rarer than "5th St
	# W" is — as does a unit designator plus its value ("Unit-2", "Apt-B", "#4").
	while cut < len(low):
		t = low[cut]
		if t in DIRECTIONALS:
			cut += 1
		elif t in UNIT_WORDS and cut + 1 < len(low):
			cut += 2
		elif t.startswith("#"):
			cut += 1
		else:
			break
	street = " ".join(_title(t) for t in tokens[:cut])
	city = " ".join(_title(t) for t in tokens[cut:])
	return street, city


def _assemble(street: str, city: str, state: str, zip_code: str) -> dict:
	street = street.strip()
	city = city.strip()
	state = state.strip().upper()
	zip_code = zip_code.strip()
	parts = [street]
	tail = " ".join(p for p in (state, zip_code) if p)
	if city:
		parts.append(city)
	if tail:
		parts.append(tail)
	return {
		"address": ", ".join(p for p in parts if p),
		"street": street,
		"city": city,
		"state": state,
		"zip": zip_code,
	}


def _parse_hyphen_run(run: str) -> dict | None:
	"""`street-city-ST-ZIP` → parts. Zillow and Auction.com both use this."""
	tokens = [t for t in run.split("-") if t]
	if len(tokens) < 4:
		return None
	# Auction.com appends its own ids after the ZIP; walk back to the ZIP.
	zi = None
	for i in range(len(tokens) - 1, 1, -1):
		if ZIP_RE.match(tokens[i]) and STATE_RE.match(tokens[i - 1]):
			zi = i
			break
	if zi is None:
		return None
	state, zip_code = tokens[zi - 1], tokens[zi]
	street, city = _split_street_city(tokens[: zi - 1])
	if not street:
		return None
	return _assemble(street, city, state, zip_code)


def _zillow(path: str) -> dict | None:
	m = re.search(r"/homedetails/([^/]+)/(\d+)_zpid", path, re.I)
	if m:
		out = _parse_hyphen_run(m.group(1))
		if out:
			out["zpid"] = m.group(2)
		return out
	# /homes/<slug>_rb/ is a SEARCH url; it still carries an address when the
	# slug is a full one (the CRM's own zillowUrl() builds these).
	m = re.search(r"/homes/([^/]+)_rb/?", path, re.I)
	if m:
		return _parse_hyphen_run(m.group(1))
	return None


def _redfin(path: str) -> dict | None:
	# /IN/Indianapolis/3820-N-Illinois-St-46208/home/1023
	m = re.search(r"^/([A-Za-z]{2})/([^/]+)/([^/]+)/home/", path)
	if not m:
		return None
	state, city_slug, street_slug = m.groups()
	tokens = [t for t in street_slug.split("-") if t]
	zip_code = ""
	if tokens and ZIP_RE.match(tokens[-1]):
		zip_code = tokens.pop()
	street = " ".join(_title(t) for t in tokens)
	if not street:
		return None
	return _assemble(street, _words(city_slug), state, zip_code)


def _realtor(path: str) -> dict | None:
	# /realestateandhomes-detail/3820-N-Illinois-St_Indianapolis_IN_46208_M10-23
	m = re.search(r"/realestateandhomes-detail/([^/?#]+)", path, re.I)
	if not m:
		return None
	parts = m.group(1).split("_")
	# Drop the trailing M… listing id.
	if parts and re.match(r"^M[\d-]+$", parts[-1], re.I):
		parts = parts[:-1]
	if len(parts) < 3:
		return None
	street_slug, city_slug = parts[0], parts[1]
	state = parts[2] if len(parts) > 2 else ""
	zip_code = parts[3] if len(parts) > 3 and ZIP_RE.match(parts[3]) else ""
	street = _words(street_slug)
	if not street:
		return None
	return _assemble(street, _words(city_slug), state, zip_code)


def _auction(path: str) -> dict | None:
	# /details/3820-n-illinois-st-indianapolis-in-46208-1023-e_12345/
	m = re.search(r"/details/([^/?#]+)", path, re.I)
	if not m:
		return None
	slug = m.group(1).split("_")[0]
	# Current links end in state + listing ID, with NO ZIP. Strip the ID
	# before looking for a ZIP: even a five-digit listing ID is not a ZIP.
	# Legacy links above include ZIP + ID + e_... and keep their old path.
	current = re.fullmatch(r"(.+)-([A-Za-z]{2})-\d+", slug)
	if current:
		street, city = _split_street_city(current.group(1).split("-"))
		if not street:
			return None
		return _assemble(street, city, current.group(2), "")
	return _parse_hyphen_run(slug)


def parse_listing_url(url: str) -> dict | None:
	"""Address parts for a supported listing URL, or None.

	Returns {address, street, city, state, zip, source, url} — `address` is
	the one-line form the CRM stores in `property_address`.
	"""
	raw = (url or "").strip()
	if not raw:
		return None
	if "://" not in raw:
		raw = "https://" + raw
	try:
		u = urlparse(raw)
	except ValueError:
		return None
	host = (u.netloc or "").lower().split(":")[0]
	host = host[4:] if host.startswith("www.") else host
	path = unquote(u.path or "")
	if host.endswith("zillow.com"):
		out, source = _zillow(path), "zillow"
	elif host.endswith("redfin.com"):
		out, source = _redfin(path), "redfin"
	elif host.endswith("realtor.com"):
		out, source = _realtor(path), "realtor"
	elif host.endswith("auction.com"):
		out, source = _auction(path), "auction"
	else:
		return None
	if not out:
		return None
	out["source"] = source
	out["url"] = raw
	return out


def looks_like_url(text: str) -> bool:
	t = (text or "").strip().lower()
	return t.startswith(("http://", "https://", "www.")) or any(
		t.startswith(h) for h in SUPPORTED
	)
