# Read API for the call transcript + waveform-sync view (Groundwork).
#
# The diarized transcript and (optional) Gemini chapters are captured into two
# custom Long Text fields on CRM Call Log by the ops repo's Quo webhook:
#   - custom_transcript          → {"dialogue": [{speaker|userId|identifier, start, end, content}], "duration": n}
#   - custom_transcript_chapters → {"chapters": [{title, start, end}], "highlights": [{quote, t}]}
# Neither field has to exist yet — this endpoint degrades to "no transcript".
#
# The frontend (components/Activities/CallTranscript.vue) needs clean speakers,
# so we normalize every segment to "rep" (the internal user) vs "lead" (the
# contact on the other end) here rather than in the browser.

import frappe
from frappe import _

from crm.integrations.api import get_contact_by_phone_number


def _last10(num):
	digits = "".join(ch for ch in str(num or "") if ch.isdigit())
	return digits[-10:]


@frappe.whitelist()
def get_call_transcript(call_log: str):
	if not call_log or not frappe.db.exists("CRM Call Log", call_log):
		frappe.throw(_("Call log not found"), frappe.DoesNotExistError)

	doc = frappe.get_cached_doc("CRM Call Log", call_log)
	if not doc.has_permission("read"):
		frappe.throw(_("Not permitted to read this call log."), frappe.PermissionError)

	recording_path = (
		f"/api/method/crm.integrations.api.get_recording_url?call_log_name={doc.name}"
		if doc.get("recording_url")
		else None
	)

	# Who is the rep vs the lead on this call. The internal user is the caller on
	# outgoing calls, the receiver on incoming; the other party is the contact.
	if doc.type == "Outgoing":
		rep_user, our_number, their_number = doc.caller, doc.get("from"), doc.to
	else:
		rep_user, our_number, their_number = doc.receiver, doc.to, doc.get("from")

	rep_name = (
		frappe.db.get_value("User", rep_user, "full_name") if rep_user else None
	) or _("Rep")
	contact = get_contact_by_phone_number(their_number)
	lead_name = (contact or {}).get("full_name") or _("Caller")

	our10 = _last10(our_number)
	their10 = _last10(their_number)

	dialogue = []
	talk = {"rep": 0.0, "lead": 0.0}
	api_duration = float(doc.get("duration") or 0)

	raw = doc.get("custom_transcript")
	if raw:
		try:
			data = frappe.parse_json(raw)
		except Exception:
			data = None
		segments = (data or {}).get("dialogue") or (data or {}).get("segments") or []
		for seg in segments:
			speaker = _classify_speaker(seg, our10, their10)
			start = float(seg.get("start") or 0)
			end = float(seg.get("end") if seg.get("end") is not None else start)
			content = (seg.get("content") or seg.get("text") or "").strip()
			if not content:
				continue
			dialogue.append(
				{"speaker": speaker, "start": start, "end": end, "content": content}
			)
			talk[speaker] += max(0.0, end - start)
		if (not api_duration) and isinstance(data, dict) and data.get("duration"):
			api_duration = float(data["duration"])
		if (not api_duration) and dialogue:
			api_duration = dialogue[-1]["end"]

	total = talk["rep"] + talk["lead"]
	talk_ratio = {
		"rep": round(talk["rep"] / total, 4) if total else 0,
		"lead": round(talk["lead"] / total, 4) if total else 0,
		"rep_seconds": round(talk["rep"]),
		"lead_seconds": round(talk["lead"]),
	}

	chapters, highlights = [], []
	chapters_raw = doc.get("custom_transcript_chapters")
	if chapters_raw:
		try:
			c = frappe.parse_json(chapters_raw)
			chapters = c.get("chapters") or []
			highlights = c.get("highlights") or []
		except Exception:
			pass

	return {
		"has_transcript": bool(dialogue),
		"recording_url_path": recording_path,
		"duration": api_duration,
		"dialogue": dialogue,
		"talk_ratio": talk_ratio,
		"chapters": chapters,
		"highlights": highlights,
		"rep_name": rep_name,
		"lead_name": lead_name,
	}


def _classify_speaker(seg, our10, their10):
	"""Map one transcript segment to 'rep' or 'lead'.

	Trusts (in order): a pre-normalized `speaker`, OpenPhone's `userId` (present
	only on the internal participant), then a last-10-digit identifier match.
	"""
	sp = seg.get("speaker")
	if sp in ("rep", "lead"):
		return sp
	if seg.get("userId"):
		return "rep"
	ident = _last10(seg.get("identifier") or seg.get("speaker"))
	if ident and ident == our10:
		return "rep"
	if ident and ident == their10:
		return "lead"
	# Unknown identifier with no userId → assume the outside party.
	return "lead"
