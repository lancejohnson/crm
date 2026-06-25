import json
from collections.abc import Iterable

import frappe
from bs4 import BeautifulSoup
from frappe import _
from frappe.desk.form.utils import add_comment as frappe_add_comment
from frappe.utils import get_fullname

from crm.fcrm.doctype.crm_notification.crm_notification import notify_user


def on_update(self, method):
	notify_mentions(self)


def notify_mentions(doc):
	"""
	Extract mentions from `content`, and notify.
	`content` must have `HTML` content.
	"""
	if doc.flags.skip_mention_notification:
		# Edits re-trigger on_update; don't re-notify everyone already mentioned.
		return
	content = getattr(doc, "content", None)
	if not content:
		return
	mentions = extract_mentions(content)
	if not mentions:
		# Nothing to notify. Crucially, this also skips the work below for the
		# assignment comments Frappe auto-creates on *any* doctype (e.g. a CRM Task
		# when it's assigned) — those reference docs aren't Leads/Deals and have no
		# `organization`/`lead_name`, so computing `name` would raise and 500 the
		# whole insert (which is what broke all task creation).
		return
	reference_doc = frappe.get_doc(doc.reference_doctype, doc.reference_name)
	owner = frappe.get_cached_value("User", doc.owner, "full_name")
	doctype = doc.reference_doctype
	if doctype.startswith("CRM "):
		doctype = doctype[4:].lower()
	name = (
		reference_doc.get("lead_name")
		if doctype == "lead"
		else reference_doc.get("organization") or reference_doc.get("lead_name")
	)
	for mention in mentions:
		notification_text = f"""
            <div class="mb-2 leading-5 text-ink-gray-5">
                <span class="font-medium text-ink-gray-9">{ owner }</span>
                <span>{ _('mentioned you in {0}').format(doctype) }</span>
                <span class="font-medium text-ink-gray-9">{ name }</span>
            </div>
        """
		notify_user(
			{
				"owner": doc.owner,
				"assigned_to": mention.email,
				"notification_type": "Mention",
				"message": doc.content,
				"notification_text": notification_text,
				"reference_doctype": "Comment",
				"reference_docname": doc.name,
				"redirect_to_doctype": doc.reference_doctype,
				"redirect_to_docname": doc.reference_name,
			}
		)
		email_mention(doc, mention, mentioned_by=owner, record_label=name)


def email_mention(doc, mention, mentioned_by, record_label):
	"""Email the mentioned user the comment plus a deep-link back to it.

	Mirrors the in-app notification's redirect: the CRM app route
	`/crm/{leads|deals}/<reference_name>#<comment_name>` lands on the record and
	scrolls to the comment (same `#<comment_name>` hash the bell menu uses).
	Best-effort — a mail failure must never roll back the comment.
	"""
	# Don't email yourself for your own mention (mirrors notify_user's skip).
	if not mention.email or mention.email == doc.owner:
		return

	route = "deals" if doc.reference_doctype == "CRM Deal" else "leads"
	comment_link = frappe.utils.get_url(f"/crm/{route}/{doc.reference_name}#{doc.name}")

	try:
		frappe.sendmail(
			recipients=mention.email,
			subject=_("{0} mentioned you in {1}").format(mentioned_by, record_label),
			template="crm_mention",
			args={
				"mentioned_by": mentioned_by,
				"record_label": record_label,
				"comment_content": doc.content,
				"comment_link": comment_link,
			},
			reference_doctype=doc.reference_doctype,
			reference_name=doc.reference_name,
		)
	except Exception:
		frappe.log_error("CRM mention email failed", frappe.get_traceback())


def extract_mentions(html):
	if not html:
		return []
	soup = BeautifulSoup(html, "html.parser")
	mentions = []
	for d in soup.find_all("span", attrs={"data-type": "mention"}):
		mentions.append(frappe._dict(full_name=d.get("data-label"), email=d.get("data-id")))
	return mentions


@frappe.whitelist()
def add_comment(reference_doctype: str, reference_name: str, content: str, attachments: list | None = None):
	"""Add a comment to the given document

	:param reference_doctype: Reference Doctype
	:param reference_name: Reference Document Name
	:param content: Comment Content (HTML)
	:param attachments: List of File names or dicts with keys "fname" and "fcontent"
	:return: Comment Document
	"""
	comment = frappe_add_comment(
		reference_doctype,
		reference_name,
		content,
		comment_email=frappe.session.user,
		comment_by=get_fullname(frappe.session.user),
	)

	if attachments and comment.name:
		add_attachments(comment.name, attachments)

	return comment


@frappe.whitelist()
def edit_comment(comment_name: str, content: str):
	"""Edit the content of an existing comment.

	Only the comment's author may edit it.

	:param comment_name: Name of the Comment to edit
	:param content: New comment content (HTML)
	:return: Updated Comment Document
	"""
	comment = frappe.get_doc("Comment", comment_name)

	if comment.comment_type != "Comment":
		frappe.throw(_("Only comments can be edited"))

	if comment.owner != frappe.session.user:
		frappe.throw(_("You can only edit your own comments"), frappe.PermissionError)

	comment.content = content
	# Don't re-notify everyone already mentioned each time the comment is edited.
	comment.flags.skip_mention_notification = True
	comment.save(ignore_permissions=True)

	return comment


@frappe.whitelist()
def delete_comment(comment_name: str):
	"""Delete an existing comment.

	Only the comment's author may delete it (mirrors `edit_comment`).

	:param comment_name: Name of the Comment to delete
	"""
	comment = frappe.get_doc("Comment", comment_name)

	if comment.comment_type != "Comment":
		frappe.throw(_("Only comments can be deleted"))

	if comment.owner != frappe.session.user:
		frappe.throw(_("You can only delete your own comments"), frappe.PermissionError)

	comment.delete(ignore_permissions=True)


QUICK_COMMENTS_MAX = 30


@frappe.whitelist()
def set_user_quick_comments(comments):
	"""Persist the current user's customizable quick-comment chips.

	A user only ever edits their own list (no `user` param — keyed to the session
	user), stored as a JSON array of strings on `User.custom_quick_comments`. An
	empty/unset value means "fall back to the frontend defaults".

	:param comments: JSON array (or already-parsed list) of comment strings
	:return: the cleaned list that was stored
	"""
	if isinstance(comments, str):
		try:
			comments = json.loads(comments)
		except (ValueError, TypeError):
			frappe.throw(_("Invalid quick comments payload."))
	if not isinstance(comments, list):
		frappe.throw(_("Quick comments must be a list."))

	cleaned = [str(c).strip() for c in comments if str(c).strip()][:QUICK_COMMENTS_MAX]
	frappe.db.set_value(
		"User",
		frappe.session.user,
		"custom_quick_comments",
		json.dumps(cleaned),
		update_modified=False,
	)
	return cleaned


def add_attachments(name: str, attachments: Iterable[str | dict]) -> None:
	"""Add attachments to the given Comment

	:param name: Comment name
	:param attachments: File names or dicts with keys "fname" and "fcontent"
	"""
	# loop through attachments
	for a in attachments:
		if isinstance(a, str):
			attach = frappe.db.get_value("File", {"name": a}, ["file_url", "is_private"], as_dict=1)
			file_args = {
				"file_url": attach.file_url,
				"is_private": attach.is_private,
			}
		elif isinstance(a, dict) and "fcontent" in a and "fname" in a:
			# dict returned by frappe.attach_print()
			file_args = {
				"file_name": a["fname"],
				"content": a["fcontent"],
				"is_private": 1,
			}
		else:
			continue

		file_args.update(
			{
				"attached_to_doctype": "Comment",
				"attached_to_name": name,
				"folder": "Home/Attachments",
			}
		)

		_file = frappe.new_doc("File")
		_file.update(file_args)
		_file.save(ignore_permissions=True)
