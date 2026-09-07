"""Talk — channels and DMs inside the CRM (the Mattermost replacement).

Doctypes (ops `scripts/setup_talk.py`): `CRM Channel` (slug-named; kind
channel|dm|bot; `members` child table), `CRM Message` (one post; `mm_post_id`
unique — the sync's idempotency key), `CRM Channel Read` (per user per channel,
`last_read_at`). Everything here is guarded on the doctypes existing, so the app
deploys before the ops script runs and Talk simply answers "no channels".

READ MODEL FIRST. `list_channels()` is what the left column renders on every
navigation, so the unread count is ONE grouped query over messages newer than
each read stamp, not a query per channel. `unread_counts()` is pure and tested.

MEMBERSHIP IS THE ACCESS MODEL. The role grid on the doctypes is a floor;
`_require_member` is what decides whether a user can read or post in a channel.
Public channels (`kind=channel`, no members listed) are open to every sales
user — that is what a public Mattermost channel means, and it is what lets the
seed channels work before the sync has filled membership in.

MIRRORING is one-way from here: a post with `origin=crm` is handed to
`crm.integrations.mattermost.sync.mirror_message` by the `CRM Message`
after_insert hook. Inbound posts arrive already stamped `origin=mattermost` and
are never mirrored back — that, plus `props.crm_origin` on what we post, is the
loop guard (see the sync module).

Realtime: `crm_talk` on insert/edit/delete (site-wide, after commit, so a
reader can't race the write), `crm_talk_read` to the reader only,
`crm_presence` from the presence path.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

import frappe
from frappe import _

from crm.api.reports import validate_access

CHANNEL = "CRM Channel"
MESSAGE = "CRM Message"
READ = "CRM Channel Read"
KINDS = ("channel", "dm", "bot")
PAGE = 50
MAX_TEXT = 16000

#: Left-column order: bot feeds and channels first (standup pinned on top), DMs after.
KIND_ORDER = {"bot": 0, "channel": 1, "dm": 2}
PINNED = ("standup",)


# ── pure helpers (unit-tested) ─────────────────────────────────────────────────


def dm_slug(a: str, b: str) -> str:
	"""Stable slug for a DM between two logins, order-independent."""
	pair = sorted(u.strip().lower() for u in (a, b))
	digest = hashlib.sha1("|".join(pair).encode()).hexdigest()[:12]
	return f"dm-{digest}"


def order_channels(rows: list[dict]) -> list[dict]:
	"""Standup pinned, then bot/channel by title, then DMs by most recent."""

	def key(row):
		pinned = 0 if row.get("name") in PINNED else 1
		kind = KIND_ORDER.get(row.get("kind"), 9)
		if row.get("kind") == "dm":
			# newest DM first; a DM with no messages yet sorts last
			stamp = row.get("last_at")
			return (kind, pinned, 1 if not stamp else 0, _desc(str(stamp or "")))
		return (kind, pinned, (row.get("title") or row.get("name") or "").lower(), "")

	return sorted(rows, key=key)


def _desc(stamp) -> str:
	"""Invert a sortable timestamp string so ascending sort yields newest first."""
	text = str(stamp or "")
	return "".join(chr(0x10FFFF - ord(ch)) for ch in text)


def unread_counts(messages: list[dict], reads: dict[str, str | None], user: str) -> dict[str, int]:
	"""{channel: unread} from (channel, author, posted_at) rows and read stamps.

	A message is unread when it is newer than the user's read stamp for that
	channel and not their own. With no stamp everything counts — a channel you
	have never opened is all news. Deleted rows are the caller's job to exclude.
	"""
	out: dict[str, int] = {}
	for m in messages:
		channel = m.get("channel")
		if not channel or m.get("author") == user or m.get("deleted"):
			continue
		stamp = reads.get(channel)
		posted = m.get("posted_at")
		if stamp and posted and _dt(posted) <= _dt(stamp):
			continue
		out[channel] = out.get(channel, 0) + 1
	return out


def _dt(value) -> datetime:
	if isinstance(value, datetime):
		return value
	return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def presence_for(mm_status: dict[str, str], on_call: set[str]) -> dict[str, str]:
	"""Merge Mattermost status with active Telnyx calls: a call wins."""
	out = {}
	for user, status in (mm_status or {}).items():
		out[user] = status if status in ("online", "away", "offline", "dnd") else "offline"
	for user in on_call or ():
		out[user] = "on_call"
	return out


# ── guards ─────────────────────────────────────────────────────────────────────


def enabled() -> bool:
	return all(frappe.db.exists("DocType", d) for d in (CHANNEL, MESSAGE, READ))


def _members(channel_doc) -> list[str]:
	return [m.user for m in (channel_doc.get("members") or []) if m.user]


def _is_member(channel_doc, user: str) -> bool:
	members = _members(channel_doc)
	if channel_doc.kind == "dm":
		return user in members
	# Public channel / bot feed: no explicit membership means everyone.
	return not members or user in members


def _require_member(channel: str):
	doc = frappe.get_doc(CHANNEL, channel)
	if doc.get("archived"):
		frappe.throw(_("This channel is archived."))
	if not _is_member(doc, frappe.session.user):
		frappe.throw(_("You are not in this channel."), frappe.PermissionError)
	return doc


# ── API ────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def list_channels():
	"""Channels + DMs the session user can see, left-column ordered, with unread."""
	validate_access()
	if not enabled():
		return []
	user = frappe.session.user
	channels = frappe.get_all(
		CHANNEL,
		filters={"archived": 0},
		fields=["name", "title", "kind", "last_message_at", "mm_channel_id"],
		limit_page_length=500,
	)
	member_rows = frappe.get_all(
		"CRM Channel Member", fields=["parent", "user"], limit_page_length=5000
	)
	members: dict[str, list[str]] = {}
	for row in member_rows:
		members.setdefault(row.parent, []).append(row.user)

	visible = []
	for ch in channels:
		mem = members.get(ch.name, [])
		if ch.kind == "dm":
			if user not in mem:
				continue
		elif mem and user not in mem:
			continue
		visible.append(ch)
	if not visible:
		return []

	names = [c.name for c in visible]
	reads = {
		r.channel: r.last_read_at
		for r in frappe.get_all(
			READ, filters={"user": user, "channel": ("in", names)},
			fields=["channel", "last_read_at"], limit_page_length=1000,
		)
	}
	# One pass over recent messages. Unread is bounded per channel by how far back
	# we look; 500 rows is more than a person reads before the count stops mattering.
	recent = frappe.get_all(
		MESSAGE,
		filters={"channel": ("in", names), "deleted": 0},
		fields=["channel", "author", "posted_at"],
		order_by="posted_at desc",
		limit_page_length=2000,
	)
	unread = unread_counts(recent, reads, user)
	# Do not name this `presence` — that shadows the module function and
	# UnboundLocalError's on the call (shipped as gw458).
	status_map = globals()["presence"]()

	out = []
	for ch in visible:
		dm_user = None
		if ch.kind == "dm":
			others = [m for m in members.get(ch.name, []) if m != user]
			dm_user = others[0] if others else None
		out.append(
			{
				"name": ch.name,
				"title": _dm_title(dm_user) if ch.kind == "dm" and dm_user else ch.title,
				"kind": ch.kind,
				"unread": unread.get(ch.name, 0),
				"last_at": ch.last_message_at,
				"dm_user": dm_user,
				"presence": status_map.get(dm_user) if dm_user else None,
			}
		)
	return order_channels(out)


def _dm_title(user: str) -> str:
	return frappe.db.get_value("User", user, "full_name") or user


@frappe.whitelist()
def thread(channel: str, before: str = None, limit: int = PAGE):
	"""Messages newest-last, paged backwards with `before` (a posted_at)."""
	validate_access()
	if not enabled():
		return {"messages": [], "has_more": False}
	_require_member(channel)
	limit = max(1, min(int(limit or PAGE), 200))
	filters = {"channel": channel, "deleted": 0}
	if before:
		filters["posted_at"] = ("<", before)
	rows = frappe.get_all(
		MESSAGE,
		filters=filters,
		fields=["name", "author", "author_label", "text", "posted_at", "origin", "edited_at", "mm_post_id"],
		order_by="posted_at desc",
		limit_page_length=limit + 1,
	)
	has_more = len(rows) > limit
	rows = list(reversed(rows[:limit]))
	names = {r.author for r in rows}
	full = {
		u.name: u.full_name
		for u in frappe.get_all("User", filters={"name": ("in", list(names))}, fields=["name", "full_name"])
	} if names else {}
	return {
		"messages": [shape_message(r, full) for r in rows],
		"has_more": has_more,
	}


def shape_message(row, full_names: dict | None = None) -> dict:
	full_names = full_names or {}
	author = row.get("author")
	return {
		"name": row.get("name"),
		"author": author,
		"author_name": row.get("author_label") or full_names.get(author) or author,
		"text": row.get("text") or "",
		"posted_at": row.get("posted_at"),
		"origin": row.get("origin") or "crm",
		"edited_at": row.get("edited_at"),
		"mm_post_id": row.get("mm_post_id"),
	}


@frappe.whitelist()
def post(channel: str, text: str):
	"""Insert a message as the session user. Mirroring to Mattermost happens in
	the after_insert hook so a webhook-driven insert and a UI insert share it."""
	validate_access()
	if not enabled():
		frappe.throw(_("Talk is not set up on this site yet."))
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Write something first."))
	if len(text) > MAX_TEXT:
		frappe.throw(_("That message is too long."))
	_require_member(channel)
	doc = frappe.get_doc(
		{
			"doctype": MESSAGE,
			"channel": channel,
			"author": frappe.session.user,
			"text": text,
			"posted_at": frappe.utils.now(),
			"origin": "crm",
		}
	).insert(ignore_permissions=True)
	# Posting is reading: the author has seen everything up to their own post.
	_stamp_read(channel, frappe.session.user, doc.posted_at)
	return shape_message(doc.as_dict())


@frappe.whitelist()
def mark_read(channel: str):
	validate_access()
	if not enabled():
		return {"unread": 0}
	_require_member(channel)
	_stamp_read(channel, frappe.session.user, frappe.utils.now())
	frappe.publish_realtime("crm_talk_read", {"channel": channel, "unread": 0}, user=frappe.session.user)
	return {"unread": 0}


def _stamp_read(channel: str, user: str, at):
	name = f"{channel}::{user}"
	if frappe.db.exists(READ, name):
		frappe.db.set_value(READ, name, "last_read_at", at, update_modified=False)
	else:
		frappe.get_doc(
			{"doctype": READ, "channel": channel, "user": user, "last_read_at": at}
		).insert(ignore_permissions=True)


@frappe.whitelist()
def ensure_dm(user: str):
	"""The DM channel between the session user and `user`, created on first use.

	Creating the Mattermost direct channel too is the sync's job (mirror on the
	first post), so a DM opened and never written to costs nothing there.
	"""
	validate_access()
	if not enabled():
		frappe.throw(_("Talk is not set up on this site yet."))
	me = frappe.session.user
	if not user or user == me:
		frappe.throw(_("Pick someone else to message."))
	if not frappe.db.exists("User", user):
		frappe.throw(_("Unknown user."))
	name = dm_slug(me, user)
	if not frappe.db.exists(CHANNEL, name):
		frappe.get_doc(
			{
				"doctype": CHANNEL,
				"name": name,
				"title": name,
				"kind": "dm",
				"members": [{"user": me}, {"user": user}],
			}
		).insert(ignore_permissions=True)
	return {"name": name}


@frappe.whitelist()
def presence():
	"""{user: online|away|offline|on_call}. Mattermost status when the sync has
	seen one, a live Telnyx call overriding it. Cheap: both live in cache."""
	try:
		mm = frappe.cache().get_value("crm:talk:mm_status") or {}
		if isinstance(mm, str):
			mm = json.loads(mm)
	except Exception:
		mm = {}
	on_call = set()
	try:
		from crm.api import telephony

		on_call = {c["rep"] for c in telephony.active_calls() if c.get("rep")}
	except Exception:
		pass
	return presence_for(mm, on_call)


def set_mm_status(user: str, status: str):
	"""Called by the Mattermost sync on `status_change`. Fans out `crm_presence`."""
	try:
		mm = frappe.cache().get_value("crm:talk:mm_status") or {}
		if isinstance(mm, str):
			mm = json.loads(mm)
		mm[user] = status
		frappe.cache().set_value("crm:talk:mm_status", mm)
		frappe.publish_realtime("crm_presence", {"user": user, "status": status})
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Talk: presence update failed")


# ── bot posts (standup, live one) ──────────────────────────────────────────────


def bot_user() -> str:
	"""The CRM user bot posts are attributed to. `talk_bot_user` in site_config,
	else Administrator — a real User row is required (Link field)."""
	return (frappe.conf.get("talk_bot_user") or "Administrator").strip()


def post_as_bot(channel: str, text: str, author_label: str | None = None, mirror: bool = True):
	"""Write a message from the system into a channel. Best-effort: a failed
	Talk write must never break the standup or a live-one alert."""
	if not enabled() or not frappe.db.exists(CHANNEL, channel):
		return None
	try:
		doc = frappe.get_doc(
			{
				"doctype": MESSAGE,
				"channel": channel,
				"author": bot_user(),
				"author_label": author_label,
				"text": text,
				"posted_at": frappe.utils.now(),
				"origin": "crm",
				"props": json.dumps({"mirror": bool(mirror)}),
			}
		).insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Talk: bot post to {channel} failed")
		return None


def dm_channel_between(a: str, b: str) -> str | None:
	"""Existing-or-created DM slug between two logins, without session checks
	(used by the live-one alert to reach the closer). None if Talk is off."""
	if not enabled() or not a or not b or a == b:
		return None
	name = dm_slug(a, b)
	if not frappe.db.exists(CHANNEL, name):
		try:
			frappe.get_doc(
				{"doctype": CHANNEL, "name": name, "title": name, "kind": "dm",
				 "members": [{"user": a}, {"user": b}]}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Talk: could not create DM channel")
			return None
	return name


# ── doc events (hooks.py) ──────────────────────────────────────────────────────


def on_message_insert(doc, method=None):
	_touch_channel(doc)
	_publish(doc, "insert")
	if doc.get("origin") == "crm":
		_mirror(doc, "insert")


def on_message_update(doc, method=None):
	_publish(doc, "delete" if doc.get("deleted") else "edit")
	if doc.get("origin") == "crm":
		_mirror(doc, "delete" if doc.get("deleted") else "edit")


def on_message_trash(doc, method=None):
	_publish(doc, "delete")
	if doc.get("origin") == "crm":
		_mirror(doc, "delete")


def _touch_channel(doc):
	try:
		frappe.db.set_value(CHANNEL, doc.channel, "last_message_at", doc.posted_at, update_modified=False)
	except Exception:
		pass


def _publish(doc, action: str):
	try:
		frappe.publish_realtime(
			"crm_talk",
			{"channel": doc.channel, "action": action, "message": shape_message(doc.as_dict())},
			after_commit=True,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Talk: realtime publish failed")


def _mirror(doc, action: str):
	"""Hand the row to the Mattermost mirror, outside the request where possible."""
	try:
		props = json.loads(doc.get("props") or "{}") if doc.get("props") else {}
	except ValueError:
		props = {}
	if props.get("mirror") is False:
		return
	try:
		from crm.integrations.mattermost import sync

		frappe.enqueue(
			sync.mirror_message, queue="short", enqueue_after_commit=True,
			message=doc.name, action=action,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Talk: could not enqueue Mattermost mirror")
