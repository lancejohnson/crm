"""Property tax / owner info pulled from BatchData (per-lead, $0.10 a pull).

A user clicks **Fetch Tax Info** on a lead → the `pull-tax-info` server script
(ops repo, `../frappe-crm-deploy`) hits BatchData's Property Search endpoint with
the Infisical-held API key and stores the raw property record on a new
**CRM Property Tax Pull** doc. The server-script sandbox can't do rich parsing or
`publish_realtime`, so the *interesting* work happens here, in the app-code
`after_insert` hook:

  - parse the raw BatchData property record into typed columns on the pull doc,
  - write the headline fields (owner, APN, tax status, annual tax, assessed value)
    back onto the CRM Lead so they show in the Property Details sidebar,
  - broadcast a `crm_tax_pull` realtime event so the open Lead's Activity feed +
    Tax Info card refresh live (mirrors the `quo_message` / `crm_task_update`
    pattern — site-wide, `after_commit=True`).

Field paths come from BatchData's OpenAPI (Property Search response). The
`tax`/`assessment` blocks only populate once the "Core Property Data (Tax
Assessor)" product is enabled on the account; until then owner/APN/value/tax-
status-flags still come through and the assessor columns simply stay empty.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt

TAX_PULL_DOCTYPE = "CRM Property Tax Pull"

# Headline fields mirrored onto the CRM Lead (only written when BatchData returns
# a value — never blanks out existing lead data). Guarded by has_field so the app
# still runs before the ops repo adds these custom fields.
LEAD_WRITEBACK_FIELDS = (
	"apn",
	"property_owner",
	"tax_status",
	"annual_tax",
	"assessed_value",
	"last_tax_pull_at",
	"last_tax_pull_by",
)


def _num(value):
	"""BatchData sends assessor money as ints; treat 0 as 'no data', not $0."""
	try:
		n = flt(value)
	except (TypeError, ValueError):
		return None
	return n or None


def _parse_property(p: dict) -> dict:
	"""Flatten a BatchData property record into our pull-doc columns."""
	owner = p.get("owner") or {}
	ids = p.get("ids") or {}
	tax = p.get("tax") or {}
	assessment = p.get("assessment") or {}
	valuation = p.get("valuation") or {}
	quick = p.get("quickLists") or {}

	delinquent_year = tax.get("taxDelinquentYear")
	# Currency/Int columns on the pull doc are NOT NULL DEFAULT 0 — store 0 (not
	# None) for "no data". The lead writeback still treats 0 as falsy and skips it.
	parsed = {
		"matched": 1 if (owner.get("fullName") or ids.get("apn")) else 0,
		"owner_name": owner.get("fullName"),
		"owner_occupied": 1 if owner.get("ownerOccupied") else 0,
		"owner_status_type": owner.get("ownerStatusType"),
		"apn": ids.get("apn"),
		"tax_id": ids.get("taxId"),
		"annual_tax": _num(tax.get("taxAmount")) or 0,
		"tax_year": int(tax.get("taxYear") or 0),
		"tax_delinquent_year": int(delinquent_year or 0),
		"tax_default": 1 if quick.get("taxDefault") else 0,
		"assessed_value": _num(assessment.get("totalAssessedValue")) or 0,
		"estimated_value": _num(valuation.get("estimatedValue")) or 0,
		"tax_status": _derive_tax_status(tax, assessment, quick),
	}
	return parsed


def _derive_tax_status(tax: dict, assessment: dict, quick: dict) -> str:
	"""Human-readable tax standing from the flags BatchData returns.

	Order matters: a delinquency/default signal trumps a 'current' read. When the
	Tax Assessor product is off (no tax/assessment data at all) we fall back to
	the foreclosure quick-list flags, else report status unknown.
	"""
	delinquent_year = tax.get("taxDelinquentYear")
	if delinquent_year:
		return _("Tax delinquent since {0}").format(delinquent_year)
	if quick.get("taxDefault"):
		return _("In tax default")
	if quick.get("preforeclosure") or quick.get("noticeOfDefault"):
		return _("Pre-foreclosure")
	# Has assessor data and no delinquency signal → current.
	if tax.get("taxAmount") or tax.get("taxYear") or assessment.get("totalAssessedValue"):
		year = tax.get("taxYear")
		return _("Taxes current (as of {0})").format(year) if year else _("Taxes current")
	return _("Unknown")


def on_tax_pull_insert(doc, method=None):
	"""after_insert hook on CRM Property Tax Pull — parse + writeback + realtime."""
	try:
		record = json.loads(doc.get("raw_response") or "{}")
	except (ValueError, TypeError):
		record = {}

	parsed = _parse_property(record if isinstance(record, dict) else {})

	# The server script can't reliably stamp a time in the sandbox; fall back to
	# the doc's own creation timestamp so pulled_at is always populated.
	pulled_at = doc.get("pulled_at") or doc.creation
	parsed["pulled_at"] = pulled_at

	# 1) Persist the flattened columns on the pull doc itself.
	frappe.db.set_value(doc.doctype, doc.name, parsed, update_modified=False)

	# 2) Mirror the headline fields onto the lead (only non-empty values).
	if doc.get("lead") and frappe.db.exists("CRM Lead", doc.lead):
		lead_meta = frappe.get_meta("CRM Lead")
		writeback = {}
		if parsed.get("apn") and lead_meta.has_field("apn"):
			writeback["apn"] = parsed["apn"]
		if parsed.get("owner_name") and lead_meta.has_field("property_owner"):
			writeback["property_owner"] = parsed["owner_name"]
		if parsed.get("tax_status") and lead_meta.has_field("tax_status"):
			writeback["tax_status"] = parsed["tax_status"]
		if parsed.get("annual_tax") and lead_meta.has_field("annual_tax"):
			writeback["annual_tax"] = parsed["annual_tax"]
		if parsed.get("assessed_value") and lead_meta.has_field("assessed_value"):
			writeback["assessed_value"] = parsed["assessed_value"]
		if lead_meta.has_field("last_tax_pull_at"):
			writeback["last_tax_pull_at"] = pulled_at
		if lead_meta.has_field("last_tax_pull_by"):
			writeback["last_tax_pull_by"] = doc.get("pulled_by") or doc.owner
		if writeback:
			frappe.db.set_value("CRM Lead", doc.lead, writeback)

	# 3) Live-refresh every open client (Activity feed + Tax Info card). Site-wide,
	# after commit so a listener's reload can't read pre-commit rows.
	if doc.get("lead"):
		frappe.publish_realtime(
			"crm_tax_pull",
			{"reference_doctype": "CRM Lead", "reference_docname": doc.lead},
			after_commit=True,
		)


@frappe.whitelist()
def get_tax_pulls(lead: str):
	"""Tax-info pulls for a lead, most recent first (sidebar card + timeline)."""
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead not found"), frappe.DoesNotExistError)
	if not frappe.has_permission("CRM Lead", "read", lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.db.exists("DocType", TAX_PULL_DOCTYPE):
		return []

	pulls = frappe.get_all(
		TAX_PULL_DOCTYPE,
		filters={"lead": lead},
		fields=[
			"name",
			"pulled_by",
			"pulled_at",
			"creation",
			"cost",
			"source",
			"matched",
			"owner_name",
			"owner_occupied",
			"owner_status_type",
			"apn",
			"tax_id",
			"annual_tax",
			"tax_year",
			"tax_delinquent_year",
			"tax_default",
			"tax_status",
			"assessed_value",
			"estimated_value",
		],
		order_by="creation desc",
	)
	for pull in pulls:
		pull["pulled_by_name"] = frappe.get_cached_value("User", pull.pulled_by, "full_name") if pull.pulled_by else None
	return pulls
