"""Send a Pi-drafted refund reply from the lead page."""

from __future__ import annotations

import json
import html as htmlmod
import re

import frappe
from frappe import _

def _draft(lead) -> dict:
	raw = lead.get("custom_refund_draft_json") or ""
	if not raw:
		return {}
	try:
		return json.loads(raw)
	except json.JSONDecodeError:
		return {}


@frappe.whitelist()
def send_draft(lead: str):
	"""Send the stored refund draft as Lance, then clear it."""
	if not lead:
		frappe.throw(_("No lead"))
	doc = frappe.get_doc("CRM Lead", lead)
	doc.check_permission("write")
	if not doc.meta.has_field("custom_refund_draft_json"):
		frappe.throw(_("Refund draft field is not provisioned."))
	draft = _draft(doc)
	body = (draft.get("reply") or "").strip()
	if not body:
		frappe.throw(_("There is no draft to send."))

	to = draft.get("reply_to") or "support@ispeedtoleadhelp.zendesk.com"
	bracket = re.search(r"<([^>]+)>" , to)
	if bracket:
		to = bracket.group(1)
	subject = draft.get("subject") or "Re: Lead Refund"
	if not subject.lower().startswith("re:"):
		subject = "Re: " + subject
	html = "<p>" + htmlmod.escape(body).replace("\n", "<br>") + "</p>"

	from frappe.core.doctype.communication.email import make

	make(
		doctype="CRM Lead",
		name=doc.name,
		content=html,
		subject=subject,
		sender="lance.johnson@groundworkpro.com",
		recipients=to,
		send_email=1,
	)

	# make() already writes on the lead; saving the in-memory doc 409s.
	updates = {"custom_refund_draft_json": ""}
	if doc.meta.has_field("custom_refund_status"):
		updates["custom_refund_status"] = "Waiting on them"
	if doc.meta.has_field("custom_refund_requested"):
		updates["custom_refund_requested"] = 1
	frappe.db.set_value("CRM Lead", doc.name, updates, update_modified=False)
	return {"ok": True, "status": updates.get("custom_refund_status")}


@frappe.whitelist()
def get_draft(lead: str):
	if not lead:
		return {}
	frappe.has_permission("CRM Lead", "read", lead, throw=True)
	doc = frappe.get_doc("CRM Lead", lead)
	if not doc.meta.has_field("custom_refund_draft_json"):
		return {}
	return _draft(doc)
