# Copyright (c) 2025, Groundwork and Contributors
"""Preset text messages with lead tokens, on the Send Text box.

Dennis's ask (2026-09-04): canned texts that fill in the seller's first name and
street so a rep taps a chip instead of retyping "Hi ___, this is ___ about your
house on ___" forty times a day. Lance picked the chips-in-the-composer shape
(mockup A) and asked for BOTH a team list and a personal one.

Two lists, two homes, no doctype:

- **Team presets** — one JSON list in a *global* Frappe default
  (`crm_text_presets`), the same no-new-doctype trick Lead Assignment rules
  use. Everyone reads them; Sales Managers / System Managers write them.
- **My presets** — one JSON list in the session user's *user* default
  (`crm_my_text_presets`), the same trick as the task due chips. Only the
  owner reads or writes them.

Rendering is done HERE, not in the browser, so the tokens have one definition
and every surface (lead page composer, header Text modal, Today card) fills a
chip identically — the Today card in particular carries only `lead_name`, not
`first_name` or the street, and shipping those onto every card just to render a
chip would be the wrong trade. One `get_value` per tap.

A token the lead cannot fill is NOT dropped silently — "Hi , this is German"
is precisely the text a seller reads as a robot. It renders as a visible
`[first name?]` marker the composer refuses to send until the rep replaces it.
"""

import json
import re

import frappe
from frappe import _

TEAM_KEY = "crm_text_presets"
MINE_KEY = "crm_my_text_presets"
PRESETS_MAX = 30
LABEL_MAX = 32
BODY_MAX = 1000

# token -> (human label used in the [label?] marker, description for the editor)
TOKENS = {
	"first_name": ("first name", "Seller's first name"),
	"street": ("street", "Street name only — “Maple Ave”"),
	"address": ("address", "House number + street — “412 Maple Ave”"),
	"city": ("city", "Property city"),
	"my_name": ("your name", "Your own first name"),
}

_TOKEN_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
# "412 Maple Ave" / "412-B Maple Ave" / "412 1/2 Maple Ave" -> "Maple Ave"
_HOUSE_NUMBER_RE = re.compile(r"^\s*\d+[A-Za-z\-/]*(\s+\d+/\d+)?\s+")
# a trailing unit is not part of the street name
_UNIT_RE = re.compile(r"\s+(?:apt|unit|ste|suite|#)\s*\S+\s*$", re.I)


def _parse(raw):
	if not raw:
		return None
	if isinstance(raw, list):
		return raw
	if isinstance(raw, str):
		try:
			parsed = json.loads(raw)
		except (ValueError, TypeError):
			return None
		return parsed if isinstance(parsed, list) else None
	return None


def _clean(presets):
	out = []
	for item in presets or []:
		if not isinstance(item, dict):
			continue
		label = str(item.get("label") or "").strip()[:LABEL_MAX]
		body = str(item.get("body") or "").strip()[:BODY_MAX]
		if not label or not body:
			continue
		out.append({"label": label, "body": body})
		if len(out) >= PRESETS_MAX:
			break
	return out


def _can_edit_team() -> bool:
	roles = set(frappe.get_roles())
	return bool(roles & {"Sales Manager", "System Manager"})


def _team_presets():
	return _parse(frappe.db.get_default(TEAM_KEY)) or []


def _my_presets():
	return _parse(frappe.defaults.get_user_default(MINE_KEY)) or []


@frappe.whitelist()
def get_text_presets():
	"""Both lists plus what the editor needs to know."""
	return {
		"team": _clean(_team_presets()),
		"mine": _clean(_my_presets()),
		"can_edit_team": _can_edit_team(),
		"tokens": [{"token": k, "label": v[0], "help": v[1]} for k, v in TOKENS.items()],
	}


@frappe.whitelist()
def set_team_text_presets(presets):
	"""Managers only. Empty list is a real choice (no team chips)."""
	if not _can_edit_team():
		frappe.throw(_("Only a Sales Manager can edit the team's text presets."), frappe.PermissionError)
	parsed = _parse(presets)
	if parsed is None:
		frappe.throw(_("Invalid text presets payload."))
	cleaned = _clean(parsed)
	frappe.db.set_default(TEAM_KEY, json.dumps(cleaned, separators=(",", ":")))
	# Same cache trap lead_assignment documents: without this the re-read in
	# this process can serve the previous blob. The helper is private and
	# singular; `frappe.defaults.clear_cache` does not exist.
	frappe.defaults._clear_cache("__default")
	return cleaned


@frappe.whitelist()
def set_my_text_presets(presets):
	parsed = _parse(presets)
	if parsed is None:
		frappe.throw(_("Invalid text presets payload."))
	cleaned = _clean(parsed)
	frappe.defaults.set_user_default(MINE_KEY, json.dumps(cleaned, separators=(",", ":")))
	return cleaned


# ---------------------------------------------------------------- rendering


def _street_line(address: str) -> str:
	"""The house-number-and-street part of a full address string."""
	line = (address or "").split(",")[0].strip()
	return _UNIT_RE.sub("", line).strip()


def _street_name(address: str) -> str:
	line = _street_line(address)
	name = _HOUSE_NUMBER_RE.sub("", line).strip()
	# a bare house number is not a street name
	return "" if re.fullmatch(r"[\d\-/ ]*", name) else name


def _lead_values(lead: str) -> dict:
	doc = frappe.db.get_value(
		"CRM Lead",
		lead,
		["first_name", "lead_name", "property_address", "property_city"],
		as_dict=True,
	)
	if not doc:
		frappe.throw(_("Lead not found"), frappe.DoesNotExistError)
	first = (doc.first_name or "").strip() or (doc.lead_name or "").strip().split(" ")[0]
	address = doc.property_address or ""
	city = (doc.property_city or "").strip()
	if not city and "," in address:
		city = address.split(",")[1].strip()
	# imports arrive as "pittsburgh" / "PITTSBURGH"; only re-case the machine-mangled
	if city and (city.islower() or city.isupper()):
		city = city.title()
	me = frappe.db.get_value("User", frappe.session.user, ["first_name", "full_name"], as_dict=True) or {}
	my_name = (me.get("first_name") or (me.get("full_name") or "").split(" ")[0] or "").strip()
	return {
		"first_name": first,
		"street": _street_name(address),
		"address": _street_line(address),
		"city": city,
		"my_name": my_name,
	}


def render_body(body: str, values: dict) -> tuple[str, list[str]]:
	"""Fill `{{token}}`s from `values`; unknown tokens are left as typed.
	Returns (text, missing) where missing lists the tokens that had no value
	and were rendered as a `[label?]` marker instead."""
	missing = []

	def sub(m):
		key = m.group(1)
		if key not in TOKENS:
			return m.group(0)
		val = (values.get(key) or "").strip()
		if val:
			return val
		if key not in missing:
			missing.append(key)
		return f"[{TOKENS[key][0]}?]"

	return _TOKEN_RE.sub(sub, body or ""), missing


@frappe.whitelist()
def render_text_preset(lead: str, body: str):
	"""One chip tap: the preset body with this lead's values filled in."""
	if not frappe.has_permission("CRM Lead", "read", lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	text, missing = render_body(body, _lead_values(lead))
	return {
		"text": text,
		"missing": [{"token": k, "label": TOKENS[k][0]} for k in missing],
	}
