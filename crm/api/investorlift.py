"""InvestorLift admin API client + Tier-1 marketing sync (property → CRM Lead).

InvestorLift (wholesale buyer marketing) has two apps sharing one numeric property id:
  - **admin.investorlift.com** — a Laravel JSON API, JWT bearer auth. THIS module.
  - **investorlift.ai** — the RSC buyer board (no JSON API). Scraped in Tier 2 by an
    ops Playwright worker that POSTs into `crm/api/investorlift_ingest.py`.

Tier 1 (here) is a clean, cron-able sync: for every lead linked to an InvestorLift
property (`CRM Lead.il_property_id`), pull the property's marketing metrics
(`notifications_stats`) + status and mirror them onto the lead (the tax-info writeback
pattern) so the Dispo dashboard header block + sidebar card + admin link render, and a
`crm_il_sync` realtime event refreshes open leads live.

Auth: `POST /api/auth/login {email,password}` → a 30-day JWT `access_token`. Creds live
in site_config `investorlift_username` / `investorlift_password` (mirrored from Infisical
`INVESTORLIFT_USERNAME`/`_PASSWORD`, the quo_api_key / gemini_api_key pattern). The token
is cached on the `IL Connection` single doctype (or `frappe.cache` before ops provisions
it). Login *sometimes* triggers a 2FA SMS to Lance's Quo line — handled by
`crm/api/investorlift_2fa.py` (auto-retrieve) with a manual-entry fallback surfaced in
Settings.
"""

import json
import re

import requests

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from crm.api import investorlift_2fa

API_BASE = "https://admin.investorlift.com/api"
LOGIN_URL = f"{API_BASE}/auth/login"
ADMIN_EDIT_URL = "https://admin.investorlift.com/properties/{id}/edit"
CONNECTION_DOCTYPE = "IL Connection"
TOKEN_SKEW = 300  # refresh a token this many seconds before it actually expires

ALLOWED_ROLES = ("System Manager", "Sales Manager", "Sales User")


# --------------------------------------------------------------------------- #
# access
# --------------------------------------------------------------------------- #
def _guard(lead=None):
	if not any(r in ALLOWED_ROLES for r in frappe.get_roles()):
		frappe.throw(_("Only sales users can access InvestorLift data."), frappe.PermissionError)
	if lead is not None:
		if not frappe.db.exists("CRM Lead", lead):
			frappe.throw(_("Lead not found"), frappe.DoesNotExistError)
		if not frappe.has_permission("CRM Lead", "read", lead):
			frappe.throw(_("Not permitted"), frappe.PermissionError)


# --------------------------------------------------------------------------- #
# token storage — IL Connection single if provisioned, else frappe.cache
# --------------------------------------------------------------------------- #
def _conn():
	if frappe.db.exists("DocType", CONNECTION_DOCTYPE):
		return frappe.get_single(CONNECTION_DOCTYPE)
	return None


def _cache_key():
	return "investorlift_token"


def _store_token(token, expires_in):
	expiry = now_datetime() + frappe.utils.datetime.timedelta(seconds=cint(expires_in) or 2592000)
	conn = _conn()
	if conn:
		conn.db_set("token", token, update_modified=False)
		conn.db_set("token_expiry", expiry, update_modified=False)
		conn.db_set("last_login_at", now_datetime(), update_modified=False)
		conn.db_set("twofa_status", "", update_modified=False)
		conn.db_set("twofa_manual_code", "", update_modified=False)
	else:
		frappe.cache().set_value(_cache_key(), {"token": token, "expiry": str(expiry)})


def _cached_token():
	"""Return a still-valid cached token, or None."""
	conn = _conn()
	if conn:
		token, expiry = conn.get("token"), conn.get("token_expiry")
	else:
		blob = frappe.cache().get_value(_cache_key()) or {}
		token, expiry = blob.get("token"), blob.get("expiry")
	if not token or not expiry:
		return None
	if frappe.utils.get_datetime(expiry) <= now_datetime() + frappe.utils.datetime.timedelta(seconds=TOKEN_SKEW):
		return None
	return token


def _creds():
	email = (frappe.conf.get("investorlift_username") or "").strip()
	pw = (frappe.conf.get("investorlift_password") or "").strip()
	if not email or not pw:
		frappe.throw(_("InvestorLift credentials are not configured (site_config investorlift_username/password)."))
	return email, pw


# --------------------------------------------------------------------------- #
# 2FA state (surfaced in Settings → InvestorLift)
# --------------------------------------------------------------------------- #
def _mark_2fa_pending(challenge_body):
	conn = _conn()
	if conn:
		conn.db_set("twofa_status", "pending", update_modified=False)
		conn.db_set("twofa_requested_at", now_datetime(), update_modified=False)
	# Always broadcast so an open Settings page shows the challenge live.
	frappe.publish_realtime("crm_il_2fa", {"status": "pending"}, after_commit=False)
	# Log the full challenge shape — the verify endpoint is unknown until 2FA first
	# fires in the wild; this capture lets us finalize _complete_2fa().
	frappe.log_error(frappe.as_json(challenge_body)[:2000], "InvestorLift 2FA challenge shape")


def _manual_code():
	conn = _conn()
	return (conn.get("twofa_manual_code") or "").strip() if conn else ""


def _complete_2fa(challenge_body, code):
	"""Submit a 2FA code and return an access_token, or None.

	The exact verify endpoint is not yet known (2FA didn't fire on the validation
	login). We try the most common patterns and log whatever comes back so the first
	real challenge lets us pin this down. `session_id` from the login body is passed
	along since InvestorLift returns one.
	"""
	email, pw = _creds()
	session_id = (challenge_body or {}).get("session_id")
	attempts = [
		# (url, payload) — re-POST login with the code is the most common shape.
		(LOGIN_URL, {"email": email, "password": pw, "code": code, "session_id": session_id}),
		(f"{API_BASE}/auth/2fa", {"code": code, "session_id": session_id}),
		(f"{API_BASE}/auth/verify-code", {"code": code, "session_id": session_id}),
		(f"{API_BASE}/auth/two-factor", {"code": code, "session_id": session_id}),
	]
	for url, payload in attempts:
		try:
			r = requests.post(url, json=payload, headers={"Accept": "application/json"}, timeout=30)
			body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
		except Exception:
			continue
		token = body.get("access_token") or body.get("token")
		if token:
			_store_token(token, body.get("expires_in"))
			return token
	frappe.log_error(f"2FA verify failed for code {code}", "InvestorLift 2FA")
	return None


# --------------------------------------------------------------------------- #
# login
# --------------------------------------------------------------------------- #
def _login():
	"""Fresh login → access_token. Handles the 2FA branch (auto-retrieve, else manual)."""
	import time

	email, pw = _creds()
	since = time.time()
	r = requests.post(LOGIN_URL, json={"email": email, "password": pw}, headers={"Accept": "application/json"}, timeout=30)
	try:
		body = r.json()
	except ValueError:
		body = {}

	token = body.get("access_token") or body.get("token")
	if token:
		_store_token(token, body.get("expires_in"))
		return token

	# Bad credentials → not a 2FA challenge, don't poll.
	msg = (body.get("message") or "").lower()
	if r.status_code in (401, 422) and ("incorrect" in msg or "invalid" in msg):
		frappe.throw(_("InvestorLift login failed: {0}").format(body.get("message") or r.status_code))

	# Otherwise treat as a 2FA challenge.
	_mark_2fa_pending(body)
	code = investorlift_2fa.fetch_2fa_code(since) or _manual_code()
	if not code:
		frappe.throw(
			_("InvestorLift asked for a 2FA code and none was retrieved. Enter the code sent to the Quo line in Settings → InvestorLift."),
			exc=frappe.ValidationError,
		)
	token = _complete_2fa(body, code)
	if not token:
		frappe.throw(_("InvestorLift 2FA verification failed. Check the code and try again."))
	return token


def get_token():
	return _cached_token() or _login()


# --------------------------------------------------------------------------- #
# API calls
# --------------------------------------------------------------------------- #
def _api(path, params=None, _retry=True):
	token = get_token()
	r = requests.get(
		f"{API_BASE}{path}",
		params=params,
		headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
		timeout=30,
	)
	if r.status_code == 401 and _retry:
		# token rejected → force a refresh once
		conn = _conn()
		if conn:
			conn.db_set("token", "", update_modified=False)
		else:
			frappe.cache().delete_value(_cache_key())
		return _api(path, params, _retry=False)
	r.raise_for_status()
	return r.json()


def get_property(il_property_id):
	body = _api(f"/properties/{il_property_id}", {"with": "notifications_stats;dispositions_manager"})
	return body.get("data") if isinstance(body, dict) and "data" in body else body


def list_properties(account_id=None, per_page=200):
	account_id = account_id or frappe.conf.get("investorlift_account_id") or "447403"
	body = _api(
		"/properties",
		{"filter[account_id]": account_id, "with": "notifications_stats", "per_page": per_page},
	)
	return body.get("data") if isinstance(body, dict) else (body or [])


# --------------------------------------------------------------------------- #
# marketing parse + writeback
# --------------------------------------------------------------------------- #
def _summary(prop):
	"""Flatten an InvestorLift property record into the marketing summary the UI needs."""
	stats = prop.get("notifications_stats") or {}
	sms = stats.get("sms") or {}
	email = stats.get("email") or {}
	pid = prop.get("id") or prop.get("property_id")
	return {
		"il_property_id": str(pid) if pid else None,
		"status": prop.get("status"),
		"admin_url": ADMIN_EDIT_URL.format(id=pid) if pid else None,
		"marketplace_url": prop.get("property_page_url"),
		"address": prop.get("full_address") or prop.get("street_address"),
		"price": flt(prop.get("price")) or None,
		"arv": flt(prop.get("arv_estimate")) or None,
		"views": cint(prop.get("views")),
		"is_published": bool(prop.get("is_published")),
		"is_expired": bool(prop.get("is_expired")),
		"sms": {
			"sent": cint(sms.get("plan_count")),
			"delivered": cint(sms.get("count_delivered")),
			"clicked": cint(sms.get("count_clicked")),
			"clicked_unique": cint(sms.get("count_clicked_unique")),
			"unsub": cint(sms.get("count_unsub")),
			"ctr": flt(sms.get("ctr")),
		},
		"email": {
			"sent": cint(email.get("plan_count")),
			"delivered": cint(email.get("count_delivered")),
			"clicked": cint(email.get("count_clicked")),
			"ctr": flt(email.get("ctr")),
		},
		"spend": flt(stats.get("total_amount")),
		"synced_at": str(now_datetime()),
	}


# CRM Lead custom fields the summary mirrors onto (guarded by has_field so the app
# runs before ops adds them). Keyed by summary path.
def _writeback(lead, summary):
	meta = frappe.get_meta("CRM Lead")
	vals = {}

	def put(field, value):
		if value not in (None, "") and meta.has_field(field):
			vals[field] = value

	put("il_property_id", summary.get("il_property_id"))
	put("il_status", summary.get("status"))
	put("il_admin_url", summary.get("admin_url"))
	put("il_sms_sent", summary["sms"]["sent"])
	put("il_sms_delivered", summary["sms"]["delivered"])
	put("il_sms_clicked", summary["sms"]["clicked"])
	put("il_sms_unsub", summary["sms"]["unsub"])
	put("il_sms_ctr", summary["sms"]["ctr"])
	put("il_email_sent", summary["email"]["sent"])
	put("il_email_delivered", summary["email"]["delivered"])
	put("il_email_clicked", summary["email"]["clicked"])
	put("il_spend", summary.get("spend"))
	put("il_views", summary.get("views"))
	if meta.has_field("il_marketing_synced_at"):
		vals["il_marketing_synced_at"] = now_datetime()
	if vals:
		frappe.db.set_value("CRM Lead", lead, vals, update_modified=False)


# --------------------------------------------------------------------------- #
# address matching — auto-link IL properties to existing CRM Leads
# --------------------------------------------------------------------------- #
# InvestorLift and the CRM write the same address differently ("11940 South
# Wallace Street" vs "11940 S Wallace St"), so we normalize both to a canonical
# key of <normalized street line> | <zip> before comparing.
_DIRECTIONALS = {
	"north": "n", "south": "s", "east": "e", "west": "w",
	"northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
}
_SUFFIXES = {
	"street": "st", "st": "st", "avenue": "ave", "ave": "ave", "av": "ave",
	"road": "rd", "rd": "rd", "drive": "dr", "dr": "dr", "boulevard": "blvd", "blvd": "blvd",
	"lane": "ln", "ln": "ln", "court": "ct", "ct": "ct", "place": "pl", "pl": "pl",
	"terrace": "ter", "ter": "ter", "circle": "cir", "cir": "cir",
	"parkway": "pkwy", "pkwy": "pkwy", "highway": "hwy", "hwy": "hwy",
	"trail": "trl", "trl": "trl", "square": "sq", "sq": "sq",
	"pike": "pike", "run": "run", "row": "row", "way": "way", "loop": "loop", "path": "path",
}


def _norm_street(street):
	"""Canonicalize a street line for matching: lowercase, drop punctuation, and
	fold directionals + suffixes to a single spelling."""
	s = re.sub(r"[.,#]", " ", (street or "").lower())
	s = re.sub(r"\bapt\b.*|\bunit\b.*|\bste\b.*", " ", s)  # drop unit/apt tails
	s = re.sub(r"\s+", " ", s).strip()
	toks = []
	for t in s.split():
		t = _DIRECTIONALS.get(t, t)
		t = _SUFFIXES.get(t, t)
		toks.append(t)
	return " ".join(toks)


def _split_address(full):
	"""From a CRM full address ('11940 S Wallace St, Chicago, IL 60628') pull the
	street line (before the first comma) and the 5-digit zip (last one seen)."""
	street = (full or "").split(",")[0]
	zips = re.findall(r"\b(\d{5})\b", full or "")
	return street, (zips[-1] if zips else "")


def _addr_key(street, zipcode):
	st = _norm_street(street)
	z = "".join(c for c in (zipcode or "") if c.isdigit())[:5]
	# require a street number to avoid matching bare street names
	if not st or not re.match(r"^\d", st):
		return ""
	return f"{st}|{z}" if z else st


@frappe.whitelist()
def match_properties(dry_run=1, overwrite=0):
	"""Auto-link every InvestorLift property to the CRM Lead at the same address.

	Matches on a normalized <street|zip> key. Sets `il_property_id` on each matched
	lead (unless it already has one and overwrite is off). `dry_run=1` (default)
	returns the proposed matches without writing. Returns one row per IL property."""
	_guard()
	return _run_match(dry_run, overwrite)


def _run_match(dry_run=1, overwrite=0):
	dry_run, overwrite = cint(dry_run), cint(overwrite)

	# index CRM leads that have an address by their normalized key
	index = {}
	for l in frappe.get_all(
		"CRM Lead",
		filters={"property_address": ("is", "set")},
		fields=["name", "property_address", "il_property_id", "lead_name", "status", "modified"],
		order_by="modified desc",
		limit_page_length=0,
	):
		street, z = _split_address(l.property_address)
		k = _addr_key(street, z)
		if k:
			index.setdefault(k, []).append(l)

	results = []
	for p in list_properties():
		pid = str(p.get("id") or p.get("property_id"))
		il_addr = p.get("full_address") or p.get("street_address")
		key = _addr_key(p.get("street_address"), p.get("zip"))
		candidates = index.get(key, []) if key else []

		# choose: a lead already correctly linked to THIS property wins; else an
		# unlinked lead (most-recently-modified, already sorted); else the first.
		chosen = None
		for c in candidates:
			if c.il_property_id == pid:
				chosen = c
				break
		if not chosen:
			for c in candidates:
				if not c.il_property_id:
					chosen = c
					break
		if not chosen and candidates:
			chosen = candidates[0]

		row = {
			"il_property_id": pid,
			"il_address": il_addr,
			"key": key,
			"candidates": len(candidates),
			"matched_lead": chosen.name if chosen else None,
			"matched_lead_name": chosen.lead_name if chosen else None,
			"matched_lead_status": chosen.status if chosen else None,
			"already_linked_to": (chosen.il_property_id if chosen else None),
			"action": "none",
		}

		if chosen and not dry_run:
			if chosen.il_property_id and chosen.il_property_id != pid and not overwrite:
				row["action"] = "skipped (already linked)"
			elif chosen.il_property_id == pid:
				row["action"] = "already correct"
			else:
				frappe.db.set_value("CRM Lead", chosen.name, "il_property_id", pid, update_modified=False)
				_sync_lead(chosen.name, pid)
				row["action"] = "linked"
		results.append(row)

	if not dry_run:
		frappe.db.commit()
	return results


def _sync_lead(lead, il_property_id):
	prop = get_property(il_property_id)
	if not prop:
		return None
	summary = _summary(prop)
	_writeback(lead, summary)
	frappe.publish_realtime(
		"crm_il_sync",
		{"reference_doctype": "CRM Lead", "reference_docname": lead},
		after_commit=True,
	)
	return summary


# --------------------------------------------------------------------------- #
# whitelisted endpoints
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def get_marketing(lead, refresh=0):
	"""Marketing summary for a lead's linked InvestorLift property (card + header).

	Reads the stored `il_*` lead fields by default (fast, no API hit on every page
	load — the hourly cron keeps them fresh). `refresh=1` forces a live re-sync
	(the card's ↻ button)."""
	_guard(lead)
	meta = frappe.get_meta("CRM Lead")
	if not meta.has_field("il_property_id"):
		return {"linked": False}
	stored = frappe.db.get_value(
		"CRM Lead",
		lead,
		[
			"il_property_id", "il_status", "il_admin_url",
			"il_sms_sent", "il_sms_delivered", "il_sms_clicked", "il_sms_unsub", "il_sms_ctr",
			"il_email_sent", "il_email_delivered", "il_email_clicked",
			"il_spend", "il_views", "il_marketing_synced_at",
		],
		as_dict=True,
	) or {}
	il_id = stored.get("il_property_id")
	if not il_id:
		return {"linked": False}

	if cint(refresh):
		summary = _sync_lead(lead, il_id)
		if summary:
			summary["linked"] = True
			return summary

	# Build the summary from the stored fields.
	return {
		"linked": True,
		"il_property_id": il_id,
		"status": stored.get("il_status"),
		"admin_url": stored.get("il_admin_url"),
		"views": cint(stored.get("il_views")),
		"spend": flt(stored.get("il_spend")),
		"sms": {
			"sent": cint(stored.get("il_sms_sent")),
			"delivered": cint(stored.get("il_sms_delivered")),
			"clicked": cint(stored.get("il_sms_clicked")),
			"unsub": cint(stored.get("il_sms_unsub")),
			"ctr": flt(stored.get("il_sms_ctr")),
		},
		"email": {
			"sent": cint(stored.get("il_email_sent")),
			"delivered": cint(stored.get("il_email_delivered")),
			"clicked": cint(stored.get("il_email_clicked")),
			"ctr": 0,
		},
		"synced_at": str(stored.get("il_marketing_synced_at") or ""),
	}


@frappe.whitelist()
def search_properties(q):
	"""Address search over InvestorLift properties, to link a lead (link-property tool)."""
	_guard()
	q = (q or "").strip().lower()
	if len(q) < 3:
		return []
	out = []
	for p in list_properties():
		hay = " ".join(str(p.get(k) or "") for k in ("full_address", "street_address", "city", "zip")).lower()
		if q in hay:
			pid = p.get("id") or p.get("property_id")
			out.append(
				{
					"il_property_id": str(pid),
					"address": p.get("full_address") or p.get("street_address"),
					"status": p.get("status"),
					"price": flt(p.get("price")) or None,
					"admin_url": ADMIN_EDIT_URL.format(id=pid),
				}
			)
		if len(out) >= 20:
			break
	return out


@frappe.whitelist()
def link_property(lead, il_property_id):
	"""Attach an InvestorLift property to a lead → turns on Active Dispo, syncs once."""
	_guard(lead)
	if not frappe.get_meta("CRM Lead").has_field("il_property_id"):
		frappe.throw(_("InvestorLift fields are not provisioned on this site yet."))
	frappe.db.set_value("CRM Lead", lead, "il_property_id", str(il_property_id).strip(), update_modified=False)
	# Sync immediately so the dashboard populates on link (don't wait for the hourly cron).
	summary = _sync_lead(lead, str(il_property_id).strip())
	if summary:
		summary["linked"] = True
		return summary
	return get_marketing(lead)


@frappe.whitelist()
def unlink_property(lead):
	_guard(lead)
	if frappe.get_meta("CRM Lead").has_field("il_property_id"):
		frappe.db.set_value("CRM Lead", lead, "il_property_id", "", update_modified=False)
	return {"linked": False}


@frappe.whitelist()
def get_captured_2fa():
	"""Latest InvestorLift 2FA code captured by our OpenPhone `message.received`
	webhook (logged to Sequence Events Log). InvestorLift texts the code from an SMS
	SHORT CODE (e.g. 22395) to the Quo line — the OpenPhone *list* API hides short
	codes, but the webhook delivers them, so we read it from our own event log. The
	Playwright scraper polls this during login. Returns {code, created_at (epoch)}."""
	_guard()
	number = (frappe.conf.get("investorlift_2fa_number") or "+16513907073")
	want = "".join(c for c in number if c.isdigit())[-10:]
	if not frappe.db.exists("DocType", "Sequence Events Log"):
		return {}
	rows = frappe.get_all(
		"Sequence Events Log",
		filters={"event_type": "message.received"},
		fields=["name", "payload", "creation"],
		order_by="creation desc",
		limit_page_length=30,
	)
	for r in rows:
		try:
			obj = (json.loads(r.payload or "{}").get("data") or {}).get("object") or {}
		except (ValueError, TypeError):
			continue
		to = "".join(c for c in str(obj.get("to") or "") if c.isdigit())[-10:]
		text = obj.get("text") or ""
		if to != want or not re.search(r"investorlift|verif|code", text, re.I):
			continue
		m = re.search(r"(?<!\d)(\d{6})(?!\d)", text) or re.search(r"(?<!\d)(\d{4,8})(?!\d)", text)
		if not m:
			continue
		created = obj.get("createdAt")
		ep = 0
		if created:
			try:
				from datetime import datetime

				ep = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
			except (ValueError, TypeError):
				ep = 0
		return {"code": m.group(1), "created_at": ep, "created_iso": created}
	return {}


@frappe.whitelist()
def get_connection_status():
	"""Connection + 2FA state for Settings → InvestorLift."""
	_guard()
	conn = _conn()
	token_ok = bool(_cached_token())
	return {
		"configured": bool((frappe.conf.get("investorlift_username") or "").strip()),
		"connected": token_ok,
		"provisioned": conn is not None,
		"twofa_status": (conn.get("twofa_status") if conn else "") or "",
		"twofa_requested_at": conn.get("twofa_requested_at") if conn else None,
		"last_login_at": conn.get("last_login_at") if conn else None,
	}


@frappe.whitelist()
def submit_2fa_code(code):
	"""Manual 2FA fallback: Lance types the code from his phone; the next login uses it."""
	_guard()
	if not any(r in ("System Manager", "Sales Manager") for r in frappe.get_roles()):
		frappe.throw(_("Only a manager can submit the InvestorLift 2FA code."), frappe.PermissionError)
	conn = _conn()
	if not conn:
		frappe.throw(_("InvestorLift is not provisioned on this site yet."))
	conn.db_set("twofa_manual_code", (code or "").strip(), update_modified=False)
	# Kick a login now so the code is consumed immediately.
	try:
		_login()
	except Exception:
		frappe.db.rollback()
		return get_connection_status()
	return get_connection_status()


# --------------------------------------------------------------------------- #
# scheduler (hooks.py) — hourly refresh of every linked lead's marketing
# --------------------------------------------------------------------------- #
def sync_all_marketing():
	"""Scheduled: refresh marketing metrics for every lead linked to an IL property.
	(New scheduler hook → remember to run `sync_jobs` on prod; see gw127/128.)"""
	if not frappe.get_meta("CRM Lead").has_field("il_property_id"):
		return
	# First auto-link any InvestorLift property to the CRM Lead at its address
	# (so newly-published deals attach to their seller lead without manual work).
	try:
		_run_match(dry_run=0, overwrite=0)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "InvestorLift property matching failed")

	leads = frappe.get_all(
		"CRM Lead",
		filters={"il_property_id": ("is", "set")},
		fields=["name", "il_property_id"],
		limit_page_length=0,
	)
	for lead in leads:
		try:
			_sync_lead(lead.name, lead.il_property_id)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"InvestorLift sync failed for {lead.name}")
