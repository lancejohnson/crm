# Copyright (c) 2025, Groundwork and Contributors
"""Per-user follow-up due-date chips on the Lead/Deal To-do list.

Mirrors quick comments (pencil editor, session-user only, frontend-owned
defaults) but stored as a Frappe *user default* rather than a custom field —
same trick as the Today priority order and lead-open mode. No ops script, and
an unset value means "use the built-in 2h / 3d / 1wk / 1mo chips".
"""

import json

import frappe
from frappe import _

PRESETS_DEFAULT_KEY = "crm_task_due_presets"
PRESETS_MAX = 20
PRESET_UNITS = ("hour", "day", "week", "month")


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
		label = str(item.get("label") or "").strip()[:24]
		unit = str(item.get("unit") or "").strip()
		try:
			amount = int(item.get("amount"))
		except (TypeError, ValueError):
			continue
		if not label or unit not in PRESET_UNITS or amount < 1 or amount > 365:
			continue
		out.append({"label": label, "amount": amount, "unit": unit})
		if len(out) >= PRESETS_MAX:
			break
	return out


@frappe.whitelist()
def get_user_task_due_presets():
	"""Return this user's saved chips, or None when they have never customized."""
	return _parse(frappe.defaults.get_user_default(PRESETS_DEFAULT_KEY))


@frappe.whitelist()
def set_user_task_due_presets(presets):
	"""Persist the current user's due-date chips. Empty list is a real choice
	(no chips); the frontend only falls back to defaults when this is unset.
	"""
	parsed = _parse(presets)
	if parsed is None:
		frappe.throw(_("Invalid task due presets payload."))
	cleaned = _clean(parsed)
	frappe.defaults.set_user_default(
		PRESETS_DEFAULT_KEY, json.dumps(cleaned, separators=(",", ":"))
	)
	return cleaned
