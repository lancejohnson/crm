"""Adopt DocuSeal envelopes that were built by hand, outside the CRM.

The team routinely builds one-off templates directly in the DocuSeal UI (deal
specific novations, amendments, AIFs) and sends them by SMS. Those envelopes
were invisible to the CRM: `docuseal_webhook` looked the submission up by
`document_id`, found no `CRM Esign Agreement` row, and returned early — so a
contract could be fully signed with no trace on the lead. That is exactly how
the 6787 N 200 E (Zurek) purchase agreement went missing.

DocuSeal webhooks are **account-wide**, so those events already reach us; we
were just dropping them. This module adds the missing branch: when an event
arrives for an unknown submission, try to work out which lead it belongs to and
create the row.

Matching, in order of trust:

1. **Phone** (last-10, format-insensitive) against `CRM Lead.mobile_no/phone`.
   This is the primary key — the team sends signing links by text, so every
   recently hand-built envelope has `email: None` on every party. Email-only
   matching would catch roughly one in eight.
2. **Email** against `CRM Lead.email`, for the older email-sent envelopes.
3. **Address** (street number + street words, scraped from the template name and
   any "Property Address" field) is used ONLY to break a tie when more than one
   lead matched. It never links on its own.

Internal parties (our own users — by login email, `custom_quo_number`, or the
`docuseal_internal_numbers` site-config list) are excluded before matching,
otherwise the rep who signs every envelope would match whichever lead happens
to hold their number.

Anything that does not resolve to exactly one lead is never guessed at: it
raises an alert (once per submission) so it can be attached by hand with
`attach_submission`. `CRM Esign Agreement.lead` is `reqd`, so a row genuinely
cannot exist without a confident match.
"""

import json
import re

import frappe
import requests
from frappe import _

AGREEMENT_DOCTYPE = "CRM Esign Agreement"
DOCUSEAL_API = "https://api.docuseal.com"

# The DocuSeal account was built out in late June 2026; everything before this
# is throwaway test envelopes ("Seller Test", "SIGNDATE TEST", clone probes).
# Override with site-config `docuseal_adopt_since`.
DEFAULT_ADOPT_SINCE = "2026-07-01"

# Who hears about an envelope we could not place.
NOTIFY_USER = "lance.johnson@groundworkpro.com"

# Site-config `notifications_quo_number` overrides; matches agreement_notify.
DEFAULT_NOTIFY_FROM = "+19523953833"

# Roles DocuSeal assigns to our own side on CRM-built envelopes.
_OUR_ROLES = {"buyer", "first party"}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _digits(v) -> str:
	return re.sub(r"\D", "", str(v or ""))


def _last10(v) -> str:
	d = _digits(v)
	return d[-10:] if len(d) >= 10 else ""


def _token() -> str:
	return (frappe.conf.get("docuseal_api_token") or "").strip()


def _fetch_submission(sub_id):
	token = _token()
	if not token:
		return None
	try:
		r = requests.get(
			f"{DOCUSEAL_API}/submissions/{sub_id}",
			headers={"X-Auth-Token": token},
			timeout=20,
		)
	except requests.RequestException:
		return None
	return r.json() if r.ok else None


def _internal_identifiers():
	"""Emails + last-10 phones belonging to our own team."""
	emails, phones = set(), set()
	fields = ["name"]
	for col in ("custom_quo_number", "mobile_no", "phone"):
		if frappe.db.has_column("User", col):
			fields.append(col)
	for u in frappe.get_all("User", filters={"enabled": 1}, fields=fields, limit_page_length=0):
		login = (u.get("name") or "").strip().lower()
		if "@" in login:
			emails.add(login)
		for col in ("custom_quo_number", "mobile_no", "phone"):
			p = _last10(u.get(col))
			if p:
				phones.add(p)
	# Reps sometimes type a personal/second number into DocuSeal that the CRM
	# has never seen (one rep uses two transposed variants of their own line).
	for extra in frappe.conf.get("docuseal_internal_numbers") or []:
		p = _last10(extra)
		if p:
			phones.add(p)
	return emails, phones


def _lead_index():
	"""All leads indexed by last-10 phone and by email.

	Indexed in Python rather than filtered in SQL so that stored formatting
	("+17089023918" / "6513219748" / "(708) 902-3918") cannot cause a miss.
	The lead table is small enough for this to be cheap.
	"""
	leads = frappe.get_all(
		"CRM Lead",
		fields=["name", "lead_name", "email", "mobile_no", "phone", "property_address", "lead_owner"],
		limit_page_length=0,
	)
	by_phone, by_email = {}, {}
	for l in leads:
		for col in ("mobile_no", "phone"):
			p = _last10(l.get(col))
			if p:
				by_phone.setdefault(p, []).append(l)
		e = (l.get("email") or "").strip().lower()
		if e:
			by_email.setdefault(e, []).append(l)
	return leads, by_phone, by_email


def _address_hint(full) -> str:
	"""Free text likely to carry the property address.

	Hand-built templates are named after the deal ("6787 N 200 E Purchase
	Updated Agreement 072426", "AIF - 355 Valley St"), which makes the template
	name the single best address signal available.
	"""
	bits = [(full.get("template") or {}).get("name") or ""]
	for s in full.get("submitters") or []:
		for v in s.get("values") or []:
			field = (v.get("field") or "").lower()
			val = v.get("value")
			if "address" in field and isinstance(val, str):
				bits.append(val)
	return " ".join(bits).lower()


def _address_score(hint: str, address: str) -> int:
	"""How strongly `hint` corroborates `address`. Tie-breaker only."""
	address = (address or "").lower()
	if not hint or not address:
		return 0
	score = 0
	m = re.match(r"\s*(\d+)", address)
	if m and re.search(r"\b%s\b" % re.escape(m.group(1)), hint):
		score += 3
	for tok in set(re.findall(r"[a-z]{4,}", address)):
		if tok in hint:
			score += 1
	return score


# --------------------------------------------------------------------------- #
# matching
# --------------------------------------------------------------------------- #
def match_submission(full) -> dict:
	"""Resolve a DocuSeal submission to exactly one CRM Lead.

	Returns {lead, confidence: high|low, basis, reason, candidates}.
	`high` is the only value that may be linked automatically.
	"""
	internal_emails, internal_phones = _internal_identifiers()
	_leads, by_phone, by_email = _lead_index()

	hits = {}          # lead name -> set of human-readable reasons
	lead_rows = {}     # lead name -> row
	externals = 0

	for s in full.get("submitters") or []:
		email = (s.get("email") or "").strip().lower()
		phone = _last10(s.get("phone"))
		who = s.get("name") or s.get("role") or "?"
		if (email and email in internal_emails) or (phone and phone in internal_phones):
			continue
		externals += 1
		for l in (by_phone.get(phone) or []) if phone else []:
			hits.setdefault(l.name, set()).add(f"phone {phone} ({who})")
			lead_rows[l.name] = l
		for l in (by_email.get(email) or []) if email else []:
			hits.setdefault(l.name, set()).add(f"email {email} ({who})")
			lead_rows[l.name] = l

	if not externals:
		return {"lead": None, "confidence": "low", "reason": "no external parties", "candidates": []}
	if not hits:
		return {"lead": None, "confidence": "low", "reason": "no lead matched", "candidates": []}

	if len(hits) == 1:
		lead = next(iter(hits))
		return {
			"lead": lead,
			"confidence": "high",
			"basis": "; ".join(sorted(hits[lead])),
			"candidates": [lead],
		}

	# More than one lead matched (e.g. two people sharing a phone across deals).
	# Break the tie on the address, and only if there is a clear winner.
	hint = _address_hint(full)
	scored = sorted(
		((_address_score(hint, (lead_rows[n] or {}).get("property_address")), n) for n in hits),
		reverse=True,
	)
	if scored and scored[0][0] >= 3 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
		lead = scored[0][1]
		return {
			"lead": lead,
			"confidence": "high",
			"basis": "; ".join(sorted(hits[lead])) + f"; address match (score {scored[0][0]})",
			"candidates": list(hits),
		}
	return {
		"lead": None,
		"confidence": "low",
		"reason": f"{len(hits)} leads matched, address could not break the tie",
		"candidates": list(hits),
	}


# --------------------------------------------------------------------------- #
# adoption
# --------------------------------------------------------------------------- #
def _build_row(full, lead: str, basis: str) -> dict:
	submitters = full.get("submitters") or []
	buyer_link, seller_links = "", []
	for s in submitters:
		link = s.get("embed_src") or s.get("slug") or ""
		if (s.get("role") or "").strip().lower() in _OUR_ROLES:
			buyer_link = buyer_link or link
		else:
			seller_links.append({"name": s.get("name"), "link": link})

	row = {
		"doctype": AGREEMENT_DOCTYPE,
		"lead": lead,
		"provider": "docuseal",
		"document_id": full.get("id"),
		"template_title": (full.get("template") or {}).get("name") or "DocuSeal agreement",
		"agreement_status": full.get("status") or "pending",
		"signed_count": sum(1 for s in submitters if s.get("completed_at")),
		"total_signers": len(submitters),
		"buyer_link": buyer_link,
		"seller_links": json.dumps(seller_links),
		"last_event": "adopted",
	}
	if frappe.db.has_column(AGREEMENT_DOCTYPE, "source"):
		row["source"] = "adopted"
	if frappe.db.has_column(AGREEMENT_DOCTYPE, "match_basis"):
		row["match_basis"] = (basis or "")[:500]
	return row


def _reassign_owner(agreement: str, lead: str):
	"""Credit an adopted row to the lead owner rather than the webhook session."""
	owner = frappe.db.get_value("CRM Lead", lead, "lead_owner")
	if owner and frappe.db.exists("User", owner):
		frappe.db.set_value(AGREEMENT_DOCTYPE, agreement, "owner", owner, update_modified=False)


def adopt_submission(sub_id, full=None, dry_run=False) -> dict:
	"""Create a CRM Esign Agreement for a submission the CRM did not create.

	Never raises — the webhook must still return 200 to DocuSeal.
	"""
	sub_id = int(sub_id)
	# Already tracked? This also covers rows the user archived: an archived row
	# is kept (soft), so a late webhook event cannot resurrect it.
	if frappe.db.exists(AGREEMENT_DOCTYPE, {"document_id": sub_id}):
		return {"status": "exists"}

	full = full or _fetch_submission(sub_id)
	if not full:
		return {"status": "error", "reason": "could not fetch submission"}
	if full.get("archived_at"):
		return {"status": "skipped", "reason": "archived in DocuSeal"}

	since = frappe.conf.get("docuseal_adopt_since") or DEFAULT_ADOPT_SINCE
	created = (full.get("created_at") or "")[:10]
	if created and created < since:
		return {"status": "skipped", "reason": f"created {created}, before cutoff {since}"}

	m = match_submission(full)
	if m.get("confidence") != "high" or not m.get("lead"):
		if not dry_run:
			_alert_unmatched(sub_id, full, m)
		return {
			"status": "unmatched",
			"reason": m.get("reason"),
			"candidates": m.get("candidates") or [],
		}

	if dry_run:
		return {
			"status": "would_adopt",
			"lead": m["lead"],
			"basis": m.get("basis"),
			"template": (full.get("template") or {}).get("name"),
			"submission_status": full.get("status"),
		}

	row = _build_row(full, m["lead"], m.get("basis"))
	agr = frappe.get_doc(row)
	agr.insert(ignore_permissions=True)
	# Attribute it to the lead owner so the sidebar card reads sensibly. This has
	# to happen AFTER insert: Frappe stamps `owner = session user` on new docs and
	# ignores a preset value, which would otherwise credit every adopted
	# agreement to "Guest" (the webhook) or "Administrator" (the backfill).
	_reassign_owner(agr.name, m["lead"])
	frappe.db.commit()
	return {"status": "adopted", "agreement": agr.name, "lead": m["lead"], "basis": m.get("basis")}


# --------------------------------------------------------------------------- #
# alerting for envelopes we refuse to guess at
# --------------------------------------------------------------------------- #
def _seen_key(sub_id) -> str:
	return f"docuseal_unmatched_{sub_id}"


def _alert_unmatched(sub_id, full, m):
	"""Tell someone once — an unmatched envelope fires many events."""
	try:
		if frappe.db.get_default(_seen_key(sub_id)):
			return
		frappe.db.set_default(_seen_key(sub_id), "1")

		template = (full.get("template") or {}).get("name") or "(untitled)"
		parties = ", ".join(
			f"{s.get('name') or '?'} ({s.get('phone') or s.get('email') or 'no contact'})"
			for s in full.get("submitters") or []
		)
		reason = m.get("reason") or "no confident match"
		cands = ", ".join(m.get("candidates") or []) or "none"
		subject = f"DocuSeal envelope not linked to a lead: {template}"
		body = (
			f"<p>A DocuSeal envelope is active but could not be attached to a lead, "
			f"so it will not show up in the CRM.</p>"
			f"<p><b>Template:</b> {frappe.utils.escape_html(template)}<br>"
			f"<b>Submission:</b> {sub_id}<br>"
			f"<b>Status:</b> {full.get('status')}<br>"
			f"<b>Parties:</b> {frappe.utils.escape_html(parties)}<br>"
			f"<b>Why:</b> {frappe.utils.escape_html(reason)}<br>"
			f"<b>Candidate leads:</b> {frappe.utils.escape_html(cands)}</p>"
			f"<p>Attach it with:<br><code>bench execute "
			f"crm.api.agreement_adopt.attach_submission "
			f'--kwargs \'{{"sub_id": {sub_id}, "lead": "CRM-LEAD-..."}}\'</code></p>'
		)
		_safe_email(subject, body)
		_safe_text(f"DocuSeal: '{template}' is active but not linked to any lead ({reason}).")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "docuseal unmatched alert failed")


def _safe_email(subject, body):
	try:
		frappe.sendmail(recipients=[NOTIFY_USER], subject=subject, message=body, now=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "docuseal unmatched email failed")


def _safe_text(message):
	try:
		token = (frappe.conf.get("quo_api_key") or "").strip()
		to = frappe.db.get_value("User", NOTIFY_USER, "custom_quo_number")
		if not token or not to:
			return
		frm = (frappe.conf.get("notifications_quo_number") or DEFAULT_NOTIFY_FROM).strip()
		requests.post(
			"https://api.openphone.com/v1/messages",
			json={"from": frm, "to": [to], "content": message[:1000]},
			headers={"Authorization": token, "Content-Type": "application/json"},
			timeout=15,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "docuseal unmatched text failed")


# --------------------------------------------------------------------------- #
# manual + bulk entry points
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def attach_submission(sub_id, lead: str):
	"""Attach a DocuSeal submission to a lead by hand (the escape hatch for
	anything the matcher would not guess at)."""
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead not found"), frappe.DoesNotExistError)
	if not frappe.has_permission("CRM Lead", "write", lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	sub_id = int(sub_id)
	if frappe.db.exists(AGREEMENT_DOCTYPE, {"document_id": sub_id}):
		frappe.throw(_("That submission is already tracked."))
	full = _fetch_submission(sub_id)
	if not full:
		frappe.throw(_("Could not fetch that submission from DocuSeal."))

	agr = frappe.get_doc(_build_row(full, lead, "attached by %s" % frappe.session.user))
	agr.insert(ignore_permissions=True)
	_reassign_owner(agr.name, lead)
	frappe.db.commit()
	return {"ok": True, "agreement": agr.name, "lead": lead}


@frappe.whitelist()
def backfill_adoptions(dry_run=1, since=None, limit=500):
	"""Sweep every DocuSeal submission and adopt the confident ones.

	Dry-run by default: reports what it WOULD attach without writing.
	  bench execute crm.api.agreement_adopt.backfill_adoptions
	  bench execute crm.api.agreement_adopt.backfill_adoptions --kwargs '{"dry_run": 0}'
	"""
	dry_run = int(dry_run or 0)
	token = _token()
	if not token:
		return {"error": "docuseal_api_token not configured"}

	subs, after, guard = [], None, 0
	while guard < 20:
		guard += 1
		url = f"{DOCUSEAL_API}/submissions?limit=100" + (f"&after={after}" if after else "")
		try:
			r = requests.get(url, headers={"X-Auth-Token": token}, timeout=30)
		except requests.RequestException as e:
			return {"error": f"list failed: {e}"}
		if not r.ok:
			return {"error": f"list failed: {r.status_code}"}
		payload = r.json() or {}
		batch = payload.get("data") or []
		subs.extend(batch)
		after = (payload.get("pagination") or {}).get("next")
		if not batch or not after or len(subs) >= int(limit):
			break

	out = {"adopted": [], "would_adopt": [], "unmatched": [], "skipped": 0, "exists": 0}
	for s in subs:
		# The list payload lacks `values`; adopt_submission refetches only when
		# it actually needs to, so hand it what we have.
		res = adopt_submission(s.get("id"), full=s, dry_run=dry_run)
		status = res.get("status")
		if status in ("adopted", "would_adopt"):
			out[status if status == "adopted" else "would_adopt"].append(
				{
					"id": s.get("id"),
					"lead": res.get("lead"),
					"template": (s.get("template") or {}).get("name"),
					"basis": res.get("basis"),
					"submission_status": s.get("status"),
				}
			)
		elif status == "unmatched":
			out["unmatched"].append(
				{
					"id": s.get("id"),
					"template": (s.get("template") or {}).get("name"),
					"reason": res.get("reason"),
					"status": s.get("status"),
				}
			)
		elif status == "exists":
			out["exists"] += 1
		else:
			out["skipped"] += 1
	out["total_submissions"] = len(subs)
	out["dry_run"] = bool(dry_run)
	return out
