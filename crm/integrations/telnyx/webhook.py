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
from crm.integrations.telnyx import api as telnyx_api
from crm.integrations.telnyx.api import _store_message

#: Seconds of silence before voicemail gives up. Long enough for a real message,
#: short enough that a pocket-dial does not record five minutes of a car.
VOICEMAIL_MAX_SECONDS = 120

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
	if event == "call.recording.saved":
		_save_recording(payload)
		return {"ok": True, "recording": True}

	if event == "call.recording.transcription.saved":
		_save_transcript(payload)
		return {"ok": True, "transcript": True}

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
			# `medium` is the discriminator -- free-text, and the Quo mirror has
			# always written it, which is why all 4,192 prod rows carry "Quo".
			#
			# `telephony_medium` is a SELECT limited to ""/Manual/Twilio/Exotel, so
			# writing "Telnyx" there fails validation -- the webhook 500s, Telnyx
			# retries, and no call is ever logged. Mirror what the Quo integration
			# does and leave it "Manual".
			"medium": "Telnyx",
			"telephony_medium": "Manual",
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

	# An answered call is a recorded call. Dual channel + transcription, started
	# the moment media exists rather than on a timer, so the first words of the
	# call -- the ones that decide the rest of it -- are in the file.
	if event == "call.answered":
		telnyx_api.start_recording(payload.get("call_control_id"))

	# INBOUND that nobody picked up -> voicemail, in the caller's own rep's voice.
	# Telnyx's own Voicemail product is number-level; doing it here means the
	# greeting is per USER and lives in the CRM next to everything else about them.
	if event == "call.initiated" and inbound:
		_answer_and_take_voicemail(payload, to)

	if event in ("call.answered", "call.hangup") and existing:
		updates = {"status": "Completed" if event == "call.hangup" else "In Progress"}
		if event == "call.hangup":
			updates["end_time"] = frappe.utils.now()
			updates["duration"] = _duration(payload, existing)
			if payload.get("hangup_cause") in ("call_rejected", "busy", "no_answer", "timeout"):
				updates["status"] = "No Answer"
		frappe.db.set_value("CRM Call Log", existing, updates)

	return {"ok": True}


def _answer_and_take_voicemail(payload, our_number):
	"""Answer, greet in the line owner's own words, and record a message.

	The greeting is the rep's, found from the line that was dialled -- the same
	line->user mapping the reports use, so a seller ringing German's number hears
	German. With no greeting set we still take a message rather than dropping the
	call: a missing greeting is our failure, and hanging up on a seller is theirs
	to suffer.
	"""
	call_control_id = payload.get("call_control_id")
	if not call_control_id:
		return
	owner = telephony.line_owners().get(telephony.last10(our_number))
	greeting = telnyx_api.voicemail_greeting(owner) if owner else ""
	if not greeting:
		greeting = (
			"Thanks for calling. Nobody is available right now — "
			"please leave a message after the tone and we'll call you straight back."
		)
	telnyx_api.command(call_control_id, "answer")
	telnyx_api.command(
		call_control_id,
		"speak",
		{"payload": greeting, "voice": "female", "language": "en-US"},
	)
	telnyx_api.command(
		call_control_id,
		"record_start",
		{
			"format": "mp3",
			"channels": "single",
			"play_beep": True,
			"max_length": VOICEMAIL_MAX_SECONDS,
			"transcription": True,
			"transcription_engine": "B",
			"transcription_language": "en",
		},
	)


def _save_recording(payload):
	"""Attach a finished recording to its call log.

	Writes `recording_url` -- the field the EXISTING Playback UI already reads --
	so a Telnyx call plays back through the same waveform, transcript and comment
	surface as a Quo one, with no frontend change at all.
	"""
	call_id = payload.get("call_session_id") or payload.get("call_control_id")
	name = frappe.db.get_value("CRM Call Log", {"id": call_id}, "name") if call_id else None
	if not name:
		return
	urls = payload.get("recording_urls") or payload.get("public_recording_urls") or {}
	url = urls.get("mp3") or urls.get("wav")
	if url and frappe.db.has_column("CRM Call Log", "recording_url"):
		frappe.db.set_value("CRM Call Log", name, "recording_url", url)


def _save_transcript(payload):
	"""Store a finished transcript in the shape `call_transcript.py` already reads.

	That shape is `{"dialogue": [{speaker, start, end, content}], "duration": n}`,
	and speaker is a REAL channel here rather than an inference: dual-channel
	recording means channel A is our line and channel B is the other party, which
	is exactly the distinction Quo forces us to guess at.
	"""
	call_id = payload.get("call_session_id") or payload.get("call_control_id")
	name = frappe.db.get_value("CRM Call Log", {"id": call_id}, "name") if call_id else None
	if not name or not frappe.db.has_column("CRM Call Log", "custom_transcript"):
		return

	dialogue = []
	for seg in payload.get("transcription_data") or payload.get("segments") or []:
		channel = str(seg.get("channel") or seg.get("speaker") or "").lower()
		dialogue.append(
			{
				# "A" is the leg we control on a dual-channel recording.
				"speaker": "rep" if channel in ("a", "1", "left", "rep") else "lead",
				"start": seg.get("start_time") or seg.get("start") or 0,
				"end": seg.get("end_time") or seg.get("end") or 0,
				"content": seg.get("transcript") or seg.get("text") or "",
			}
		)
	if not dialogue:
		text = payload.get("transcript") or payload.get("text")
		if not text:
			return
		dialogue = [{"speaker": "lead", "start": 0, "end": 0, "content": text}]

	frappe.db.set_value(
		"CRM Call Log",
		name,
		"custom_transcript",
		json.dumps({"dialogue": dialogue, "duration": payload.get("duration_millis", 0) / 1000 or 0}),
		update_modified=False,
	)


def _duration(payload, call_log_name):
	"""Seconds of call, from the best source available.

	Three sources, best first, because the obvious one is not always there: the
	first cut read `call_duration_secs` alone and a real answered call landed with
	**duration NULL** -- a call log that says nothing about talk time is useless to
	the activity report, the pulse and the desk, all of which sum exactly this
	column.

	1. whatever Telnyx states outright;
	2. its own start/end stamps, which describe the media rather than our webhooks;
	3. our row's start_time to now -- last resort, and it measures webhook arrival,
	   so it can only ever be slightly long.
	"""
	for key in ("call_duration_secs", "duration_secs", "call_duration"):
		value = payload.get(key)
		if value not in (None, ""):
			try:
				return int(float(value))
			except (TypeError, ValueError):
				pass

	start, end = payload.get("start_time"), payload.get("end_time")
	if start and end:
		try:
			from datetime import datetime

			parse = lambda s: datetime.fromisoformat(str(s).replace("Z", "+00:00"))
			return max(0, int((parse(end) - parse(start)).total_seconds()))
		except Exception:
			pass

	row_start = frappe.db.get_value("CRM Call Log", call_log_name, "start_time")
	if row_start:
		try:
			return max(
				0,
				int(
					(frappe.utils.now_datetime() - frappe.utils.get_datetime(row_start)).total_seconds()
				),
			)
		except Exception:
			pass
	return 0


def _client_state_user(payload):
	"""The CRM user we stamped on an outbound dial, if this is one of ours."""
	state = payload.get("client_state")
	if not state:
		return None
	try:
		return (json.loads(base64.b64decode(state).decode()) or {}).get("user")
	except Exception:
		return None
