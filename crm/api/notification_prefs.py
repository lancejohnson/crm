"""Per-user notification preferences (stored on `User.custom_notification_prefs`).

A single JSON blob on the User doctype (mirrors the `custom_quick_comments`
pattern) so a user customizes, cross-device, how they're told about activity on
their leads' e-sign agreements. Read into the frontend via
`crm.api.session.get_users` (the field is added to the SELECT there) and written
by `set_notification_prefs` below (session user's own row only).

Today the only producer is the DocuSeal agreement webhook
(`crm.api.agreement_notify.notify_event`), which texts + emails the lead owner
when a recipient views / starts / signs an agreement.
"""

import json

import frappe

# Defaults applied for any user who hasn't customized (the feature is opt-out:
# both channels + all three events on). `text_number` empty → fall back to the
# user's own Quo line (`User.custom_quo_number`). Keep in sync with the frontend
# defaults in `NotificationsSettings.vue`.
DEFAULT_PREFS = {
	"text": True,
	"email": True,
	"viewed": True,
	"started": True,
	"signed": True,
	"text_number": "",
}

_BOOL_KEYS = ("text", "email", "viewed", "started", "signed")


def get_prefs(user: str) -> dict:
	"""Resolved prefs for `user`: defaults overlaid with their stored JSON."""
	prefs = dict(DEFAULT_PREFS)
	raw = frappe.db.get_value("User", user, "custom_notification_prefs")
	if raw:
		try:
			stored = json.loads(raw)
		except (ValueError, TypeError):
			stored = {}
		if isinstance(stored, dict):
			for k in _BOOL_KEYS:
				if k in stored:
					prefs[k] = bool(stored[k])
			if "text_number" in stored:
				prefs["text_number"] = str(stored.get("text_number") or "").strip()
	return prefs


@frappe.whitelist()
def set_notification_prefs(prefs):
	"""Persist the session user's own notification preferences (cleaned JSON)."""
	if isinstance(prefs, str):
		try:
			prefs = json.loads(prefs)
		except (ValueError, TypeError):
			prefs = {}
	if not isinstance(prefs, dict):
		frappe.throw("Invalid notification preferences.")

	cleaned = dict(DEFAULT_PREFS)
	for k in _BOOL_KEYS:
		if k in prefs:
			cleaned[k] = bool(prefs[k])
	cleaned["text_number"] = str(prefs.get("text_number") or "").strip()[:20]

	frappe.db.set_value(
		"User",
		frappe.session.user,
		"custom_notification_prefs",
		json.dumps(cleaned),
		update_modified=False,
	)
	return cleaned


# ── Frappe's own "assigned to you" emails ─────────────────────────────────────
#
# Every `_assign` (lead owner change, Today-board handover, buyer import) makes
# core Frappe email the assignee via Notification Log → Notification Settings
# `enable_email_assignment`, which ships ON. Handing 41 leads to two people
# sent 41 emails each (2026-09-08). Off by default here; a user who wants them
# flips the switch at /app/notification-settings/<user>.


def default_assignment_emails_off(doc, method=None):
	"""`Notification Settings` before_insert hook: new users start with
	assignment emails off. Only touches the row Frappe is about to create."""
	doc.enable_email_assignment = 0


def disable_assignment_emails(dry_run=1):
	"""One-time sweep for existing users (bench execute). Idempotent."""
	rows = frappe.get_all(
		"Notification Settings",
		filters={"enable_email_assignment": 1},
		pluck="name",
	)
	if not int(dry_run):
		for name in rows:
			frappe.db.set_value(
				"Notification Settings", name, "enable_email_assignment", 0, update_modified=False
			)
		frappe.db.commit()
	return {"dry_run": int(dry_run), "users": rows}
