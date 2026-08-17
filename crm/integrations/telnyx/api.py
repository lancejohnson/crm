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

	data = _post(
		"/calls",
		{
			"connection_id": connection,
			"to": to,
			"from": frm,
			# Carried back on every webhook for this call, so the handler can
			# attribute it to the person who dialled without guessing from the
			# line -- the exact trap that put 47 inbound calls on one rep.
			"client_state": frappe.safe_encode(
				frappe.as_json({"user": frappe.session.user, "lead": lead})
			).decode()
			if hasattr(frappe, "safe_encode")
			else None,
		},
	)
	return {"ok": True, "call_control_id": data.get("call_control_id"), "to": to, "from": frm}


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
