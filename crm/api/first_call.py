"""First-Call Read — a 2x2 lead qualification recorded after the first call.

Two yes/no reads on the lead place it in a 2x2:

  first_call_motivated — is the seller motivated?  ('' | Yes | No)
  first_call_on_price  — is their price realistic?  ('' | Yes | No)

(motivated x on-price) -> Hot / Work-the-price / Timing / Cold; blank on either
axis = "not qualified yet". The four CRM Lead custom fields are added by the ops
repo (`../frappe-crm-deploy/scripts/setup_first_call_read.py`); this module is the
single writer. We use db.set_value (not a full doc.save) so recording a read
doesn't fire the lead's status/assignment side-effects, then broadcast a
`crm_first_call` realtime event so every open board's quadrant chip refreshes
live (site-wide, after_commit — mirrors the `crm_task_update` / `quo_message`
pattern).
"""

import frappe
from frappe import _

VALID = ("", "Yes", "No")

FIELDS = ("first_call_motivated", "first_call_on_price", "first_call_by", "first_call_at")


@frappe.whitelist()
def set_first_call_read(lead: str, motivated: str = "", on_price: str = ""):
	"""Record (or clear) the first-call 2x2 read for a lead. motivated/on_price
	are each '' (unanswered), 'Yes', or 'No'. Stamps who/when server-side and
	broadcasts a realtime refresh. Returns the saved values."""
	motivated = (motivated or "").strip()
	on_price = (on_price or "").strip()
	if motivated not in VALID or on_price not in VALID:
		frappe.throw(_("Motivated / On-price must be blank, Yes, or No."))

	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead {0} not found.").format(lead))
	# Permission parity with any other edit to the lead.
	frappe.has_permission("CRM Lead", "write", lead, throw=True)

	answered = bool(motivated) or bool(on_price)
	now = frappe.utils.now()
	values = {
		"first_call_motivated": motivated,
		"first_call_on_price": on_price,
		"first_call_by": frappe.session.user if answered else None,
		"first_call_at": now if answered else None,
	}
	frappe.db.set_value("CRM Lead", lead, values)

	frappe.publish_realtime(
		"crm_first_call",
		{"reference_doctype": "CRM Lead", "reference_docname": lead, **values},
		after_commit=True,
	)
	return values
