"""Cross-doctype quick search for the Cmd-K command palette.

One whitelisted endpoint that substring-searches the records a rep reaches for
by name / phone / email / address across CRM Lead, Contact and CRM Buyer, and
returns a uniform, route-ready shape. Candidate fields are guarded with
has_field so custom fields (e.g. property_address) are used only where present
and a pre-provision site never errors. Final fuzzy ranking happens client-side
with the same scorer the palette uses for commands.
"""

import frappe
from frappe import _

# doctype -> (candidate search fields, extra fields to fetch for display)
_SOURCES = [
	{
		"doctype": "CRM Lead",
		"route": "Lead",
		"param": "leadId",
		"title": "lead_name",
		"search": [
			"lead_name",
			"first_name",
			"last_name",
			"mobile_no",
			"phone",
			"email",
			"organization",
			"property_address",
			"property_city",
			"property_state",
		],
		"display": ["lead_name", "mobile_no", "phone", "email", "status"],
		"subtitle": ["property_address", "mobile_no", "phone", "email"],
	},
	{
		"doctype": "CRM Buyer",
		"route": "Buyer",
		"param": "buyerId",
		"title": "buyer_name",
		"search": ["buyer_name", "phone", "email", "first_name", "last_name"],
		"display": ["buyer_name", "phone", "email"],
		"subtitle": ["phone", "email"],
	},
	{
		"doctype": "Contact",
		"route": "Contact",
		"param": "contactId",
		"title": "full_name",
		"search": ["full_name", "first_name", "last_name", "email_id", "mobile_no", "phone"],
		"display": ["full_name", "email_id", "mobile_no"],
		"subtitle": ["email_id", "mobile_no", "phone"],
	},
]


@frappe.whitelist()
def search(query, limit=8):
	"""Substring-search records across the palette's source doctypes.

	Returns a flat list of {doctype, name, label, description, route, param}.
	The frontend re-ranks with its fuzzy scorer, so ordering here only needs to
	surface the right candidates (LIKE %query% on each usable field).
	"""
	query = (query or "").strip()
	if len(query) < 2:
		return []

	try:
		limit = min(int(limit), 20)
	except (TypeError, ValueError):
		limit = 8

	like = f"%{query}%"
	results = []

	for src in _SOURCES:
		doctype = src["doctype"]
		if not frappe.db.exists("DocType", doctype):
			continue
		# permission check — skip a doctype the user can't read
		if not frappe.has_permission(doctype, "read"):
			continue

		meta = frappe.get_meta(doctype)
		search_fields = [f for f in src["search"] if meta.has_field(f)]
		if not search_fields:
			continue

		fetch = list(
			dict.fromkeys(
				["name"]
				+ [f for f in src["display"] if meta.has_field(f)]
				+ [f for f in src["subtitle"] if meta.has_field(f)]
			)
		)

		try:
			rows = frappe.get_list(
				doctype,
				or_filters=[[doctype, f, "like", like] for f in search_fields],
				fields=fetch,
				limit_page_length=limit,
				order_by="modified desc",
				ignore_permissions=False,
			)
		except frappe.PermissionError:
			continue

		title_field = src["title"] if meta.has_field(src["title"]) else "name"
		for row in rows:
			label = row.get(title_field) or row.get("name")
			subtitle = ""
			for f in src["subtitle"]:
				if row.get(f):
					subtitle = row.get(f)
					break
			results.append(
				{
					"doctype": doctype,
					"name": row.get("name"),
					"label": label,
					"description": subtitle,
					"route": src["route"],
					"param": src["param"],
					"group": _(doctype),
				}
			)

	return results
