"""Telnyx webhooks: inbound texts and call events.

TWO GUEST ENDPOINTS, BOTH SIGNATURE-VERIFIED:

    crm.integrations.telnyx.webhook.messaging
    crm.integrations.telnyx.webhook.voice

VERIFICATION IS MANDATORY AND FAILS CLOSED. These are `allow_guest` endpoints on
a public host, and they create CRM records — a forged POST would otherwise
manufacture calls and texts. Telnyx signs `timestamp|body` with Ed25519; we check
that against the account's public key (`GET /v2/public_key`, stored as
`telnyx_public_key`). With no key configured the endpoints refuse everything
rather than accepting it, because the alternative is a webhook that looks like it
works and is wide open.

The timestamp is checked too: a valid signature is valid forever, so without a
freshness window a captured request can be replayed indefinitely.

Rows land in the SAME tables Quo fills, marked `medium`/`provider = "Telnyx"`, so
the activity report, the intraday pulse, the standup and the desk all keep
working across both providers.
"""

import base64
import json
import time

import frappe

from crm.api import telephony
from crm.integrations.telnyx.api import _store_message

#: How old a signed request may be. Telnyx retries for a while, so this is not a
#: delivery deadline -- it is a replay window.
MAX_SKEW_SECONDS = 5 * 60


def _verify(raw_body: bytes) -> bool:
	"""Ed25519 over `timestamp|body`, per Telnyx's webhook signing."""
	public_key = (frappe.conf.get("telnyx_public_key") or "").strip()
	if not public_key:
		frappe.log_error(
			title="Telnyx webhook refused",
			message="telnyx_public_key is not set; refusing to accept unverified webhooks.",
		)
		return False

	headers = frappe.request.headers if frappe.request else {}
	signature = headers.get("Telnyx-Signature-Ed25519") or headers.get("telnyx-signature-ed25519")
	timestamp = headers.get("Telnyx-Timestamp") or headers.get("telnyx-timestamp")
	if not signature or not timestamp:
		return False

	try:
		if abs(time.time() - int(timestamp)) > MAX_SKEW_SECONDS:
			return False
	except (TypeError, ValueError):
		return False

	try:
		from cryptography.exceptions import InvalidSignature
		from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

		key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))
		signed = f"{timestamp}|".encode() + raw_body
		key.verify(base64.b64decode(signature), signed)
		return True
	except InvalidSignature:
		return False
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Telnyx signature check failed")
		return False


def _payload():
	"""The verified event payload, or None. Reads the RAW body: re-serialising
	`frappe.form_dict` would change a byte somewhere and break the signature."""
	raw = frappe.request.get_data() if frappe.request else b""
	if not _verify(raw):
		frappe.local.response["http_status_code"] = 403
		return None
	try:
		return (json.loads(raw or b"{}") or {}).get("data") or {}
	except ValueError:
		frappe.local.response["http_status_code"] = 400
		return None


def _link(number: str):
	"""(doctype, name) for whoever owns this number — lead first, then buyer.

	Leads win ties: a person who is both is being called about their house.
	Matching is last-10 through the shared helper, so this cannot disagree with
	the attribution the reports use.
	"""
	digits = telephony.last10(number)
	if not digits:
		return None, None
	for doctype, fields in (("CRM Lead", ("mobile_no", "phone")), ("CRM Buyer", ("phone",))):
		if not frappe.db.exists("DocType", doctype):
			continue
		for field in fields:
			if not frappe.db.has_column(doctype, field):
				continue
			row = frappe.db.sql(
				f"""SELECT name FROM `tab{doctype}`
				    WHERE RIGHT(REGEXP_REPLACE(COALESCE(`{field}`,''), '[^0-9]', ''), 10) = %s
				    LIMIT 1""",
				(digits,),
				as_dict=True,
			)
			if row:
				return doctype, row[0].name
	return None, None


@frappe.whitelist(allow_guest=True)
def messaging():
	"""Inbound SMS/MMS, and delivery receipts for what we sent."""
	data = _payload()
	if data is None:
		return {"ok": False}

	event = data.get("event_type") or ""
	payload = data.get("payload") or {}
	if event not in ("message.received", "message.sent", "message.finalized"):
		return {"ok": True, "ignored": event}

	# Only inbound creates a row; the outbound row was written when we sent it.
	if payload.get("direction") != "inbound":
		return {"ok": True, "ignored": "outbound receipt"}

	frm = (payload.get("from") or {}).get("phone_number")
	to = ((payload.get("to") or [{}])[0]).get("phone_number")
	doctype, name = _link(frm)
	_store_message(
		direction="Incoming",
		frm=frm,
		to=to,
		text=payload.get("text") or "",
		message_id=payload.get("id"),
		reference_doctype=doctype,
		reference_docname=name,
		media=[{"url": m.get("url"), "type": m.get("content_type")} for m in (payload.get("media") or [])],
		status="received",
	)
	return {"ok": True}


@frappe.whitelist(allow_guest=True)
def voice():
	"""Call events -> one `CRM Call Log` row per call, updated as it progresses.

	`call.initiated` opens the row and `call.hangup` closes it. Duration comes
	from the hangup event rather than being computed here, because Telnyx knows
	when the media actually stopped and we only know when a webhook arrived.
	"""
	data = _payload()
	if data is None:
		return {"ok": False}

	event = data.get("event_type") or ""
	payload = data.get("payload") or {}
	call_id = payload.get("call_session_id") or payload.get("call_control_id")
	if not call_id:
		return {"ok": True, "ignored": "no call id"}

	if not frappe.db.exists("DocType", "CRM Call Log"):
		return {"ok": True, "ignored": "no call log doctype"}

	inbound = (payload.get("direction") or "") == "incoming"
	frm = payload.get("from")
	to = payload.get("to")
	external = frm if inbound else to

	existing = frappe.db.get_value("CRM Call Log", {"id": call_id}, "name")

	if event == "call.initiated" and not existing:
		doctype, name = _link(external)
		doc = {
			"doctype": "CRM Call Log",
			"id": call_id,
			"from": frm,
			"to": to,
			"type": "Incoming" if inbound else "Outgoing",
			"status": "Ringing",
			"medium": "Telnyx",
			"telephony_medium": "Telnyx",
			"start_time": frappe.utils.now(),
		}
		if doctype:
			doc["reference_doctype"] = doctype
			doc["reference_docname"] = name
		# Who dialled, carried on client_state, NOT inferred from the line: on an
		# INCOMING call the line owner is not the person who answered, and
		# guessing that way is what once mis-attributed 47 calls.
		user = _client_state_user(payload)
		if user:
			doc["caller" if not inbound else "receiver"] = user
		frappe.get_doc(doc).insert(ignore_permissions=True)
		return {"ok": True, "created": call_id}

	if event in ("call.answered", "call.hangup") and existing:
		updates = {"status": "Completed" if event == "call.hangup" else "In Progress"}
		if event == "call.hangup":
			updates["end_time"] = frappe.utils.now()
			seconds = payload.get("call_duration_secs") or payload.get("duration_secs")
			if seconds is not None:
				updates["duration"] = int(seconds)
			if payload.get("hangup_cause") in ("call_rejected", "busy", "no_answer", "timeout"):
				updates["status"] = "No Answer"
		frappe.db.set_value("CRM Call Log", existing, updates)

	return {"ok": True}


def _client_state_user(payload):
	"""The CRM user we stamped on an outbound dial, if this is one of ours."""
	state = payload.get("client_state")
	if not state:
		return None
	try:
		return (json.loads(base64.b64decode(state).decode()) or {}).get("user")
	except Exception:
		return None
