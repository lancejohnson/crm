# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Call history export for a refund request.

iSpeedToLead refunds a lead when we can SHOW the dials — ten outbound calls
inside fourteen days and nobody picked up (see `istl_refund_nudge.py`). The
proof they accept is a list of calls with recordings. Before this, a rep
assembled that by hand: open each CRM Call Log, copy the Quo recording link,
paste it into the ticket. This produces the whole list in one click, two ways:

* **CSV download** — date/time, direction, from/to, status, duration, outcome,
  rep, recording link — for attaching to a ticket or an email.
* **Plain text** (copy button) — the same rows as a numbered list with a
  one-line summary on top, for pasting straight into the provider's form.

**Recording links are the Quo share URLs already on the call log**
(`share.quo.com/…?sig=…`): signed, public, and playable without a login —
verified with an anonymous ranged GET (206, audio/mpeg). That is exactly what
a third party needs. The CRM's own `get_recording_url` proxy needs a CRM
session and is useless to iSpeedToLead.

Calls are the ones LINKED to the lead (`reference_docname`), plus any unlinked
log whose from/to number is one of the lead's phones — the multi-phone backfill
relinks those on the next add, but a call logged between adds would otherwise
be missing from the very list that is supposed to be complete. Oldest first,
because the refund story reads forward: "we called on the 1st, the 2nd, …".
"""

from __future__ import annotations

import csv
import io
import re

import frappe
from frappe import _
from frappe.utils import get_datetime

from crm.utils import seconds_to_duration

DIALED_STATUSES = {"Completed", "No Answer", "Busy", "Failed", "Canceled"}


def _digits10(v) -> str:
	d = re.sub(r"\D", "", str(v or ""))
	return d[-10:] if len(d) >= 10 else ""


def _lead_phones(doc) -> list[str]:
	try:
		from crm.api.lead_phones import iter_phones

		phones = iter_phones(doc)
	except Exception:
		phones = [doc.get("mobile_no") or "", doc.get("phone") or ""]
	return [p for p in phones if p]


def _call_fields() -> list[str]:
	fields = [
		"name",
		"caller",
		"receiver",
		"`from`",
		"`to`",
		"duration",
		"start_time",
		"status",
		"type",
		"recording_url",
		"creation",
		"reference_docname",
	]
	if frappe.db.has_column("CRM Call Log", "custom_call_class"):
		fields.append("custom_call_class")
	return fields


def _rows(doc) -> list[dict]:
	fields = _call_fields()
	rows = frappe.get_all(
		"CRM Call Log",
		filters={"reference_doctype": "CRM Lead", "reference_docname": doc.name},
		fields=fields,
		limit_page_length=2000,
	)
	seen = {r["name"] for r in rows}
	keys = {_digits10(p) for p in _lead_phones(doc)}
	keys.discard("")
	if keys:
		# Unlinked logs on the lead's numbers. `reference_docname` empty is the
		# genuinely-unlinked test (the doctype has a default, see CLAUDE.md).
		for r in frappe.get_all(
			"CRM Call Log",
			filters=[["reference_docname", "in", ["", None]]],
			or_filters=[["from", "like", f"%{k}"] for k in keys] + [["to", "like", f"%{k}"] for k in keys],
			fields=fields,
			limit_page_length=2000,
		):
			if r["name"] not in seen and (_digits10(r.get("from")) in keys or _digits10(r.get("to")) in keys):
				rows.append(r)
				seen.add(r["name"])
	rows.sort(key=lambda r: (get_datetime(r.get("start_time") or r.get("creation")), r["name"]))
	return rows


def _rep_name(row) -> str:
	user = row.get("caller") if (row.get("type") or "Outgoing") == "Outgoing" else row.get("receiver")
	if not user:
		return ""
	return frappe.utils.get_fullname(user) or user


def _shape(rows) -> list[dict]:
	out = []
	for i, r in enumerate(rows, 1):
		when = get_datetime(r.get("start_time") or r.get("creation"))
		out.append(
			{
				"n": i,
				"name": r["name"],
				"when": when.strftime("%Y-%m-%d %H:%M:%S") if when else "",
				"date": when.strftime("%b %-d, %Y") if when else "",
				"time": when.strftime("%-I:%M %p") if when else "",
				"direction": r.get("type") or "Outgoing",
				"from": r.get("from") or "",
				"to": r.get("to") or "",
				"status": r.get("status") or "",
				"duration": int(r.get("duration") or 0),
				"duration_label": seconds_to_duration(r.get("duration") or 0),
				"outcome": r.get("custom_call_class") or "",
				"rep": _rep_name(r),
				"recording_url": r.get("recording_url") or "",
			}
		)
	return out


def _summary(doc, calls) -> dict:
	outgoing = [c for c in calls if c["direction"] == "Outgoing"]
	first = next((c["date"] for c in calls if c["date"]), "")
	last = next((c["date"] for c in reversed(calls) if c["date"]), "")
	return {
		"total": len(calls),
		"outgoing": len(outgoing),
		"incoming": len(calls) - len(outgoing),
		"with_recording": sum(1 for c in calls if c["recording_url"]),
		"connected": sum(1 for c in calls if c["outcome"] == "Connected"),
		"first": first,
		"last": last,
	}


def _header(doc) -> str:
	bits = [doc.get("lead_name") or doc.name]
	if doc.get("property_address"):
		bits.append(doc.get("property_address"))
	phones = _lead_phones(doc)
	if phones:
		bits.append(" / ".join(phones))
	return " · ".join(bits)


def _render_text(doc, calls, summary) -> str:
	L = [f"Call history — {_header(doc)}"]
	span = f" · {summary['first']} – {summary['last']}" if summary["first"] else ""
	L.append(
		f"{summary['outgoing']} outgoing call(s), {summary['incoming']} incoming, "
		f"{summary['connected']} connected, {summary['with_recording']} with a recording{span}"
	)
	L.append("")
	for c in calls:
		line = f"{c['n']}. {c['date']} {c['time']} CT · {c['direction']}"
		if c["duration"]:
			line += f" · {c['duration_label']}"
		if c["status"]:
			line += f" · {c['status']}"
		if c["outcome"]:
			line += f" · {c['outcome']}"
		if c["direction"] == "Outgoing" and c["to"]:
			line += f" · to {c['to']}"
		elif c["from"]:
			line += f" · from {c['from']}"
		line += f" — {c['recording_url']}" if c["recording_url"] else " — no recording"
		L.append(line)
	return "\n".join(L)


def _load(lead: str):
	if not lead or not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead not found"), frappe.DoesNotExistError)
	frappe.has_permission("CRM Lead", "read", lead, throw=True)
	doc = frappe.get_doc("CRM Lead", lead)
	calls = _shape(_rows(doc))
	return doc, calls, _summary(doc, calls)


@frappe.whitelist()
def get_call_history(lead: str):
	"""Rows + summary + the pasteable text, for the Refund card."""
	doc, calls, summary = _load(lead)
	return {
		"lead": doc.name,
		"header": _header(doc),
		"summary": summary,
		"calls": calls,
		"text": _render_text(doc, calls, summary),
	}


def _slug(text: str) -> str:
	s = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-")
	return s[:60] or "lead"


@frappe.whitelist()
def export_call_history(lead: str, fmt: str = "csv"):
	"""GET → file download. `fmt` is csv (default) or txt."""
	doc, calls, summary = _load(lead)
	base = f"call-history-{_slug(doc.get('lead_name') or doc.name)}"
	if (fmt or "csv").lower() == "txt":
		content = _render_text(doc, calls, summary)
		frappe.local.response.filename = f"{base}.txt"
		frappe.local.response.filecontent = content.encode("utf-8")
		frappe.local.response.type = "download"
		frappe.local.response.content_type = "text/plain"
		return

	buf = io.StringIO()
	w = csv.writer(buf)
	w.writerow(["Lead", doc.get("lead_name") or doc.name])
	w.writerow(["Property", doc.get("property_address") or ""])
	w.writerow(["Phone(s)", " / ".join(_lead_phones(doc))])
	w.writerow(
		[
			"Summary",
			f"{summary['outgoing']} outgoing, {summary['incoming']} incoming, "
			f"{summary['connected']} connected, {summary['with_recording']} with a recording",
		]
	)
	w.writerow([])
	w.writerow(
		[
			"#",
			"Date",
			"Time (CT)",
			"Direction",
			"From",
			"To",
			"Status",
			"Duration (s)",
			"Duration",
			"Outcome",
			"Rep",
			"Recording URL",
		]
	)
	for c in calls:
		w.writerow(
			[
				c["n"],
				c["date"],
				c["time"],
				c["direction"],
				c["from"],
				c["to"],
				c["status"],
				c["duration"],
				c["duration_label"],
				c["outcome"],
				c["rep"],
				c["recording_url"],
			]
		)
	frappe.local.response.filename = f"{base}.csv"
	frappe.local.response.filecontent = buf.getvalue().encode("utf-8-sig")
	frappe.local.response.type = "download"
	frappe.local.response.content_type = "text/csv"
