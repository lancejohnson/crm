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

# Any of these changing is a refund ACTION, and stamps custom_refund_updated_on.
# The board shows that stamp as "Updated" because `modified` is the whole lead
# and moves for a status change, a note, a phone edit — none of which say
# anything about where the refund is.
REFUND_FIELDS = (
	"custom_refundable",
	"custom_refund_requested",
	"custom_refund_requested_on",
	"custom_refund_not_in_provider",
	"custom_refund_manual_ticket",
	"custom_refund_status",
)
UPDATED_FIELD = "custom_refund_updated_on"

# A lead the provider will never refund. Today that is one case: iSpeedToLead
# orders paid from the "Sale leads balance" (their `bonus` wallet). LeadMarket
# reads the wallet split off every order and calls `mark_non_refundable` with
# the order ids; `CRM Lead.vendor_lead_id` IS the iSTL order id (the webhook's
# `lead_id`), so the join is exact. Fields: ops `setup_refundable_field.py`.
NON_REFUNDABLE_FIELD = "custom_non_refundable"
NON_REFUNDABLE_REASON_FIELD = "custom_non_refundable_reason"
DEFAULT_NON_REFUNDABLE_REASON = "Paid with iSpeedToLead sale-leads (bonus) balance"


def _has_updated_field() -> bool:
	return frappe.db.has_column("CRM Lead", UPDATED_FIELD)


def _has_non_refundable_field() -> bool:
	return frappe.db.has_column("CRM Lead", NON_REFUNDABLE_FIELD)


def is_non_refundable(doc) -> bool:
	"""True when the provider will not refund this lead. has_field-guarded so a
	site that has not run the ops script simply never says so."""
	try:
		return bool(doc.meta.has_field(NON_REFUNDABLE_FIELD) and doc.get(NON_REFUNDABLE_FIELD))
	except Exception:
		return False


def on_lead_update(doc, method=None):
	"""CRM Lead on_update: stamp the refund clock when a refund field moved via
	doc.save — the mail poller's REST PUTs and the lead-page Refundable toggle.
	The set_value paths below stamp it themselves. Best-effort."""
	try:
		if not _has_updated_field():
			return
		if doc.flags.in_insert or not any(
			doc.has_value_changed(f) for f in REFUND_FIELDS if doc.meta.has_field(f)
		):
			return
		frappe.db.set_value(
			"CRM Lead", doc.name, UPDATED_FIELD, now_datetime(), update_modified=False
		)
	except Exception:
		frappe.log_error("refund updated_on stamp failed")


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

	# Every branch below except "clear Refundable" puts the lead on the Refunds
	# board. A non-refundable lead must not get there by any of them -- the
	# request would be filed, tracked, chased, and denied.
	wants_on_board = (
		(refundable is not None and _as_bool(refundable))
		or (not_in_provider is not None and _as_bool(not_in_provider))
		or (manual_ticket is not None and _as_bool(manual_ticket))
		or status is not None
	)
	if wants_on_board and is_non_refundable(doc):
		why = (doc.get(NON_REFUNDABLE_REASON_FIELD) or "").strip() if doc.meta.has_field(
			NON_REFUNDABLE_REASON_FIELD
		) else ""
		frappe.throw(
			_("This lead is non-refundable{0}.").format(f" — {why}" if why else ""),
			title=_("Non-refundable"),
		)

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
		if _has_updated_field():
			updates[UPDATED_FIELD] = now_datetime()
		frappe.db.set_value("CRM Lead", doc.name, updates, update_modified=False)
	return {"ok": True, **updates}


@frappe.whitelist()
def mark_non_refundable(orders, reason: str | None = None):
	"""Flag the leads behind these iSpeedToLead ORDER ids as non-refundable.

	Called by LeadMarket (`src/refundability.py`) after every purchase sync with
	the orders paid from the bonus wallet; idempotent, so it is safe to be called
	with the same ids again. Returns {matched: [order ids], unmatched: [...],
	leads: {order id: lead name}} so the caller can stop re-sending the matched
	ones and retry the rest (the vendor webhook may not have landed yet).

	A lead already queued on the Refunds board is flagged but NOT pulled off it:
	the board shows the flag and a human decides whether to withdraw. Nothing
	here ever clears the flag.

	    bench --site crm.groundworkpro.com execute crm.api.refunds.mark_non_refundable \
	        --kwargs '{"orders": ["6aa1c76307686fe776648f22"]}'
	"""
	frappe.only_for(("System Manager", "Sales Manager"))
	if not _has_non_refundable_field():
		frappe.throw(_("custom_non_refundable is not provisioned."))
	if isinstance(orders, str):
		try:
			parsed = json.loads(orders)
		except json.JSONDecodeError:
			parsed = [orders]
		orders = parsed if isinstance(parsed, list) else [parsed]
	ids = []
	for o in orders or []:
		o = str(o or "").strip()
		if o and o not in ids:
			ids.append(o)
	if not ids:
		return {"matched": [], "unmatched": [], "leads": {}}
	reason = (reason or DEFAULT_NON_REFUNDABLE_REASON).strip()[:140]
	has_reason = frappe.db.has_column("CRM Lead", NON_REFUNDABLE_REASON_FIELD)

	rows = frappe.get_all(
		"CRM Lead",
		filters={"vendor_lead_id": ["in", ids]},
		fields=["name", "vendor_lead_id", NON_REFUNDABLE_FIELD, "custom_refundable"],
		limit=len(ids) + 50,
	)
	leads, already_on_board = {}, []
	for r in rows:
		leads[r["vendor_lead_id"]] = r["name"]
		if r.get(NON_REFUNDABLE_FIELD):
			continue
		updates = {NON_REFUNDABLE_FIELD: 1}
		if has_reason:
			updates[NON_REFUNDABLE_REASON_FIELD] = reason
		if _has_updated_field():
			updates[UPDATED_FIELD] = now_datetime()
		frappe.db.set_value("CRM Lead", r["name"], updates, update_modified=False)
		if r.get("custom_refundable"):
			already_on_board.append(r["name"])
	if already_on_board:
		frappe.log_error(
			"Non-refundable lead(s) already on the Refunds board: " + ", ".join(already_on_board),
			"mark_non_refundable",
		)
	matched = [o for o in ids if o in leads]
	unmatched = [o for o in ids if o not in leads]
	return {"matched": matched, "unmatched": unmatched, "leads": leads,
		"already_on_board": already_on_board}


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
	if _has_updated_field():
		updates[UPDATED_FIELD] = now_datetime()
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


def _last_refund_activity(name: str):
	"""Reconstruct the last refund action from what already exists on the lead:
	Version rows touching a refund field (doc.save paths), refund email
	Communications (the poller attaches every provider message), the poller's
	refund Comments, and the request stamp. set_value writes left no trace,
	so a drag on the board before gw442 is genuinely unrecoverable."""
	ts = []
	for v in frappe.get_all(
		"Version",
		filters={"ref_doctype": "CRM Lead", "docname": name},
		fields=["creation", "data"],
		limit=500,
	):
		if "custom_refund" in (v.data or ""):
			ts.append(v.creation)
	for c in frappe.get_all(
		"Communication",
		filters={"reference_doctype": "CRM Lead", "reference_name": name},
		fields=["creation"],
	):
		ts.append(c.creation)
	for c in frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "CRM Lead",
			"reference_name": name,
			"comment_type": "Comment",
		},
		fields=["creation", "content"],
	):
		if "refund" in (c.content or "").lower():
			ts.append(c.creation)
	requested_on = frappe.db.get_value("CRM Lead", name, "custom_refund_requested_on")
	if requested_on:
		ts.append(requested_on)
	return max(ts) if ts else None


@frappe.whitelist()
def backfill_refund_updated_on(dry_run=1, overwrite=0):
	"""bench execute crm.api.refunds.backfill_refund_updated_on --kwargs '{"dry_run":0}'

	Fills custom_refund_updated_on on every refundable lead from the
	reconstructible history; a lead with no trace falls back to `modified`
	(the previous meaning of "Updated"). Leaves already-stamped leads alone
	unless overwrite=1. Writes with update_modified=False.
	"""
	frappe.only_for(("System Manager", "Sales Manager"))
	if not _has_updated_field():
		frappe.throw(_("custom_refund_updated_on is not provisioned."))
	dry = _as_bool(dry_run)
	rows = frappe.get_all(
		"CRM Lead",
		filters={"custom_refundable": 1},
		fields=["name", "modified", UPDATED_FIELD],
		limit=5000,
	)
	out = {"total": len(rows), "from_history": 0, "from_modified": 0, "skipped": 0, "dry_run": dry}
	for r in rows:
		if r.get(UPDATED_FIELD) and not _as_bool(overwrite):
			out["skipped"] += 1
			continue
		when = _last_refund_activity(r.name)
		if when:
			out["from_history"] += 1
		else:
			when = r.modified
			out["from_modified"] += 1
		if not dry:
			frappe.db.set_value(
				"CRM Lead", r.name, UPDATED_FIELD, when, update_modified=False
			)
	if not dry:
		frappe.db.commit()
	return out
