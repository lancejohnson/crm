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
from frappe.desk.form.assign_to import add as assign_todo

LEAD = "CRM Lead"
VIEW = "CRM View Settings"

MAX_ROWS_PER_CALL = 500
MAX_LIST_NAME = 100

# NOTE: promotion to the main board is deliberately MANUAL only.
#
# An earlier version auto-promoted a lead as soon as its status left "New".
# That was wrong for how these lists are actually worked: the callers run a
# vendor batch through many rounds of follow-up ON the import board, moving
# leads through statuses the whole time, and none of that means the lead is
# ready for the main board. So status changes never un-park a lead — someone
# has to press the button (unhide_leads, from the import view's banner or the
# lead's own "Add to main board" action).

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


def _dump(value) -> str:
	"""ensure_ascii=False is REQUIRED, not cosmetic.

	import_lists is stored as JSON text and matched with a raw SQL LIKE built
	from the list name. Default json.dumps escapes non-ASCII, so a list called
	"LeadPack — Jun 2026" is stored as "LeadPack \\u2014 Jun 2026" while the
	filter looks for the literal em-dash — they never match, and every lead in
	the list becomes invisible to its own view. Same trap for any accented name.
	"""
	return json.dumps(value, ensure_ascii=False)


def _valid_email(value: str) -> bool:
	"""Vendor sheets routinely put junk in the Email column — the ISTL LeadPack
	ships semicolon-separated alt PHONE numbers there. Frappe rejects those at
	insert and would fail the whole row, losing a perfectly good lead over a
	field we don't even need, so an unusable address is dropped instead."""
	return bool(re.fullmatch(r"[^@\s;,]+@[^@\s;,]+\.[A-Za-z]{2,}", (value or "").strip()))


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

	# Uppercase LIKE, matching what the filter popover itself writes — its
	# operator map is keyed on the uppercase form, and a lowercase one used to
	# come back as an undefined operator that broke the whole popover.
	filters = {"import_lists": ["LIKE", f'%"{list_name}"%']}
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
def import_leads(
	list_name: str,
	rows,
	source: str | None = None,
	lead_owner: str | None = None,
	assign_to=None,
	assign_offset: int = 0,
):
	"""Create/tag a batch of leads under `list_name`.

	rows: list of dicts already keyed by CRM Lead fieldname (the frontend does
	the CSV parse + column mapping, so the user can eyeball it first).

	assign_to: optional list of users to split the NEW leads between, evenly and
	deterministically (round-robin). `assign_offset` carries the rotation across
	chunked calls so a 500-row import split between two reps doesn't restart at
	rep #1 every chunk and hand one of them everything.

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

	assignees = frappe.parse_json(assign_to) if assign_to else []
	assignees = [u for u in assignees if frappe.db.exists("User", u)]
	assign_i = int(assign_offset or 0)

	created, matched, skipped, errors = [], [], 0, []
	assigned_counts = {u: 0 for u in assignees}
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

		if row.get("email") and not _valid_email(row["email"]):
			dropped_email = row.pop("email")
			# Keep it visible rather than silently binning it: on these sheets it's
			# usually alternate numbers, which is exactly what a caller wants.
			note = f"Other contact: {dropped_email}"
			if "lead_summary" in allowed:
				row["lead_summary"] = (
					f"{row['lead_summary']} · {note}" if row.get("lead_summary") else note
				)

		# Put the address block straight even when the sheet didn't. Vendor packs
		# mix layouts within one file — the Jun 2026 LeadPack landed 88 whole
		# street addresses in the ZIP column and 31 seller emails in Property
		# Address / Property City — and column mapping alone can't catch that,
		# because it varies row by row. `_repair_one` only ever moves a value it
		# can positively identify (and restores ZIPs whose leading zero the
		# spreadsheet ate), so a correctly-shaped row passes through untouched.
		row.update({k: v for k, v in _repair_one(row).items() if k in allowed})

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

			# Round-robin owner. This MUST be set as lead_owner, not just bolted
			# on afterwards: CRM Lead.after_insert assigns lead_owner, and that
			# field otherwise falls back to a site default (Dennis today), so the
			# lead would end up assigned to BOTH him and the intended caller.
			turn_user = None
			if assignees:
				turn_user = assignees[assign_i % len(assignees)]
				assign_i += 1
				row["lead_owner"] = turn_user

			doc = frappe.new_doc(LEAD)
			doc.update(row)
			if tag_lists:
				doc.import_lists = _dump([list_name])
			if tag_hidden:
				doc.import_hidden = 1
			doc.insert(ignore_permissions=True)

			if turn_user:
				# after_insert normally assigns lead_owner already; only step in if
				# it didn't, and never double-assign.
				current = frappe.parse_json(doc.get("_assign") or "[]")
				if turn_user not in current:
					try:
						assign_todo(
							{"assign_to": [turn_user], "doctype": LEAD, "name": doc.name},
							ignore_permissions=True,
						)
					except Exception:
						frappe.log_error(
							f"lead_import assign {doc.name} -> {turn_user}",
							frappe.get_traceback(),
						)
				assigned_counts[turn_user] = assigned_counts.get(turn_user, 0) + 1

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
		"assigned": assigned_counts,
		"assign_offset": assign_i,
	}


def _add_to_list(lead_name: str, list_name: str):
	current = _load_list_names(frappe.db.get_value(LEAD, lead_name, "import_lists"))
	if list_name in current:
		return
	current.append(list_name)
	# db.set_value, not doc.save: tagging must not fire status/assignment side
	# effects or bump `modified` into the rep's "recently touched" view.
	frappe.db.set_value(LEAD, lead_name, "import_lists", _dump(current), update_modified=False)


# ------------------------------------------------------------------ reads


@frappe.whitelist()
def get_list_summary(list_name: str):
	"""Counts for the promote banner on an open import view."""
	if not frappe.db.has_column(LEAD, "import_lists"):
		return {"total": 0, "parked": 0}
	like = {"import_lists": ["like", f'%"{list_name}"%']}
	total = frappe.db.count(LEAD, like)
	parked = (
		frappe.db.count(LEAD, {**like, "import_hidden": 1})
		if frappe.db.has_column(LEAD, "import_hidden")
		else 0
	)
	return {"list_name": list_name, "total": total, "parked": parked}


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


# ---------------------------------------------------------------- repair
#
# The Jun 2026 LeadPack came in with the address block scrambled on part of the
# batch: 88 leads had the whole street address sitting in `property_zip` with
# `property_address` empty (or holding the seller's EMAIL), and every
# leading-zero ZIP (MA/NJ/RI/CT) had arrived as a 4-digit number because the
# source cells were numeric.
#
# The damage is self-describing — a full address carries its own city/state/ZIP
# — so it can be undone deterministically rather than re-imported. Everything
# below only ever moves a value that is provably in the wrong field; a value
# that already looks right for its field is never touched.

# "1218 Tobin Ct, Waukegan, IL 60085" / "56 Mary Ln Apt 5, Bridgewater, MA 02324"
FULL_ADDR_RE = re.compile(
	r"^(?P<street>.+?),\s*(?P<city>[^,]+),\s*(?P<state>[A-Za-z]{2})\.?\s+(?P<zip>\d{5})(?:-\d{4})?$"
)
# Some rows carry a Google-style ", USA" tail ("Mill St, Marion, MA 02738, USA")
# which would otherwise defeat the match above and strand the address.
COUNTRY_TAIL_RE = re.compile(r",\s*(usa|us|united states)\.?$", re.I)
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")

ADDRESS_FIELDS = (
	"property_address",
	"property_city",
	"property_state",
	"property_zip",
	"property_county",
)

# Placeholders vendors use for "we don't have this".
NULL_TEXT = {"not provided", "n/a", "na", "none", "null", "-", "--"}


def _looks_like_zip(value: str) -> bool:
	return bool(ZIP_RE.fullmatch(value))


def _looks_like_street(value: str) -> bool:
	"""House-number-led ("7005 156th Ave NW") or comma-separated.

	Deliberately strict, because this is what decides whether a value may be
	lifted out of the City column — and a bare town name ("Waukegan") belongs
	there, so it must not qualify.
	"""
	return bool(re.match(r"^\d+\S*\s+\S", value)) or "," in value


def _pad_zip(value: str) -> str:
	"""02324 arrives as 2324 whenever the sheet stored the ZIP as a number.

	Only 3- and 4-digit runs are padded: those are unambiguous (no US ZIP has
	fewer than 5 digits), whereas a longer run is something else entirely and is
	left alone for a human to look at.
	"""
	if re.fullmatch(r"\d{3,4}", value):
		return value.zfill(5)
	return value


def _repair_one(doc: dict) -> dict:
	"""Return {field: corrected_value} for one lead — empty when nothing is wrong.

	The one rule this must never break: a value is only ever cleared out of a
	field if it has been written somewhere else, or it is a placeholder. A cell
	we can't classify stays exactly where it is for a human to look at — a wrong
	address is recoverable, a deleted one isn't.
	"""
	vals = {f: str(doc.get(f) or "").strip() for f in ADDRESS_FIELDS}
	desired = dict(vals)
	email = str(doc.get("email") or "").strip()
	summary = str(doc.get("lead_summary") or "").strip()
	new_email, spare_emails = None, []

	# 1. An email that landed in an address field. Rescue it onto `email` when
	#    the lead has none, then clear it out of where it doesn't belong. A
	#    second address the lead can't hold is parked in the summary rather than
	#    binned (same as the importer does with junk Email cells).
	for f in ADDRESS_FIELDS:
		v = desired[f]
		if v and _valid_email(v):
			if not email and not new_email:
				new_email = v.lower()
			else:
				spare_emails.append(v)
			desired[f] = ""

	# 2. Drop vendor placeholders so they don't survive as a "value".
	for f in ADDRESS_FIELDS:
		if desired[f].lower() in NULL_TEXT:
			desired[f] = ""

	# 3. A complete address is authoritative wherever it turns up: it re-seeds
	#    address/city/state/ZIP in one go. Prefer the one already in
	#    property_address so a correct lead is a no-op.
	match, src, full = None, None, None
	for f in ("property_address", "property_zip", "property_city", "property_county"):
		candidate = COUNTRY_TAIL_RE.sub("", desired[f]).strip()
		m = FULL_ADDR_RE.match(candidate)
		if m:
			match, src, full = m, f, candidate
			break

	if match:
		if src != "property_address":
			desired[src] = ""
		desired["property_address"] = full
		city = match.group("city").strip()
		state = match.group("state").upper()
		zip_code = match.group("zip")
		# The parsed parts win over a blank or a demonstrably wrong cell only —
		# a city the team may have corrected by hand is left as it is.
		if not desired["property_city"] or desired["property_city"] == full:
			desired["property_city"] = city
		if not desired["property_state"]:
			desired["property_state"] = state
		if not _looks_like_zip(_pad_zip(desired["property_zip"])):
			desired["property_zip"] = zip_code
	elif not desired["property_address"]:
		# No parseable full address, but a street line may still be sitting in
		# the ZIP or City column with nothing in the address field. Anything in
		# the ZIP column that isn't a ZIP is misfiled by definition; the City
		# column needs the stricter test so a real town name stays put.
		leftover = desired["property_zip"]
		if leftover and not _looks_like_zip(_pad_zip(leftover)):
			desired["property_address"] = leftover
			desired["property_zip"] = ""
		elif desired["property_city"] and _looks_like_street(desired["property_city"]):
			desired["property_address"] = desired["property_city"]
			desired["property_city"] = ""

	# 4. Restore a ZIP's stripped leading zero. Anything still left in there that
	#    isn't a ZIP is left alone — step 3 already moved out everything we could
	#    identify, so what remains is unknown, not junk.
	desired["property_zip"] = _pad_zip(desired["property_zip"])

	changes = {f: v for f, v in desired.items() if v != vals[f]}
	if new_email:
		changes["email"] = new_email
	if spare_emails:
		note = "Other contact: " + ", ".join(spare_emails)
		changes["lead_summary"] = f"{summary} · {note}" if summary else note
	return changes


@frappe.whitelist()
def repair_import_addresses(list_name: str | None = None, dry_run: int = 1, limit: int = 0):
	"""Move mis-filed address values back into the right fields on imported leads.

	Scoped to leads carrying an `import_lists` tag (optionally one list). Writes
	with `db.set_value(update_modified=False)` — no `doc.save`, so no status,
	assignment or realtime side-effects, and nothing jumps into anyone's
	"recently touched" view. Dry-run by default; returns a sample of the diffs.

	    bench execute crm.api.lead_import.repair_import_addresses \
	        --kwargs '{"list_name": "ISTL LeadPack — Jun 2026", "dry_run": 1}'
	"""
	_validate_access()
	if not _has("import_lists"):
		return {"scanned": 0, "changed": 0, "samples": []}

	filters = {"import_lists": ["is", "set"]}
	if list_name:
		filters = {"import_lists": ["like", f'%"{list_name}"%']}

	rows = frappe.get_all(
		LEAD,
		filters=filters,
		fields=["name", "email", "lead_summary", *ADDRESS_FIELDS],
		limit_page_length=int(limit) or 0,
		order_by="creation asc",
	)

	changed, samples = 0, []
	field_counts = {}
	for row in rows:
		changes = _repair_one(row)
		if not changes:
			continue
		changed += 1
		for f in changes:
			field_counts[f] = field_counts.get(f, 0) + 1
		if len(samples) < 15:
			samples.append(
				{
					"name": row["name"],
					"before": {f: row.get(f) for f in changes},
					"after": changes,
				}
			)
		if not int(dry_run):
			for field, value in changes.items():
				frappe.db.set_value(LEAD, row["name"], field, value, update_modified=False)

	if not int(dry_run):
		frappe.db.commit()

	return {
		"dry_run": bool(int(dry_run)),
		"scanned": len(rows),
		"changed": changed,
		"fields": field_counts,
		"samples": samples,
	}


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
