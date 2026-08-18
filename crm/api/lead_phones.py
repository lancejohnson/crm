"""Multiple phone numbers on a CRM Lead, plus Quo call backfill.

A lead has always had `mobile_no` (primary) and a leftover `phone` slot.
Sellers give us more than that — a cell, a spouse, a landline — and a call to
any of them belongs on the lead. Extra numbers live in `CRM Lead.extra_phones`
(JSON list of strings; ops `setup_lead_phones.py`). The column is
has_column-guarded, so two numbers still work before the script runs.

Adding a number:
  1. Writes the list (primary stays `mobile_no`).
  2. Relinks any already-mirrored CRM Call Log whose from/to matches and is
     unlinked (the usual case: we just called them, then typed the number in).
  3. Enqueues a Quo `/v1/calls` sweep per workspace line and inserts any
     missing logs oldest-first. Dedupes on the Quo call id, so re-adding or
     a hook + API race cannot double-create.

Matching everywhere else (the sequence-events webhook, texts, the ring
silencer) reads the same list via `iter_phones` / `find_lead_by_phone`.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import frappe
import requests
from frappe import _
from frappe.utils import convert_utc_to_system_timezone

from crm.api.telephony import last10

QUO_API = "https://api.openphone.com"
QUO_TIMEOUT = 20
QUO_UA = "curl/8.1.0"
QUO_SLEEP = 0.15
QUO_LINES_TTL = 21600
QUO_USERS_TTL = 3600
MAX_PAGES = 20


def _has_extra() -> bool:
	return frappe.db.has_column("CRM Lead", "extra_phones")


def _parse_extra(raw) -> list[str]:
	if not raw:
		return []
	if isinstance(raw, list):
		parsed = raw
	else:
		try:
			parsed = json.loads(raw)
		except (TypeError, ValueError):
			return []
	out = []
	if not isinstance(parsed, list):
		return out
	for item in parsed:
		if isinstance(item, str) and item.strip():
			out.append(item.strip())
		elif isinstance(item, dict):
			number = (item.get("number") or "").strip()
			if number:
				out.append(number)
	return out


def iter_phones(doc) -> list[str]:
	"""Every distinct number on a lead, primary first. Accepts a doc, dict, or name."""
	if doc is None:
		return []
	if isinstance(doc, str):
		fields = ["mobile_no", "phone"]
		if _has_extra():
			fields.append("extra_phones")
		doc = frappe.db.get_value("CRM Lead", doc, fields, as_dict=True) or {}

	def _get(field):
		if isinstance(doc, dict):
			return doc.get(field)
		return getattr(doc, field, None)

	seen = set()
	out = []
	candidates = [_get("mobile_no"), _get("phone"), *_parse_extra(_get("extra_phones"))]
	for number in candidates:
		number = (number or "").strip()
		digits = last10(number)
		if not number or not digits or digits in seen:
			continue
		seen.add(digits)
		out.append(number)
	return out


def find_lead_by_phone(phone: str) -> str:
	"""Lead name whose list contains this number, or "". Newest lead wins a tie."""
	digits = last10(phone)
	if not digits:
		return ""
	fields = ["name", "mobile_no", "phone"]
	if _has_extra():
		fields.append("extra_phones")
	for row in frappe.get_all(
		"CRM Lead",
		fields=fields,
		order_by="creation desc",
		limit_page_length=0,
	):
		for number in iter_phones(row):
			if last10(number) == digits:
				return row.name
	return ""


def _serialize(lead: str) -> list[dict]:
	numbers = iter_phones(lead)
	return [
		{
			"number": number,
			"last10": last10(number),
			"primary": i == 0,
		}
		for i, number in enumerate(numbers)
	]


def _write(lead: str, numbers: list[str]) -> None:
	values = {"mobile_no": numbers[0] if numbers else ""}
	rest = numbers[1:]
	if _has_extra():
		values["extra_phones"] = json.dumps(rest)
		# Fold the leftover `phone` slot into extra_phones so the list has one home.
		if frappe.db.get_value("CRM Lead", lead, "phone"):
			values["phone"] = ""
	else:
		if len(rest) > 1:
			frappe.throw(_("This site can only store two numbers until extra phones are set up."))
		values["phone"] = rest[0] if rest else ""
	frappe.db.set_value("CRM Lead", lead, values)


def _other_owner(digits: str, lead: str) -> str:
	"""Another lead that already holds this last-10, or ""."""
	if not digits:
		return ""
	or_filters = [
		["mobile_no", "like", f"%{digits}%"],
		["phone", "like", f"%{digits}%"],
	]
	if _has_extra():
		or_filters.append(["extra_phones", "like", f"%{digits}%"])
	for row in frappe.get_all(
		"CRM Lead",
		fields=["name", "mobile_no", "phone"] + (["extra_phones"] if _has_extra() else []),
		or_filters=or_filters,
		limit_page_length=50,
	):
		if row.name == lead:
			continue
		for number in iter_phones(row):
			if last10(number) == digits:
				return row.name
	return ""


def _guard_write(lead: str) -> None:
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead {0} not found.").format(lead))
	frappe.has_permission("CRM Lead", "write", lead, throw=True)


def _to_e164(raw: str) -> str:
	digits = "".join(ch for ch in (raw or "") if ch.isdigit())
	if len(digits) == 10:
		return "+1" + digits
	if len(digits) == 11 and digits.startswith("1"):
		return "+" + digits
	if digits:
		return "+" + digits
	return ""


def _to_site_dt(iso):
	if not iso:
		return None
	aware = datetime.fromisoformat(iso.replace("Z", "+00:00"))
	utc_naive = aware.astimezone(timezone.utc).replace(tzinfo=None)
	return convert_utc_to_system_timezone(utc_naive).replace(tzinfo=None)


def _quo_headers() -> dict | None:
	token = (frappe.conf.get("quo_api_key") or "").strip()
	if not token:
		return None
	return {"Authorization": token, "User-Agent": QUO_UA}


def _workspace_lines() -> list[dict]:
	"""[{id, number, e164}] for every Quo line. Cached; live fetch, then user fallback."""
	cached = frappe.cache().get_value("crm_quo_lines_full")
	if cached:
		try:
			return json.loads(cached)
		except (TypeError, ValueError):
			pass

	lines = []
	headers = _quo_headers()
	if headers:
		try:
			resp = requests.get(
				f"{QUO_API}/v1/phone-numbers",
				headers=headers,
				timeout=QUO_TIMEOUT,
			)
			resp.raise_for_status()
			for row in (resp.json() or {}).get("data") or []:
				number = row.get("number") or ""
				if row.get("id") and last10(number):
					lines.append(
						{"id": row["id"], "number": number, "e164": _to_e164(number)}
					)
		except Exception:
			frappe.log_error(title="Quo line list failed", message=frappe.get_traceback())

	if not lines:
		for number in frappe.get_all(
			"User",
			filters={"custom_quo_number": ["is", "set"]},
			pluck="custom_quo_number",
		):
			e164 = _to_e164(number)
			if e164:
				lines.append({"id": "", "number": number, "e164": e164})

	if lines:
		frappe.cache().set_value(
			"crm_quo_lines_full", json.dumps(lines), expires_in_sec=QUO_LINES_TTL
		)
	return lines


def _quo_users() -> dict[str, str]:
	"""Quo userId → CRM User email, only where the email is a real User."""
	cached = frappe.cache().get_value("crm_quo_users")
	if cached:
		try:
			return json.loads(cached)
		except (TypeError, ValueError):
			pass
	headers = _quo_headers()
	out = {}
	if not headers:
		return out
	try:
		resp = requests.get(
			f"{QUO_API}/v1/users",
			headers=headers,
			params={"maxResults": 50},
			timeout=QUO_TIMEOUT,
		)
		resp.raise_for_status()
		crm_users = set(frappe.get_all("User", pluck="name"))
		for row in (resp.json() or {}).get("data") or []:
			email = (row.get("email") or "").strip()
			uid = row.get("id") or ""
			if uid and email and email in crm_users:
				out[uid] = email
	except Exception:
		frappe.log_error(title="Quo user list failed", message=frappe.get_traceback())
	if out:
		frappe.cache().set_value("crm_quo_users", json.dumps(out), expires_in_sec=QUO_USERS_TTL)
	return out


def _relink_existing(lead: str, digits: str) -> int:
	"""Attach already-mirrored call logs whose from/to is this number and that
	aren't owned by someone else. Returns how many newly linked."""
	if not digits:
		return 0
	linked = 0
	seen = set()
	for field in ("from", "to"):
		for row in frappe.get_all(
			"CRM Call Log",
			filters=[[field, "like", f"%{digits}%"]],
			fields=["name", "from", "to", "reference_doctype", "reference_docname"],
			limit_page_length=500,
		):
			if row.name in seen:
				continue
			seen.add(row.name)
			if last10(row.get("from")) != digits and last10(row.get("to")) != digits:
				continue
			owner = (row.reference_docname or "").strip()
			if owner and owner != lead:
				continue
			if owner == lead:
				continue
			frappe.db.set_value(
				"CRM Call Log",
				row.name,
				{"reference_doctype": "CRM Lead", "reference_docname": lead},
			)
			linked += 1
	return linked


def _list_quo_calls(phone_number_id: str, participant: str) -> list[dict]:
	headers = _quo_headers()
	if not headers or not phone_number_id or not participant:
		return []
	out = []
	page_token = None
	for _ in range(MAX_PAGES):
		params = {
			"phoneNumberId": phone_number_id,
			"participants": [participant],
			"maxResults": 100,
		}
		if page_token:
			params["pageToken"] = page_token
		resp = requests.get(
			f"{QUO_API}/v1/calls",
			headers=headers,
			params=params,
			timeout=QUO_TIMEOUT,
		)
		time.sleep(QUO_SLEEP)
		resp.raise_for_status()
		body = resp.json() or {}
		out.extend(body.get("data") or [])
		page_token = body.get("nextPageToken")
		if not page_token:
			break
	return out


def _insert_call(lead: str, call: dict, participant: str, our_no: str, quo_users: dict) -> bool:
	call_id = str(call.get("id") or "")
	if not call_id:
		return False
	existing = frappe.db.get_value(
		"CRM Call Log", {"id": call_id}, ["name", "reference_docname"], as_dict=True
	)
	if existing:
		if not (existing.reference_docname or "").strip():
			frappe.db.set_value(
				"CRM Call Log",
				existing.name,
				{"reference_doctype": "CRM Lead", "reference_docname": lead},
			)
			return True
		return False

	incoming = (call.get("direction") or "") == "incoming"
	answered = call.get("answeredAt")
	completed = call.get("completedAt")
	duration = call.get("duration") or 0
	if answered and completed:
		try:
			duration = int(
				(
					datetime.fromisoformat(completed.replace("Z", "+00:00"))
					- datetime.fromisoformat(answered.replace("Z", "+00:00"))
				).total_seconds()
			)
		except (TypeError, ValueError):
			pass

	# Same rule as the call.completed webhook (gw303): outgoing userId is the
	# dialer; incoming userId is the line owner and answeredBy is who picked up.
	# No answeredBy → leave receiver blank, do not credit the line owner.
	if incoming:
		handler = quo_users.get(str(call.get("answeredBy") or ""))
	else:
		handler = quo_users.get(str(call.get("userId") or ""))

	fields = {
		"doctype": "CRM Call Log",
		"id": call_id,
		"telephony_medium": "Manual",
		"medium": "Quo",
		"from": participant if incoming else our_no,
		"to": our_no if incoming else participant,
		"type": "Incoming" if incoming else "Outgoing",
		"status": "Completed" if answered else "No Answer",
		"duration": duration,
		"start_time": _to_site_dt(call.get("createdAt")),
		"end_time": _to_site_dt(completed),
		"reference_doctype": "CRM Lead",
		"reference_docname": lead,
	}
	if handler:
		fields["receiver" if incoming else "caller"] = handler
	frappe.get_doc(fields).insert(ignore_permissions=True)
	return True


def _publish(lead: str, digits: str, payload: dict) -> None:
	frappe.publish_realtime(
		"crm_call_log",
		{
			"reference_doctype": "CRM Lead",
			"reference_docname": lead,
			"last10": digits,
			**payload,
		},
		after_commit=True,
	)


def enqueue_backfill(lead: str, number: str) -> None:
	digits = last10(number)
	if not digits:
		return
	try:
		frappe.enqueue(
			"crm.api.lead_phones.backfill_calls_for_number",
			lead=lead,
			number=number,
			queue="short",
			job_id=f"lead-phone-backfill-{lead}-{digits}",
			deduplicate=True,
			enqueue_after_commit=True,
		)
	except TypeError:
		frappe.enqueue(
			"crm.api.lead_phones.backfill_calls_for_number",
			lead=lead,
			number=number,
			queue="short",
			enqueue_after_commit=True,
		)


def on_lead_phones_changed(doc, method=None):
	"""after_insert / on_update: backfill any number that just appeared."""
	try:
		# A LeadPack import would otherwise enqueue hundreds of Quo sweeps.
		# Parked leads are not being worked; refresh on the card still works.
		if getattr(doc, "import_hidden", None):
			return
		current = {last10(n): n for n in iter_phones(doc) if last10(n)}
		if method == "after_insert":
			added = current
		else:
			before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
			old = {last10(n) for n in iter_phones(before) if last10(n)}
			added = {d: n for d, n in current.items() if d not in old}
		for number in added.values():
			enqueue_backfill(doc.name, number)
	except Exception:
		frappe.log_error(
			title="lead_phones: on_lead_phones_changed failed",
			message=f"lead={getattr(doc, 'name', '?')}\n{frappe.get_traceback()}",
		)


@frappe.whitelist()
def get_lead_phones(lead: str) -> dict:
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead {0} not found.").format(lead))
	frappe.has_permission("CRM Lead", "read", lead, throw=True)
	return {"phones": _serialize(lead), "has_extra": _has_extra()}


@frappe.whitelist()
def add_lead_phone(lead: str, number: str) -> dict:
	"""Add a number and kick off Quo backfill. Relinks existing logs immediately."""
	_guard_write(lead)
	number = (number or "").strip()
	digits = last10(number)
	if not digits:
		frappe.throw(_("That does not look like a phone number."))

	existing = iter_phones(lead)
	if any(last10(n) == digits for n in existing):
		enqueue_backfill(lead, number)
		linked = _relink_existing(lead, digits)
		return {
			"phones": _serialize(lead),
			"has_extra": _has_extra(),
			"linked": linked,
			"queued": True,
			"already": True,
		}

	other = _other_owner(digits, lead)
	if other:
		frappe.throw(_("That number is already on lead {0}.").format(other))

	if not _has_extra() and len(existing) >= 2:
		frappe.throw(_("This site can only store two numbers until extra phones are set up."))

	_write(lead, existing + [number])
	linked = _relink_existing(lead, digits)
	enqueue_backfill(lead, number)
	return {
		"phones": _serialize(lead),
		"has_extra": _has_extra(),
		"linked": linked,
		"queued": True,
	}


@frappe.whitelist()
def remove_lead_phone(lead: str, number: str) -> dict:
	_guard_write(lead)
	digits = last10(number)
	if not digits:
		frappe.throw(_("That does not look like a phone number."))
	kept = [n for n in iter_phones(lead) if last10(n) != digits]
	if len(kept) == len(iter_phones(lead)):
		frappe.throw(_("That number is not on this lead."))
	_write(lead, kept)
	return {"phones": _serialize(lead), "has_extra": _has_extra()}


@frappe.whitelist()
def set_primary_phone(lead: str, number: str) -> dict:
	_guard_write(lead)
	digits = last10(number)
	numbers = iter_phones(lead)
	match = next((n for n in numbers if last10(n) == digits), None)
	if not match:
		frappe.throw(_("That number is not on this lead."))
	_write(lead, [match] + [n for n in numbers if last10(n) != digits])
	return {"phones": _serialize(lead), "has_extra": _has_extra()}


@frappe.whitelist()
def backfill_calls_for_number(lead: str, number: str) -> dict:
	"""Fetch Quo calls for one number and insert them oldest-first.

	Also the worker entry. Relinks existing unlinked logs first, then pages
	`/v1/calls` per workspace line. Safe to re-run (dedupes on Quo call id).
	"""
	if frappe.session.user not in ("Administrator", "Guest"):
		frappe.has_permission("CRM Lead", "write", lead, throw=True)
	if not frappe.db.exists("CRM Lead", lead):
		return {"ok": False, "error": "lead not found"}

	digits = last10(number)
	participant = _to_e164(number)
	if not digits or not participant:
		return {"ok": False, "error": "bad number"}

	try:
		linked = _relink_existing(lead, digits)
		created = 0
		headers = _quo_headers()
		if not headers:
			_publish(lead, digits, {"created": 0, "linked": linked, "error": "quo not configured"})
			return {"ok": True, "created": 0, "linked": linked, "error": "quo not configured"}

		quo_users = _quo_users()
		# Collect every new call across every line, then insert oldest-first so
		# the timeline is chronological even if autoname were sequential.
		pending = []
		seen_ids = set()
		for line in _workspace_lines():
			if not line.get("id"):
				continue
			for call in _list_quo_calls(line["id"], participant):
				cid = str(call.get("id") or "")
				if not cid or cid in seen_ids:
					continue
				seen_ids.add(cid)
				pending.append((call, line.get("e164") or line.get("number") or ""))

		def _when(item):
			return item[0].get("createdAt") or ""

		pending.sort(key=_when)
		for call, our_no in pending:
			if _insert_call(lead, call, participant, our_no, quo_users):
				created += 1

		_publish(lead, digits, {"created": created, "linked": linked})
		return {"ok": True, "created": created, "linked": linked}
	except Exception as exc:
		frappe.log_error(
			title="lead_phones: Quo backfill failed",
			message=f"lead={lead} number={number}\n{frappe.get_traceback()}",
		)
		_publish(lead, digits, {"created": 0, "linked": 0, "error": str(exc)[:200]})
		return {"ok": False, "error": str(exc)[:200]}
