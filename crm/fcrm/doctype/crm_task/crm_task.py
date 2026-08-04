# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.desk.form.assign_to import add as assign
from frappe.desk.form.assign_to import remove as unassign
from frappe.model.document import Document


class CRMTask(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		assigned_to: DF.Link | None
		description: DF.TextEditor | None
		due_date: DF.Datetime | None
		name: DF.Int | None
		priority: DF.Literal["Low", "Medium", "High"]
		reference_docname: DF.DynamicLink | None
		reference_doctype: DF.Link | None
		start_date: DF.Date | None
		status: DF.Literal["Backlog", "Todo", "In Progress", "Done", "Canceled"]
		title: DF.Data
	# end: auto-generated types

	def after_insert(self):
		self.assign_to()
		self.notify_task_update()

	def on_update(self):
		self.notify_task_update()

	def on_trash(self):
		self.notify_task_update()

	def notify_task_update(self):
		"""Broadcast a realtime event so the Lead/Deal Activity feed (the Trello-style
		to-do list) and the Kanban next-task-due badge refresh without a page reload.
		Mirrors the quo_message pattern in crm/api/sms.py (the front-end listens for
		`crm_task_update` and reloads the matching lead/deal).

		No room/user is passed, so Frappe broadcasts to the site room ("all") — every
		logged-in System User receives it (site-wide). `after_commit=True` defers the
		emit until the DB transaction commits, so the client's reload can't race ahead
		and read the task in its pre-commit (stale / not-yet-deleted) state."""
		if self.reference_doctype and self.reference_docname:
			frappe.publish_realtime(
				"crm_task_update",
				{
					"reference_doctype": self.reference_doctype,
					"reference_docname": self.reference_docname,
				},
				after_commit=True,
			)
			# A new/due-today lead task can pull the lead onto the shared Today board.
			# This is add-only and queued after commit, so task saves stay fast.
			from crm.api.today_board import enqueue_today_sync

			enqueue_today_sync(self)

	def validate(self):
		if self.is_new() or not self.assigned_to:
			return

		if self.get_doc_before_save().assigned_to != self.assigned_to:
			self.unassign_from_previous_user(self.get_doc_before_save().assigned_to)
			self.assign_to()

	def unassign_from_previous_user(self, user: str | None):
		if user:
			unassign(self.doctype, self.name, user)

	def assign_to(self):
		if self.assigned_to:
			assign(
				{
					"assign_to": [self.assigned_to],
					"doctype": self.doctype,
					"name": self.name,
					"description": self.title or self.description,
				}
			)

	@staticmethod
	def default_list_data():
		columns = [
			{
				"label": "Title",
				"type": "Data",
				"key": "title",
				"width": "16rem",
			},
			{
				"label": "Status",
				"type": "Select",
				"key": "status",
				"width": "8rem",
			},
			{
				"label": "Priority",
				"type": "Select",
				"key": "priority",
				"width": "8rem",
			},
			{
				"label": "Due Date",
				"type": "Date",
				"key": "due_date",
				"width": "8rem",
			},
			{
				"label": "Assigned To",
				"type": "Link",
				"key": "assigned_to",
				"width": "10rem",
			},
			{
				"label": "Last Modified",
				"type": "Datetime",
				"key": "modified",
				"width": "8rem",
			},
		]

		rows = [
			"name",
			"title",
			"description",
			"assigned_to",
			"due_date",
			"status",
			"priority",
			"reference_doctype",
			"reference_docname",
			"modified",
		]
		return {"columns": columns, "rows": rows}

	@staticmethod
	def default_kanban_settings():
		return {
			"column_field": "status",
			"title_field": "title",
			"kanban_fields": '["description", "priority", "creation"]',
		}
