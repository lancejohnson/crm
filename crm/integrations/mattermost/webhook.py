"""The signed inbound endpoint the Mattermost forwarder posts to.

    POST /api/method/crm.integrations.mattermost.webhook.event
    X-Groundwork-Signature: sha256=<hex HMAC-SHA256(secret, raw body)>

GUEST, SO IT VERIFIES AND FAILS CLOSED. This creates chat rows from the public
internet; without a shared secret in site_config (`mattermost_sync_secret`) it
refuses everything rather than accepting everything — same rule as the Telnyx
and DocuSeal webhooks. The signature is over the RAW body: re-serialising
`frappe.form_dict` would change a byte and break it. Comparison is constant
time.

The forwarder lives in `Projects/Groundwork/mattermost/agent-listener`
(`crm_sync.py`) — the existing websocket listener already sees every post and
DM, which Mattermost's outgoing webhooks cannot (they skip DMs).

Envelope (what the forwarder sends; see the listener handoff):

    {
      "event": "posted" | "post_edited" | "post_deleted" | "status_change",
      "post": {id, channel_id, user_id, root_id, message, props, create_at, update_at, edit_at, delete_at},
      "channel": {id, type, name, display_name},
      "user": {id, username, email},
      "members": [{user_id, email?}],           # optional, on channel creation
      "status": {user_id, status}               # status_change only
    }
"""

from __future__ import annotations

import hashlib
import hmac
import json

import frappe

HEADER = "X-Groundwork-Signature"


def compute_signature(secret: str, raw_body: bytes) -> str:
	return "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, raw_body: bytes, header_value: str | None) -> bool:
	"""Pure: constant-time check; missing secret or header is a refusal."""
	if not secret or not header_value:
		return False
	given = header_value.strip()
	if not given.startswith("sha256="):
		given = "sha256=" + given
	return hmac.compare_digest(compute_signature(secret, raw_body), given)


def _verified_body() -> dict | None:
	secret = (frappe.conf.get("mattermost_sync_secret") or "").strip()
	raw = frappe.request.get_data() if frappe.request else b""
	headers = frappe.request.headers if frappe.request else {}
	header = headers.get(HEADER) or headers.get(HEADER.lower())
	if not secret:
		frappe.log_error(
			title="Mattermost sync refused",
			message="mattermost_sync_secret is not set; refusing to accept unverified events.",
		)
	if not verify_signature(secret, raw, header):
		frappe.local.response["http_status_code"] = 403
		return None
	try:
		return json.loads(raw or b"{}") or {}
	except ValueError:
		frappe.local.response["http_status_code"] = 400
		return None


@frappe.whitelist(allow_guest=True)
def event():
	envelope = _verified_body()
	if envelope is None:
		return {"ok": False}
	from crm.integrations.mattermost import sync

	try:
		result = sync.apply_event(envelope)
		frappe.db.commit()
		return result
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Mattermost sync: event failed")
		frappe.local.response["http_status_code"] = 500
		return {"ok": False}
