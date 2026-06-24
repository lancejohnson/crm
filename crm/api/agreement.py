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
import re

import frappe
from frappe import _

AGREEMENT_DOCTYPE = "CRM Esign Agreement"

# Documenso public API (same host/version the ops server scripts use). The signed
# PDF lives behind the API token, so we proxy the bytes through the backend.
DOCUMENSO_API = "https://sign.groundworkpro.com/api/v2"


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
		r["is_signed"] = _is_completed(r)
	return rows


def _is_completed(agr) -> bool:
	"""A fully-signed agreement: Documenso says COMPLETED, or every signer signed."""
	if (agr.get("agreement_status") or "").upper() == "COMPLETED":
		return True
	signed = agr.get("signed_count") or 0
	total = agr.get("total_signers") or 0
	return bool(total and signed >= total)


def _signed_filename(agr) -> str:
	base = (agr.get("template_title") or "agreement").strip()
	safe = re.sub(r"[^\w.-]+", "_", base).strip("_") or "agreement"
	return f"{safe}_signed.pdf"


@frappe.whitelist()
def download_signed_agreement(agreement: str):
	"""Stream the fully-signed PDF for a completed CRM Esign Agreement.

	Documenso's `download-beta` endpoint hands back an internal, expiring MinIO
	presigned URL (`http://minio:9000/...`) that a browser can't reach, so we can't
	just store/redirect to a link. Instead the backend — which holds the Documenso
	API token — fetches the signed PDF bytes from `/document/{id}/download?version=signed`
	and streams them to the client as a download.
	"""
	import requests

	if not frappe.db.exists(AGREEMENT_DOCTYPE, agreement):
		frappe.throw(_("Agreement not found"), frappe.DoesNotExistError)

	agr = frappe.db.get_value(
		AGREEMENT_DOCTYPE,
		agreement,
		["lead", "document_id", "agreement_status", "signed_count", "total_signers", "template_title"],
		as_dict=True,
	)
	if not agr.lead or not frappe.has_permission("CRM Lead", "read", agr.lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not _is_completed(agr):
		frappe.throw(_("This agreement is not fully signed yet."))
	if not agr.document_id:
		frappe.throw(_("This agreement has no Documenso document on file."))

	token = (frappe.conf.get("documenso_api_token") or "").strip()
	if not token:
		frappe.throw(_("Documenso API token is not configured on this site."))

	try:
		resp = requests.get(
			f"{DOCUMENSO_API}/document/{agr.document_id}/download",
			params={"version": "signed"},
			headers={"Authorization": token},
			timeout=30,
		)
	except requests.RequestException:
		frappe.throw(_("Could not reach Documenso to fetch the signed document."))

	if resp.status_code != 200 or not resp.content:
		frappe.throw(_("Could not fetch the signed document from Documenso ({0}).").format(resp.status_code))

	frappe.local.response.filename = _signed_filename(agr)
	frappe.local.response.filecontent = resp.content
	frappe.local.response.type = "download"
