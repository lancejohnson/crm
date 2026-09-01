"""Send a Pi-drafted refund reply from the lead page."""

from __future__ import annotations

import json
import html as htmlmod
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

REFUND_STATUSES = (
	"To Request",
	"Requested",
	"Waiting on us",
	"Waiting on them",
	"Complete",
)


def _as_bool(value) -> bool:
	return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _draft(lead) -> dict:
	raw = lead.get("custom_refund_draft_json") or ""
	if not raw:
		return {}
	try:
		return json.loads(raw)
	except json.JSONDecodeError:
		return {}


@frappe.whitelist()
def set_refund_state(
	lead: str,
	refundable=None,
	not_in_provider=None,
	manual_ticket=None,
	status: str | None = None,
):
	"""Keep the lead-page refund controls internally consistent.

	A manual support ticket is already a request: it must put the lead on the
	Refunds board and out of To Request in one click. Clearing Refundable is the
	explicit remove-from-board action and clears the workflow flags with it.
	"""
	if not lead:
		frappe.throw(_("No lead"))
	doc = frappe.get_doc("CRM Lead", lead)
	doc.check_permission("write")
	if not doc.meta.has_field("custom_refundable"):
		frappe.throw(_("Refund fields are not provisioned."))

	updates = {}
	if refundable is not None:
		on = _as_bool(refundable)
		updates["custom_refundable"] = 1 if on else 0
		if on:
			if not (doc.get("custom_refund_status") or "").strip():
				updates["custom_refund_status"] = "To Request"
		else:
			updates.update({
				"custom_refund_requested": 0,
				"custom_refund_requested_on": None,
				"custom_refund_status": "",
			})
			if doc.meta.has_field("custom_refund_not_in_provider"):
				updates["custom_refund_not_in_provider"] = 0
			if doc.meta.has_field("custom_refund_manual_ticket"):
				updates["custom_refund_manual_ticket"] = 0

	if not_in_provider is not None:
		if not doc.meta.has_field("custom_refund_not_in_provider"):
			frappe.throw(_("Provider-form tracking is not provisioned."))
		missing = _as_bool(not_in_provider)
		updates["custom_refund_not_in_provider"] = 1 if missing else 0
		if missing:
			updates["custom_refundable"] = 1
			if not (doc.get("custom_refund_status") or "").strip():
				updates["custom_refund_status"] = "To Request"

	if manual_ticket is not None:
		if not doc.meta.has_field("custom_refund_manual_ticket"):
			frappe.throw(_("Manual refund tracking is not provisioned."))
		manual = _as_bool(manual_ticket)
		updates["custom_refund_manual_ticket"] = 1 if manual else 0
		if manual:
			updates["custom_refundable"] = 1
			if doc.meta.has_field("custom_refund_not_in_provider"):
				updates["custom_refund_not_in_provider"] = 1
			updates["custom_refund_requested"] = 1
			if not doc.get("custom_refund_requested_on"):
				updates["custom_refund_requested_on"] = now_datetime()
			if (doc.get("custom_refund_status") or "") in ("", "To Request"):
				updates["custom_refund_status"] = "Requested"

	if status is not None:
		status = (status or "").strip()
		if status not in REFUND_STATUSES:
			frappe.throw(_("Invalid refund status."))
		updates["custom_refundable"] = 1
		updates["custom_refund_status"] = status
		if status != "To Request":
			updates["custom_refund_requested"] = 1
			if not doc.get("custom_refund_requested_on"):
				updates["custom_refund_requested_on"] = now_datetime()

	if updates:
		frappe.db.set_value("CRM Lead", doc.name, updates, update_modified=False)
	return {"ok": True, **updates}


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
