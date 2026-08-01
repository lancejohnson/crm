"""Parse a fully-signed contract into the lead's fields (pi, on the Mac mini).

Flow: DocuSeal fires → `crm.api.agreement.docuseal_webhook` refetches the
submission and saves the CRM Esign Agreement row → if the envelope is now fully
signed, we POST a *trigger* to a listener on the Mac mini (Tailscale Funnel
URL). The listener fetches the agreement + signed PDF back out of this CRM,
runs a one-shot `pi` over the PDF, and posts what it extracted to
`write_agreement_fields`.

Four design points that are load-bearing:

* **The push carries an ID, not a payload.** The Funnel URL is public, so the
  request body must never reach the model — anything attacker-supplied would
  otherwise land in an LLM prompt on a machine with a shell. The mini
  re-fetches everything authoritative from here with its own credentials, so a
  forged trigger can at worst cause a real agreement to be re-read.

* **The field map lives here, not on the mini.** `get_agreement_for_parse`
  returns it next to the lead's current values, so the prompt is built from
  server-side truth: adding a field later is a change in THIS file with no
  redeploy on the mini.

* **Writes go through `doc.save()`, not `db.set_value`** — deliberately the
  opposite of the tax-pull/first-call pattern. We *want* the Version row: it's
  what puts "changed Acq Price from … to …" on the lead's activity timeline,
  and that timeline is the entire audit trail for this feature.

* **One agreement parses once** (`parsed_at`). An amendment arrives as its own
  agreement row, so it parses on its own and correctly overwrites the price or
  closing date — while a re-delivered webhook for an already-parsed contract
  can't clobber a human's later correction.

Cancellations are deliberately NOT parsed: the DocuSeal sync already tracks the
document, and clearing real fields on an LLM read of a cancellation is the one
failure here that loses data instead of just being wrong.
"""

import json

import frappe
import requests
from frappe import _
from frappe.utils import getdate, now_datetime

from crm.api.agreement import AGREEMENT_DOCTYPE, _is_completed

# --------------------------------------------------------------------------- #
# the field map — single source of truth for what a contract may write
# --------------------------------------------------------------------------- #
# `hint` is fed to the model verbatim, so it carries the acquisition-vs-dispo
# distinction that trips people up here: this CRM runs the whole lifecycle on
# CRM Lead, so buy-side and sell-side fields sit side by side on one record.
PARSE_FIELDS = {
	"acq_price": {
		"type": "currency",
		"label": "Acquisition price",
		"hint": (
			"The price WE (the buyer) pay the seller for the property, per this "
			"contract. Not the seller's asking price, not a list price, not an "
			"assignment fee."
		),
	},
	"dd_expiration_date": {
		"type": "date",
		"label": "DD expiration date",
		"hint": (
			"The date OUR due-diligence / inspection / feasibility period ends. "
			"Often expressed as 'N days from the Effective Date' — if so, compute "
			"the actual calendar date from the effective/binding agreement date."
		),
	},
	"closing_date": {
		"type": "date",
		"label": "Closing date",
		"hint": (
			"The date the purchase is scheduled to close. If expressed as 'on or "
			"before <date>', use that date."
		),
	},
	"property_address": {
		"type": "text",
		"label": "Property address",
		"hint": (
			"Street address only (no city/state/zip). Only report this if the "
			"contract's address clearly differs from what the CRM already has."
		),
	},
	"property_city": {"type": "text", "label": "Property city", "hint": "City only."},
	"property_state": {"type": "text", "label": "Property state", "hint": "2-letter state code."},
	"property_zip": {"type": "text", "label": "Property ZIP", "hint": "5-digit ZIP."},
}

# Sanity bounds. A parse outside these is rejected outright rather than written:
# a mis-read decimal or a year pulled off a form's copyright line is the
# realistic failure, and both land far outside these ranges.
MAX_PRICE = 100_000_000
MIN_YEAR = 2000
MAX_YEAR = 2100

# How far back the catch-up sweep looks when the listener restarts.
CATCHUP_DAYS = 30


# --------------------------------------------------------------------------- #
# push trigger (CRM → mini)
# --------------------------------------------------------------------------- #
def notify_mini(agr):
	"""POST the agreement id to the mini's listener, if this envelope is signed.

	Called from `docuseal_webhook`. Never raises: a signed contract must not be
	held up by the parser being unreachable — the listener's start-up catch-up
	sweep picks up anything missed while it was down.
	"""
	if not _is_completed(agr):
		return
	if agr.get("is_archived"):
		return
	if frappe.db.has_column(AGREEMENT_DOCTYPE, "parsed_at") and agr.get("parsed_at"):
		return

	url = (frappe.conf.get("contract_parser_url") or "").strip()
	secret = (frappe.conf.get("contract_parser_secret") or "").strip()
	if not url or not secret:
		return

	requests.post(
		url,
		headers={"X-Parser-Secret": secret, "Content-Type": "application/json"},
		json={"agreement": agr.get("name")},
		timeout=10,
	)


# --------------------------------------------------------------------------- #
# read side (mini → CRM)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def get_agreement_for_parse(agreement: str):
	"""Everything the mini needs to build its prompt, from server-side truth."""
	if not frappe.db.exists(AGREEMENT_DOCTYPE, agreement):
		frappe.throw(_("Agreement not found"), frappe.DoesNotExistError)

	wanted = ["name", "lead", "template_title", "agreement_status", "signed_count", "total_signers"]
	for optional in ("parsed_at", "parse_status", "is_archived"):
		if frappe.db.has_column(AGREEMENT_DOCTYPE, optional):
			wanted.append(optional)
	agr = frappe.db.get_value(AGREEMENT_DOCTYPE, agreement, wanted, as_dict=True)

	if not agr.lead or not frappe.has_permission("CRM Lead", "read", agr.lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	lead = frappe.db.get_value(
		"CRM Lead", agr.lead, ["name", "lead_name"] + list(PARSE_FIELDS), as_dict=True
	)

	return {
		"agreement": agr.name,
		"lead": agr.lead,
		"lead_name": lead.get("lead_name"),
		"template_title": agr.get("template_title"),
		"is_signed": _is_completed(agr),
		"already_parsed": bool(agr.get("parsed_at")),
		# The prompt is built from these two, so a field added above ships to the
		# mini on the next trigger with nothing to redeploy there.
		"fields": PARSE_FIELDS,
		"current": {k: lead.get(k) for k in PARSE_FIELDS},
	}


@frappe.whitelist()
def list_unparsed_agreements(days: int = CATCHUP_DAYS):
	"""Signed-but-unparsed agreements — the listener's start-up catch-up sweep.

	This is the durability backstop for the push (mini rebooting for an OS
	update, listener crash-looping, a dropped POST). It runs once on startup,
	NOT on a timer: there is no steady-state polling in this feature.
	"""
	if not frappe.db.has_column(AGREEMENT_DOCTYPE, "parsed_at"):
		return []

	filters = {"parsed_at": ["is", "not set"], "creation": [">", frappe.utils.add_days(None, -abs(int(days)))]}
	if frappe.db.has_column(AGREEMENT_DOCTYPE, "is_archived"):
		filters["is_archived"] = 0

	rows = frappe.get_all(
		AGREEMENT_DOCTYPE,
		filters=filters,
		fields=["name", "lead", "agreement_status", "signed_count", "total_signers"],
		order_by="creation desc",
		limit_page_length=200,
	)
	# `_is_completed` is a Python rule (status OR all-signers-signed), not a
	# column, so the signed test happens here rather than in the query.
	return [r.name for r in rows if r.lead and _is_completed(r)]


# --------------------------------------------------------------------------- #
# write side (mini → CRM)
# --------------------------------------------------------------------------- #
def _coerce(fieldname, raw):
	"""Validate + normalize one extracted value. Returns None to skip the field."""
	spec = PARSE_FIELDS[fieldname]
	if raw is None:
		return None
	if isinstance(raw, str) and not raw.strip():
		return None

	kind = spec["type"]

	if kind == "currency":
		if isinstance(raw, str):
			raw = raw.replace("$", "").replace(",", "").strip()
		try:
			val = float(raw)
		except (TypeError, ValueError):
			raise ValueError(f"{fieldname}: {raw!r} is not a number")
		if val <= 0 or val > MAX_PRICE:
			raise ValueError(f"{fieldname}: {val} is outside the plausible range")
		return val

	if kind == "date":
		try:
			d = getdate(raw)
		except Exception:
			raise ValueError(f"{fieldname}: {raw!r} is not a date")
		if not (MIN_YEAR <= d.year <= MAX_YEAR):
			raise ValueError(f"{fieldname}: {d} is outside the plausible range")
		return d.isoformat()

	return str(raw).strip()[:140]


@frappe.whitelist()
def write_agreement_fields(agreement: str, values, note: str = None):
	"""Write extracted values onto the lead + stamp the agreement as parsed.

	`values` is the model's JSON: {fieldname: value}. Unknown fieldnames are
	rejected (not silently dropped) — a model inventing a field name means the
	prompt and the map have drifted, and that should be loud.
	"""
	if isinstance(values, str):
		values = json.loads(values or "{}")
	if not isinstance(values, dict):
		frappe.throw(_("values must be an object"))

	if not frappe.db.exists(AGREEMENT_DOCTYPE, agreement):
		frappe.throw(_("Agreement not found"), frappe.DoesNotExistError)
	agr = frappe.get_doc(AGREEMENT_DOCTYPE, agreement)
	if not agr.lead or not frappe.has_permission("CRM Lead", "write", agr.lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	unknown = [k for k in values if k not in PARSE_FIELDS]
	if unknown:
		frappe.throw(_("Unknown field(s): {0}").format(", ".join(sorted(unknown))))

	cleaned, rejected = {}, {}
	for k, raw in values.items():
		try:
			v = _coerce(k, raw)
		except ValueError as e:
			rejected[k] = str(e)
			continue
		if v is not None:
			cleaned[k] = v

	# Apply through save() so Frappe writes a Version row — that is what renders
	# as "changed Acq Price from … to …" on the lead's activity timeline.
	written = {}
	if cleaned:
		lead = frappe.get_doc("CRM Lead", agr.lead)
		for k, v in cleaned.items():
			before = lead.get(k)
			# Compare as strings: Currency comes back as Decimal, Date as date.
			if str(before or "") == str(v or ""):
				continue
			lead.set(k, v)
			written[k] = {"from": str(before or ""), "to": str(v)}
		if written:
			lead.save()

	_stamp(agr, "ok" if not rejected else "partial", {
		"written": written,
		"rejected": rejected,
		"skipped_unchanged": sorted(set(cleaned) - set(written)),
		"note": (note or "")[:2000],
	})

	return {"ok": True, "written": written, "rejected": rejected}


@frappe.whitelist()
def mark_parse_failed(agreement: str, error: str = None):
	"""Record a parse that could not produce values (bad PDF, model error)."""
	if not frappe.db.exists(AGREEMENT_DOCTYPE, agreement):
		frappe.throw(_("Agreement not found"), frappe.DoesNotExistError)
	agr = frappe.get_doc(AGREEMENT_DOCTYPE, agreement)
	_stamp(agr, "error", {"error": (error or "")[:2000]})
	return {"ok": True}


def _stamp(agr, status, result):
	"""Record the outcome on the agreement row (best-effort, never fatal).

	Guarded on the columns existing so the app code runs on a site that hasn't
	had `setup_agreement.py` re-run yet — the parse still works, it just doesn't
	remember, which is the right way round.
	"""
	if not frappe.db.has_column(AGREEMENT_DOCTYPE, "parsed_at"):
		return
	try:
		frappe.db.set_value(
			AGREEMENT_DOCTYPE,
			agr.name,
			{
				"parsed_at": now_datetime(),
				"parse_status": status,
				"parse_result": json.dumps(result)[:100000],
			},
			update_modified=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "contract parse stamp failed")
