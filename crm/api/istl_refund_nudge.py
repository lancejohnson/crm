"""Prompt the owner when an iSpeedToLead lead is refund-eligible on call volume.

iSpeedToLead refund when we dial a lot and never actually reach anyone.
The rule Lance asked for: **10 outgoing phone calls inside 21 calendar days
with no connect**. When that trips, the lead page shows a banner and the
owner gets one CRM notification.

A connect is `custom_call_class == "Connected"` when the classifier (or a
human) has labelled the call; otherwise a talk-time of 60s or more. Incoming
calls do not count toward the 10.

The custom fields this reads (`custom_refundable`, `custom_refund_requested`)
are provisioned by ops `setup_refundable_field.py`. Every access is
has_column-guarded so a site that has not run the script just never nudges.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import frappe
from frappe.utils import get_datetime

from crm.fcrm.doctype.crm_notification.crm_notification import notify_user

ISTL_SOURCES = {"iSpeedToLead"}
MIN_CALLS = 10
WINDOW_DAYS = 21
CONNECT_CLASS = "Connected"
CONNECT_SECONDS = 60
# Calls that never left the phone do not count as attempts.
COUNTABLE_STATUSES = {
	"Completed",
	"No Answer",
	"Busy",
	"Failed",
	"Canceled",
}


def _is_connect(row: dict) -> bool:
	klass = (row.get("custom_call_class") or "").strip()
	if klass:
		return klass == CONNECT_CLASS
	return int(row.get("duration") or 0) >= CONNECT_SECONDS


def window_from_calls(calls: list[dict]) -> dict | None:
	"""Return the 10-call / 21-day no-connect window, or None.

	`calls` must already be outgoing + countable, newest first.
	Pure function so the rule can be tested without a site.
	"""
	if len(calls) < MIN_CALLS:
		return None
	batch = calls[:MIN_CALLS]
	if any(_is_connect(row) for row in batch):
		return None
	times = [get_datetime(row.get("start_time")) for row in batch if row.get("start_time")]
	times = [t for t in times if isinstance(t, datetime)]
	if len(times) < MIN_CALLS:
		return None
	newest, oldest = max(times), min(times)
	if newest.date() - oldest.date() >= timedelta(days=WINDOW_DAYS):
		return None
	return {
		"calls": MIN_CALLS,
		"window_days": (newest.date() - oldest.date()).days,
		"first_at": oldest,
		"last_at": newest,
	}


def _lead_source(lead) -> str:
	return (lead.get("source") or "").strip()


def evaluate(lead_name: str) -> dict:
	"""Compute whether this lead should show the ISTL refund nudge."""
	empty = {"show": False}
	if not lead_name or not frappe.db.exists("CRM Lead", lead_name):
		return empty
	lead = frappe.get_doc("CRM Lead", lead_name)
	if _lead_source(lead) not in ISTL_SOURCES:
		return empty
	if lead.meta.has_field("custom_refund_requested") and lead.get("custom_refund_requested"):
		return {"show": False, "reason": "already_requested"}
	if lead.meta.has_field("custom_refundable") and lead.get("custom_refundable"):
		return {"show": False, "reason": "already_refundable"}

	fields = ["name", "start_time", "duration", "status", "type"]
	if frappe.db.has_column("CRM Call Log", "custom_call_class"):
		fields.append("custom_call_class")

	rows = frappe.get_all(
		"CRM Call Log",
		filters={
			"reference_doctype": "CRM Lead",
			"reference_docname": lead_name,
			"type": "Outgoing",
		},
		fields=fields,
		order_by="start_time desc",
		limit_page_length=50,
	)
	countable = [r for r in rows if (r.get("status") or "Completed") in COUNTABLE_STATUSES]
	hit = window_from_calls(countable)
	if not hit:
		return empty
	return {
		"show": True,
		"calls": hit["calls"],
		"window_days": hit["window_days"],
		"first_at": str(hit["first_at"]),
		"last_at": str(hit["last_at"]),
		"message": (
			f"{hit['calls']} outgoing calls in {hit['window_days'] or 'less than 1'} "
			f"day(s) and no connect — ask iSpeedToLead for a refund."
		),
	}


@frappe.whitelist()
def get_nudge(lead: str):
	"""Lead page banner. Sales users only see leads they can read."""
	if not lead:
		return {"show": False}
	frappe.has_permission("CRM Lead", "read", lead, throw=True)
	return evaluate(lead)


def on_call_log_change(doc, method=None):
	"""After a call is logged or updated, notify the owner once if the rule trips."""
	if doc.reference_doctype != "CRM Lead" or not doc.reference_docname:
		return
	if doc.type != "Outgoing":
		return
	try:
		result = evaluate(doc.reference_docname)
	except Exception:
		frappe.log_error(title="ISTL refund nudge failed")
		return
	if not result.get("show"):
		return
	lead = frappe.get_doc("CRM Lead", doc.reference_docname)
	owner = lead.lead_owner
	if not owner:
		return
	name = lead.lead_name or lead.name
	notify_user(
		{
			"owner": frappe.session.user if frappe.session.user != owner else "Administrator",
			"assigned_to": owner,
			"notification_type": "Assignment",
			"message": result["message"],
			"notification_text": (
				f'<div class="mb-2 leading-5 text-ink-gray-5">'
				f'<span class="font-medium text-ink-gray-9">{frappe.utils.escape_html(name)}</span>'
				f"<span> — {frappe.utils.escape_html(result['message'])}</span>"
				f"</div>"
			),
			"reference_doctype": "CRM Lead",
			"reference_docname": lead.name,
			"redirect_to_doctype": "CRM Lead",
			"redirect_to_docname": lead.name,
		}
	)
