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
from crm.integrations.telnyx import desk
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

	# CONFERENCE-FIRST DESK LEGS. Anything we dialled ourselves carries a
	# `kind` in client_state; those legs are wiring, not calls, and never get a
	# CRM Call Log of their own. The external party's leg (peer/caller) does.
	state_bits = desk.decode_client_state(payload.get("client_state"))
	kind = state_bits.get("kind")
	if kind in desk.INTERNAL_KINDS:
		_desk_internal_leg(event, payload, state_bits)
		return {"ok": True, "leg": kind}

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
		created = frappe.get_doc(doc).insert(ignore_permissions=True)
		if kind == "peer_leg":
			_desk_peer_initiated(created.name, payload, state_bits)
		elif inbound:
			# A line with ring members rings them (conference-first); otherwise the
			# legacy behaviour: answer and take voicemail in the line owner's voice.
			if not _desk_inbound_initiated(created.name, payload, to):
				_answer_and_take_voicemail(payload, to)
		return {"ok": True, "created": call_id}

	if event == "call.answered":
		state = _desk_state_for_external(payload)
		if state and kind == "peer_leg":
			_desk_peer_answered(state, payload)
		elif not state:
			# Legacy (non-desk) answered call: record it, dual channel, immediately.
			telnyx_api.start_recording(payload.get("call_control_id"))

	if event in ("call.answered", "call.hangup") and existing:
		updates = {"status": "Completed" if event == "call.hangup" else "In Progress"}
		if event == "call.hangup":
			updates["end_time"] = frappe.utils.now()
			updates["duration"] = _duration(payload, existing)
			if payload.get("hangup_cause") in ("call_rejected", "busy", "no_answer", "timeout"):
				updates["status"] = "No Answer"
			state = _desk_state_for_external(payload)
			if state:
				if not state.get("answered_by") and state.get("direction") == "inbound" and state.get("state") != "active":
					updates["status"] = "No Answer"
				_desk_end(state)
		frappe.db.set_value("CRM Call Log", existing, updates)

	return {"ok": True}


# ── the desk: conference-first legs ───────────────────────────────────────────


def _desk_state_for_external(payload):
	"""Desk state for an external leg (peer/caller), by its desk id or ccid."""
	bits = desk.decode_client_state(payload.get("client_state"))
	state = telephony._load(bits["desk"]) if bits.get("desk") else None
	if state:
		return state
	ccid = payload.get("call_control_id")
	for s in telephony._all_states():
		if ccid and ccid in (s.get("caller_leg"), s.get("peer_leg")):
			return s
	return None


def _desk_peer_initiated(call_log_name, payload, bits):
	"""The other party's leg exists: link the CRM Call Log to the desk state."""
	state = telephony._load(bits.get("desk") or "")
	if not state:
		return
	state["peer_leg"] = payload.get("call_control_id")
	state["call_log"] = call_log_name
	telephony._save(state)
	telephony.publish_call(state, "ringing")


def _desk_peer_answered(state, payload):
	"""Seller picked up: put them in the room with the rep; record if the line says so."""
	if not state.get("conference_id"):
		return
	ccid = payload.get("call_control_id")
	telnyx_api.conference_command(state["conference_id"], "join", desk.join_payload(ccid))
	state["state"] = "active"
	_desk_maybe_record(state, ccid)
	telephony._save(state)
	telephony.publish_call(state, "answered")


def _desk_inbound_initiated(call_log_name, payload, our_number) -> bool:
	"""Incoming call on a line with ring members: ring them all, first answer wins.

	Returns False when the line has nobody to ring (no CRM Phone Line, or no
	members with a reachable phone), so the caller falls through to voicemail.
	"""
	if not telephony.desk_enabled():
		return False
	line = telephony.line_by_number(our_number)
	if not line or not line.get("active", True):
		return False
	settings = telephony.phone_settings()
	members = desk.ring_members(line)
	sips = {u: telephony.sip_username(u) for u in members}
	mobiles = {u: telephony.user_mobile(u) for u in members} if settings["ring_cell_fallback"] else {}
	targets = desk.ring_targets(members, sips, mobiles, settings["ring_cell_fallback"])
	if not targets:
		return False
	connection = (frappe.conf.get("telnyx_connection_id") or "").strip()
	if not connection:
		return False

	desk_id = desk.new_desk_id()
	caller = payload.get("from")
	lead = frappe.db.get_value("CRM Call Log", call_log_name, "reference_docname")
	state = desk.new_state(desk_id, "inbound", line["number"], lead=lead, frm=caller, to=line["number"])
	state["caller_leg"] = payload.get("call_control_id")
	state["call_log"] = call_log_name
	state["started_at"] = frappe.utils.now()
	for target in targets:
		client_state = desk.encode_client_state(kind="ring_leg", desk=desk_id, user=target["user"], via=target["via"])
		try:
			data = telnyx_api._post(
				"/calls",
				desk.dial_leg_payload(connection, target["to"], caller or line["number"], client_state, settings["ring_timeout_secs"]),
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Telnyx: ring leg to {target['user']} failed")
			continue
		if data.get("call_control_id"):
			state["ring_legs"][data["call_control_id"]] = {"user": target["user"], "via": target["via"]}
	if not state["ring_legs"]:
		return False
	telephony._save(state)
	for user in members:
		try:
			frappe.publish_realtime(
				"crm_incoming",
				{"call_log": call_log_name, "desk_id": desk_id, "from": caller, "lead": lead,
				 "lead_name": telephony._lead_name(lead), "line": line["number"], "line_label": line.get("label")},
				user=user, after_commit=True,
			)
		except Exception:
			pass
	telephony.publish_call(state, "ringing")
	return True


def _desk_internal_leg(event, payload, bits):
	"""Events on the legs WE dialled: rep, ring members, supervisors."""
	state = telephony._load(bits.get("desk") or "")
	if not state:
		return
	ccid = payload.get("call_control_id")
	kind = bits.get("kind")

	if event == "call.answered":
		if kind == "rep_leg":
			_desk_rep_answered(state, ccid, bits)
		elif kind == "ring_leg":
			_desk_ring_answered(state, ccid)
		elif kind == "supervisor_leg":
			_desk_supervisor_answered(state, ccid, bits)
		return

	if event == "call.hangup":
		if kind == "ring_leg":
			state.get("ring_legs", {}).pop(ccid, None)
			if desk.all_ring_legs_gone(state):
				# Nobody picked up: voicemail on the caller's leg, as before.
				_answer_and_take_voicemail({"call_control_id": state.get("caller_leg")}, state.get("line"))
				state["state"] = "voicemail"
			telephony._save(state)
		elif kind == "supervisor_leg":
			state.get("supervisors", {}).pop(ccid, None)
			telephony._save(state)
			telephony.publish_call(state)
		elif kind == "rep_leg":
			# The rep hung up (or never answered): end the whole call.
			if state.get("peer_leg") and state.get("state") != "ended":
				telnyx_api.command(state["peer_leg"], "hangup")
			if state.get("caller_leg") and state.get("state") == "active":
				telnyx_api.command(state["caller_leg"], "hangup")
			if not state.get("peer_leg") and not state.get("caller_leg"):
				_desk_end(state)


def _desk_rep_answered(state, ccid, bits):
	"""Outbound: the rep is on. Make the room with them, then dial the other party into it."""
	state["rep_leg"] = ccid
	try:
		conf = telnyx_api.create_conference(desk.create_conference_payload(state["desk_id"], ccid))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Telnyx: conference create failed")
		telnyx_api.command(ccid, "hangup")
		_desk_end(state)
		return
	state["conference_id"] = conf.get("id")
	connection = (frappe.conf.get("telnyx_connection_id") or "").strip()
	client_state = desk.encode_client_state(kind="peer_leg", desk=state["desk_id"], user=state.get("rep"), lead=state.get("lead"))
	try:
		data = telnyx_api._post("/calls", desk.dial_leg_payload(connection, state["to"], state["from"], client_state))
		state["peer_leg"] = data.get("call_control_id")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Telnyx: peer dial failed")
		telnyx_api.command(ccid, "hangup")
		_desk_end(state)
		return
	telephony._save(state)
	telephony.publish_call(state, "ringing")


def _desk_ring_answered(state, ccid):
	"""Inbound: a ring member picked up. First one claims the call; the others are hung up."""
	if not desk.first_answer_wins(state, ccid):
		telnyx_api.command(ccid, "hangup")
		return
	caller = state.get("caller_leg")
	telnyx_api.command(caller, "answer")
	try:
		conf = telnyx_api.create_conference(desk.create_conference_payload(state["desk_id"], caller))
		state["conference_id"] = conf.get("id")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Telnyx: conference create failed (inbound)")
		# Degrade to a plain bridge so the caller is not left hanging.
		telnyx_api.command(caller, "bridge", {"call_control_id": ccid})
	if state.get("conference_id"):
		telnyx_api.conference_command(state["conference_id"], "join", desk.join_payload(ccid))
	for loser in desk.losing_ring_legs(state, ccid):
		telnyx_api.command(loser, "hangup")
		state["ring_legs"].pop(loser, None)
	_desk_maybe_record(state, caller)
	if state.get("call_log"):
		frappe.db.set_value("CRM Call Log", state["call_log"], {"receiver": state["rep"], "status": "In Progress"})
	telephony._save(state)
	telephony.publish_call(state, "answered")


def _desk_supervisor_answered(state, ccid, bits):
	"""A closer's leg is up: join as supervisor, then the rep-only join tone."""
	mode = bits.get("mode") if bits.get("mode") in desk.MODES else "monitor"
	conf = state.get("conference_id")
	if not conf:
		telnyx_api.command(ccid, "hangup")
		return
	telnyx_api.conference_command(conf, "join", desk.join_payload(ccid, mode, state.get("rep_leg")))
	state.setdefault("supervisors", {})[ccid] = {"user": bits.get("user"), "mode": mode, "joined": True}
	if state.get("rep_leg"):
		settings = telephony.phone_settings()
		action, body = desk.tone_payload(state["rep_leg"], settings.get("join_tone_url"))
		telnyx_api.conference_command(conf, action, body)
	telephony._save(state)
	telephony.publish_call(state, "supervisor_joined")


def _desk_maybe_record(state, external_ccid):
	"""Record at bridge time when the line resolves to recording on."""
	settings = telephony.phone_settings()
	line = telephony.line_by_number(state.get("line")) or {"recording": "inherit"}
	if desk.resolve_recording(line.get("recording"), settings["recording_default"]):
		telnyx_api.command(external_ccid, "record_start", desk.record_payload())
		state["recording"] = True


def _desk_end(state):
	state["state"] = "ended"
	telephony.publish_call(state, "ended")
	telephony._drop(state)


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
	line = telephony.line_by_number(our_number) if telephony.desk_enabled() else None
	owner = (line or {}).get("owner") or telephony.line_owners().get(telephony.last10(our_number))
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
