"""Prompt the owner when an iSpeedToLead lead is refund-eligible on call volume.

iSpeedToLead refund when we place **10 outgoing dials inside 14 days** and never
reach anyone. The 10 are the **first** 10 outbound calls on the lead, not the
most recent 10 — a later no-answer streak cannot resurrect a flag. Dead/Lost
leads are excluded. When that trips, the lead page shows a banner and the
owner gets one CRM notification.

A connect is `custom_call_class == "Connected"` when the classifier (or a
human) has labelled the call; otherwise a talk-time of 60s or more. Incoming
calls do not count as dials, but a pickup on either direction — ever — or
any inbound text, kills the refund for good (Willie Simmons).

The custom fields this reads (`custom_refundable`, `custom_refund_requested`)
are provisioned by ops `setup_refundable_field.py`. Every access is
has_column-guarded so a site that has not run the script just never nudges.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import frappe
from frappe.utils import get_datetime

from crm.api.task_hygiene import is_terminal_status
from crm.fcrm.doctype.crm_notification.crm_notification import notify_user

ISTL_SOURCES = {"iSpeedToLead"}
MIN_CALLS = 10
WINDOW_DAYS = 14
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


def _when(row: dict) -> datetime | None:
	t = get_datetime(row.get("start_time")) if row.get("start_time") else None
	return t if isinstance(t, datetime) else None


def first_ten_in_fourteen(outgoing: list[dict]) -> dict | None:
	"""The first 10 outbound dials, if they all land inside 14 days."""
	dated = []
	for row in outgoing:
		t = _when(row)
		if t:
			dated.append((t, row))
	dated.sort(key=lambda x: x[0])
	if len(dated) < MIN_CALLS:
		return None
	batch = dated[:MIN_CALLS]
	first, last = batch[0][0], batch[-1][0]
	span = (last.date() - first.date()).days
	if span > WINDOW_DAYS:
		return None
	return {
		"calls": MIN_CALLS,
		"window_days": span,
		"first_at": first,
		"last_at": last,
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
	if is_terminal_status(lead.status):
		return {"show": False, "reason": "lost"}
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
		},
		fields=fields,
		order_by="start_time desc",
		limit_page_length=1000,
	)
	countable = [r for r in rows if (r.get("status") or "Completed") in COUNTABLE_STATUSES]
	# Lifetime, both directions. Once we have talked to them, never flag again.
	if any(_is_connect(r) for r in countable):
		return {"show": False, "reason": "connected"}
	if _inbound_text(lead_name):
		return {"show": False, "reason": "texted"}
	outgoing = [r for r in countable if (r.get("type") or "Outgoing") == "Outgoing"]
	hit = first_ten_in_fourteen(outgoing)
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
			f"day(s), no pickup and no text reply — ask iSpeedToLead for a refund."
		),
	}


def _inbound_text(lead_name: str) -> bool:
	"""Any inbound SMS on this lead. Sequence outbound does not count."""
	if not frappe.db.exists("DocType", "Quo Message"):
		return False
	return bool(
		frappe.db.count(
			"Quo Message",
			{
				"reference_doctype": "CRM Lead",
				"reference_docname": lead_name,
				"direction": "Incoming",
			},
		)
	)


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


def eligible_now():
	"""Bench-only, read-only: ISTL leads the first-10-days rule would flag."""
	import json

	leads = frappe.get_all(
		"CRM Lead",
		filters={"source": "iSpeedToLead"},
		fields=[
			"name",
			"lead_name",
			"lead_owner",
			"status",
			"creation",
			"property_address",
		],
		limit_page_length=2000,
	)
	hits = []
	reasons = {}
	for row in leads:
		r = evaluate(row.name)
		why = r.get("reason") or ("eligible" if r.get("show") else "no_outreach")
		reasons[why] = reasons.get(why, 0) + 1
		if not r.get("show"):
			continue
		owner = row.lead_owner or ""
		hits.append(
			{
				"name": row.name,
				"lead_name": row.lead_name,
				"owner": owner.split("@")[0] if owner else "",
				"status": row.status,
				"creation": str(row.creation)[:10],
				"calls": r.get("calls"),
				"address": row.property_address or "",
			}
		)
	hits.sort(key=lambda h: (-h["calls"], h["creation"]))
	print(json.dumps({"istl": len(leads), "reasons": reasons, "eligible": hits}, default=str))
	return {"istl": len(leads), "reasons": reasons, "n": len(hits)}
