"""Human override for the AI/rule call classification on CRM Call Log.

The classification fields (custom_call_class / custom_call_class_source /
custom_call_note / custom_call_side) are provisioned by the classify-crm-calls
workflow (custom fields, not schema). A human picking a class in the UI stamps
source=human, which the classifier's write-back script treats as immutable —
re-runs never overwrite a human verdict. The agent's evidence note is kept.
"""

import frappe
from frappe import _

CALL_CLASSES = (
	"Connected",
	"Voicemail Left",
	"Greeting Hangup",
	"Screener - No Contact",
	"IVR / Robot",
	"No Answer",
	"Phantom",
	"No Transcript",
)

SALES_ROLES = {"Sales User", "Sales Manager", "System Manager"}


@frappe.whitelist()
def set_call_class(call: str, call_class: str):
	"""Set the classification on one call, stamped as a human verdict."""
	if not SALES_ROLES & set(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if call_class not in CALL_CLASSES:
		frappe.throw(_("Invalid call class: {0}").format(call_class))
	if not frappe.db.has_column("CRM Call Log", "custom_call_class"):
		frappe.throw(_("Call classification fields are not provisioned on this site."))
	if not frappe.db.exists("CRM Call Log", call):
		frappe.throw(_("Call Log {0} not found").format(call))

	frappe.db.set_value(
		"CRM Call Log",
		call,
		{
			"custom_call_class": call_class,
			"custom_call_class_source": "human",
		},
		update_modified=False,
	)
	# get_call_log serves from the document cache — drop it so the next fetch
	# (and every other user's) sees the human verdict immediately
	frappe.clear_document_cache("CRM Call Log", call)
	return {"call_class": call_class, "source": "human"}
