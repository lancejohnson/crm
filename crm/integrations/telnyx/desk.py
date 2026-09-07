"""The phone desk's pure logic: numbers, line access, ring fan-out, and the
exact Telnyx Call Control payloads for a CONFERENCE-FIRST call.

Nothing here touches frappe or the network, so every rule is unit-tested
without a bench. The glue lives in `crm/api/telephony.py` (endpoints) and
`crm/integrations/telnyx/webhook.py` (event handling); both call into here.

WHY CONFERENCE-FIRST. A plain bridge is a private pipe between two legs —
nobody can attach to it later. Putting the rep and the other party into a
two-person conference from the start sounds and behaves identically to them,
but the room has a door: a closer can `join` as `monitor` / `whisper` / `barge`
mid-call, the tone that tells the rep someone joined can be played to the REP
LEG ONLY, and a third party can be invited without tearing the call down.

THE LEGS (each is its own Telnyx call, told apart by `client_state.kind`):

    rep_leg         outbound: we ring the rep's own softphone first
    peer_leg        outbound: the seller/buyer, dialled once the rep answered
    caller_leg      inbound:  the external party who rang one of our lines
    ring_leg        inbound:  one per ring member (softphone or cell); first
                              answer wins, the rest are hung up
    supervisor_leg  a closer joining an in-progress call

`desk_id` ties the legs of one call together: it is minted in `dial()` (or on
the inbound `call.initiated`), carried in every leg's client_state, and is the
key of the transient state kept in Redis while the call is up. The `CRM Call
Log` row is still written by the webhook and only for the EXTERNAL leg (peer or
caller) — the existing rule — so a call that never connects is still logged and
nothing is logged twice.

Telnyx commands used (all POST, see /tmp/telnyx-spec.json when present):

    /calls                                          place a leg
    /calls/{id}/actions/answer                      pick up the caller leg
    /calls/{id}/actions/hangup
    /conferences  {call_control_id, name,           create the room with its
                   beep_enabled: never,              first participant
                   start_conference_on_create: true}
    /conferences/{id}/actions/join                  add a leg; supervisors pass
        {call_control_id, supervisor_role,           monitor|whisper|barge (+
         whisper_call_control_ids, beep_enabled}     whisper targets)
    /conferences/{id}/actions/update                change a supervisor's role
    /conferences/{id}/actions/play {audio_url,       play a file to SOME legs —
         call_control_ids: [rep_leg]}                the rep-only join tone
    /conferences/{id}/actions/speak {payload,        TTS fallback for the tone
         call_control_ids: [rep_leg]}
    /calls/{id}/actions/record_start                dual-channel recording
"""

from __future__ import annotations

import base64
import json
import re
import secrets

KINDS = ("rep_leg", "peer_leg", "caller_leg", "ring_leg", "supervisor_leg")
MODES = ("monitor", "whisper", "barge")
INTERNAL_KINDS = ("rep_leg", "ring_leg", "supervisor_leg")

#: Default seconds a ring member's phone rings before Telnyx gives up on that leg.
RING_TIMEOUT_SECS = 25
#: Default TTS the rep hears when a supervisor joins and no tone file is set.
DEFAULT_JOIN_TONE_TEXT = "Someone is listening."
DEFAULT_CONSENT_NOTE = (
	"Turning recording on does not obtain consent. Whether a call may be recorded, "
	"who must be told and how, and how long recordings are kept are decided by the "
	"laws of every state a call touches and by company policy — settle those before "
	"recording real calls."
)


# ── numbers ────────────────────────────────────────────────────────────────────


def e164(value) -> str:
	"""`+1XXXXXXXXXX` for anything that looks like a US/NANP number; '' otherwise.

	Ten digits are assumed US, eleven starting with 1 are US, anything else
	with 11–15 digits is passed through with a `+` (we do dial internationally,
	rarely). Letters and punctuation are ignored. SIP URIs are returned as-is.
	"""
	text = str(value or "").strip()
	if text.lower().startswith("sip:"):
		return text
	digits = re.sub(r"\D", "", text)
	if len(digits) == 10:
		return "+1" + digits
	if len(digits) == 11 and digits.startswith("1"):
		return "+" + digits
	if 11 <= len(digits) <= 15:
		return "+" + digits
	return ""


def last10(value) -> str:
	digits = re.sub(r"\D", "", str(value or ""))
	return digits[-10:] if len(digits) >= 10 else digits


def sip_uri(username: str) -> str:
	return f"sip:{username}@sip.telnyx.com" if username else ""


# ── client_state ───────────────────────────────────────────────────────────────


def encode_client_state(**fields) -> str:
	"""Base64 JSON — Telnyx requires base64 and hands it back verbatim."""
	clean = {k: v for k, v in fields.items() if v not in (None, "")}
	return base64.b64encode(json.dumps(clean, separators=(",", ":")).encode()).decode()


def decode_client_state(value) -> dict:
	if not value:
		return {}
	try:
		data = json.loads(base64.b64decode(value).decode())
		return data if isinstance(data, dict) else {}
	except Exception:
		return {}


def new_desk_id() -> str:
	return secrets.token_hex(6)


def conference_name(desk_id: str) -> str:
	return f"crm-{desk_id}"


# ── line access & recording ────────────────────────────────────────────────────


def line_access(line: dict, user: str) -> dict:
	"""{view, use, ring} for `user` on a line. The owner has everything."""
	user = (user or "").lower()
	if (line.get("owner") or "").lower() == user:
		return {"view": True, "use": True, "ring": True}
	for m in line.get("members") or []:
		if (m.get("user") or "").lower() == user:
			return {"view": bool(m.get("view")), "use": bool(m.get("use")), "ring": bool(m.get("ring"))}
	return {"view": False, "use": False, "ring": False}


def can(line: dict, user: str, permission: str) -> bool:
	return bool(line_access(line, user).get(permission))


def resolve_recording(line_recording, workspace_default) -> bool:
	"""inherit -> the workspace default; on/off are explicit overrides."""
	value = (line_recording or "inherit").strip().lower()
	if value == "on":
		return True
	if value == "off":
		return False
	return bool(workspace_default)


def ring_members(line: dict) -> list[str]:
	"""Logins whose phone rings on an incoming call to this line. Owner always."""
	out = []
	owner = (line.get("owner") or "").lower()
	if owner:
		out.append(owner)
	for m in line.get("members") or []:
		login = (m.get("user") or "").lower()
		if login and m.get("ring") and login not in out:
			out.append(login)
	return out


def ring_targets(members: list[str], sip_usernames: dict, mobiles: dict, cell_fallback: bool) -> list[dict]:
	"""What to dial for each ring member: their softphone, plus their cell when
	the fallback is on. A member with neither is skipped, not guessed at."""
	targets = []
	for login in members:
		sip = sip_usernames.get(login)
		if sip:
			targets.append({"user": login, "to": sip_uri(sip), "via": "softphone"})
		cell = e164(mobiles.get(login)) if cell_fallback else ""
		if cell:
			targets.append({"user": login, "to": cell, "via": "cell"})
	return targets


# ── Telnyx payloads ────────────────────────────────────────────────────────────


def dial_leg_payload(connection_id: str, to: str, frm: str, client_state: str, timeout_secs: int | None = None) -> dict:
	body = {"connection_id": connection_id, "to": to, "from": frm, "client_state": client_state}
	if timeout_secs:
		body["timeout_secs"] = int(timeout_secs)
	return body


def create_conference_payload(desk_id: str, call_control_id: str) -> dict:
	return {
		"call_control_id": call_control_id,
		"name": conference_name(desk_id),
		"beep_enabled": "never",
		"start_conference_on_create": True,
		"comfort_noise": True,
	}


def join_payload(call_control_id: str, mode: str | None = None, rep_leg: str | None = None) -> dict:
	"""A participant joins; with `mode` they join as a supervisor.

    monitor -> hears everyone, heard by nobody
    whisper -> hears everyone, heard by the rep leg only
    barge   -> a normal participant (Telnyx's own definition)

	`beep_enabled: never` on every join: the seller must never hear a join
	beep, and the rep-only tone is played separately (see tone_payload).
	"""
	body = {"call_control_id": call_control_id, "beep_enabled": "never"}
	if mode:
		if mode not in MODES:
			raise ValueError(f"unknown mode {mode}")
		body["supervisor_role"] = mode
		if mode == "whisper" and rep_leg:
			body["whisper_call_control_ids"] = [rep_leg]
	return body


def update_mode_payload(call_control_id: str, mode: str, rep_leg: str | None = None) -> dict:
	if mode not in MODES:
		raise ValueError(f"unknown mode {mode}")
	body = {"call_control_id": call_control_id, "supervisor_role": mode}
	if mode == "whisper" and rep_leg:
		body["whisper_call_control_ids"] = [rep_leg]
	return body


def tone_payload(rep_leg: str, audio_url: str | None = None, text: str | None = None) -> tuple[str, dict]:
	"""(action, body) for the rep-only join tone: `play` a file when one is
	configured, else `speak` a short phrase. `call_control_ids` scopes it to
	the rep leg — the other party hears nothing."""
	if audio_url:
		return "play", {"audio_url": audio_url, "call_control_ids": [rep_leg]}
	return "speak", {
		"payload": text or DEFAULT_JOIN_TONE_TEXT,
		"voice": "female",
		"language": "en-US",
		"call_control_ids": [rep_leg],
	}


def record_payload() -> dict:
	return {
		"format": "mp3",
		"channels": "dual",
		"play_beep": False,
		"transcription": True,
		"transcription_engine": "B",
		"transcription_language": "en",
	}


# ── call state (transient, lives in Redis while a call is up) ─────────────────


def new_state(desk_id: str, direction: str, line: str, rep: str | None = None, lead: str | None = None, to: str | None = None, frm: str | None = None) -> dict:
	return {
		"desk_id": desk_id,
		"direction": direction,  # outbound | inbound
		"line": line,
		"rep": rep,
		"lead": lead,
		"to": to,
		"from": frm,
		"call_log": None,
		"conference_id": None,
		"rep_leg": None,
		"peer_leg": None,
		"caller_leg": None,
		"ring_legs": {},  # ccid -> {user, via}
		"supervisors": {},  # ccid -> {user, mode}
		"state": "ringing",  # ringing | active | ended
		"answered_by": None,
		"recording": False,
		"started_at": None,
	}


def first_answer_wins(state: dict, ccid: str) -> bool:
	"""True if this ring leg is the first to answer (and claims the call)."""
	if state.get("answered_by") or state.get("state") == "active":
		return False
	leg = (state.get("ring_legs") or {}).get(ccid)
	if not leg:
		return False
	state["answered_by"] = leg["user"]
	state["rep"] = leg["user"]
	state["rep_leg"] = ccid
	state["state"] = "active"
	return True


def losing_ring_legs(state: dict, winner: str) -> list[str]:
	return [ccid for ccid in (state.get("ring_legs") or {}) if ccid != winner]


def all_ring_legs_gone(state: dict) -> bool:
	return not state.get("ring_legs") and state.get("state") == "ringing"


def leg_kind(state: dict, ccid: str) -> str | None:
	if ccid == state.get("rep_leg"):
		return "rep_leg"
	if ccid == state.get("peer_leg"):
		return "peer_leg"
	if ccid == state.get("caller_leg"):
		return "caller_leg"
	if ccid in (state.get("ring_legs") or {}):
		return "ring_leg"
	if ccid in (state.get("supervisors") or {}):
		return "supervisor_leg"
	return None


def external_leg(state: dict) -> str | None:
	return state.get("peer_leg") or state.get("caller_leg")


def active_call_row(state: dict, lead_name: str | None = None) -> dict:
	"""The shape `telephony.active_calls()` returns."""
	return {
		"call_log": state.get("call_log"),
		"desk_id": state.get("desk_id"),
		"rep": state.get("rep"),
		"lead": state.get("lead"),
		"lead_name": lead_name,
		"number": state.get("to") if state.get("direction") == "outbound" else state.get("from"),
		"line": state.get("line"),
		"direction": state.get("direction"),
		"state": state.get("state"),
		"started_at": state.get("started_at"),
		"conference": state.get("conference_id"),
		"supervisors": [
			{"user": s.get("user"), "mode": s.get("mode")} for s in (state.get("supervisors") or {}).values()
		],
		"recording": bool(state.get("recording")),
	}
