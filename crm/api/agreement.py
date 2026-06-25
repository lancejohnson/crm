"""E-sign agreements tracked per lead.

**DocuSeal** (current) — a user clicks **Create Purchase Agreement** on a lead →
`create_docuseal_agreement()` resolves the right DocuSeal template (Standard vs
Novation/+AIF × one/two sellers), prefills the buyer/seller fields, creates a
submission with `send_email:false`, stores a **CRM Esign Agreement** row
(`provider="docuseal"`) and hands back self-serve signing links. A DocuSeal
webhook (`docuseal_webhook`) keeps the row's status current as recipients
view / sign / complete.

**Documenso** (legacy) — existing rows (`provider="documenso"`) were created by
the ops `create-agreement-draft` server script + tracked by the `documenso-webhook`
script; their signed-PDF download is proxied through `DOCUMENSO_API`. Those rows
keep working untouched — every provider-specific branch here keys off `provider`.

The `crm_esign` realtime event (published on the insert/update hooks below) drives
the live sidebar-card + Activity-timeline refresh for both providers.
"""

import json
import re

import frappe
import requests
from frappe import _

AGREEMENT_DOCTYPE = "CRM Esign Agreement"

# DocuSeal cloud API. Token in site_config `docuseal_api_token` (the Infisical
# DOCUSEAL_API_KEY mirrored in via `bench set-config`, like documenso_api_token).
DOCUSEAL_API = "https://api.docuseal.com"

# Documenso public API (legacy rows). Signed PDF lives behind the token, so we
# proxy the bytes through the backend.
DOCUMENSO_API = "https://sign.groundworkpro.com/api/v2"

# Occupancy default text (buyer can still edit on the signing page).
_OCCUPANCY_DEFAULT = (
	"Seller shall vacate the Property and remove all personal belongings "
	"on or before the Closing Date."
)


# --------------------------------------------------------------------------- #
# realtime + hooks (shared by both providers)
# --------------------------------------------------------------------------- #
def _publish(lead):
	if lead:
		frappe.publish_realtime(
			"crm_esign",
			{"reference_doctype": "CRM Lead", "reference_docname": lead},
			after_commit=True,
		)


def on_agreement_insert(doc, method=None):
	"""after_insert — stamp the created time + live-refresh the open lead."""
	if not doc.get("last_event_at"):
		frappe.db.set_value(doc.doctype, doc.name, {"last_event_at": doc.creation}, update_modified=False)
	_publish(doc.get("lead"))


def on_agreement_update(doc, method=None):
	"""on_update — webhook status changes land here; stamp + live-refresh."""
	frappe.db.set_value(doc.doctype, doc.name, {"last_event_at": frappe.utils.now_datetime()}, update_modified=False)
	_publish(doc.get("lead"))


# --------------------------------------------------------------------------- #
# DocuSeal — create
# --------------------------------------------------------------------------- #
def _docuseal_token() -> str:
	token = (frappe.conf.get("docuseal_api_token") or "").strip()
	if not token:
		frappe.throw(_("DocuSeal API token is not configured on this site."))
	return token


def _resolve_template_ids(want_aif: bool, want_two: bool):
	"""Resolve the template id(s) for this deal; newest id wins per match.

	Templates in the "Purchase Agreements" folder (one document each):
	  Purchase Agreement - One Seller / - Two Sellers   (Buyer + Seller(s))
	  AIF - One Seller / - Two Sellers                  (Seller(s) only)

	A Standard deal is the Purchase Agreement template alone; a Novation deal
	adds the matching AIF document into the SAME envelope at create time (via
	`POST /submissions/pdf` `template_ids`) — no pre-merged templates to maintain.
	Returns (template_ids, display_title).
	"""
	token = _docuseal_token()
	resp = requests.get(
		f"{DOCUSEAL_API}/templates",
		params={"limit": 100},
		headers={"X-Auth-Token": token},
		timeout=30,
	)
	items = (resp.json() or {}).get("data") or []

	def _best(pred):
		chosen = None
		for t in items:
			if t.get("archived_at"):
				continue
			if pred(t.get("name") or ""):
				if chosen is None or (t.get("id") or 0) > (chosen.get("id") or 0):
					chosen = t
		return chosen

	wpa = _best(lambda n: n.startswith("Purchase Agreement") and "AIF" not in n and (("Two" in n) == want_two))
	if not wpa:
		frappe.throw(_("No matching DocuSeal Purchase Agreement template was found."))
	template_ids = [wpa["id"]]
	title = wpa["name"]
	if want_aif:
		aif = _best(lambda n: n.startswith("AIF") and (("Two" in n) == want_two))
		if not aif:
			frappe.throw(_("No matching DocuSeal AIF template was found."))
		template_ids.append(aif["id"])
		title = wpa["name"] + " + AIF"
	return template_ids, title


def _truthy(v) -> bool:
	return str(v).strip().lower() in ("1", "2", "true", "yes", "on", "two", "novation", "aif")


def _placeholder_email(given: str, lead: str, idx: int) -> str:
	"""Signers need an email to complete; nobody is emailed (send_email:false)."""
	given = (given or "").strip()
	if "@" in given:
		return given
	return f"signer{idx}.{lead.lower()}@noreply.groundworkpro.com"


@frappe.whitelist()
def create_docuseal_agreement(
	lead: str,
	template: str = "standard",
	two_sellers=None,
	seller1_email: str = None,
	seller2_name: str = None,
	seller2_email: str = None,
):
	"""Create a DocuSeal submission for a lead; return self-serve signing links.

	The logged-in sales user is the Buyer (signs first, fields stay editable);
	Seller 1 is the lead, Seller 2 is collected for two-seller deals.
	"""
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead not found"), frappe.DoesNotExistError)
	if not frappe.has_permission("CRM Lead", "write", lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	leaddoc = frappe.get_doc("CRM Lead", lead)
	want_aif = str(template).strip().lower() in ("novation", "aif")
	want_two = _truthy(two_sellers)

	# Buyer = the session user (its own no-login link comes back regardless).
	user = frappe.get_doc("User", frappe.session.user)
	buyer_name = user.full_name or user.first_name or frappe.session.user
	buyer_email = (user.email or frappe.session.user or "").strip()
	if "@" not in buyer_email:
		buyer_email = "acq@groundworkpro.com"

	# Seller 1 = the lead.
	seller1_name = (leaddoc.get("lead_name") or "").strip() or (
		((leaddoc.get("first_name") or "") + " " + (leaddoc.get("last_name") or "")).strip()
	)
	seller1_email = (seller1_email or leaddoc.get("email") or "").strip()
	seller2_name = (seller2_name or "").strip()
	seller2_email = (seller2_email or "").strip()
	if want_two and not seller2_name:
		frappe.throw(_("Enter the second seller's name."))

	template_ids, template_title = _resolve_template_ids(want_aif, want_two)

	addr = (leaddoc.get("property_address") or "").strip()
	sellers_joined = seller1_name + ((" and " + seller2_name) if (want_two and seller2_name) else "")

	def _clean(d):
		return {k: v for k, v in d.items() if v}

	# Buyer-role prefill: identity pulled off the lead + standard defaults for the
	# boilerplate terms (all still editable by the buyer on the signing page).
	buyer_values = _clean({
		# from the lead
		"Seller Name(s)": sellers_joined,
		"Property Address": addr,
		"County": (leaddoc.get("property_county") or "").strip(),
		"APN": (leaddoc.get("apn") or "").strip(),
		"Governing State": (leaddoc.get("property_state") or "").strip(),
		"Signer Name": buyer_name,
		# standard defaults
		"Earnest Money": "100",
		"Due Diligence Days": "30",
		"Occupancy": _OCCUPANCY_DEFAULT,
		"Personal Property": "None.",
		"Additional Terms": "None.",
		"Disclosed Defects": "None known.",
	})

	# Seller-role prefill. Field names differ across templates; pass the superset
	# and DocuSeal ignores keys that don't exist on that submitter.
	def _seller_values(name, two_idx=None):
		if two_idx == 1:
			d = {"Seller 1 Legal Name": name, "Seller 1 Name": name}
		elif two_idx == 2:
			d = {"Seller 2 Legal Name": name, "Seller 2 Name": name}
		else:
			d = {"Seller Name": name}
		d["Property Address"] = addr  # AIF puts the address on the seller role
		return _clean(d)

	submitters = [{
		"role": "Buyer",
		"name": buyer_name,
		"email": buyer_email,
		"send_email": False,
		"values": buyer_values,
	}]
	if want_two:
		submitters.append({
			"role": "Seller 1", "name": seller1_name,
			"email": _placeholder_email(seller1_email, lead, 1),
			"send_email": False, "values": _seller_values(seller1_name, 1),
		})
		submitters.append({
			"role": "Seller 2", "name": seller2_name,
			"email": _placeholder_email(seller2_email, lead, 2),
			"send_email": False, "values": _seller_values(seller2_name, 2),
		})
	else:
		submitters.append({
			"role": "Seller", "name": seller1_name,
			"email": _placeholder_email(seller1_email, lead, 1),
			"send_email": False, "values": _seller_values(seller1_name),
		})

	# One template (Standard) → POST /submissions. Two+ (Novation = Purchase
	# Agreement + AIF) → POST /submissions/pdf with `template_ids`, which assembles
	# both documents into ONE envelope at create time — no pre-merged templates.
	token = _docuseal_token()
	if len(template_ids) == 1:
		endpoint, payload = "/submissions", {
			"template_id": template_ids[0],
			"send_email": False, "order": "preserved", "submitters": submitters,
		}
	else:
		endpoint, payload = "/submissions/pdf", {
			"template_ids": template_ids, "documents": [], "name": template_title,
			"send_email": False, "order": "preserved", "submitters": submitters,
		}
	try:
		resp = requests.post(
			f"{DOCUSEAL_API}{endpoint}",
			json=payload,
			headers={"X-Auth-Token": token, "Content-Type": "application/json"},
			timeout=90,
		)
	except requests.RequestException:
		frappe.throw(_("Could not reach DocuSeal to create the agreement."))
	if resp.status_code not in (200, 201):
		frappe.throw(_("DocuSeal rejected the agreement ({0}): {1}").format(resp.status_code, resp.text[:300]))

	# /submissions returns a list of submitters; /submissions/pdf returns a dict.
	data = resp.json()
	if isinstance(data, list):
		subs = data
		submission_id = subs[0].get("submission_id") if subs else None
	else:
		subs = (data or {}).get("submitters") or []
		submission_id = (data or {}).get("id")
	if not submission_id or not subs:
		frappe.throw(_("DocuSeal returned no submission."))
	buyer_link = ""
	seller_links = []
	for s in subs:
		link = s.get("embed_src") or s.get("slug") or ""
		if s.get("role") == "Buyer":
			buyer_link = link
		else:
			seller_links.append({"name": s.get("name"), "link": link})

	agr = frappe.get_doc({
		"doctype": AGREEMENT_DOCTYPE,
		"lead": lead,
		"provider": "docuseal",
		"document_id": submission_id,
		"template_title": template_title,
		"agreement_status": "pending",
		"signed_count": 0,
		"total_signers": len(subs),
		"buyer_link": buyer_link,
		"seller_links": json.dumps(seller_links),
		"last_event": "created",
	})
	agr.insert(ignore_permissions=True)
	frappe.db.commit()

	# Capture Seller 2 as a Contact on the lead (mirrors the Documenso flow).
	if want_two and seller2_name:
		_attach_second_seller_contact(lead, seller2_name, seller2_email)

	return {
		"ok": True,
		"document_id": submission_id,
		"agreement": agr.name,
		"template": template_title,
		"buyer_link": buyer_link,
		"seller_links": seller_links,
	}


def _attach_second_seller_contact(lead: str, name: str, email: str):
	for dl in frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": "CRM Lead", "link_name": lead, "parenttype": "Contact"},
		fields=["parent"],
	):
		existing = frappe.db.get_value("Contact", dl.parent, "full_name")
		if existing and existing.strip().lower() == name.strip().lower():
			return
	parts = name.split(" ", 1)
	cdoc = {
		"doctype": "Contact",
		"first_name": parts[0],
		"last_name": parts[1] if len(parts) > 1 else "",
		"links": [{"link_doctype": "CRM Lead", "link_name": lead}],
	}
	if email:
		cdoc["email_ids"] = [{"email_id": email, "is_primary": 1}]
	frappe.get_doc(cdoc).insert(ignore_permissions=True)


# --------------------------------------------------------------------------- #
# DocuSeal — webhook
# --------------------------------------------------------------------------- #
@frappe.whitelist(allow_guest=True)
def docuseal_webhook(secret: str = None):
	"""Keep a CRM Esign Agreement current as DocuSeal recipients view/sign/complete.

	Registered in DocuSeal Settings → Webhooks pointing at
	`/api/method/crm.api.agreement.docuseal_webhook?secret=<docuseal_webhook_secret>`
	with events form.viewed/started/completed/declined + submission.completed/
	expired/archived. We refetch the submission for authoritative status/counts,
	then save() — the on_update hook publishes `crm_esign` for the live refresh.
	"""
	expected = (frappe.conf.get("docuseal_webhook_secret") or "").strip()
	provided = secret or (frappe.request.args.get("secret") if frappe.request else None)
	if not expected or provided != expected:
		frappe.throw(_("Unauthorized"), frappe.PermissionError)

	body = {}
	if frappe.request:
		body = frappe.request.get_json(force=True, silent=True) or {}
	event = body.get("event_type")
	data = body.get("data") or {}
	sub_id = data.get("submission_id") or (data.get("submission") or {}).get("id") or data.get("id")
	if not sub_id:
		return {"ok": True, "skipped": "no submission id"}

	rows = frappe.get_all(
		AGREEMENT_DOCTYPE,
		filters={"document_id": sub_id, "provider": "docuseal"},
		fields=["name"],
	)
	if not rows:
		return {"ok": True, "skipped": "no agreement"}

	status, signed, total = None, 0, 0
	token = (frappe.conf.get("docuseal_api_token") or "").strip()
	if token:
		try:
			r = requests.get(
				f"{DOCUSEAL_API}/submissions/{sub_id}",
				headers={"X-Auth-Token": token},
				timeout=20,
			)
			if r.ok:
				full = r.json() or {}
				status = full.get("status")
				submitters = full.get("submitters") or []
				total = len(submitters)
				signed = sum(1 for s in submitters if s.get("completed_at"))
		except requests.RequestException:
			pass

	for m in rows:
		agr = frappe.get_doc(AGREEMENT_DOCTYPE, m.name)
		if status:
			agr.agreement_status = status
		if total:
			agr.total_signers = total
			agr.signed_count = signed
		if event:
			agr.last_event = event
		agr.raw_last_payload = json.dumps(body)[:100000]
		agr.save(ignore_permissions=True)

	return {"ok": True, "updated": len(rows)}


# --------------------------------------------------------------------------- #
# read + download (both providers)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def get_agreements(lead: str):
	"""E-sign agreements for a lead, most recent first (sidebar card + timeline)."""
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead not found"), frappe.DoesNotExistError)
	if not frappe.has_permission("CRM Lead", "read", lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.db.exists("DocType", AGREEMENT_DOCTYPE):
		return []

	has_provider = frappe.db.has_column(AGREEMENT_DOCTYPE, "provider")
	fields = [
		"name", "document_id", "template_title", "agreement_status",
		"signed_count", "total_signers", "buyer_link", "seller_links",
		"last_event", "last_event_at", "creation", "owner",
	]
	if has_provider:
		fields.append("provider")

	rows = frappe.get_all(AGREEMENT_DOCTYPE, filters={"lead": lead}, fields=fields, order_by="creation desc")
	for r in rows:
		r["created_by_name"] = frappe.get_cached_value("User", r.owner, "full_name") if r.owner else None
		try:
			r["seller_links"] = json.loads(r.get("seller_links") or "[]")
		except (ValueError, TypeError):
			r["seller_links"] = []
		r["provider"] = r.get("provider") or "documenso"
		r["is_signed"] = _is_completed(r)
	return rows


def _is_completed(agr) -> bool:
	"""Fully signed: status COMPLETED/completed, or every signer signed."""
	if (agr.get("agreement_status") or "").upper() == "COMPLETED":
		return True
	signed = agr.get("signed_count") or 0
	total = agr.get("total_signers") or 0
	return bool(total and signed >= total)


def _signed_filename(agr) -> str:
	base = (agr.get("template_title") or "agreement").strip()
	safe = re.sub(r"[^\w.-]+", "_", base).strip("_") or "agreement"
	return f"{safe}_signed.pdf"


@frappe.whitelist()
def download_signed_agreement(agreement: str):
	"""Stream the fully-signed PDF (branches on provider)."""
	if not frappe.db.exists(AGREEMENT_DOCTYPE, agreement):
		frappe.throw(_("Agreement not found"), frappe.DoesNotExistError)

	wanted = ["lead", "document_id", "agreement_status", "signed_count", "total_signers", "template_title"]
	if frappe.db.has_column(AGREEMENT_DOCTYPE, "provider"):
		wanted.append("provider")
	agr = frappe.db.get_value(AGREEMENT_DOCTYPE, agreement, wanted, as_dict=True)

	if not agr.lead or not frappe.has_permission("CRM Lead", "read", agr.lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not _is_completed(agr):
		frappe.throw(_("This agreement is not fully signed yet."))
	if not agr.document_id:
		frappe.throw(_("This agreement has no document on file."))

	provider = (agr.get("provider") or "documenso").lower()
	content = _docuseal_signed_pdf(agr) if provider == "docuseal" else _documenso_signed_pdf(agr)

	frappe.local.response.filename = _signed_filename(agr)
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"


def _docuseal_signed_pdf(agr) -> bytes:
	"""Fetch the combined signed PDF for a DocuSeal submission."""
	token = _docuseal_token()
	try:
		meta = requests.get(
			f"{DOCUSEAL_API}/submissions/{agr.document_id}",
			headers={"X-Auth-Token": token},
			timeout=30,
		)
		url = (meta.json() or {}).get("combined_document_url") if meta.ok else None
		if not url:
			# fall back to the per-document list (merged)
			docs = requests.get(
				f"{DOCUSEAL_API}/submissions/{agr.document_id}/documents",
				headers={"X-Auth-Token": token},
				timeout=30,
			).json()
			arr = (docs.get("documents") if isinstance(docs, dict) else docs) or []
			url = arr[0].get("url") if arr else None
		if not url:
			frappe.throw(_("DocuSeal has no signed document URL yet."))
		pdf = requests.get(url, timeout=60)
	except requests.RequestException:
		frappe.throw(_("Could not reach DocuSeal to fetch the signed document."))
	if pdf.status_code != 200 or not pdf.content:
		frappe.throw(_("Could not fetch the signed document from DocuSeal ({0}).").format(pdf.status_code))
	return pdf.content


def _documenso_signed_pdf(agr) -> bytes:
	"""Legacy: proxy the signed PDF from Documenso (token in site_config)."""
	token = (frappe.conf.get("documenso_api_token") or "").strip()
	if not token:
		frappe.throw(_("Documenso API token is not configured on this site."))
	try:
		resp = requests.get(
			f"{DOCUMENSO_API}/document/{agr.document_id}/download",
			params={"version": "signed"},
			headers={"Authorization": token},
			timeout=30,
		)
	except requests.RequestException:
		frappe.throw(_("Could not reach Documenso to fetch the signed document."))
	if resp.status_code != 200 or not resp.content:
		frappe.throw(_("Could not fetch the signed document from Documenso ({0}).").format(resp.status_code))
	return resp.content
