# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from datetime import datetime

import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date, get_datetime


class CRMStatusChangeLog(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		duration: DF.Duration | None
		from_date: DF.Datetime | None
		from_type: DF.Data | None
		last_status_change_log: DF.Link | None
		log_owner: DF.Link | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		to: DF.Data | None
		to_date: DF.Datetime | None
		to_type: DF.Data | None
	# end: auto-generated types

	pass


def get_duration(from_date, to_date):
	if not isinstance(from_date, datetime):
		from_date = get_datetime(from_date)
	if not isinstance(to_date, datetime):
		to_date = get_datetime(to_date)
	duration = to_date - from_date
	return duration.total_seconds()


# A status held for less than this is treated as a mis-click and collapsed out of
# the log (so a quick A→B→C reads as A→C, hiding the fleeting intermediate B).
MIN_STATUS_HELD_SECONDS = 60


def add_status_change_log(doc):
	to_status_type = frappe.db.get_value("CRM Deal Status", doc.status, "type") if doc.status else None

	skip_new_row = False

	if not doc.is_new():
		previous_status = doc.get_doc_before_save().status if doc.get_doc_before_save() else None
		previous_status_type = (
			frappe.db.get_value("CRM Deal Status", previous_status, "type") if previous_status else None
		)
		if not doc.status_change_log and previous_status:
			now_minus_one_minute = add_to_date(datetime.now(), minutes=-1)
			doc.append(
				"status_change_log",
				{
					"from": previous_status,
					"from_type": previous_status_type or "",
					"to": "",
					"to_type": "",
					"from_date": now_minus_one_minute,
					"to_date": "",
					"log_owner": frappe.session.user,
				},
			)
		last_status_change = doc.status_change_log[-1]

		# How long the status we're now leaving was actually held. If it was only
		# held briefly AND it was itself reached via a recorded transition (i.e.
		# there's a prior completed row), treat it as a mistaken click: rewrite
		# that prior transition to point straight at the new status and drop the
		# fleeting intermediate row instead of recording a second quick change.
		held_seconds = (datetime.now() - get_datetime(last_status_change.from_date)).total_seconds()
		prior = doc.status_change_log[-2] if len(doc.status_change_log) >= 2 else None
		is_fleeting = (
			prior is not None
			and held_seconds < MIN_STATUS_HELD_SECONDS
			and prior.to == last_status_change.get("from")
		)

		if is_fleeting and doc.status == prior.get("from"):
			# Bounced straight back to the original status (A→B→A): undo entirely,
			# reopening the prior row as if the detour never happened.
			prior.to = ""
			prior.to_type = ""
			prior.to_date = None
			prior.duration = None
			doc.status_change_log.remove(last_status_change)
			_renumber_status_change_log(doc)
			skip_new_row = True
		elif is_fleeting:
			# Collapse the fleeting intermediate status (A→B→C reads as A→C).
			prior.to = doc.status
			prior.to_type = to_status_type or ""
			prior.to_date = datetime.now()
			prior.log_owner = frappe.session.user
			prior.duration = get_duration(prior.from_date, prior.to_date)
			doc.status_change_log.remove(last_status_change)
			_renumber_status_change_log(doc)
		else:
			last_status_change.to = doc.status
			last_status_change.to_type = to_status_type or ""
			last_status_change.to_date = datetime.now()
			last_status_change.log_owner = frappe.session.user
			last_status_change.duration = get_duration(
				last_status_change.from_date, last_status_change.to_date
			)

	if not skip_new_row:
		doc.append(
			"status_change_log",
			{
				"from": doc.status,
				"from_type": to_status_type or "",
				"to": "",
				"to_type": "",
				"from_date": datetime.now(),
				"to_date": "",
				"log_owner": frappe.session.user,
			},
		)


def _renumber_status_change_log(doc):
	# Keep child-row idx contiguous after removing a row — the dashboard reports
	# read the lowest-idx row as the lead's creation status (see leads_dashboard).
	for i, row in enumerate(doc.status_change_log, start=1):
		row.idx = i
