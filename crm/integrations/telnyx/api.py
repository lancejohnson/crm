"""Telnyx: outbound calls and texts, and the config they read.

NATIVE Call Control, not TeXML. TeXML would let Telnyx pretend to be Twilio and
reuse more of upstream's code, but it cannot carry Media Streaming — the live
audio websocket the copilot needs — so the cheap start would have to be thrown
away exactly when the interesting work began.

Everything writes into the tables Quo already fills, with the discriminators the
prerequisite work put in place:

    CRM Call Log.medium   = "Telnyx"      (Quo rows say "Quo")
    Quo Message.provider  = "Telnyx"      (blank/"Quo" is legacy Quo)

That is what lets both providers run in parallel without every report silently
under-counting, which is the failure this migration is most likely to cause.

Config (site_config, all absent by default so this is inert until switched on):

    telnyx_api_key                the v2 API key
    telnyx_public_key             Ed25519 key that signs webhooks (GET /v2/public_key)
    telnyx_connection_id          call control application id
    telnyx_messaging_profile_id   messaging profile id
    telnyx_default_number         E.164 line to send from when a user has none
"""

import base64
import json

import frappe
import requests
from frappe import _

API = "https://api.telnyx.com/v2"
TIMEOUT = 20


def _key():
	return (frappe.conf.get("telnyx_api_key") or "").strip()


def enabled() -> bool:
	"""Whether Telnyx is configured at all. Every entry point checks this, so a
	site without the keys behaves exactly as it did before."""
	return bool(_key())


def _headers():
	return {"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"}


def _post(path, payload):
	r = requests.post(f"{API}{path}", json=payload, headers=_headers(), timeout=TIMEOUT)
	if r.status_code >= 400:
		# Surface Telnyx's own message: "Invalid Date"-class errors are only
		# debuggable if the body survives.
		frappe.log_error(
			title="Telnyx API error",
			message=f"POST {path} -> {r.status_code}\n{r.text[:2000]}\n{frappe.as_json(payload)[:1000]}",
		)
		frappe.throw(_("Telnyx rejected the request ({0}).").format(r.status_code))
	return r.json().get("data") or {}


def sending_number(user=None):
	"""The line this user sends from, or the site default.

	Reads through `telephony.user_lines`, so a rep who holds a Quo line AND a
	Telnyx line is answered per provider rather than by one single-valued field.
	"""
	from crm.api import telephony

	user = user or frappe.session.user
	line = telephony.sending_line(user, provider=telephony.TELNYX)
	return line or (frappe.conf.get("telnyx_default_number") or "").strip()


@frappe.whitelist()
def send_sms(to: str, text: str, reference_doctype: str = None, reference_docname: str = None):
	"""Send one text and mirror it into `Quo Message` as a Telnyx row.

	Do-not-contact is checked HERE as well as in the UI, and deliberately last:
	the flag is a statement about a person, it can be set by another system
	between the page rendering and the click, and "we were careful" is not a
	mechanism. Same rule `bulk_text.send_buyer_text` follows.
	"""
	if not enabled():
		frappe.throw(_("Telnyx is not configured on this site."))

	from crm.api.do_not_contact import is_blocked_number

	if is_blocked_number(to):
		frappe.throw(_("{0} has asked not to be contacted.").format(to))

	frm = sending_number()
	if not frm:
		frappe.throw(_("No Telnyx number is set for you or for this site."))

	payload = {"from": frm, "to": to, "text": text}
	profile = (frappe.conf.get("telnyx_messaging_profile_id") or "").strip()
	if profile:
		payload["messaging_profile_id"] = profile

	data = _post("/messages", payload)
	_store_message(
		direction="Outgoing",
		frm=frm,
		to=to,
		text=text,
		message_id=data.get("id"),
		reference_doctype=reference_doctype,
		reference_docname=reference_docname,
		sent_by=frappe.session.user,
	)
	return {"ok": True, "id": data.get("id"), "from": frm, "to": to}


@frappe.whitelist()
def dial(to: str, lead: str = None):
	"""Place an outbound call from the user's Telnyx line.

	The CRM Call Log row is written by the WEBHOOK, not here: a call that is
	dialled and then fails to connect is still a call that happened, and the
	webhook is the only place that knows how it ended. Writing it twice from two
	sources is how a call log ends up double-counted.
	"""
	if not enabled():
		frappe.throw(_("Telnyx is not configured on this site."))

	connection = (frappe.conf.get("telnyx_connection_id") or "").strip()
	if not connection:
		frappe.throw(_("No Telnyx call control application is configured."))

	frm = sending_number()
	if not frm:
		frappe.throw(_("No Telnyx number is set for you or for this site."))

	# VOICEMAIL IS REQUIRED BEFORE YOU CAN DIAL, and the gate is here rather than
	# in the UI because it is a promise to the person on the other end: we ring
	# sellers who then ring back, and a number that rings out with no greeting --
	# or worse, a stranger's default -- costs the lead we just paid for. Setting it
	# takes one sentence, so this is a small tax on the rep and a real protection
	# for the deal.
	if not voicemail_greeting(frappe.session.user):
		frappe.throw(
			_("Set your voicemail greeting before making calls — sellers call this number back."),
			title=_("Voicemail not set up"),
		)

	data = _post(
		"/calls",
		{
			"connection_id": connection,
			"to": to,
			"from": frm,
			# Carried back on every webhook for this call, so the handler can
			# attribute it to the person who dialled without guessing from the
			# line -- the exact trap that put 47 inbound calls on one rep.
			#
			# Telnyx requires this BASE64-ENCODED and hands it back verbatim; the
			# first cut sent plain UTF-8 (frappe.safe_encode) while the webhook
			# b64-decoded it, so every dial would have come back unattributed.
			"client_state": base64.b64encode(
				json.dumps({"user": frappe.session.user, "lead": lead}).encode()
			).decode(),
		},
	)
	return {"ok": True, "call_control_id": data.get("call_control_id"), "to": to, "from": frm}


def command(call_control_id: str, action: str, payload: dict = None):
	"""One Call Control command. Errors are logged, never raised: a command that
	fails mid-call must not take down the webhook that is handling the call."""
	try:
		return _post(f"/calls/{call_control_id}/actions/{action}", payload or {})
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Telnyx command {action} failed")
		return {}


def start_recording(call_control_id: str):
	"""Record the call, DUAL CHANNEL, with transcription.

	`channels: "dual"` is the whole reason this is worth doing on Telnyx: the rep
	and the other party land on separate channels, so who said what is a fact of
	the file rather than a guess. Quo gives one mixed channel, which is why
	`call_transcript.py` has to infer speakers from `userId` and a last-10 digit
	match -- and why an inbound call it cannot attribute reads as the wrong person.

	`transcription: true` here rather than a separate `transcription_start`: that
	one is the REAL-TIME stream (webhook `call.transcription`), which the copilot
	will need and which bills per minute. Paying for both to get one post-call
	transcript would be paying twice for the same words.
	"""
	return command(
		call_control_id,
		"record_start",
		{
			"format": "mp3",
			"channels": "dual",
			"play_beep": False,
			"transcription": True,
			"transcription_engine": "B",
			"transcription_language": "en",
		},
	)


def voicemail_greeting(user: str) -> str:
	"""This user's greeting, or "" if they have never set one."""
	if not frappe.db.has_column("User", "custom_voicemail_greeting"):
		return ""
	return (frappe.db.get_value("User", user, "custom_voicemail_greeting") or "").strip()


@frappe.whitelist()
def set_voicemail_greeting(greeting: str):
	"""Record the session user's own greeting. Text, spoken by Telnyx TTS.

	Text rather than an audio upload on purpose: a rep can fix a typo in ten
	seconds from a phone, and nobody has to find a quiet room to re-record.
	"""
	greeting = (greeting or "").strip()
	if len(greeting) < 10:
		frappe.throw(_("A voicemail greeting needs to be a sentence, not a word."))
	if not frappe.db.has_column("User", "custom_voicemail_greeting"):
		frappe.throw(_("Voicemail is not set up on this site yet."))
	frappe.db.set_value("User", frappe.session.user, "custom_voicemail_greeting", greeting)
	return {"ok": True, "greeting": greeting}


@frappe.whitelist()
def voicemail_status(user: str = None):
	"""Whether this user is ready to take calls. The UI gates on this."""
	user = user or frappe.session.user
	greeting = voicemail_greeting(user)
	return {"configured": bool(greeting), "greeting": greeting}


def _store_message(
	direction, frm, to, text, message_id=None, reference_doctype=None,
	reference_docname=None, sent_by=None, media=None, status="delivered",
):
	"""One text -> one `Quo Message` row, stamped as Telnyx.

	Idempotent on the provider's message id: Telnyx retries a webhook until it
	gets a 2xx, so the same inbound text arrives more than once as a matter of
	course, not as an anomaly.
	"""
	if not frappe.db.exists("DocType", "Quo Message"):
		return None
	if message_id and frappe.db.exists("Quo Message", {"id": message_id}):
		return None

	doc = {
		"doctype": "Quo Message",
		"id": message_id,
		"direction": direction,
		"from": frm,
		"to": to,
		"content": text,
		"status": status,
		"message_date": frappe.utils.now(),
	}
	if frappe.db.has_column("Quo Message", "provider"):
		doc["provider"] = "Telnyx"
	if media and frappe.db.has_column("Quo Message", "media"):
		doc["media"] = frappe.as_json(media)
	if sent_by and frappe.db.has_column("Quo Message", "sent_by"):
		doc["sent_by"] = sent_by
	if reference_doctype and reference_docname:
		doc["reference_doctype"] = reference_doctype
		doc["reference_docname"] = reference_docname

	return frappe.get_doc(doc).insert(ignore_permissions=True)
