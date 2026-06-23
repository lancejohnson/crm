"""E-sign agreements (Documenso) tracked per lead.

A user clicks **Create Purchase Agreement** on a lead → the `create-agreement-draft`
server script (ops repo) spins up a pre-filled Documenso draft and inserts a
**CRM Esign Agreement** row. A Documenso webhook → the `documenso-webhook` server
script updates that row's status as recipients open / sign / complete.

Both server scripts run in the RestrictedPython sandbox, which can't
`publish_realtime` or reliably stamp time — so the live refresh + time-stamping
happen here on the insert/update hooks, broadcasting a `crm_esign` realtime event
so the open lead's sidebar card + Activity timeline refresh live. Mirrors the
tax-info pattern (crm/api/tax_info.py).
"""

import json

import frappe
from frappe import _

AGREEMENT_DOCTYPE = "CRM Esign Agreement"


def _publish(lead):
	if lead:
		frappe.publish_realtime(
			"crm_esign",
			{"reference_doctype": "CRM Lead", "reference_docname": lead},
			after_commit=True,
		)


def on_agreement_insert(doc, method=None):
	"""after_insert — stamp the created time + live-refresh the open lead."""
	if not doc.get("last_event_at"):
		frappe.db.set_value(doc.doctype, doc.name, {"last_event_at": doc.creation}, update_modified=False)
	_publish(doc.get("lead"))


def on_agreement_update(doc, method=None):
	"""on_update — webhook status changes land here; stamp + live-refresh.

	set_value(update_modified=False) writes directly and fires no doc events, so
	there is no recursion with the webhook's save().
	"""
	frappe.db.set_value(doc.doctype, doc.name, {"last_event_at": frappe.utils.now_datetime()}, update_modified=False)
	_publish(doc.get("lead"))


@frappe.whitelist()
def get_agreements(lead: str):
	"""E-sign agreements for a lead, most recent first (sidebar card + timeline)."""
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead not found"), frappe.DoesNotExistError)
	if not frappe.has_permission("CRM Lead", "read", lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.db.exists("DocType", AGREEMENT_DOCTYPE):
		return []

	rows = frappe.get_all(
		AGREEMENT_DOCTYPE,
		filters={"lead": lead},
		fields=[
			"name",
			"document_id",
			"template_title",
			"agreement_status",
			"signed_count",
			"total_signers",
			"buyer_link",
			"seller_links",
			"last_event",
			"last_event_at",
			"creation",
			"owner",
		],
		order_by="creation desc",
	)
	for r in rows:
		r["created_by_name"] = frappe.get_cached_value("User", r.owner, "full_name") if r.owner else None
		try:
			r["seller_links"] = json.loads(r.get("seller_links") or "[]")
		except (ValueError, TypeError):
			r["seller_links"] = []
	return rows
