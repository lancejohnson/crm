"""Lance-only team activity pulse.

Combines human work already mirrored into the CRM:
- Quo calls (CRM Call Log)
- human-sent Quo texts (Quo Message; automated sequence texts are excluded)
- completed CRM tasks
- completed Today-board cards

Daily goals are stored as a JSON user default for Lance, so they persist across
browsers without adding another custom doctype.
"""

import json
from collections import defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime

ACTIVITY_PROGRESS_USER = "lance.johnson@groundworkpro.com"
GOALS_DEFAULT_KEY = "crm_activity_progress_goals"
GOAL_KEYS = ("calls", "texts", "tasks", "today")
CRM_ROLES = {"System Manager", "Sales Manager", "Sales User"}


def _guard():
	# Administrator remains available for bench/read-only verification. The only
	# human account allowed through this endpoint is Lance's.
	if frappe.session.user not in (ACTIVITY_PROGRESS_USER, "Administrator"):
		frappe.throw(_("Only Lance can view team activity progress."), frappe.PermissionError)


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
		goals[user] = {key: max(0, int(row.get(key) or 0)) for key in GOAL_KEYS}
	return goals


def _bounds(for_date=None):
	day = getdate(for_date or now_datetime())
	# This is an operational pulse, not an unbounded reporting endpoint.
	if day > getdate(now_datetime()) or day < getdate(now_datetime()) - timedelta(days=90):
		frappe.throw(_("Choose a date within the last 90 days."))
	return day, f"{day} 00:00:00", f"{day} 23:59:59.999999"


def _event(people, user, kind, at, **extra):
	if not user or user not in people or not at:
		return False
	people[user]["events"].append({"kind": kind, "at": at, **extra})
	return True


def _call_events(people, number_users, start, end):
	rows = frappe.get_all(
		"CRM Call Log",
		filters={"start_time": ["between", [start, end]]},
		fields=[
			"caller",
			"receiver",
			"from",
			"to",
			"type",
			"start_time",
			"duration",
			"status",
		],
		order_by="start_time asc",
		limit_page_length=5000,
	)
	unattributed = 0
	for row in rows:
		workspace_number = row.get("from") if row.type == "Outgoing" else row.get("to")
		user = row.get("caller") or row.get("receiver") or number_users.get(workspace_number)
		kind = "call_in" if row.type == "Incoming" else "call_out"
		if not _event(
			people,
			user,
			kind,
			row.start_time,
			duration=int(row.duration or 0),
			status=row.status or "",
		):
			unattributed += 1
			continue
		people[user]["counts"]["calls"] += 1
		people[user]["counts"]["talk_seconds"] += int(row.duration or 0)
		if row.type == "Incoming":
			people[user]["counts"]["inbound_calls"] += 1
		else:
			people[user]["counts"]["outbound_calls"] += 1
	return unattributed


def _text_events(people, start, end):
	if not frappe.db.exists("DocType", "Quo Message"):
		return 0, False

	meta = frappe.get_meta("Quo Message")
	has_sender = meta.has_field("sent_by")
	has_source = meta.has_field("activity_source")
	fields = ["owner", "from", "message_date"]
	if has_sender:
		fields.append("sent_by")
	if has_source:
		fields.append("activity_source")

	rows = frappe.get_all(
		"Quo Message",
		filters={
			"direction": "Outgoing",
			"message_date": ["between", [start, end]],
		},
		fields=fields,
		order_by="message_date asc",
		limit_page_length=10000,
	)
	unattributed = 0
	for row in rows:
		source = row.get("activity_source") if has_source else ""
		# Sequence steps are useful communication, but they are not a person
		# completing work and must not inflate a rep's daily progress.
		if source == "Sequence":
			continue
		user = row.get("sent_by") if has_sender else None
		# Existing locally-sent messages already carry the real session user as
		# owner. Be conservative with Guest rows until the sender backfill runs:
		# line ownership would incorrectly credit automated sequence texts.
		if not user and row.owner in people:
			user = row.owner
		if not _event(people, user, "text", row.message_date, source=source or "Legacy"):
			unattributed += 1
			continue
		people[user]["counts"]["texts"] += 1
	return unattributed, has_sender and has_source


def _task_events(people, start, end):
	rows = frappe.get_all(
		"CRM Task",
		filters={"status": "Done", "modified": ["between", [start, end]]},
		fields=["modified", "modified_by", "assigned_to"],
		order_by="modified asc",
		limit_page_length=5000,
	)
	unattributed = 0
	for row in rows:
		user = row.modified_by if row.modified_by in people else row.assigned_to
		if not _event(people, user, "task", row.modified):
			unattributed += 1
			continue
		people[user]["counts"]["tasks"] += 1
	return unattributed


def _today_events(people, start, end):
	if not frappe.db.exists("DocType", "CRM Today Item"):
		return 0
	meta = frappe.get_meta("CRM Today Item")
	if not meta.has_field("done_by") or not meta.has_field("done_at"):
		return 0
	rows = frappe.get_all(
		"CRM Today Item",
		filters={"state": "Done", "done_at": ["between", [start, end]]},
		fields=["done_by", "done_at"],
		order_by="done_at asc",
		limit_page_length=5000,
	)
	unattributed = 0
	for row in rows:
		if not _event(people, row.done_by, "today", row.done_at):
			unattributed += 1
			continue
		people[row.done_by]["counts"]["today"] += 1
	return unattributed


@frappe.whitelist()
def get_activity_progress(for_date=None):
	"""Return one day's per-user activity totals and timestamp-only event stream."""
	_guard()
	day, start, end = _bounds(for_date)
	users = _crm_users()
	user_names = {user.name for user in users}
	goals = _load_goals(user_names)

	people = {}
	number_users = {}
	for user in users:
		people[user.name] = {
			"user": user.name,
			"name": user.full_name or user.name,
			"image": user.user_image,
			"counts": {
				"calls": 0,
				"outbound_calls": 0,
				"inbound_calls": 0,
				"talk_seconds": 0,
				"texts": 0,
				"tasks": 0,
				"today": 0,
			},
			"goals": goals.get(user.name, {}),
			"events": [],
		}
		if user.custom_quo_number:
			number_users[user.custom_quo_number.strip()] = user.name

	unattributed = defaultdict(int)
	unattributed["calls"] = _call_events(people, number_users, start, end)
	unattributed["texts"], exact_text_attribution = _text_events(people, start, end)
	unattributed["tasks"] = _task_events(people, start, end)
	unattributed["today"] = _today_events(people, start, end)

	for person in people.values():
		person["events"].sort(key=lambda event: str(event["at"]))

	return {
		"date": str(day),
		"generated_at": now_datetime(),
		"people": list(people.values()),
		"unattributed": dict(unattributed),
		"exact_text_attribution": exact_text_attribution,
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
