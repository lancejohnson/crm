"""A thin Mattermost REST client for the Talk sync.

Two credentials, deliberately:

- the `pi` bot token (`mattermost_token`, kept in site_config by the ops
  `mattermost-token-sync` timer — never `bench set-config` it from a laptop),
- per-rep personal access tokens (`mattermost_user_tokens` = {login email:
  token}), minted for the live-one alert. A post mirrored AS THE REP shows up in
  Mattermost under their name and their teammates can reply to them; the bot
  fallback prefixes `**Name:**` so nobody reads a bot as a person.

Everything raises `requests.HTTPError` on a non-2xx; callers decide whether a
failure is worth an Error Log or a retry. Nothing here touches the CRM database.
"""

from __future__ import annotations

import json

import frappe
import requests

DEFAULT_BASE = "https://app.groundworkpro.com/mattermost/api/v4"
TIMEOUT = 20


def base_url() -> str:
	return (frappe.conf.get("mattermost_base") or DEFAULT_BASE).rstrip("/")


def bot_token() -> str:
	return (frappe.conf.get("mattermost_token") or "").strip()


def user_token(login: str) -> str:
	"""The rep's own PAT, or ''. Keys are lower-cased CRM logins."""
	tokens = frappe.conf.get("mattermost_user_tokens") or {}
	if isinstance(tokens, str):
		try:
			tokens = json.loads(tokens)
		except ValueError:
			tokens = {}
	return (tokens.get((login or "").strip().lower()) or "").strip()


def enabled() -> bool:
	return bool(bot_token())


def request(method: str, path: str, token: str, body=None, params=None):
	r = requests.request(
		method,
		base_url() + path,
		headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
		data=json.dumps(body) if body is not None else None,
		params=params,
		timeout=TIMEOUT,
	)
	r.raise_for_status()
	if not r.text:
		return {}
	return r.json()


# ── convenience wrappers (bot token unless a token is passed) ──────────────────


def me(token: str | None = None) -> dict:
	return request("GET", "/users/me", token or bot_token())


def user_by_email(email: str, token: str | None = None) -> dict | None:
	try:
		return request("GET", f"/users/email/{email}", token or bot_token())
	except requests.HTTPError as e:
		if getattr(e.response, "status_code", None) == 404:
			return None
		raise


def user_by_id(user_id: str, token: str | None = None) -> dict | None:
	try:
		return request("GET", f"/users/{user_id}", token or bot_token())
	except requests.HTTPError as e:
		if getattr(e.response, "status_code", None) == 404:
			return None
		raise


def channel(channel_id: str, token: str | None = None) -> dict:
	return request("GET", f"/channels/{channel_id}", token or bot_token())


def channel_members(channel_id: str, token: str | None = None) -> list[dict]:
	out, page = [], 0
	while True:
		rows = request(
			"GET", f"/channels/{channel_id}/members", token or bot_token(),
			params={"page": page, "per_page": 200},
		)
		out.extend(rows or [])
		if not rows or len(rows) < 200:
			return out
		page += 1


def direct_channel(user_a: str, user_b: str, token: str | None = None) -> dict:
	return request("POST", "/channels/direct", token or bot_token(), [user_a, user_b])


def create_post(channel_id: str, message: str, token: str, props: dict | None = None, root_id: str | None = None) -> dict:
	body = {"channel_id": channel_id, "message": message}
	if props:
		body["props"] = props
	if root_id:
		body["root_id"] = root_id
	return request("POST", "/posts", token, body)


def update_post(post_id: str, message: str, token: str, props: dict | None = None) -> dict:
	body = {"id": post_id, "message": message}
	if props:
		body["props"] = props
	return request("PUT", f"/posts/{post_id}", token, body)


def delete_post(post_id: str, token: str) -> dict:
	return request("DELETE", f"/posts/{post_id}", token)


def posts_since(channel_id: str, since_ms: int, token: str | None = None) -> dict:
	"""`/channels/{id}/posts?since=` — Mattermost returns {order, posts}."""
	return request(
		"GET", f"/channels/{channel_id}/posts", token or bot_token(),
		params={"since": int(since_ms), "per_page": 200},
	)


def statuses(user_ids: list[str], token: str | None = None) -> list[dict]:
	if not user_ids:
		return []
	return request("POST", "/users/status/ids", token or bot_token(), list(user_ids))
