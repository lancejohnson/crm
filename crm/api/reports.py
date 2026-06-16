"""Read-only API powering the in-CRM operational reports (Groundwork).

Phase 1: the **Daily Call Review** — every call logged on a given day, split by
the rep who made/took it and grouped by lead, so a manager can listen back to
recordings, read Quo's AI summary, and see the disposition without leaving the CRM.

Data sources, all already in the CRM:
- `CRM Call Log` — direction (`type`), `duration` (= talk time), `status`,
  `recording_url`, `caller`/`receiver` (the rep), `start_time`, lead link.
- `custom_ai_summary` on CRM Call Log (Quo's AI summary, a custom field synced by
  the ops repo's `sequence-events` webhook) — surfaced when the field exists.
- `call_outcome` on CRM Task (the disposition dropdown), linked to a call via the
  Call Log `links` (Dynamic Link) child table — best-effort, shown when present.

Read-only: this module touches no secrets and writes nothing.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

ALLOWED_REPORT_ROLES = ["System Manager", "Sales Manager", "Sales User"]


def validate_access():
	if not any(role in ALLOWED_REPORT_ROLES for role in frappe.get_roles()):
		frappe.throw(_("Only sales users can access reports."), frappe.PermissionError)


def _quo_number_map():
	"""Map each Quo workspace number -> the User who sends from it
	(User.custom_quo_number). Prefer a real user over Administrator when a number
	is shared (Lance runs the CRM as himself, so his number maps to both)."""
	out = {}
	for u in frappe.get_all(
		"User",
		filters={"custom_quo_number": ["is", "set"]},
		fields=["name", "full_name", "custom_quo_number"],
	):
		num = (u.get("custom_quo_number") or "").strip()
		if not num:
			continue
		existing = out.get(num)
		if not existing or existing["name"] == "Administrator":
			out[num] = u
	return out


@frappe.whitelist()
def get_call_review(date: str = None, user: str = None):
	"""Calls logged on `date`, split by rep then grouped by lead.

	date: 'YYYY-MM-DD' (defaults to today, site timezone).
	user: optional rep email to filter to a single person (else everyone, split).
	"""
	validate_access()

	day = getdate(date) if date else getdate(today())
	start = f"{day} 00:00:00"
	end = f"{day} 23:59:59.999999"

	has_ai = frappe.get_meta("CRM Call Log").has_field("custom_ai_summary")
	fields = [
		"name",
		"caller",
		"receiver",
		"from",
		"to",
		"type",
		"status",
		"duration",
		"recording_url",
		"start_time",
		"reference_doctype",
		"reference_docname",
	]
	if has_ai:
		fields.append("custom_ai_summary")

	calls = frappe.get_all(
		"CRM Call Log",
		filters={"start_time": ["between", [start, end]]},
		fields=fields,
		order_by="start_time asc",
	)

	# Resolve the rep on each call. Quo's `caller`/`receiver` (a User link) is the
	# truth when set, but it's often blank on mirrored/backfilled rows — so fall
	# back to the workspace number (`from` on outbound, `to` on inbound) mapped via
	# User.custom_quo_number, and finally to the raw number so the row is still
	# attributable. `rep` = resolved User email (may be ""); `rep_key`/`rep_label`
	# drive grouping/display even when no user resolves.
	number_to_user = _quo_number_map()
	for c in calls:
		ws_num = (c.get("from") if c.get("type") == "Outgoing" else c.get("to")) or ""
		email = c.get("caller") or c.get("receiver") or ""
		if not email and ws_num in number_to_user:
			email = number_to_user[ws_num]["name"]
		c["rep"] = email
		c["rep_key"] = email or ws_num or ""
		c["_ws_num"] = ws_num

	if user:
		calls = [c for c in calls if c["rep"] == user]

	# --- best-effort call_outcome via the Call Log -> CRM Task dynamic links ---
	call_names = [c["name"] for c in calls]
	call_to_outcome = {}
	if call_names:
		links = frappe.get_all(
			"Dynamic Link",
			filters={
				"parenttype": "CRM Call Log",
				"parent": ["in", call_names],
				"link_doctype": "CRM Task",
			},
			fields=["parent", "link_name"],
		)
		task_names = list({l["link_name"] for l in links})
		outcomes = {}
		if task_names:
			for t in frappe.get_all(
				"CRM Task",
				filters={"name": ["in", task_names]},
				fields=["name", "call_outcome"],
			):
				if t.get("call_outcome"):
					outcomes[t["name"]] = t["call_outcome"]
		for l in links:
			if outcomes.get(l["link_name"]):
				call_to_outcome[l["parent"]] = outcomes[l["link_name"]]

	# --- lead display name + current status (calls are lead-linked) ---
	lead_names = list({c["reference_docname"] for c in calls if c.get("reference_doctype") == "CRM Lead" and c.get("reference_docname")})
	lead_info = {}
	if lead_names:
		for ld in frappe.get_all(
			"CRM Lead",
			filters={"name": ["in", lead_names]},
			fields=["name", "lead_name", "first_name", "last_name", "status", "mobile_no", "phone"],
		):
			display = (
				ld.get("lead_name")
				or " ".join(x for x in [ld.get("first_name"), ld.get("last_name")] if x)
				or ld["name"]
			)
			lead_info[ld["name"]] = {
				"lead_name": display,
				"status": ld.get("status") or "",
				"mobile_no": ld.get("mobile_no") or ld.get("phone") or "",
			}

	# --- which of today's leads were called for the very first time today ---
	first_time_leads = set()
	if lead_names:
		prior = set(
			frappe.get_all(
				"CRM Call Log",
				filters={"reference_docname": ["in", lead_names], "start_time": ["<", start]},
				pluck="reference_docname",
			)
		)
		first_time_leads = {ln for ln in lead_names if ln not in prior}

	# --- rep display names ---
	rep_emails = list({c["rep"] for c in calls if c["rep"]})
	user_names = {}
	if rep_emails:
		for u in frappe.get_all(
			"User",
			filters={"name": ["in", rep_emails]},
			fields=["name", "full_name"],
		):
			user_names[u["name"]] = u.get("full_name") or u["name"]

	# --- assemble: rep -> lead -> calls ---
	reps = {}
	for c in calls:
		ref = c.get("reference_docname") or ""
		is_lead = c.get("reference_doctype") == "CRM Lead"
		info = lead_info.get(ref, {})

		if c["rep"]:
			rep_label = user_names.get(c["rep"]) or c["rep"]
		else:
			rep_label = c.get("_ws_num") or _("Unassigned")

		rep_bucket = reps.setdefault(
			c["rep_key"],
			{
				"user": c["rep"],
				"user_name": rep_label,
				"leads": {},
			},
		)
		lead_bucket = rep_bucket["leads"].setdefault(
			ref or c["name"],
			{
				"reference_doctype": c.get("reference_doctype"),
				"reference_name": ref,
				"lead_name": info.get("lead_name") or ref or _("Unknown"),
				"status": info.get("status") or "",
				"mobile_no": info.get("mobile_no") or "",
				"first_time_today": bool(is_lead and ref in first_time_leads),
				"calls": [],
			},
		)
		lead_bucket["calls"].append(
			{
				"name": c["name"],
				"time": c.get("start_time"),
				"type": c.get("type"),
				"status": c.get("status"),
				"duration": c.get("duration") or 0,
				"recording_url": c.get("recording_url") or "",
				"ai_summary": c.get("custom_ai_summary") or "" if has_ai else "",
				"call_outcome": call_to_outcome.get(c["name"], ""),
			}
		)

	# --- per-rep + overall totals, materialise leads as a sorted list ---
	rep_list = []
	overall = {"calls": 0, "inbound": 0, "outbound": 0, "talk_time": 0, "leads": 0, "first_time": 0}
	for rep_bucket in reps.values():
		leads = list(rep_bucket["leads"].values())
		t = {"calls": 0, "inbound": 0, "outbound": 0, "talk_time": 0, "leads": len(leads), "first_time": 0}
		for ld in leads:
			if ld["first_time_today"]:
				t["first_time"] += 1
			for call in ld["calls"]:
				t["calls"] += 1
				t["talk_time"] += call["duration"] or 0
				if call["type"] == "Incoming":
					t["inbound"] += 1
				else:
					t["outbound"] += 1
		# most calls first, so the busiest leads float up
		leads.sort(key=lambda x: len(x["calls"]), reverse=True)
		rep_bucket["leads"] = leads
		rep_bucket["totals"] = t
		rep_list.append(rep_bucket)

		overall["calls"] += t["calls"]
		overall["inbound"] += t["inbound"]
		overall["outbound"] += t["outbound"]
		overall["talk_time"] += t["talk_time"]
		overall["leads"] += t["leads"]
		overall["first_time"] += t["first_time"]

	# busiest rep first
	rep_list.sort(key=lambda r: r["totals"]["calls"], reverse=True)

	return {
		"date": str(day),
		"reps": rep_list,
		"totals": overall,
	}


@frappe.whitelist()
def get_call_review_reps():
	"""Distinct reps that appear as a caller/receiver on any call — feeds the
	rep filter dropdown so it only lists people who actually have calls."""
	validate_access()
	callers = set(frappe.get_all("CRM Call Log", filters={"caller": ["is", "set"]}, pluck="caller"))
	receivers = set(frappe.get_all("CRM Call Log", filters={"receiver": ["is", "set"]}, pluck="receiver"))
	# also include anyone configured with a Quo sending number — they're a rep even
	# if caller/receiver was never stamped on their mirrored calls
	number_users = {u["name"] for u in _quo_number_map().values() if u["name"] != "Administrator"}
	emails = sorted(e for e in (callers | receivers | number_users) if e)
	out = []
	for u in frappe.get_all("User", filters={"name": ["in", emails]}, fields=["name", "full_name"]) if emails else []:
		out.append({"value": u["name"], "label": u.get("full_name") or u["name"]})
	out.sort(key=lambda x: x["label"].lower())
	return out
