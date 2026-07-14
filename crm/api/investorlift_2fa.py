"""Auto-retrieve an InvestorLift 2FA login code from our own OpenPhone line.

InvestorLift's admin login (`crm/api/investorlift.py`) *sometimes* SMS-challenges a
verification code to Lance's Quo line **(651) 390-7073**. That line lives in the same
OpenPhone/Quo workspace as our `quo_api_key`, so we can read its inbound texts over
the OpenPhone API and pull the code out — no human in the loop.

The tricky part is *not* grabbing the wrong text. That line also receives unrelated
notifications (e.g. "Property Leads" missed-call texts full of street numbers), so the
extractor:
  - only considers conversations touched *after* the login attempt started (`since_ts`),
  - only reads their **incoming** messages newer than `since_ts`,
  - prefers a message that mentions a code/verification/InvestorLift/OTP, and
  - pulls a standalone 4–8 digit token out of it.

If auto-retrieval fails (no matching text within the window), the caller falls back to
a manual code Lance types into Settings → InvestorLift.
"""

import re

import requests

import frappe

OPENPHONE_BASE = "https://api.openphone.com/v1"
# The Quo line InvestorLift texts the 2FA code to. Config-overridable in case the
# number ever changes; the phoneNumberId is resolved from it at call time.
DEFAULT_2FA_NUMBER = "+16513907073"
# A message is a strong code candidate if it mentions any of these.
CODE_HINT = re.compile(r"code|verif|investorlift|invest\s*lift|otp|one[-\s]?time|login", re.I)
# A standalone verification token: 4–8 digits not glued to other digits.
CODE_TOKEN = re.compile(r"(?<!\d)(\d{4,8})(?!\d)")


def _digits(s):
	return "".join(ch for ch in (s or "") if ch.isdigit())


def _headers():
	token = (frappe.conf.get("quo_api_key") or "").strip()
	if not token:
		frappe.log_error("quo_api_key not set in site_config", "InvestorLift 2FA")
		return None
	return {"Authorization": token, "User-Agent": "curl/8.1.0"}


def _resolve_phone_number_id(headers, number):
	"""Map the configured 2FA number to its OpenPhone phoneNumberId (required by the
	/messages endpoint). Matched on last-10 digits so formatting differences don't bite."""
	want = _digits(number)[-10:]
	try:
		r = requests.get(f"{OPENPHONE_BASE}/phone-numbers", headers=headers, timeout=20)
		for p in (r.json().get("data") or []):
			if _digits(p.get("number"))[-10:] == want:
				return p.get("id")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "InvestorLift 2FA: phone-number lookup failed")
	return None


def _parse_iso(ts):
	"""ISO8601 (e.g. '2026-07-13T03:33:06.963Z') → epoch seconds, or None."""
	if not ts:
		return None
	try:
		from datetime import datetime

		return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
	except (ValueError, TypeError):
		return None


def _extract_code(text):
	"""Pull a verification code out of a candidate SMS body, or None."""
	if not text:
		return None
	# Prefer a token adjacent to a hint word ("code: 123456", "your InvestorLift code is 123456").
	for m in CODE_TOKEN.finditer(text):
		window = text[max(0, m.start() - 24) : m.end() + 4]
		if CODE_HINT.search(window):
			return m.group(1)
	# Otherwise, if the whole message reads like a code notice, take the first token.
	if CODE_HINT.search(text):
		m = CODE_TOKEN.search(text)
		if m:
			return m.group(1)
	return None


def fetch_2fa_code(since_ts, timeout=120, interval=6):
	"""Poll the 2FA OpenPhone line for a verification code sent after `since_ts`.

	`since_ts` = epoch seconds captured just before the login POST. Returns the code
	string or None if none arrived within `timeout` seconds.
	"""
	headers = _headers()
	if not headers:
		return None
	number = (frappe.conf.get("investorlift_2fa_number") or DEFAULT_2FA_NUMBER).strip()
	pn_id = _resolve_phone_number_id(headers, number)
	if not pn_id:
		frappe.log_error(f"could not resolve phoneNumberId for {number}", "InvestorLift 2FA")
		return None

	import time

	deadline = time.time() + timeout
	while time.time() < deadline:
		time.sleep(interval)
		try:
			convos = requests.get(
				f"{OPENPHONE_BASE}/conversations",
				params={"phoneNumbers": [number], "maxResults": 10},
				headers=headers,
				timeout=20,
			).json().get("data", [])
		except Exception:
			continue
		for c in convos:
			updated = _parse_iso(c.get("updatedAt") or c.get("lastActivityAt"))
			if updated is None or updated < since_ts:
				continue
			participants = c.get("participants") or []
			if not participants:
				continue
			try:
				msgs = requests.get(
					f"{OPENPHONE_BASE}/messages",
					params={"phoneNumberId": pn_id, "participants": participants, "maxResults": 10},
					headers=headers,
					timeout=20,
				).json().get("data", [])
			except Exception:
				continue
			for m in msgs:
				if m.get("direction") != "incoming":
					continue
				created = _parse_iso(m.get("createdAt"))
				if created is not None and created < since_ts:
					continue
				code = _extract_code(m.get("text") or m.get("content") or "")
				if code:
					return code
	return None
