import json
import re

import frappe
from bs4 import BeautifulSoup
from frappe import _
from frappe.desk.form.load import get_docinfo
from frappe.query_builder import JoinType
from frappe.translate import get_translated_doctypes
from frappe.utils import get_datetime

from crm.fcrm.doctype.crm_call_log.crm_call_log import parse_call_log


@frappe.whitelist()
def get_activities(name: str):
	if frappe.db.exists("CRM Deal", name):
		return get_deal_activities(name)
	elif frappe.db.exists("CRM Lead", name):
		return get_lead_activities(name)
	elif frappe.db.exists("DocType", "CRM Buyer") and frappe.db.exists("CRM Buyer", name):
		return get_buyer_activities(name)
	else:
		frappe.throw(_("Document not found"), frappe.DoesNotExistError)


def strip_currency_cents(val):
	"""Version docs store currency changes as display strings ("$ 2,500.00");
	show them whole-dollar in the timeline, like currency renders everywhere
	else in the app."""
	if isinstance(val, str):
		return re.sub(r"\.\d+$", "", val)
	return val


def version_activities(version, doc_fields, avoid_fields, is_lead):
	"""Render EVERY field change in a Version, not just the first one.

	Frappe writes ONE Version per save, listing every field that changed in it.
	This used to read `changed[0]` alone, so a save touching several fields put
	exactly one of them on the timeline and silently dropped the rest. Editing
	two fields in the side panel and saving once was enough to hit it; the
	contract parser made it obvious, since it writes a price and two dates in a
	single save and only the price appeared.

	The old shape also had a latent duplicate: the activity dict was assembled
	outside the `if change :=` branch that populated its variables, so a version
	whose first change was falsy appended a stale copy of the PREVIOUS activity.
	Building one activity per change, inside the loop, removes that too.
	"""
	out = []
	for change in json.loads(version.data).get("changed") or []:
		if not change:
			continue
		field = doc_fields.get(change[0], None)
		if not field or change[0] in avoid_fields or (not change[1] and not change[2]):
			continue

		field_label = field.get("label") or change[0]
		field_option = field.get("options") or None

		activity_type = "changed"
		data = {
			"field": change[0],
			"field_label": field_label,
			"old_value": change[1],
			"value": change[2],
		}
		if not change[1] and change[2]:
			activity_type = "added"
			data = {"field": change[0], "field_label": field_label, "value": change[2]}
		elif change[1] and not change[2]:
			activity_type = "removed"
			data = {"field": change[0], "field_label": field_label, "value": change[1]}

		if data.get("value") and field_option and is_translatable(field_option):
			data["value"] = _(data["value"])
			if data.get("old_value"):
				data["old_value"] = _(data["old_value"])

		if field.get("fieldtype") == "Currency":
			data["value"] = strip_currency_cents(data.get("value"))
			data["old_value"] = strip_currency_cents(data.get("old_value"))

		out.append({
			"activity_type": activity_type,
			"creation": version.creation,
			"owner": version.owner,
			"data": data,
			"is_lead": is_lead,
			"options": field_option,
		})
	return out


def get_deal_activities(name: str):
	if not frappe.has_permission("CRM Deal", "read", name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	get_docinfo("", "CRM Deal", name)
	docinfo = frappe.response["docinfo"]
	deal_meta = frappe.get_meta("CRM Deal")
	deal_fields = {
		field.fieldname: {"label": field.label, "options": field.options, "fieldtype": field.fieldtype}
		for field in deal_meta.fields
	}
	avoid_fields = [
		"lead",
		"response_by",
		"sla_creation",
		"sla",
		"first_response_time",
		"first_responded_on",
	]

	doc = frappe.db.get_values("CRM Deal", name, ["creation", "owner", "lead"])[0]
	lead = doc[2]

	activities = []
	calls = []
	notes = []
	tasks = []
	attachments = []
	creation_text = _("created this deal")

	if lead:
		activities, calls, notes, tasks, attachments = get_lead_activities(lead)
		creation_text = _("converted the lead to this deal")

	activities.append(
		{
			"activity_type": "creation",
			"creation": doc[0],
			"owner": doc[1],
			"data": creation_text,
			"is_lead": False,
		}
	)

	docinfo.versions.reverse()

	for version in docinfo.versions:
		activities.extend(version_activities(version, deal_fields, avoid_fields, False))

	for comment in docinfo.comments:
		activity = {
			"name": comment.name,
			"activity_type": "comment",
			"creation": comment.creation,
			"owner": comment.owner,
			"content": comment.content,
			"attachments": get_attachments("Comment", comment.name),
			"is_lead": False,
		}
		activities.append(activity)

	for communication in docinfo.communications + docinfo.automated_messages:
		activity = {
			"activity_type": "communication",
			"communication_type": communication.communication_type,
			"communication_date": communication.communication_date or communication.creation,
			"creation": communication.creation,
			"data": {
				"subject": communication.subject,
				"content": communication.content,
				"sender_full_name": communication.sender_full_name,
				"sender": communication.sender,
				"recipients": communication.recipients,
				"cc": communication.cc,
				"bcc": communication.bcc,
				"attachments": get_attachments("Communication", communication.name),
				"read_by_recipient": communication.read_by_recipient,
				"delivery_status": communication.delivery_status,
			},
			"is_lead": False,
		}
		activities.append(activity)

	for attachment_log in docinfo.attachment_logs:
		activity = {
			"name": attachment_log.name,
			"activity_type": "attachment_log",
			"creation": attachment_log.creation,
			"owner": attachment_log.owner,
			"data": parse_attachment_log(attachment_log.content, attachment_log.comment_type),
			"is_lead": False,
		}
		activities.append(activity)

	calls = calls + get_linked_calls(name).get("calls", [])
	notes = notes + get_linked_notes(name) + get_linked_calls(name).get("notes", [])
	tasks = tasks + get_linked_tasks(name) + get_linked_calls(name).get("tasks", [])
	attachments = attachments + get_attachments("CRM Deal", name)

	activities = collapse_rapid_status_changes(activities)
	activities.sort(key=lambda x: x["creation"], reverse=True)
	activities = handle_multiple_versions(activities)

	return activities, calls, notes, tasks, attachments


def get_lead_activities(name: str):
	if not frappe.has_permission("CRM Lead", "read", name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	get_docinfo("", "CRM Lead", name)
	docinfo = frappe.response["docinfo"]
	lead_meta = frappe.get_meta("CRM Lead")
	lead_fields = {
		field.fieldname: {"label": field.label, "options": field.options, "fieldtype": field.fieldtype}
		for field in lead_meta.fields
	}
	avoid_fields = [
		"converted",
		"response_by",
		"sla_creation",
		"sla",
		"first_response_time",
		"first_responded_on",
		"custom_refund_draft_json",
	]

	doc = frappe.db.get_values("CRM Lead", name, ["creation", "owner"])[0]
	activities = [
		{
			"activity_type": "creation",
			"creation": doc[0],
			"owner": doc[1],
			"data": _("created this lead"),
			"is_lead": True,
		}
	]

	docinfo.versions.reverse()

	for version in docinfo.versions:
		activities.extend(version_activities(version, lead_fields, avoid_fields, True))

	for comment in docinfo.comments:
		activity = {
			"name": comment.name,
			"activity_type": "comment",
			"creation": comment.creation,
			"owner": comment.owner,
			"content": comment.content,
			"attachments": get_attachments("Comment", comment.name),
			"is_lead": True,
		}
		activities.append(activity)

	for communication in docinfo.communications + docinfo.automated_messages:
		activity = {
			"activity_type": "communication",
			"communication_type": communication.communication_type,
			"communication_date": communication.communication_date or communication.creation,
			"creation": communication.creation,
			"data": {
				"subject": communication.subject,
				"content": communication.content,
				"sender_full_name": communication.sender_full_name,
				"sender": communication.sender,
				"recipients": communication.recipients,
				"cc": communication.cc,
				"bcc": communication.bcc,
				"attachments": get_attachments("Communication", communication.name),
				"read_by_recipient": communication.read_by_recipient,
				"delivery_status": communication.delivery_status,
			},
			"is_lead": True,
		}
		activities.append(activity)

	for attachment_log in docinfo.attachment_logs:
		activity = {
			"name": attachment_log.name,
			"activity_type": "attachment_log",
			"creation": attachment_log.creation,
			"owner": attachment_log.owner,
			"data": parse_attachment_log(attachment_log.content, attachment_log.comment_type),
			"is_lead": True,
		}
		activities.append(activity)

	calls = get_linked_calls(name).get("calls", [])
	notes = get_linked_notes(name) + get_linked_calls(name).get("notes", [])
	tasks = get_linked_tasks(name) + get_linked_calls(name).get("tasks", [])
	attachments = get_attachments("CRM Lead", name)

	activities = collapse_rapid_status_changes(activities)
	activities.sort(key=lambda x: x["creation"], reverse=True)
	activities = handle_multiple_versions(activities)

	return activities, calls, notes, tasks, attachments


def get_buyer_activities(name: str):
	"""Activity feed for a CRM Buyer — mirrors get_lead_activities (versions,
	comments, communications, attachments, linked notes/tasks/calls) so the
	buyer page can reuse the same Activities component as leads/deals."""
	if not frappe.has_permission("CRM Buyer", "read", name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	get_docinfo("", "CRM Buyer", name)
	docinfo = frappe.response["docinfo"]
	buyer_meta = frappe.get_meta("CRM Buyer")
	buyer_fields = {
		field.fieldname: {"label": field.label, "options": field.options, "fieldtype": field.fieldtype}
		for field in buyer_meta.fields
	}
	# machine-maintained fields (scraper/webhook churn) — noise in the feed
	avoid_fields = [
		"il_buyer_id",
		"last_active",
		"deal_history",
	]

	doc = frappe.db.get_values("CRM Buyer", name, ["creation", "owner"])[0]
	activities = [
		{
			"activity_type": "creation",
			"creation": doc[0],
			"owner": doc[1],
			"data": _("created this buyer"),
			"is_lead": False,
		}
	]

	docinfo.versions.reverse()

	for version in docinfo.versions:
		activities.extend(version_activities(version, buyer_fields, avoid_fields, False))

	for comment in docinfo.comments:
		activity = {
			"name": comment.name,
			"activity_type": "comment",
			"creation": comment.creation,
			"owner": comment.owner,
			"content": comment.content,
			"attachments": get_attachments("Comment", comment.name),
			"is_lead": False,
		}
		activities.append(activity)

	for communication in docinfo.communications + docinfo.automated_messages:
		activity = {
			"activity_type": "communication",
			"communication_type": communication.communication_type,
			"communication_date": communication.communication_date or communication.creation,
			"creation": communication.creation,
			"data": {
				"subject": communication.subject,
				"content": communication.content,
				"sender_full_name": communication.sender_full_name,
				"sender": communication.sender,
				"recipients": communication.recipients,
				"cc": communication.cc,
				"bcc": communication.bcc,
				"attachments": get_attachments("Communication", communication.name),
				"read_by_recipient": communication.read_by_recipient,
				"delivery_status": communication.delivery_status,
			},
			"is_lead": False,
		}
		activities.append(activity)

	for attachment_log in docinfo.attachment_logs:
		activity = {
			"name": attachment_log.name,
			"activity_type": "attachment_log",
			"creation": attachment_log.creation,
			"owner": attachment_log.owner,
			"data": parse_attachment_log(attachment_log.content, attachment_log.comment_type),
			"is_lead": False,
		}
		activities.append(activity)

	calls = get_linked_calls(name).get("calls", [])
	notes = get_linked_notes(name) + get_linked_calls(name).get("notes", [])
	tasks = get_linked_tasks(name) + get_linked_calls(name).get("tasks", [])
	attachments = get_attachments("CRM Buyer", name)

	activities.sort(key=lambda x: x["creation"], reverse=True)
	activities = handle_multiple_versions(activities)

	return activities, calls, notes, tasks, attachments


def get_attachments(doctype: str, name: str):
	return (
		frappe.db.get_all(
			"File",
			filters={"attached_to_doctype": doctype, "attached_to_name": name},
			fields=[
				"name",
				"file_name",
				"file_type",
				"file_url",
				"file_size",
				"is_private",
				"modified",
				"creation",
				"owner",
			],
		)
		or []
	)


# Status changes held for less than this are treated as mis-clicks and hidden
# from the activity timeline — mirrors the CRM Status Change Log collapse so the
# two surfaces agree (see crm_status_change_log.add_status_change_log).
STATUS_COLLAPSE_SECONDS = 60


def _is_status_change(activity):
	return (
		activity.get("activity_type") in ("changed", "added", "removed")
		and isinstance(activity.get("data"), dict)
		and activity["data"].get("field") == "status"
	)


def _status_from(activity):
	# "added" entries carry only the new value; their prior status is empty
	if activity["activity_type"] == "added":
		return ""
	return activity["data"].get("old_value") or ""


def _status_to(activity):
	return activity["data"].get("value") or ""


def collapse_rapid_status_changes(activities, threshold_seconds=STATUS_COLLAPSE_SECONDS):
	"""Hide fleeting intermediate status changes from the activity timeline.

	A run of consecutive status changes where each intermediate status was held
	for less than ``threshold_seconds`` collapses to a single net transition, so
	a mistaken A→B→C done within a minute shows only A→C. A run that returns to
	where it started (A→B→A) is dropped entirely. The surviving entry keeps the
	final change's timestamp (when the status actually settled). This is a
	display-only filter — it never touches the underlying Version audit trail.
	"""
	status_acts = sorted(
		(a for a in activities if _is_status_change(a)),
		key=lambda a: get_datetime(a["creation"]),
	)
	if len(status_acts) < 2:
		return activities

	drop = set()
	i, n = 0, len(status_acts)
	while i < n:
		j = i
		while (
			j + 1 < n
			and (
				get_datetime(status_acts[j + 1]["creation"]) - get_datetime(status_acts[j]["creation"])
			).total_seconds()
			< threshold_seconds
			and _status_to(status_acts[j]) == _status_from(status_acts[j + 1])
		):
			j += 1
		if j > i:
			first, last = status_acts[i], status_acts[j]
			net_from, net_to = _status_from(first), _status_to(last)
			for k in range(i, j):
				drop.add(id(status_acts[k]))  # drop the fleeting intermediates
			if net_from == net_to:
				drop.add(id(last))  # bounced back — no net change to show
			else:
				# rewrite the surviving entry to read as the net transition
				last["data"]["old_value"] = net_from
				last["activity_type"] = "changed"
		i = j + 1

	if not drop:
		return activities
	return [a for a in activities if id(a) not in drop]


def handle_multiple_versions(versions: list):
	activities = []
	grouped_versions = []
	old_version = None
	for version in versions:
		is_version = version["activity_type"] in ["changed", "added", "removed"]
		# status changes stay standalone on the timeline (never collapsed
		# into "+N changes") so they're visible while scrolling
		is_status_change = (
			is_version
			and isinstance(version.get("data"), dict)
			and version["data"].get("field") == "status"
		)
		if is_status_change:
			if grouped_versions:
				activities.append(parse_grouped_versions(grouped_versions))
				grouped_versions = []
			activities.append(version)
			old_version = version
			continue
		if not is_version:
			activities.append(version)
		if not old_version:
			old_version = version
			if is_version:
				grouped_versions.append(version)
			continue
		if is_version and old_version.get("owner") and version["owner"] == old_version["owner"]:
			grouped_versions.append(version)
		else:
			if grouped_versions:
				activities.append(parse_grouped_versions(grouped_versions))
			grouped_versions = []
			if is_version:
				grouped_versions.append(version)
		old_version = version
		if version == versions[-1] and grouped_versions:
			activities.append(parse_grouped_versions(grouped_versions))

	return activities


def parse_grouped_versions(versions: list):
	version = versions[0]
	if len(versions) == 1:
		return version
	other_versions = versions[1:]
	version["other_versions"] = other_versions
	return version


def get_linked_calls(name: str):
	calls = frappe.db.get_all(
		"CRM Call Log",
		filters={"reference_docname": name},
		fields=[
			"name",
			"caller",
			"receiver",
			"from",
			"to",
			"duration",
			"start_time",
			"end_time",
			"status",
			"type",
			"recording_url",
			"creation",
			"note",
		],
	)

	linked_calls = frappe.db.get_all(
		"Dynamic Link", filters={"link_name": name, "parenttype": "CRM Call Log"}, pluck="parent"
	)

	notes = []
	tasks = []

	if linked_calls:
		CallLog = frappe.qb.DocType("CRM Call Log")
		Link = frappe.qb.DocType("Dynamic Link")
		query = (
			frappe.qb.from_(CallLog)
			.select(
				CallLog.name,
				CallLog.caller,
				CallLog.receiver,
				CallLog["from"],
				CallLog.to,
				CallLog.duration,
				CallLog.start_time,
				CallLog.end_time,
				CallLog.status,
				CallLog.type,
				CallLog.recording_url,
				CallLog.creation,
				CallLog.note,
				Link.link_doctype,
				Link.link_name,
			)
			.join(Link, JoinType.inner)
			.on(Link.parent == CallLog.name)
			.where(CallLog.name.isin(linked_calls))
		)
		_calls = query.run(as_dict=True)

		for call in _calls:
			if call.get("link_doctype") == "FCRM Note":
				notes.append(call.link_name)
			elif call.get("link_doctype") == "CRM Task":
				tasks.append(call.link_name)

		_calls = [call for call in _calls if call.get("link_doctype") not in ["FCRM Note", "CRM Task"]]
		if _calls:
			calls = calls + _calls

	if notes:
		notes = frappe.db.get_all(
			"FCRM Note",
			filters={"name": ("in", notes)},
			fields=["name", "title", "content", "owner", "modified"],
		)

	if tasks:
		tasks = frappe.db.get_all(
			"CRM Task",
			filters={"name": ("in", tasks)},
			fields=[
				"name",
				"title",
				"description",
				"assigned_to",
				"due_date",
				"priority",
				"status",
				"call_outcome",
				"modified",
			],
		)

	calls = [parse_call_log(call) for call in calls] if calls else []

	return {"calls": calls, "notes": notes, "tasks": tasks}


def get_linked_notes(name: str):
	notes = frappe.db.get_all(
		"FCRM Note",
		filters={"reference_docname": name},
		fields=["name", "title", "content", "owner", "modified", "creation"],
	)
	return notes or []


def get_linked_tasks(name: str):
	tasks = frappe.db.get_all(
		"CRM Task",
		filters={"reference_docname": name},
		fields=[
			"name",
			"title",
			"description",
			"assigned_to",
			"due_date",
			"priority",
			"status",
			"call_outcome",
			"modified",
			"creation",
		],
	)
	return tasks or []


def parse_attachment_log(html: str, type: str):
	soup = BeautifulSoup(html, "html.parser")
	a_tag = soup.find("a")
	type = "added" if type == "Attachment" else "removed"
	if not a_tag:
		return {
			"type": type,
			"file_name": html.replace("Removed ", ""),
			"file_url": "",
			"is_private": False,
		}

	is_private = False
	if "private/files" in a_tag["href"]:
		is_private = True

	return {
		"type": type,
		"file_name": a_tag.text,
		"file_url": a_tag["href"],
		"is_private": is_private,
	}


def is_translatable(doctype: str) -> bool:
	return doctype in get_translated_doctypes()
