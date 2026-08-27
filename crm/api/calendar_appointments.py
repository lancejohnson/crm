# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Seller appointments, read from the closer's Google Calendar.

**Why not from the CRM.** The Today card carries a "Booked an Appointment"
outcome, and it is the natural place to count this from. It does not work, and
this is measured rather than assumed. Over 2026-07-30..08-12 the calendar holds
53 seller appointments while the card outcome recorded 13 — 25% of reality:

    creator     real (calendar)   logged on cards
    German                   36                13     36%
    Exe                      13                 0      0%
    Dennis                    4                 -

Exe's thirteen were the case that exposed it: he books appointments and records
them either as a free-text SKIP note ("Scheduled for Thursday") or as a plain
`Connected` — his own call transcript has him saying "I'll schedule you for the
afternoon then" on a card marked Connected. And a **Skipped card structurally
cannot carry an outcome** (`today_board` forces `outcome = ""` on skip), so when
a rep skips a card *because* the lead is already booked, the CRM offers nowhere
to say so. German under-records by the same margin, so this is a property of the
tool, not of a person.

The calendar is where the work actually lands: the team creates the event to put
the seller in front of the closer, so an unbooked appointment simply does not
exist there. That is why it is trustworthy and the card outcome is not.

**The `(S)` prefix is a convention, not a schema**, and conventions drift. Every
seller appointment is titled `(S) <name> - <city>`, so that is the filter — but
`unmatched` counts the events that were skipped for not matching, so the day the
convention slips it shows up as a number instead of as a silent undercount.

**Credentials — two ways, and the tighter one is preferred.**

1. *Share the calendar* (recommended). Share the closer's calendar read-only
   with the existing `crm-underwriting` service account's address. Nothing new
   goes into site config, no impersonation happens, and the CRM's reach grows by
   exactly one calendar.
2. *Domain-wide delegation*. Set `appointment_calendar_subject` and the
   **workspace-admin** service account key, which can impersonate a user. This
   works without touching Google sharing settings, but that key can impersonate
   ANY user in the domain for every scope it is granted — a much larger blast
   radius to park in a production config file for the sake of one read.

The code takes whichever is configured, preferring an explicit
`google_calendar_sa_json` over the shared `google_sa_json`, and only sends a
`sub` claim when a subject is set. Absent any of it, everything here degrades to
"unavailable" and the report omits appointments rather than failing.
"""

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import frappe
import jwt
import requests
from frappe.utils import convert_utc_to_system_timezone, getdate

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
TIMEOUT = 20

#: Whose calendar the appointments land on — the closer's. Also the calendar ID,
#: so this works whether we impersonate them or they shared it with us.
DEFAULT_CALENDAR = "dennis.szafran@groundworkpro.com"

#: How the team titles a seller appointment.
DEFAULT_PREFIX = "(S)"

#: An appointment is created for a date that can be well ahead of the booking —
#: the widest observed gap was 11 days, but the API window filters on the event's
#: START, so it has to be generous enough that a far-future booking made today is
#: still seen. Filtering to "created on the report day" happens in Python.
LOOKBACK_DAYS = 7
LOOKAHEAD_DAYS = 180


def _conf():
	# An explicit calendar key wins; otherwise reuse the service account the CRM
	# already carries, which is enough when the calendar has been shared with it.
	raw = frappe.conf.get("google_calendar_sa_json") or frappe.conf.get("google_sa_json")
	if not raw:
		return None
	try:
		sa = json.loads(raw) if isinstance(raw, str) else raw
	except (TypeError, ValueError):
		return None
	if not (sa.get("client_email") and sa.get("private_key")):
		return None
	return sa


def _token():
	"""Access token for the Calendar read.

	The `sub` claim is sent ONLY when `appointment_calendar_subject` is set, which
	is what selects impersonation. Left unset (the recommended setup) the service
	account acts as itself and can see the calendar purely because it was shared
	with it — same present-but-empty-subject convention `underwriting.py` uses.
	"""
	sa = _conf()
	if not sa:
		return None
	now = int(time.time())
	claim = {
		"iss": sa["client_email"],
		"scope": SCOPE,
		"aud": sa.get("token_uri") or GOOGLE_TOKEN_URI,
		"iat": now,
		"exp": now + 3600,
	}
	subject = (frappe.conf.get("appointment_calendar_subject") or "").strip()
	if subject:
		claim["sub"] = subject
	assertion = jwt.encode(claim, sa["private_key"], algorithm="RS256")
	resp = requests.post(
		sa.get("token_uri") or GOOGLE_TOKEN_URI,
		data={
			"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
			"assertion": assertion,
		},
		timeout=TIMEOUT,
	)
	resp.raise_for_status()
	return resp.json()["access_token"]


def _to_site_date(stamp):
	"""RFC3339 UTC -> a calendar DATE in site time.

	The conversion is the whole point: an appointment booked at 6:30pm Chicago is
	stamped 23:30Z, and one booked at 9pm Chicago is stamped the NEXT day in UTC.
	Bucketing on the raw string would move a chunk of every evening's bookings
	onto the following day's report.
	"""
	if not stamp:
		return None
	text = stamp.strip().replace("Z", "+00:00")
	try:
		aware = datetime.fromisoformat(text)
	except ValueError:
		return None
	naive_utc = aware.astimezone(timezone.utc).replace(tzinfo=None)
	return getdate(convert_utc_to_system_timezone(naive_utc))


def _fetch_events(day):
	calendar = frappe.conf.get("appointment_calendar") or DEFAULT_CALENDAR
	token = _token()
	if not token:
		return None
	lo = (datetime.combine(day, datetime.min.time()) - timedelta(days=LOOKBACK_DAYS))
	hi = (datetime.combine(day, datetime.min.time()) + timedelta(days=LOOKAHEAD_DAYS))
	events, page = [], None
	while True:
		params = {
			"timeMin": lo.isoformat() + "Z",
			"timeMax": hi.isoformat() + "Z",
			"singleEvents": "true",
			"orderBy": "startTime",
			"maxResults": 250,
		}
		if page:
			params["pageToken"] = page
		resp = requests.get(
			f"{CALENDAR_API}/calendars/{calendar}/events",
			headers={"Authorization": f"Bearer {token}"},
			params=params,
			timeout=TIMEOUT,
		)
		resp.raise_for_status()
		body = resp.json()
		events.extend(body.get("items") or [])
		page = body.get("nextPageToken")
		if not page:
			break
	return events


def get_appointments(day):
	"""Seller appointments CREATED on `day`, grouped by the person who booked.

	Never raises: a Google outage, an expired key or a missing config degrades to
	`available: False` and the report omits the section rather than failing. An
	appointment count that silently reads zero would be worse than none at all,
	so `reason` always says why.
	"""
	day = getdate(day)
	out = {
		"available": False, "reason": "", "by_user": {}, "total": 0,
		"cancelled": 0, "unmatched": 0,
	}
	if not _conf():
		out["reason"] = "no google service account in site config"
		return out

	prefix = frappe.conf.get("appointment_prefix") or DEFAULT_PREFIX
	try:
		events = _fetch_events(day)
	except Exception:
		frappe.log_error(
			title="daily outreach: calendar fetch failed",
			message=frappe.get_traceback(),
		)
		out["reason"] = "calendar unavailable"
		return out
	if events is None:
		out["reason"] = "could not authenticate to Google"
		return out

	by_user = defaultdict(list)
	for event in events:
		if _to_site_date(event.get("created")) != day:
			continue
		summary = (event.get("summary") or "").strip()
		if not summary.startswith(prefix):
			# Counted, so a drifting title convention shows up as a number
			# rather than as a silent undercount.
			out["unmatched"] += 1
			continue
		if event.get("status") == "cancelled":
			out["cancelled"] += 1
			continue
		creator = (event.get("creator") or {}).get("email") or ""
		if not creator:
			continue
		start = event.get("start") or {}
		by_user[creator].append({
			"summary": summary[len(prefix):].strip(" -–:"),
			"meets": (start.get("dateTime") or start.get("date") or "")[:10],
		})
		out["total"] += 1

	out["available"] = True
	out["by_user"] = dict(by_user)
	return out


@frappe.whitelist()
def preview_appointments(for_date=None):
	"""Read-only check that the calendar wiring works. Sales-manager gated."""
	if frappe.session.user != "Administrator":
		roles = set(frappe.get_roles())
		if not roles & {"System Manager", "Sales Manager"}:
			frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
	from frappe.utils import now_datetime

	data = get_appointments(for_date or getdate(now_datetime()))
	return {
		"date": str(getdate(for_date or now_datetime())),
		"available": data["available"],
		"reason": data["reason"],
		"total": data["total"],
		"unmatched": data["unmatched"],
		"cancelled": data["cancelled"],
		"by_user": {u: len(v) for u, v in data["by_user"].items()},
		"detail": data["by_user"],
	}
