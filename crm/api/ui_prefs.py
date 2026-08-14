# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Small per-user UI preferences that do not deserve a schema field.

Stored as standard Frappe user defaults, the same mechanism the Today board's
personal priority order uses (`today_board.PRIORITY_DEFAULT_KEY`). That buys
cross-device persistence -- Lance works from a laptop, a mini and a phone, and a
preference about how the app opens records is useless if it only follows one
browser -- without a custom field, an ops script, or anything to migrate.

Deliberately NOT localStorage. The existing localStorage prefs (`dispoView`,
`activityScope`, `statusReportScope`, `compsPillDetail`) are all VIEW MODES: what
shape do I want this one screen in, right now. This is a workflow preference the
user is asked about once and then expects to be honoured everywhere, which is the
same category as the Today priority order.
"""

import frappe
from frappe import _

#: How a lead should open when its Kanban card is clicked.
#: "" (unset) means the user has not been asked yet -- the board prompts once and
#: then stores one of the two real modes. Unset is a distinct, meaningful state:
#: it is the difference between "wants the full page" and "has not said".
LEAD_OPEN_MODE_KEY = "crm_lead_open_mode"
LEAD_OPEN_MODES = ("modal", "page")


def _lead_open_mode():
	mode = frappe.defaults.get_user_default(LEAD_OPEN_MODE_KEY)
	return mode if mode in LEAD_OPEN_MODES else ""


@frappe.whitelist()
def get_lead_open_mode():
	"""Return this user's lead-open preference: "modal", "page", or "" if unasked."""
	return _lead_open_mode()


@frappe.whitelist()
def set_lead_open_mode(mode):
	"""Persist this user's lead-open preference.

	:param mode: "modal", "page", or "" to forget the answer and be asked again
	:return: the stored value
	"""
	mode = (mode or "").strip()
	if mode and mode not in LEAD_OPEN_MODES:
		frappe.throw(_("Invalid lead open mode."))
	# An empty value clears the default, which puts the user back in the
	# "not asked yet" state rather than silently pinning them to a mode. That is
	# what makes the Preferences control able to offer "ask me again".
	frappe.defaults.set_user_default(LEAD_OPEN_MODE_KEY, mode or None)
	return mode
