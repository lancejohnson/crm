"""Two-way sync between Talk (`CRM Message`) and Mattermost.

MATTERMOST STAYS THE SOURCE OF TRUTH DURING THE TRANSITION. If this module
dies, the team keeps chatting in Mattermost and loses nothing; the CRM just goes
quiet until it is fixed. That is the whole reason the sync is a mirror and not a
migration.

Outbound (CRM -> MM): `mirror_message(name, action)` runs off the `CRM Message`
after_insert / on_update / on_trash hooks (enqueued, after commit). Posts as the
author through their own PAT when we hold one; otherwise as the `pi` bot with a
`**Name:**` prefix. Every post we write carries `props.crm_origin = 1` and
`props.crm_message = <name>`, and the returned post id is stored on the row.

Inbound (MM -> CRM): `apply_event(envelope)` is what the signed webhook hands
us. `posted` inserts, `post_edited` updates text/edited_at, `post_deleted` flags
`deleted`, `status_change` updates presence. Two loop guards, both pure and
tested: skip when the post carries `crm_origin`, and skip when its id already
exists as a `CRM Message.mm_post_id`. A Mattermost channel we have never seen is
created on the spot from its type (O/P -> channel, D -> dm, G -> channel) with
membership pulled from Mattermost, so a new channel over there is a new channel
here with no admin step.

Users are matched BY EMAIL — both systems run on the Workspace accounts — and a
Mattermost author with no CRM login is written as the bot with the MM username
carried in `author_label`, so nothing is dropped for want of a mapping.

`backfill(channel, since_days)` pulls a channel's recent history; it is
idempotent on `mm_post_id` and safe to re-run.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import frappe

from crm.integrations.mattermost import client

CHANNEL = "CRM Channel"
MESSAGE = "CRM Message"
MEMBER = "CRM Channel Member"

MM_TYPE_TO_KIND = {"O": "channel", "P": "channel", "D": "dm", "G": "channel"}


# ── pure helpers (unit-tested) ─────────────────────────────────────────────────


def is_crm_origin(post: dict) -> bool:
	"""True when a Mattermost post was written by us (carries crm_origin)."""
	props = (post or {}).get("props") or {}
	if isinstance(props, str):
		try:
			props = json.loads(props)
		except ValueError:
			props = {}
	value = props.get("crm_origin")
	return bool(value) and str(value).lower() not in ("0", "false", "")


def should_skip_inbound(post: dict, known_post_ids) -> bool:
	"""The loop guard: our own post, or one we already hold."""
	if is_crm_origin(post):
		return True
	pid = (post or {}).get("id")
	return bool(pid) and pid in known_post_ids


def kind_for_mm_type(mm_type: str) -> str:
	return MM_TYPE_TO_KIND.get((mm_type or "").upper(), "channel")


def channel_slug(mm_channel: dict) -> str:
	"""Slug for a Mattermost channel we are meeting for the first time.

	Public/private channels keep Mattermost's own URL name (`acquisitions`); DMs
	and groups get a stable id-derived slug so two syncs cannot invent two rows.
	"""
	kind = kind_for_mm_type(mm_channel.get("type"))
	if kind == "dm":
		return f"dm-{(mm_channel.get('id') or '')[:12]}"
	name = (mm_channel.get("name") or "").strip().lower()
	if not name or "__" in name:  # MM names DM/group channels `id__id`
		return f"mm-{(mm_channel.get('id') or '')[:12]}"
	return name


def bot_prefixed(full_name: str, text: str) -> str:
	"""How a bot-posted mirror names its real author."""
	return f"**{full_name}:** {text}" if full_name else text


def ms_to_datetime(ms) -> datetime:
	return datetime.utcfromtimestamp(int(ms or 0) / 1000.0)


def inbound_row(post: dict, channel_name: str, author: str, author_label: str | None) -> dict:
	"""Shape a Mattermost post as a CRM Message insert dict."""
	return {
		"doctype": MESSAGE,
		"channel": channel_name,
		"author": author,
		"author_label": author_label,
		"text": post.get("message") or "",
		"posted_at": ms_to_datetime(post.get("create_at")),
		"origin": "mattermost",
		"mm_post_id": post.get("id"),
		"mm_root_id": post.get("root_id") or None,
		"edited_at": ms_to_datetime(post["edit_at"]) if post.get("edit_at") else None,
		"deleted": 1 if post.get("delete_at") else 0,
		"props": json.dumps({"mirror": False}),
	}


def status_for(mm_status: str) -> str:
	return mm_status if mm_status in ("online", "away", "offline", "dnd") else "offline"


# ── user / channel mapping ─────────────────────────────────────────────────────


def _bot_user() -> str:
	from crm.api.talk import bot_user

	return bot_user()


def crm_user_for_mm(mm_user: dict | None) -> tuple[str, str | None]:
	"""(author login, author_label). Email match first; else bot + username."""
	if not mm_user:
		return _bot_user(), "mattermost"
	email = (mm_user.get("email") or "").strip().lower()
	if email and frappe.db.exists("User", email):
		return email, None
	return _bot_user(), mm_user.get("username") or "mattermost"


def _mm_user(user_id: str) -> dict | None:
	if not user_id:
		return None
	key = f"crm:mm:user:{user_id}"
	cached = frappe.cache().get_value(key)
	if cached:
		return json.loads(cached) if isinstance(cached, str) else cached
	try:
		user = client.user_by_id(user_id)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Mattermost: user lookup failed")
		return None
	if user:
		frappe.cache().set_value(key, json.dumps({k: user.get(k) for k in ("id", "username", "email", "first_name", "last_name")}))
	return user


def ensure_channel(mm_channel: dict, members: list[dict] | None = None) -> str | None:
	"""The CRM Channel for a Mattermost channel, created if unknown. Returns name."""
	if not mm_channel or not mm_channel.get("id"):
		return None
	existing = frappe.db.get_value(CHANNEL, {"mm_channel_id": mm_channel["id"]}, "name")
	if existing:
		return existing
	slug = channel_slug(mm_channel)
	if frappe.db.exists(CHANNEL, slug):
		# A seed channel with the same slug and no MM id yet: adopt it.
		frappe.db.set_value(CHANNEL, slug, {"mm_channel_id": mm_channel["id"], "mm_type": mm_channel.get("type")}, update_modified=False)
		if members:
			_set_members(slug, members)
		return slug
	kind = kind_for_mm_type(mm_channel.get("type"))
	rows = _member_rows(members or [])
	if kind == "dm" and len(rows) < 2:
		# A DM with an unmapped side has nobody to show it to; keep it out.
		return None
	try:
		frappe.get_doc(
			{
				"doctype": CHANNEL,
				"name": slug,
				"title": mm_channel.get("display_name") or mm_channel.get("name") or slug,
				"kind": kind,
				"mm_channel_id": mm_channel["id"],
				"mm_type": mm_channel.get("type"),
				"members": rows,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Mattermost: channel create failed")
		return None
	return slug


def _member_rows(members: list[dict]) -> list[dict]:
	rows = []
	for m in members:
		mm_user = m if m.get("email") else _mm_user(m.get("user_id") or m.get("id"))
		if not mm_user:
			continue
		login, label = crm_user_for_mm(mm_user)
		if label:  # unmapped: no CRM login to grant
			continue
		rows.append({"user": login, "mm_user_id": mm_user.get("id")})
	return rows


def _set_members(channel_name: str, members: list[dict]):
	try:
		doc = frappe.get_doc(CHANNEL, channel_name)
		doc.set("members", _member_rows(members))
		doc.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Mattermost: membership update failed")


# ── inbound ────────────────────────────────────────────────────────────────────


def apply_event(envelope: dict) -> dict:
	"""Apply one verified event. Returns {ok, action, name|skipped}."""
	if not frappe.db.exists("DocType", MESSAGE):
		return {"ok": True, "skipped": "talk not set up"}
	event = (envelope or {}).get("event") or ""
	post = envelope.get("post") or {}

	if event == "status_change":
		return _apply_status(envelope)

	if event not in ("posted", "post_edited", "post_deleted"):
		return {"ok": True, "skipped": f"ignored {event}"}

	existing = frappe.db.get_value(MESSAGE, {"mm_post_id": post.get("id")}, "name") if post.get("id") else None

	if event == "posted":
		if should_skip_inbound(post, {post.get("id")} if existing else set()):
			return {"ok": True, "skipped": "loop guard"}
		channel_name = ensure_channel(envelope.get("channel") or {"id": post.get("channel_id")}, envelope.get("members"))
		if not channel_name:
			return {"ok": True, "skipped": "no channel"}
		author, label = crm_user_for_mm(envelope.get("user") or _mm_user(post.get("user_id")))
		doc = frappe.get_doc(inbound_row(post, channel_name, author, label)).insert(ignore_permissions=True)
		return {"ok": True, "action": "insert", "name": doc.name}

	if not existing:
		return {"ok": True, "skipped": "unknown post"}
	if event == "post_edited":
		frappe.db.set_value(
			MESSAGE, existing,
			{"text": post.get("message") or "", "edited_at": ms_to_datetime(post.get("edit_at") or post.get("update_at"))},
		)
		doc = frappe.get_doc(MESSAGE, existing)
		doc.run_method("on_update")
		return {"ok": True, "action": "edit", "name": existing}
	frappe.db.set_value(MESSAGE, existing, "deleted", 1)
	doc = frappe.get_doc(MESSAGE, existing)
	doc.run_method("on_update")
	return {"ok": True, "action": "delete", "name": existing}


def _apply_status(envelope: dict) -> dict:
	from crm.api.talk import set_mm_status

	user = envelope.get("user") or _mm_user((envelope.get("status") or {}).get("user_id"))
	if not user:
		return {"ok": True, "skipped": "no user"}
	login, label = crm_user_for_mm(user)
	if label:
		return {"ok": True, "skipped": "unmapped user"}
	status = status_for((envelope.get("status") or {}).get("status"))
	set_mm_status(login, status)
	return {"ok": True, "action": "status", "user": login, "status": status}


# ── outbound ───────────────────────────────────────────────────────────────────


def mirror_message(message: str, action: str = "insert"):
	"""Mirror one CRM Message to Mattermost. Runs in a worker after commit."""
	if not client.enabled():
		return
	try:
		doc = frappe.get_doc(MESSAGE, message)
	except Exception:
		return
	if doc.get("origin") != "crm":
		return
	try:
		props = json.loads(doc.get("props") or "{}")
	except ValueError:
		props = {}
	if props.get("mirror") is False:
		return
	try:
		if action == "insert":
			_mirror_insert(doc)
		elif action == "edit" and doc.get("mm_post_id"):
			token = _token_for(doc.author) or client.bot_token()
			client.update_post(doc.mm_post_id, _outbound_text(doc, token), token, {"crm_origin": 1, "crm_message": doc.name})
		elif action == "delete" and doc.get("mm_post_id"):
			token = _token_for(doc.author) or client.bot_token()
			client.delete_post(doc.mm_post_id, token)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Mattermost mirror {action} failed for {message}")


def _token_for(login: str) -> str:
	return client.user_token(login)


def _outbound_text(doc, token: str) -> str:
	"""Prefix the author when the bot is speaking on their behalf."""
	if token == client.bot_token():
		label = doc.get("author_label") or frappe.db.get_value("User", doc.author, "full_name") or doc.author
		if doc.author == _bot_user() and not doc.get("author_label"):
			return doc.text
		return bot_prefixed(label, doc.text)
	return doc.text


def _mirror_insert(doc):
	channel = frappe.get_doc(CHANNEL, doc.channel)
	mm_channel_id = channel.get("mm_channel_id")
	token = _token_for(doc.author) or client.bot_token()
	if not mm_channel_id and channel.kind == "dm":
		mm_channel_id = _ensure_mm_direct(channel, token)
	if not mm_channel_id:
		return
	post = client.create_post(
		mm_channel_id, _outbound_text(doc, token), token,
		props={"crm_origin": 1, "crm_message": doc.name}, root_id=doc.get("mm_root_id"),
	)
	if post.get("id"):
		frappe.db.set_value(MESSAGE, doc.name, "mm_post_id", post["id"], update_modified=False)


def _ensure_mm_direct(channel, token: str) -> str | None:
	"""Create the Mattermost direct channel for a CRM DM on first mirror."""
	logins = [m.user for m in channel.get("members") or []]
	ids = []
	for login in logins:
		user = client.user_by_email(login)
		if not user:
			return None
		ids.append(user["id"])
	if len(ids) != 2:
		return None
	direct = client.direct_channel(ids[0], ids[1], token)
	if direct.get("id"):
		frappe.db.set_value(CHANNEL, channel.name, {"mm_channel_id": direct["id"], "mm_type": "D"}, update_modified=False)
	return direct.get("id")


# ── backfill ───────────────────────────────────────────────────────────────────


@frappe.whitelist()
def backfill(channel: str, since_days: int = 30):
	"""Pull a mapped channel's recent Mattermost posts into Talk. Idempotent."""
	frappe.only_for("System Manager")
	mm_channel_id = frappe.db.get_value(CHANNEL, channel, "mm_channel_id")
	if not mm_channel_id:
		frappe.throw(f"{channel} is not mapped to a Mattermost channel")
	since = datetime.utcnow() - timedelta(days=int(since_days or 30))
	data = client.posts_since(mm_channel_id, int(since.timestamp() * 1000))
	posts = data.get("posts") or {}
	order = data.get("order") or list(posts)
	known = set(
		r.mm_post_id for r in frappe.get_all(MESSAGE, filters={"channel": channel, "mm_post_id": ("is", "set")}, fields=["mm_post_id"], limit_page_length=100000)
	)
	inserted = 0
	for pid in reversed(order):
		post = posts.get(pid) or {}
		if should_skip_inbound(post, known):
			continue
		author, label = crm_user_for_mm(_mm_user(post.get("user_id")))
		frappe.get_doc(inbound_row(post, channel, author, label)).insert(ignore_permissions=True)
		known.add(pid)
		inserted += 1
	return {"channel": channel, "inserted": inserted, "seen": len(order)}
