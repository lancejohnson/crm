"""Lance-only team activity board.

One row per person for one day, built from work already recorded:
- Quo calls (CRM Call Log — the `call.completed` webhook mirror, attributed to
  the Quo user who actually dialled, not the line owner)
- human-sent Quo texts (Quo Message; automated sequence texts are excluded)
- Today-board cards resolved (Done / Skipped)
- completed CRM tasks, split by whether the lead was on that day's Today list
- hours tracked in Toggl, including the clocked-in windows

Toggl is matched to CRM users by **email** — the Toggl workspace exposes the same
addresses, so no mapping field is needed. Every Toggl call is best-effort: if the
API is slow, down, or unconfigured the board still renders without it.

Daily goals are stored as a JSON user default for Lance, so they persist across
browsers without another custom doctype.
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import frappe
import requests
from frappe import _
from frappe.utils import convert_utc_to_system_timezone, getdate, now_datetime

from crm.api import telephony

ACTIVITY_PROGRESS_USER = "lance.johnson@groundworkpro.com"
GOALS_DEFAULT_KEY = "crm_activity_progress_goals"
GOAL_KEYS = ("calls", "texts", "tasks", "cards")
CRM_ROLES = {"System Manager", "Sales Manager", "Sales User"}

TOGGL_API = "https://api.track.toggl.com"
TOGGL_USERS_TTL = 3600
TOGGL_DAY_TTL = 120
TOGGL_TIMEOUT = 12

QUO_API = "https://api.openphone.com"
QUO_LINES_TTL = 21600
QUO_TIMEOUT = 10


def _guard():
	# Administrator stays allowed so bench/read-only verification keeps working.
	if frappe.session.user not in (ACTIVITY_PROGRESS_USER, "Administrator"):
		frappe.throw(_("Only Lance can view team activity progress."), frappe.PermissionError)


# ---------------------------------------------------------------------------
# Toggl
# ---------------------------------------------------------------------------


def _toggl_conf():
	user = (frappe.conf.get("toggl_username") or "").strip()
	pwd = (frappe.conf.get("toggl_password") or "").strip()
	ws = frappe.conf.get("toggl_workspace_id")
	if not (user and pwd and ws):
		return None
	return user, pwd, ws


def _toggl_user_ids():
	"""Toggl user id -> email. Cached: workspace membership rarely changes."""
	cached = frappe.cache().get_value("crm_toggl_users")
	if cached:
		return {int(k): v for k, v in json.loads(cached).items()}
	conf = _toggl_conf()
	if not conf:
		return {}
	user, pwd, ws = conf
	resp = requests.get(
		f"{TOGGL_API}/api/v9/workspaces/{ws}/users", auth=(user, pwd), timeout=TOGGL_TIMEOUT
	)
	resp.raise_for_status()
	out = {}
	for row in resp.json() or []:
		if row.get("id") and row.get("email"):
			out[int(row["id"])] = row["email"].strip().lower()
	frappe.cache().set_value("crm_toggl_users", json.dumps(out), expires_in_sec=TOGGL_USERS_TTL)
	return out


def _digits(value):
	"""Last 10 digits — the house phone-matching rule.

	Kept as a name local to this module, but the rule now lives in one place
	(`telephony.last10`) because there were NINE copies of it in this app and they
	did not agree.
	"""
	return telephony.last10(value)


def _workspace_lines():
	"""Every Quo line in the workspace, as last-10 digits.

	Used to tell a teammate-to-teammate call apart from real outreach. Read live
	from Quo (one cheap, cached request) because `User.custom_quo_number` misses
	shared lines that belong to no one — the "Backup Number", for instance.
	Falls back to the per-user numbers if Quo is unreachable.
	"""
	cached = frappe.cache().get_value("crm_quo_lines")
	if cached:
		return set(json.loads(cached))

	lines = set()
	token = (frappe.conf.get("quo_api_key") or "").strip()
	if token:
		try:
			resp = requests.get(
				f"{QUO_API}/v1/phone-numbers",
				headers={"Authorization": token, "User-Agent": "curl/8.1.0"},
				timeout=QUO_TIMEOUT,
			)
			resp.raise_for_status()
			for row in (resp.json() or {}).get("data") or []:
				number = _digits(row.get("number"))
				if number:
					lines.add(number)
		except Exception:
			frappe.log_error(title="Quo line list failed", message=frappe.get_traceback())

	# Union with every line we have CONFIGURED, across providers. The live call
	# above asks Quo, and Quo does not know about a Telnyx line -- so during
	# parallel running a rep-to-rep call over Telnyx would be counted as outreach
	# to a stranger. Configured lines are also the whole answer when Quo is
	# unreachable, which is what this used to fall back to on its own.
	lines |= telephony.our_numbers()

	if not lines:
		return lines

	frappe.cache().set_value("crm_quo_lines", json.dumps(sorted(lines)), expires_in_sec=QUO_LINES_TTL)
	return lines


def _to_site_time(iso):
	"""Toggl stamps carry the member's own offset (the setters are on -03:00); the
	rest of this report is naive site time, so normalise before anything is
	compared. Same conversion the Quo webhook uses."""
	aware = datetime.fromisoformat(iso)
	utc_naive = aware.astimezone(timezone.utc).replace(tzinfo=None)
	return convert_utc_to_system_timezone(utc_naive).replace(tzinfo=None)


def _toggl_day(day):
	"""Per-email tracked seconds + clocked-in windows for `day`.

	Never raises: a Toggl outage must not take the board down with it.
	"""
	key = f"crm_toggl_day::{day}"
	cached = frappe.cache().get_value(key)
	if cached:
		return json.loads(cached)

	result = {"ok": False, "people": {}}
	conf = _toggl_conf()
	if not conf:
		result["reason"] = "not configured"
		return result
	user, pwd, ws = conf
	try:
		emails = _toggl_user_ids()
		if not emails:
			result["reason"] = "no workspace members"
			return result
		resp = requests.post(
			f"{TOGGL_API}/reports/api/v3/workspace/{ws}/search/time_entries",
			auth=(user, pwd),
			json={"start_date": str(day), "end_date": str(day), "user_ids": list(emails)},
			timeout=TOGGL_TIMEOUT,
		)
		resp.raise_for_status()
		people = {}
		now = now_datetime()
		for row in resp.json() or []:
			email = emails.get(int(row.get("user_id") or 0))
			if not email:
				continue
			bucket = people.setdefault(email, {"seconds": 0, "bands": [], "running": False})
			for entry in row.get("time_entries") or []:
				start, stop = entry.get("start"), entry.get("stop")
				if not start:
					continue
				began = _to_site_time(start)
				if stop:
					# Toggl reports a running timer's duration as a negative number,
					# so a completed entry's own seconds are only trusted here.
					ended = _to_site_time(stop)
					bucket["seconds"] += max(0, int(entry.get("seconds") or 0))
				else:
					# Still clocked in: run the band to now so the live board shows
					# today's real time instead of zero.
					ended = max(began, now)
					bucket["seconds"] += max(0, int((ended - began).total_seconds()))
					bucket["running"] = True
				bucket["bands"].append([began.isoformat(), ended.isoformat()])
		for bucket in people.values():
			bucket["bands"].sort()
		result = {"ok": True, "people": people}
	except Exception:
		# Logged, not raised — the rest of the board is still worth showing.
		frappe.log_error(title="Toggl fetch failed", message=frappe.get_traceback())
		result = {"ok": False, "people": {}, "reason": "unavailable"}

	frappe.cache().set_value(key, json.dumps(result), expires_in_sec=TOGGL_DAY_TTL)
	return result


# ---------------------------------------------------------------------------
# goals
# ---------------------------------------------------------------------------


def _load_goals(valid_users):
	raw = frappe.defaults.get_user_default(GOALS_DEFAULT_KEY)
	try:
		stored = json.loads(raw) if isinstance(raw, str) else raw
	except (TypeError, ValueError):
		stored = {}
	if not isinstance(stored, dict):
		stored = {}
	goals = {}
	for user in valid_users:
		row = stored.get(user) if isinstance(stored.get(user), dict) else {}
		# `today` was the pre-rename key for the Today-card goal.
		if "cards" not in row and "today" in row:
			row = dict(row, cards=row.get("today"))
		goals[user] = {key: max(0, int(row.get(key) or 0)) for key in GOAL_KEYS}
	return goals


def _crm_users():
	users = []
	for user in frappe.get_all(
		"User",
		filters={"enabled": 1},
		fields=["name", "full_name", "user_image", "custom_quo_number"],
		order_by="full_name asc",
	):
		if user.name in ("Administrator", "Guest"):
			continue
		if CRM_ROLES.intersection(frappe.get_roles(user.name)):
			users.append(user)
	return users


def _bounds(for_date=None):
	day = getdate(for_date or now_datetime())
	if day > getdate(now_datetime()) or day < getdate(now_datetime()) - timedelta(days=90):
		frappe.throw(_("Choose a date within the last 90 days."))
	return day, f"{day} 00:00:00", f"{day} 23:59:59.999999"


def _event(people, user, kind, at, **extra):
	if not user or user not in people or not at:
		return False
	people[user]["events"].append({"kind": kind, "at": at, **extra})
	return True


# ---------------------------------------------------------------------------
# activity sources
# ---------------------------------------------------------------------------


def _call_events(people, number_users, start, end):
	"""Classify every call, then count only the outreach.

	Four buckets:
	  lead / buyer — the webhook linked the call to a record at call time
	  outside      — external number with no record: cold calls, and contacts
	                 that only became a lead/buyer later (the link is stamped
	                 once, at call time, and is never back-filled)
	  internal     — teammate-to-teammate on our own Quo lines; real, but not
	                 outreach, so it is kept out of the headline call count

	NOTE: `reference_doctype` defaults to "CRM Lead" on every row whether or not
	anything matched — only a non-empty `reference_docname` means truly linked.
	"""
	rows = frappe.get_all(
		"CRM Call Log",
		filters={"start_time": ["between", [start, end]]},
		fields=[
			"caller", "receiver", "from", "to", "type", "start_time", "duration",
			"status", "reference_doctype", "reference_docname",
		],
		order_by="start_time asc",
		limit_page_length=5000,
	)
	lines = _workspace_lines()
	unattributed = 0
	for row in rows:
		incoming = row.type == "Incoming"
		workspace_number = row.get("to") if incoming else row.get("from")
		user = row.get("caller") or row.get("receiver") or number_users.get(_digits(workspace_number))
		external = _digits(row.get("from") if incoming else row.get("to"))

		if external and external in lines:
			bucket = "internal"
		elif (row.get("reference_docname") or "").strip():
			bucket = "buyer" if row.get("reference_doctype") == "CRM Buyer" else "lead"
		else:
			bucket = "outside"

		kind = "call_internal" if bucket == "internal" else ("call_in" if incoming else "call_out")
		if not _event(
			people, user, kind, row.start_time, duration=int(row.duration or 0), bucket=bucket
		):
			unattributed += 1
			continue

		counts = people[user]["counts"]
		if bucket == "internal":
			# counted and shown, but deliberately excluded from `calls`
			counts["calls_internal"] += 1
			counts["internal_seconds"] += int(row.duration or 0)
			continue
		counts["calls"] += 1
		counts[f"calls_{bucket}"] += 1
		counts["talk_seconds"] += int(row.duration or 0)
		counts["inbound_calls" if incoming else "outbound_calls"] += 1
	return unattributed


def _text_events(people, start, end, number_users=None):
	"""Human-sent outbound texts, attributed by the LINE they went out on.

	`sent_by` is NOT reliable for a text sent from the OpenPhone app: the webhook
	resolves Quo's `userId`, which comes back as the workspace OWNER rather than
	the person who typed the message. Measured over the full history: 309 texts
	were credited to Lance that went out on German's (187) and Exe's (122) lines,
	and there were zero mismatches in the other direction. Every CRM-sent
	(`Manual`) and sequence text agrees with the line owner, so the line is right
	in all 649 verifiable cases and wrong in none.

	This is the same shape as the inbound-call `userId` trap: Quo's idea of "who"
	is the account, not the human. `sent_by` survives only as a fallback for a
	shared line that belongs to nobody (the Backup Number), where it is the only
	signal available.
	"""
	if not frappe.db.exists("DocType", "Quo Message"):
		return 0, False
	meta = frappe.get_meta("Quo Message")
	has_sender = meta.has_field("sent_by")
	has_source = meta.has_field("activity_source")
	line_users = {_digits(number): user for number, user in (number_users or {}).items()}
	fields = ["owner", "from", "message_date"]
	if has_sender:
		fields.append("sent_by")
	if has_source:
		fields.append("activity_source")

	rows = frappe.get_all(
		"Quo Message",
		filters={"direction": "Outgoing", "message_date": ["between", [start, end]]},
		fields=fields,
		order_by="message_date asc",
		limit_page_length=10000,
	)
	unattributed = 0
	for row in rows:
		# A sequence step is real outreach but nobody *did* it — never credit a rep.
		if has_source and row.get("activity_source") == "Sequence":
			continue
		user = line_users.get(_digits(row.get("from")))
		if not user and has_sender:
			user = row.get("sent_by")
		if not user and row.owner in people:
			user = row.owner
		if not _event(people, user, "text", row.message_date):
			unattributed += 1
			continue
		people[user]["counts"]["texts"] += 1
	return unattributed, bool(has_sender and has_source)


def _today_cards(people, day):
	"""Per-person Done/Skipped plus the board-level totals.

	The Today board is shared, so `total`/`remaining` belong to the board, not to
	any one person. `resolved_*` (Done AND Skipped) is preferred over `done_*`
	(Done only) so a skip — a real judgement someone made — is credited too.
	"""
	board = {"total": 0, "done": 0, "skipped": 0, "remaining": 0, "resolved_stamp": False}
	if not frappe.db.exists("DocType", "CRM Today Item"):
		return 0, board, set()
	meta = frappe.get_meta("CRM Today Item")
	resolved = meta.has_field("resolved_at") and meta.has_field("resolved_by")
	board["resolved_stamp"] = resolved
	fields = ["name", "lead", "state", "done_by", "done_at"]
	if resolved:
		fields += ["resolved_by", "resolved_at"]

	rows = frappe.get_all(
		"CRM Today Item", filters={"for_date": day}, fields=fields, limit_page_length=5000
	)
	unattributed = 0
	leads = set()
	for row in rows:
		board["total"] += 1
		if row.lead:
			leads.add(row.lead)
		if row.state == "Done":
			board["done"] += 1
		elif row.state == "Skipped":
			board["skipped"] += 1
		else:
			continue
		who = (row.get("resolved_by") if resolved else None) or row.get("done_by")
		when = (row.get("resolved_at") if resolved else None) or row.get("done_at")
		kind = "card_done" if row.state == "Done" else "card_skip"
		if not _event(people, who, kind, when):
			unattributed += 1
			continue
		key = "cards" if row.state == "Done" else "cards_skipped"
		people[who]["counts"][key] += 1
	board["remaining"] = board["total"] - board["done"] - board["skipped"]
	return unattributed, board, leads


def _task_events(people, start, end, board_leads):
	rows = frappe.get_all(
		"CRM Task",
		filters={"status": "Done", "modified": ["between", [start, end]]},
		fields=["modified", "modified_by", "assigned_to", "reference_docname"],
		order_by="modified asc",
		limit_page_length=5000,
	)
	unattributed = 0
	for row in rows:
		user = row.modified_by if row.modified_by in people else row.assigned_to
		on_list = bool(row.reference_docname and row.reference_docname in board_leads)
		if not _event(people, user, "task", row.modified, on_list=on_list):
			unattributed += 1
			continue
		people[user]["counts"]["tasks"] += 1
		people[user]["counts"]["tasks_on_list" if on_list else "tasks_other"] += 1
	return unattributed


@frappe.whitelist()
def get_activity_progress(for_date=None):
	"""One day of team activity: per-person totals, event stream, and Toggl time."""
	_guard()
	day, start, end = _bounds(for_date)
	users = _crm_users()
	goals = _load_goals({u.name for u in users})

	people = {}
	for user in users:
		people[user.name] = {
			"user": user.name,
			"name": user.full_name or user.name,
			"image": user.user_image,
			"counts": {
				"calls": 0, "outbound_calls": 0, "inbound_calls": 0, "talk_seconds": 0,
				"calls_lead": 0, "calls_buyer": 0, "calls_outside": 0,
				"calls_internal": 0, "internal_seconds": 0,
				"texts": 0, "tasks": 0, "tasks_on_list": 0, "tasks_other": 0,
				"cards": 0, "cards_skipped": 0,
			},
			"goals": goals.get(user.name, {}),
			"events": [],
			"toggl": {"seconds": 0, "bands": [], "running": False},
		}
	# Line -> user for every provider, keyed on last-10. This USED to be an exact
	# string match against `custom_quo_number`, which meant a line stored as
	# "+16125551234" silently failed to match a call log carrying "6125551234".
	# It happens to agree today (verified on prod: 0 of 2,896 calls over 30 days
	# change attribution) because both sides are E.164 — but that was luck, not
	# design, and Telnyx will not necessarily store numbers the same way Quo does.
	number_users = telephony.line_owners()

	unattributed = defaultdict(int)
	unattributed["calls"] = _call_events(people, number_users, start, end)
	unattributed["texts"], exact_text_attribution = _text_events(
		people, start, end, number_users
	)
	unattributed["cards"], board, board_leads = _today_cards(people, day)
	unattributed["tasks"] = _task_events(people, start, end, board_leads)

	toggl = _toggl_day(day)
	for person in people.values():
		entry = toggl["people"].get(person["user"].lower())
		if entry:
			person["toggl"] = {
				"seconds": entry["seconds"],
				"bands": entry["bands"],
				"running": entry.get("running", False),
			}
		person["events"].sort(key=lambda event: str(event["at"]))

	return {
		"date": str(day),
		"generated_at": now_datetime(),
		"people": list(people.values()),
		"board": board,
		"unattributed": dict(unattributed),
		"exact_text_attribution": exact_text_attribution,
		"toggl_ok": toggl.get("ok", False),
		"toggl_reason": toggl.get("reason", ""),
	}


@frappe.whitelist(methods=["POST"])
def set_activity_goals(goals):
	"""Persist Lance's per-user daily goals (0 disables a metric's goal)."""
	_guard()
	if isinstance(goals, str):
		try:
			goals = json.loads(goals)
		except ValueError:
			goals = {}
	if not isinstance(goals, dict):
		frappe.throw(_("Invalid goals."))

	valid_users = {user.name for user in _crm_users()}
	clean = {}
	for user, values in goals.items():
		if user not in valid_users or not isinstance(values, dict):
			continue
		clean[user] = {}
		for key in GOAL_KEYS:
			try:
				value = int(values.get(key) or 0)
			except (TypeError, ValueError):
				value = 0
			clean[user][key] = max(0, min(1000, value))

	frappe.defaults.set_user_default(GOALS_DEFAULT_KEY, json.dumps(clean, separators=(",", ":")))
	return clean
