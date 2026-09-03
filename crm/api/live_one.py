# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

""" "Got a live one" — one click on a lead pings the closer in Mattermost.

A setter mid-call who realises the seller is real needs Dennis looking at the
house NOW, not after a Slack-style "hey are you around". This posts a message
with the lead, the address, the phone, an optional note from the rep, and a
link straight to the lead's COMPS screen (the page Dennis prices from), plus
the lead page.

**Posted AS THE REP, into their own DM with the closer** (Lance: Dennis
has to be able to reply to *them*). That needs a Mattermost personal access
token per rep: site_config `mattermost_user_tokens` is `{crm_login_email:
token}`, minted server-side with `mmctl --local token generate <username>
"CRM live-one alerts"` on the Mattermost box (`EnableUserAccessTokens` is on;
no per-user role is needed — the token is valid a moment after creation).
Adding a rep = mint a token, add the pair, `bench set-config … --parse`.

Fallback when the rep has no token (or IS the closer): the `pi` bot posts
into a GROUP of bot + rep + closer, naming the rep — the closer's reply still
lands with the rep, just in a three-way channel. No Mattermost account at
all → bot→closer DM. The closer is @mentioned in the fallback paths.

The recipient is site_config `live_one_user` (a Mattermost username,
default `dennisszafran`); the bot token/base are the same `mattermost_token`
/ `mattermost_base` the standup uses. Absent a bot token the endpoint refuses
with a readable error rather than silently no-oping — a rep who clicked this
needs to know it did not go out.

Every alert is also written onto the lead's timeline as a Comment, because
"did anyone flag this to Dennis?" is a question asked later, on the lead.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import escape_html, get_url

from crm.api.daily_standup import _mm, _mm_conf
from crm.api.reports import validate_access

DEFAULT_RECIPIENT = "dennisszafran"
TARGET_CACHE_KEY = "crm:live-one-target"
TARGET_CACHE_TTL = 3600


def _recipient_username() -> str:
	return (frappe.conf.get("live_one_user") or DEFAULT_RECIPIENT).strip()


def _display_name(user: dict) -> str:
	"""A human name for a Mattermost user. Profiles there are not reliably
	filled in (Dennis's has no first/last name at all), so the CRM User with
	the same email is the fallback before the bare username."""
	name = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x).strip()
	if name:
		return name
	if user.get("nickname"):
		return user["nickname"]
	email = (user.get("email") or "").strip().lower()
	if email and "@" in email:
		full = frappe.db.get_value("User", {"email": email, "enabled": 1}, "full_name")
		if full:
			return full
	return user.get("username") or ""


def _first_name(user: dict) -> str:
	if user.get("first_name"):
		return user["first_name"]
	full = _display_name(user)
	return full.split(" ")[0] if full else ""


@frappe.whitelist()
def get_target():
	"""Who the button alerts, for the UI to say so ("Alert Dennis"). Cached an
	hour; a Mattermost outage degrades to the bare username."""
	validate_access()
	username = _recipient_username()
	try:
		cached = frappe.cache().get_value(TARGET_CACHE_KEY)
	except Exception:
		cached = None
	if isinstance(cached, dict) and cached.get("username") == username:
		return cached
	out = {"username": username, "name": username, "first_name": username}
	base, token, _dm_user = _mm_conf()
	if token:
		try:
			u = _mm(f"/users/username/{username}", token, base)
			out = {
				"username": username,
				"name": _display_name(u) or username,
				"first_name": _first_name(u) or username,
			}
			frappe.cache().set_value(TARGET_CACHE_KEY, out, expires_in_sec=TARGET_CACHE_TTL)
		except Exception:
			pass
	return out


def _sender_mm_user(base, token):
	"""The rep's own Mattermost account, matched by CRM login email (the
	workspace uses the same addresses). None when they have no account."""
	email = (frappe.session.user or "").strip()
	if not email or "@" not in email:
		return None
	try:
		return _mm(f"/users/email/{email}", token, base)
	except Exception:
		return None


def _lead_summary(doc) -> dict:
	try:
		from crm.api.lead_phones import iter_phones

		phones = iter_phones(doc)
	except Exception:
		phones = [doc.get("mobile_no") or ""]
	return {
		"name": doc.get("lead_name") or doc.name,
		"address": doc.get("property_address") or "",
		"phones": [p for p in phones if p],
		"status": doc.get("status") or "",
	}


def _site_url() -> str:
	"""Public site URL. `get_url()` has no request to read a scheme from when
	this runs off a worker, and answers `http://`; the site is TLS-only, so
	a plain-http link would bounce through a redirect (or fail in a client
	that refuses it). Localhost is left alone for dev servers."""
	site = get_url().rstrip("/")
	if site.startswith("http://") and "localhost" not in site and "127.0.0.1" not in site:
		site = "https://" + site[len("http://") :]
	return site


def _phone_link(raw: str) -> str:
	"""`(618) 794-8139` as a Quo deep link. Same `openphone://dial` URL the
	CRM's own Call button uses on a phone (`utils/phoneFormat.js`); Mattermost
	renders any scheme that is not javascript/vbscript/data, and the OS hands
	it to the Quo app on desktop and mobile alike."""
	from urllib.parse import urlencode

	from crm.api.lead_phones import _to_e164

	e164 = _to_e164(raw)
	if not e164:
		return raw
	digits = e164[2:] if e164.startswith("+1") and len(e164) == 12 else ""
	label = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}" if digits else e164
	return f"[{label}](openphone://dial?{urlencode({'number': e164, 'action': 'call'})})"


def _user_token() -> str:
	"""The session user's own Mattermost PAT, or ''."""
	tokens = frappe.conf.get("mattermost_user_tokens") or {}
	if isinstance(tokens, str):
		try:
			tokens = json.loads(tokens)
		except ValueError:
			tokens = {}
	return (tokens.get((frappe.session.user or "").lower()) or "").strip()


def _message(sender_name, lead, summary, note, mention, as_self=False):
	"""The lead name IS the comps link — one click, no separate link line
	(Lance: the comps screen is the destination; the lead page is one click
	further from there anyway). `as_self`: the rep is speaking, so no
	third-person attribution and no @mention (a DM notifies by itself)."""
	site = _site_url()
	comps = f"{site}/crm/leads/{lead}/comps"
	if as_self:
		lines = [f"🔥 Got a live one: [**{summary['name']}**]({comps})"]
	else:
		lines = [f"🔥 {mention} **{sender_name}** has a live one: [**{summary['name']}**]({comps})"]
	if summary["address"]:
		lines.append(f"📍 {summary['address']}")
	for phone in summary["phones"]:
		lines.append(f"📞 {_phone_link(phone)}")
	if summary["status"]:
		lines.append(f"Status: {summary['status']}")
	if note:
		lines.append("")
		lines.append("> " + note.strip().replace("\n", "\n> "))
	return "\n".join(lines)


def _log_comment(lead, recipient_name, note, mode):
	try:
		head = _("Flagged as a live one to {0} on Mattermost").format(recipient_name)
		if mode == "direct":
			head += " " + _("(via the pi bot)")
		elif mode == "group":
			head += " " + _("(group chat with the pi bot)")
		content = "<div><b>{0}</b>{1}</div>".format(
			escape_html(head), "<br>{0}".format(escape_html(note)) if note else ""
		)
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Comment",
				"reference_doctype": "CRM Lead",
				"reference_name": lead,
				"content": content,
				"comment_email": frappe.session.user,
				"comment_by": frappe.session.user,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Live one: timeline comment failed")


@frappe.whitelist()
def alert(lead: str, note: str = ""):
	"""Post the alert. Returns {ok, mode: group|direct, to, channel_id}."""
	validate_access()
	if not lead or not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead not found"), frappe.DoesNotExistError)
	doc = frappe.get_doc("CRM Lead", lead)
	doc.check_permission("read")
	note = (note or "").strip()[:1000]

	base, token, _dm_user = _mm_conf()
	if not token:
		frappe.throw(_("Mattermost is not configured on this site, so the alert was not sent."))

	username = _recipient_username()
	target = _mm(f"/users/username/{username}", token, base)
	sender_name = frappe.utils.get_fullname(frappe.session.user) or frappe.session.user
	summary = _lead_summary(doc)
	recipient_name = _display_name(target) or username

	# Preferred: the rep's own DM with the closer, posted as the rep.
	user_token = _user_token()
	if user_token:
		try:
			as_user = _mm("/users/me", user_token, base)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Live one: rep's Mattermost token rejected")
			as_user = None
		if as_user and as_user["id"] != target["id"]:
			ch = _mm("/channels/direct", user_token, base, "POST", [as_user["id"], target["id"]])
			text = _message(sender_name, lead, summary, note, "", as_self=True)
			post = _mm("/posts", user_token, base, "POST", {"channel_id": ch["id"], "message": text})
			_log_comment(lead, recipient_name, note, "self")
			return {"ok": True, "mode": "self", "to": recipient_name, "post_id": post.get("id")}

	# Fallback: the bot speaks, in a group with the rep where possible.
	me = _mm("/users/me", token, base)
	sender = _sender_mm_user(base, token)
	mode = "direct"
	if sender and sender["id"] not in (target["id"], me["id"]):
		try:
			ch = _mm("/channels/group", token, base, "POST", [me["id"], sender["id"], target["id"]])
			mode = "group"
		except Exception:
			ch = _mm("/channels/direct", token, base, "POST", [me["id"], target["id"]])
	else:
		ch = _mm("/channels/direct", token, base, "POST", [me["id"], target["id"]])

	text = _message(sender_name, lead, summary, note, f"@{username}")
	post = _mm("/posts", token, base, "POST", {"channel_id": ch["id"], "message": text})
	_log_comment(lead, recipient_name, note, mode)
	return {"ok": True, "mode": mode, "to": recipient_name, "post_id": post.get("id")}
