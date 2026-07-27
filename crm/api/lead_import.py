"""Bulk lead import — paste/CSV -> CRM Leads, grouped under a named list.

Why this exists: nearly every lead already arrives on its own (the iSpeedToLead
webhook). Every so often a vendor emails a batch instead — a "LeadPack" — and
that batch has to be workable as its own list WITHOUT burying the live board.

So an import does three things:

  1. Creates the leads we don't already have.
  2. TAGS every lead in the batch — newly created *and* already-existing — with
     the list name on `CRM Lead.import_lists` (a JSON array, so one lead can
     belong to several lists over time; mirrors CRM Buyer.metro_areas).
  3. Ensures a saved list view + kanban view filtered to that tag, so the batch
     is one click away from the Leads page.

Two separate flags, deliberately:

  * `import_lists`  — membership. Also set on matched existing leads, so the
    list view shows the whole batch, not just the new rows.
  * `import_hidden` — parking. Set ONLY on leads this import CREATED. That is
    what `crm.api.doc.get_data` reads to keep a fresh batch out of the main
    board/list. A lead already being worked that happens to appear in a
    LeadPack keeps its visibility — tagging must never make it vanish.

Dedupe is by phone (last 10 digits, format-insensitive) then email — the same
identity rule the DocuSeal adoption matcher uses. Re-importing the same pack is
therefore idempotent: it re-tags, it does not duplicate.

All writes are guarded by `has_column`, so this runs fine before the ops script
(../frappe-crm-deploy/scripts/setup_lead_import.py) adds the two custom fields.
"""

import json
import re

import frappe
from frappe import _

LEAD = "CRM Lead"
VIEW = "CRM View Settings"

MAX_ROWS_PER_CALL = 500
MAX_LIST_NAME = 100

# Never let a spreadsheet column write these, whatever the mapping says.
BLOCKED_FIELDS = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"naming_series",
	"converted",
	"lead_name",
	"import_lists",
	"import_hidden",
	"_assign",
	"_liked_by",
	"_comments",
	"_user_tags",
	"sla",
	"sla_status",
	"sla_creation",
	"response_by",
	"first_response_time",
	"first_responded_on",
}


# ---------------------------------------------------------------- helpers


def _has(field: str) -> bool:
	return frappe.db.has_column(LEAD, field)


def _digits(value) -> str:
	return re.sub(r"\D", "", str(value or ""))


def _phone_key(value) -> str:
	"""Last 10 digits — format-insensitive phone identity."""
	d = _digits(value)
	return d[-10:] if len(d) >= 10 else ""


def _email_key(value) -> str:
	return (str(value or "")).strip().lower()


def _clean(value) -> str:
	"""Spreadsheet cells arrive with float noise ('60085.0' for a ZIP,
	'713159.0' for a population) because xlsx stores every number as a double.
	Trim that back to an integer string, otherwise leave the text alone."""
	s = str(value if value is not None else "").strip()
	if re.fullmatch(r"-?\d+\.0+", s):
		s = s.split(".")[0]
	return s


def _load_list_names(raw) -> list:
	if not raw:
		return []
	try:
		parsed = json.loads(raw)
		return [str(x) for x in parsed] if isinstance(parsed, list) else []
	except (ValueError, TypeError):
		return []


def _validate_access():
	roles = frappe.get_roles()
	if frappe.session.user == "Administrator":
		return
	if any(r in roles for r in ("System Manager", "Sales Manager", "Sales User")):
		return
	frappe.throw(_("Not permitted to import leads."), frappe.PermissionError)


def _allowed_fields() -> set:
	meta = frappe.get_meta(LEAD)
	out = set()
	for df in meta.fields:
		if df.fieldname in BLOCKED_FIELDS:
			continue
		if df.fieldtype in ("Section Break", "Column Break", "Tab Break", "Table", "HTML"):
			continue
		out.add(df.fieldname)
	return out


# ------------------------------------------------------------------ views


def _ensure_views(list_name: str):
	"""A saved list view + kanban view scoped to this import list.

	The filter is a LIKE against the JSON array, quoted so "Pack 1" can't match
	"Pack 10" (same trick as get_buyers(metro=)).

	NOTE: CRM View Settings is `autoname: autoincrement`, so the row name is an
	integer and assigning doc.name is ignored — existence has to be checked on
	(label, dt, type), not by name, or a chunked import would create a fresh
	pair of views per chunk. The integer name is what the Leads route's
	`?view=` query param expects, so it's returned for the caller to link to.
	"""
	if not _has("import_lists"):
		return []

	filters = {"import_lists": ["like", f'%"{list_name}"%']}
	views = []

	for view_type, label in (("list", list_name), ("kanban", f"{list_name} (Board)")):
		existing = frappe.db.get_value(
			VIEW, {"label": label, "dt": LEAD, "type": view_type}, "name"
		)
		if existing:
			views.append({"name": existing, "label": label, "type": view_type})
			continue

		doc = frappe.new_doc(VIEW)
		doc.label = label
		doc.dt = LEAD
		doc.type = view_type
		doc.icon = "upload-cloud"
		doc.public = 1
		doc.pinned = 0
		# MUST be "" (not NULL): crm.api.views.get_views selects on
		# `user == "" OR user == session_user`, so a NULL-user view is invisible
		# to everyone, including its creator. "" is the global/user-less marker
		# (same convention as the global standard Kanban view).
		doc.user = ""
		doc.route_name = "Leads"
		doc.filters = json.dumps(filters)
		doc.order_by = "modified desc"
		if view_type == "kanban":
			doc.column_field = "status"
			doc.title_field = "lead_name"
			doc.kanban_fields = json.dumps(
				["mobile_no", "email", "property_address", "_assign", "_next_task_due"]
			)
		doc.insert(ignore_permissions=True)
		views.append({"name": doc.name, "label": label, "type": view_type})

	return views


# ----------------------------------------------------------------- import


@frappe.whitelist()
def import_leads(list_name: str, rows, source: str | None = None, lead_owner: str | None = None):
	"""Create/tag a batch of leads under `list_name`.

	rows: list of dicts already keyed by CRM Lead fieldname (the frontend does
	the CSV parse + column mapping, so the user can eyeball it first).
	Returns a summary the modal renders.
	"""
	_validate_access()

	list_name = (list_name or "").strip()
	if not list_name:
		frappe.throw(_("A list name is required."))
	if len(list_name) > MAX_LIST_NAME:
		frappe.throw(_("List name is too long."))

	rows = frappe.parse_json(rows) or []
	if not isinstance(rows, list):
		frappe.throw(_("Invalid rows payload."))
	if len(rows) > MAX_ROWS_PER_CALL:
		frappe.throw(_("Too many rows in one call (max {0}).").format(MAX_ROWS_PER_CALL))

	tag_lists = _has("import_lists")
	tag_hidden = _has("import_hidden")
	allowed = _allowed_fields()

	if source:
		# CRM Lead Source is `autoname: field:source_name`, so the row name IS the
		# source name and the field is `source_name` (not lead_source_name).
		source = source.strip()
		if source and not frappe.db.exists("CRM Lead Source", source):
			frappe.get_doc({"doctype": "CRM Lead Source", "source_name": source}).insert(
				ignore_permissions=True
			)

	# One pass over existing leads to build the dedupe index. Cheap (3 columns)
	# and far faster than a query per row.
	by_phone, by_email = {}, {}
	for lead in frappe.get_all(LEAD, fields=["name", "mobile_no", "phone", "email"], limit_page_length=0):
		for p in (lead.get("mobile_no"), lead.get("phone")):
			k = _phone_key(p)
			if k:
				by_phone.setdefault(k, lead["name"])
		k = _email_key(lead.get("email"))
		if k:
			by_email.setdefault(k, lead["name"])

	created, matched, skipped, errors = [], [], 0, []
	seen_in_batch = set()

	for idx, raw_row in enumerate(rows):
		if not isinstance(raw_row, dict):
			skipped += 1
			continue

		row = {}
		for key, value in raw_row.items():
			if key in allowed:
				v = _clean(value)
				if v:
					row[key] = v

		phone_k = _phone_key(row.get("mobile_no") or row.get("phone"))
		email_k = _email_key(row.get("email"))

		# A row with no name and no way to reach anyone isn't a lead.
		if not phone_k and not email_k and not (row.get("first_name") or row.get("last_name")):
			skipped += 1
			continue

		dedupe_k = phone_k or email_k
		if dedupe_k and dedupe_k in seen_in_batch:
			skipped += 1
			continue
		if dedupe_k:
			seen_in_batch.add(dedupe_k)

		existing = (by_phone.get(phone_k) if phone_k else None) or (
			by_email.get(email_k) if email_k else None
		)

		try:
			if existing:
				# Already ours — tag it into the list, but leave it visible and
				# don't overwrite a single field a rep may have curated.
				if tag_lists:
					_add_to_list(existing, list_name)
				matched.append(existing)
				continue

			if source and "source" in allowed:
				row.setdefault("source", source)
			if lead_owner and "lead_owner" in allowed:
				row.setdefault("lead_owner", lead_owner)

			doc = frappe.new_doc(LEAD)
			doc.update(row)
			if tag_lists:
				doc.import_lists = json.dumps([list_name])
			if tag_hidden:
				doc.import_hidden = 1
			doc.insert(ignore_permissions=True)

			created.append(doc.name)
			if phone_k:
				by_phone.setdefault(phone_k, doc.name)
			if email_k:
				by_email.setdefault(email_k, doc.name)
		except Exception as e:
			errors.append({"row": idx + 1, "error": str(e)[:200]})
			frappe.log_error(
				f"lead_import row {idx + 1} ({list_name})", frappe.get_traceback()
			)

	views = _ensure_views(list_name)
	frappe.db.commit()

	return {
		"list_name": list_name,
		"created": len(created),
		"matched": len(matched),
		"skipped": skipped,
		"errors": errors[:20],
		"error_count": len(errors),
		"views": views,
	}


def _add_to_list(lead_name: str, list_name: str):
	current = _load_list_names(frappe.db.get_value(LEAD, lead_name, "import_lists"))
	if list_name in current:
		return
	current.append(list_name)
	# db.set_value, not doc.save: tagging must not fire status/assignment side
	# effects or bump `modified` into the rep's "recently touched" view.
	frappe.db.set_value(LEAD, lead_name, "import_lists", json.dumps(current), update_modified=False)


# ------------------------------------------------------------------ reads


@frappe.whitelist()
def get_import_lists():
	"""Every import list with counts, newest first."""
	if not frappe.db.has_column(LEAD, "import_lists"):
		return []

	has_hidden = frappe.db.has_column(LEAD, "import_hidden")
	fields = ["name", "import_lists", "creation"] + (["import_hidden"] if has_hidden else [])
	rows = frappe.get_all(
		LEAD, filters={"import_lists": ["is", "set"]}, fields=fields, limit_page_length=0
	)

	buckets = {}
	for r in rows:
		for ln in _load_list_names(r.get("import_lists")):
			b = buckets.setdefault(ln, {"list_name": ln, "total": 0, "hidden": 0, "last": None})
			b["total"] += 1
			if has_hidden and r.get("import_hidden"):
				b["hidden"] += 1
			if not b["last"] or r["creation"] > b["last"]:
				b["last"] = r["creation"]

	return sorted(buckets.values(), key=lambda b: b["last"] or "", reverse=True)


@frappe.whitelist()
def unhide_leads(list_name: str | None = None, leads=None):
	"""Promote parked leads into the main board/list.

	Either the whole list (`list_name`) or specific `leads`."""
	_validate_access()
	if not frappe.db.has_column(LEAD, "import_hidden"):
		return {"updated": 0}

	names = frappe.parse_json(leads) if leads else None
	if not names:
		if not list_name:
			frappe.throw(_("Provide a list name or lead names."))
		names = [
			r["name"]
			for r in frappe.get_all(
				LEAD,
				filters={
					"import_lists": ["like", f'%"{list_name}"%'],
					"import_hidden": 1,
				},
				fields=["name"],
				limit_page_length=0,
			)
		]

	for n in names:
		frappe.db.set_value(LEAD, n, "import_hidden", 0, update_modified=False)
	frappe.db.commit()
	return {"updated": len(names)}


def apply_import_visibility(doctype: str, filters: dict):
	"""Park bulk-imported leads out of the default list/kanban.

	Called from crm.api.doc.get_data with the *merged* filter dict, before any
	query runs, so the exclusion reaches the list rows, the kanban columns and
	the total count alike.

	Opt out simply by filtering on either import field — which is exactly what
	the auto-created "<List name>" views do, so opening an import list shows it.
	"""
	if doctype != LEAD or not isinstance(filters, dict):
		return
	if "import_lists" in filters or "import_hidden" in filters:
		return
	if not frappe.db.has_column(LEAD, "import_hidden"):
		return
	filters["import_hidden"] = ["!=", 1]
