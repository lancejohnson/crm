"""Groundwork custom leads dashboard.

A focused, single-call dashboard answering three questions:
  1. New leads per day over the selected range (+ a total).
  2. Status changes for leads — how many entered vs. exited each stage.
  3. New leads broken down by source.

Status-change data comes from the `CRM Status Change Log` child table that the
Lead doctype writes to on every status change (see crm_lead.py -> add_status_change_log).
Each completed row means: the lead entered `from` at `from_date` and left it for
`to` at `to_date` — i.e. one "exited `from`" event and one "entered `to`" event,
both stamped at `to_date`.
"""

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count, Date

from crm.api.dashboard import get_leads_by_source
from crm.utils import sales_user_only


@frappe.whitelist()
@sales_user_only
def get_leads_dashboard(
	from_date: str | None = None, to_date: str | None = None, user: str | None = None
):
	"""Return all three datasets for the Groundwork leads dashboard in one call."""
	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	# Sales users only ever see their own leads, regardless of the passed-in user.
	roles = frappe.get_roles(frappe.session.user)
	is_sales_manager = "Sales Manager" in roles or "System Manager" in roles
	if "Sales User" in roles and not is_sales_manager:
		user = frappe.session.user

	return {
		"new_leads_trend": _new_leads_trend(from_date, to_date, user),
		"status_changes": _status_changes(from_date, to_date, user),
		"leads_by_source": get_leads_by_source(from_date, to_date, user),
		"summary": _summary(from_date, to_date, user),
	}


def _summary(from_date, to_date, user):
	"""Two headline numbers: new leads created, and status changes recorded."""
	Lead = DocType("CRM Lead")
	leads_q = (
		frappe.qb.from_(Lead)
		.select(Count("*").as_("count"))
		.where(Date(Lead.creation).between(from_date, to_date))
	)
	if user:
		leads_q = leads_q.where(Lead.lead_owner == user)
	new_leads = (leads_q.run(as_dict=True)[0].count) or 0

	SCL = DocType("CRM Status Change Log")
	changes_q = (
		frappe.qb.from_(SCL)
		.join(Lead)
		.on(SCL.parent == Lead.name)
		.select(Count("*").as_("count"))
		.where(
			(SCL.parenttype == "CRM Lead")
			& (SCL.to.isnotnull())
			& (SCL.to != "")
			& (Date(SCL.to_date).between(from_date, to_date))
		)
	)
	if user:
		changes_q = changes_q.where(Lead.lead_owner == user)
	status_changes = (changes_q.run(as_dict=True)[0].count) or 0

	return [
		{
			"title": _("New leads"),
			"tooltip": _("Leads created in the selected range"),
			"value": new_leads,
		},
		{
			"title": _("Status changes"),
			"tooltip": _("Stage transitions recorded for leads in the selected range"),
			"value": status_changes,
		},
	]


def _new_leads_trend(from_date, to_date, user):
	"""Daily count of leads created, zero-filled across the whole range."""
	Lead = DocType("CRM Lead")
	query = (
		frappe.qb.from_(Lead)
		.select(Date(Lead.creation).as_("date"), Count("*").as_("leads"))
		.where(Date(Lead.creation).between(from_date, to_date))
		.groupby(Date(Lead.creation))
		.orderby(Date(Lead.creation))
	)
	if user:
		query = query.where(Lead.lead_owner == user)

	counts = {
		frappe.utils.get_datetime(row.date).strftime("%Y-%m-%d"): row.leads or 0
		for row in query.run(as_dict=True)
	}

	# Zero-fill every day in the range so the chart reads cleanly.
	data = []
	day = frappe.utils.getdate(from_date)
	last = frappe.utils.getdate(to_date)
	while day <= last:
		key = day.strftime("%Y-%m-%d")
		data.append({"date": key, "leads": counts.get(key, 0)})
		day = frappe.utils.add_days(day, 1)

	return {
		"data": data,
		"title": _("New leads per day"),
		"subtitle": _("Leads created each day in the selected range"),
		"xAxis": {
			"title": _("Date"),
			"key": "date",
			"type": "time",
			"timeGrain": "day",
		},
		"yAxis": {"title": _("New leads")},
		"series": [{"name": "leads", "type": "bar"}],
	}


def _status_changes(from_date, to_date, user):
	"""Per-stage entered vs. exited counts from the lead status change log.

	`entered S` = completed rows whose `to` is S (lead moved into S).
	`exited S`  = completed rows whose `from` is S (lead moved out of S).
	Both are dated by `to_date` (the moment the transition happened).
	"""
	SCL = DocType("CRM Status Change Log")
	Lead = DocType("CRM Lead")
	# `from` is a Python keyword, so the column must be reached via getattr
	# (Frappe's query builder resolves any attribute access to a column).
	scl_from = getattr(SCL, "from")

	base_cond = (
		(SCL.parenttype == "CRM Lead")
		& (SCL.to.isnotnull())
		& (SCL.to != "")
		& (Date(SCL.to_date).between(from_date, to_date))
	)

	entered_q = (
		frappe.qb.from_(SCL)
		.join(Lead)
		.on(SCL.parent == Lead.name)
		.select(SCL.to.as_("stage"), Count("*").as_("count"))
		.where(base_cond)
		.groupby(SCL.to)
	)
	exited_q = (
		frappe.qb.from_(SCL)
		.join(Lead)
		.on(SCL.parent == Lead.name)
		.select(scl_from.as_("stage"), Count("*").as_("count"))
		.where(base_cond & (scl_from.isnotnull()) & (scl_from != ""))
		.groupby(scl_from)
	)
	if user:
		entered_q = entered_q.where(Lead.lead_owner == user)
		exited_q = exited_q.where(Lead.lead_owner == user)

	stages = {}
	for row in entered_q.run(as_dict=True):
		stages.setdefault(row.stage, {"entered": 0, "exited": 0})["entered"] = row.count or 0
	for row in exited_q.run(as_dict=True):
		stages.setdefault(row.stage, {"entered": 0, "exited": 0})["exited"] = row.count or 0

	data = [
		{"stage": stage, "entered": vals["entered"], "exited": vals["exited"]}
		for stage, vals in stages.items()
	]
	# Busiest stages first.
	data.sort(key=lambda r: r["entered"] + r["exited"], reverse=True)

	return {
		"data": data,
		"title": _("Status changes by stage"),
		"subtitle": _("How many leads entered and exited each stage"),
		"xAxis": {
			"title": _("Stage"),
			"key": "stage",
			"type": "category",
		},
		"yAxis": {"title": _("Leads")},
		"series": [
			{"name": "entered", "type": "bar"},
			{"name": "exited", "type": "bar"},
		],
	}
