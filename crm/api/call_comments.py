"""Timestamped comments on a recorded call (Groundwork).

Reviewers annotate a specific moment in a call; the comment is pinned on the
Playback waveform at `at_time` seconds. Stored as `CRM Call Comment` rows (the
custom doctype is created by the ops repo's setup_crm_call_comment.py) — one row
per comment, `author` is always the session user, edit/delete are owner-only
(managers may also delete). Every mutation broadcasts a site-wide
`crm_call_comment` realtime event (after_commit) so other open Playback views of
the same call refresh live — done from app code because the server-script sandbox
can't publish_realtime (see the quo_message / crm_tax_pull pattern).

Collaborative: every sales user sees all comments on a call.
"""
import frappe
from frappe import _
from frappe.utils import flt, get_fullname

ALLOWED_ROLES = ["System Manager", "Sales Manager", "Sales User"]
MANAGER_ROLES = ["System Manager", "Sales Manager"]
DOCTYPE = "CRM Call Comment"


def _validate_access():
	if not any(role in ALLOWED_ROLES for role in frappe.get_roles()):
		frappe.throw(_("Only sales users can comment on calls."), frappe.PermissionError)


def _provisioned():
	return frappe.db.exists("DocType", DOCTYPE)


def _publish(call_log):
	# site-wide (no room/user) so every reviewer's open Playback view refreshes;
	# after_commit so a listener's reload can't race ahead of the write
	frappe.publish_realtime("crm_call_comment", {"call_log": call_log}, after_commit=True)


def _row(d):
	return {
		"name": d.name,
		"at_time": flt(d.at_time),
		"author": d.author,
		"author_name": get_fullname(d.author),
		"content": d.content or "",
		"creation": str(d.creation),
		"mine": d.author == frappe.session.user,
	}


@frappe.whitelist()
def get_call_comments(call_log: str):
	"""All comments on a call, oldest moment first. Degrades to [] pre-provision."""
	_validate_access()
	if not _provisioned():
		return []
	rows = frappe.get_all(
		DOCTYPE,
		filters={"call_log": call_log},
		fields=["name", "at_time", "author", "content", "creation"],
		order_by="at_time asc",
	)
	mine = frappe.session.user
	out = []
	for r in rows:
		out.append({
			"name": r["name"],
			"at_time": flt(r["at_time"]),
			"author": r["author"],
			"author_name": get_fullname(r["author"]),
			"content": r["content"] or "",
			"creation": str(r["creation"]),
			"mine": r["author"] == mine,
		})
	return out


@frappe.whitelist()
def add_call_comment(call_log: str, at_time, content: str):
	"""Add a comment at `at_time` seconds on a call (author = session user)."""
	_validate_access()
	if not _provisioned():
		frappe.throw(_("Call comments are not enabled on this site yet."))
	if not frappe.db.exists("CRM Call Log", call_log):
		frappe.throw(_("Call {0} does not exist.").format(call_log), frappe.DoesNotExistError)
	content = (content or "").strip()
	if not content:
		frappe.throw(_("Comment cannot be empty."))

	doc = frappe.new_doc(DOCTYPE)
	doc.call_log = call_log
	doc.at_time = flt(at_time)
	doc.author = frappe.session.user
	doc.content = content
	doc.save(ignore_permissions=True)  # role-gated above, author is the session user

	_publish(call_log)
	return _row(doc)


@frappe.whitelist()
def edit_call_comment(name: str, content: str):
	"""Edit your own comment's text (owner-only)."""
	_validate_access()
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.author != frappe.session.user:
		frappe.throw(_("You can only edit your own comments."), frappe.PermissionError)
	content = (content or "").strip()
	if not content:
		frappe.throw(_("Comment cannot be empty."))
	doc.content = content
	doc.save(ignore_permissions=True)
	_publish(doc.call_log)
	return _row(doc)


@frappe.whitelist()
def delete_call_comment(name: str):
	"""Delete a comment — your own, or any if you're a manager."""
	_validate_access()
	doc = frappe.get_doc(DOCTYPE, name)
	is_manager = any(role in MANAGER_ROLES for role in frappe.get_roles())
	if doc.author != frappe.session.user and not is_manager:
		frappe.throw(_("You can only delete your own comments."), frappe.PermissionError)
	call_log = doc.call_log
	doc.delete(ignore_permissions=True)
	_publish(call_log)
	return {"deleted": name}
