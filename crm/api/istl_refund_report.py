"""iSpeedToLead refund-eligibility call report (Groundwork).

ISTL refunds a lead (typically $29) when it was NOT bought on a sale balance
and the team placed **five double-dials within ten days** of delivery. The
operating cadence is one double-dial every other day for those ten days.

This module emails a short digest twice on business days:

  * **8:00am** — which in-window leads are due / behind pace (call them today),
    plus any leads that *became* refund-ineligible since the last business-day
    report and the $ lost on them.
  * **3:00pm** — which of today's due leads still have no outbound call logged
    today, while there's still afternoon left to fix it.

Double-dial counting: outbound `CRM Call Log` rows on the lead are clustered
when successive dials are ≤ ``DOUBLE_DIAL_GAP_SECONDS`` apart; a cluster of
≥2 dials counts as one double-dial attempt. Lone single dials are shown but
do not count toward the five (ISTL wants double dials).

Sale-balance purchases: the iSpeedToLead webhook does not currently flag
them, so every `source=iSpeedToLead` lead is treated as refund-eligible.
If that signal lands later, filter in ``_is_refund_eligible``.

Scheduler (hooks.py cron): ``0 8 * * 1-5`` and ``0 15 * * 1-5``. Frappe
evaluates cron in the SITE timezone (System Settings = America/Chicago) —
``is_event_due`` compares against ``now_datetime()`` — so those are plain local
times and DST handles itself. Do NOT pre-convert to UTC.

After deploy:
``bench execute frappe.core.doctype.scheduled_job_type.scheduled_job_type.sync_jobs``
so the cron rows land — same gotcha as the integrity-report / seqdrain hooks.
(`sync_jobs` rewrites frequency/cron on an existing row, so schedule changes do
apply to already-registered jobs.)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, get_url, getdate

# --- config -------------------------------------------------------------------

# The `CRM Lead Source` row every ISTL lead is stamped with (set by the
# iSpeedToLead webhook). This report applies to NOTHING else — other vendors
# (PropertyLeads, Red Panda) have no double-dial refund deal.
SOURCE = "iSpeedToLead"


def is_istl(source) -> bool:
	"""Case/space-insensitive source match.

	MariaDB compares with a ``_ci`` collation, so the SQL filter behind the email
	matches 'ispeedtolead' too — but Python ``==`` would not, which would let the
	board and the email disagree about the same lead. Normalize both sides.
	"""
	return str(source or "").strip().casefold() == SOURCE.casefold()
WINDOW_DAYS = 10
REQUIRED_DOUBLE_DIALS = 5
# Successive outbound dials within this many seconds count as one double-dial
# attempt. Live data shows the pair ~15–60s apart; 3 min leaves room for a
# redial without merging afternoon follow-ups into the morning attempt.
DOUBLE_DIAL_GAP_SECONDS = 180
DEFAULT_REFUND_AMOUNT = 29.0
TZ = ZoneInfo("America/Chicago")

# Digest recipient(s). Override via site_config `istl_report_recipients` (list
# or comma-separated string) without a code change.
DEFAULT_RECIPIENTS = ["lance.johnson@groundworkpro.com"]

# Mattermost incoming webhook (site_config `istl_mattermost_webhook`). Locked to
# the #acq channel on the Mattermost side, so this can only ever post there.
# Unset = no chat post, email only.
MATTERMOST_WEBHOOK_KEY = "istl_mattermost_webhook"
MATTERMOST_TIMEOUT = 15
# Keep the post scannable on a phone; the rest is a click away in the CRM.
MAX_CHAT_ROWS = 15

# --- status policy ------------------------------------------------------------
# The real `CRM Lead Status` ladder, in pipeline order:
#   New · Called No Answer · Follow Up · Underwriting · Make Offer · Contract Sent
#   · Signed Contract · Photos & Lockbox In Progress · Needs Listing
#   · Marketing to Buyer · Buyer Assigned · Future Follow Up · Dead Lead · Lost · Won
#
# Only leads we are still trying to REACH belong in this report. Once a lead is
# in underwriting or beyond, the refund is moot (we got what we paid for); once
# it's dead/lost/won, more dials are pointless.

# Still chasing a conversation → the only statuses the report acts on.
# "Future Follow Up" stays in: it's a deliberate callback-later state and those
# leads still need the dials logged inside the 10-day window.
WORKABLE_STATUSES = {
	"New",
	"Called No Answer",
	"Follow Up",
	"Future Follow Up",
}

# We reached them and the deal moved — underwriting through dispo. The lead did
# its job; a refund is irrelevant. Never chased, never counted as a loss.
IN_DEAL_STATUSES = {
	"Underwriting",
	"Make Offer",
	"Contract Sent",
	"Signed Contract",
	"Photos & Lockbox In Progress",
	"Needs Listing",
	"Marketing to Buyer",
	"Buyer Assigned",
}

# Over, one way or another. No more dialing.
CLOSED_STATUSES = {"Dead Lead", "Lost", "Won"}

# --- "did we actually have a CONVERSATION?" -------------------------------------
# A voicemail is NOT a conversation. Call duration can't tell them apart: a
# 90-second call can be a long voicemail greeting, and a genuine "we already
# sold it, take me off your list" can be 13 seconds. So we read the diarized
# transcript (`custom_transcript`, ~91% coverage on ISTL calls) and judge what
# the OTHER PARTY actually said.
#
# Voicemail greetings play in the opening seconds, so the greeting patterns are
# only matched inside GREETING_WINDOW. Matching the whole transcript produced
# false negatives — e.g. an 841s call where a screening service answered first
# and the seller then talked for minutes, and a call where the lead *described*
# a voicemail ordeal mid-conversation. If a human keeps talking substantively
# after the greeting, it counts as a conversation (screened, then reached).
GREETING_WINDOW_SECONDS = 30.0

_VOICEMAIL_PATTERNS = [
	r"leave (me |a |your )?(brief |detailed )?message",
	r"leave your (name|number|message)",
	r"after the (tone|beep)", r"at the tone",
	r"record your (name|message)",
	r"i'?ll see if this person is available", r"call assistant",
	r"is not available", r"can'?t take your call", r"can'?t get to (my|the) phone",
	r"please (leave|record|state|press)",
	r"voice ?mail", r"voice messaging", r"mailbox",
	r"you have reached", r"you'?ve reached", r"the person you'?ve dialed",
	r"subscriber at", r"is unavailable", r"missed your call",
	r"no longer in service", r"forwarded to (an? )?(automated |)voice",
	r"youmail", r"telephone number", r"press \d to", r"to connect your call",
	# Spanish / Portuguese greetings seen in the live data
	r"buz[oó]n", r"oprima", r"deixa", r"liga o message",
]
VOICEMAIL_RE = re.compile("|".join(_VOICEMAIL_PATTERNS), re.I)

# Greetings and acknowledgements. A lead who only says these hasn't had a
# conversation — it's the pickup-then-hangup / hold-please pattern.
_FILLER_WORDS = {
	"hello", "hi", "hey", "yes", "yeah", "yep", "no", "okay", "ok", "alright",
	"mhmm", "uh-huh", "mm-hmm", "sure", "bye", "goodbye", "thanks", "thank",
	"what", "huh", "speaking", "sorry", "for", "calling",
	"a", "the", "i", "you", "it", "is", "and", "to", "that", "s", "t", "m",
}

# Below BOTH of these, the other party said nothing of substance.
MIN_CONVERSATION_SECONDS = 8
MIN_CONVERSATION_WORDS = 10
# Substantive words spoken AFTER a voicemail greeting that still count as
# "a screening service answered, then we reached a human".
MIN_POST_GREETING_WORDS = 15

# Fallback for calls with no transcript (~9%): only a long call is assumed to be
# a conversation. Deliberately generous — we'd rather keep chasing a lead than
# wrongly drop it off the list.
NO_TRANSCRIPT_CONVERSATION_SECONDS = 120

# Back-compat: older callers referenced this name.
ACTIVE_DEAL_STATUSES = IN_DEAL_STATUSES


# ---------------------------------------------------------------------------------
# Scheduler entry points
# ---------------------------------------------------------------------------------


def run_morning_report():
	"""Weekday morning cron: due / at-risk leads + newly ineligible $ loss."""
	_run_safe("morning")


def run_eod_report():
	"""Weekday 3pm cron: today's due leads that still have no call logged.

	Name kept as `eod` (not `afternoon`) because the Scheduled Job Type row is
	keyed on this dotted path — renaming it would orphan the registered job.
	"""
	_run_safe("eod")


def _run_safe(when: str):
	"""Never raise out of a scheduler job."""
	try:
		# Cron is Mon–Fri UTC; still guard so a manual weekend run is honest.
		today = _today()
		if today.weekday() >= 5:
			frappe.logger("istl_refund_report").info(f"skip {when}: weekend {today}")
			return
		report = build_report(when=when, on_date=today)
		_send_email(report)
		_send_mattermost(report)
		frappe.logger("istl_refund_report").info(
			f"ISTL {when} report {today}: due={len(report['due'])} "
			f"uncalled={len(report['uncalled_today'])} "
			f"new_ineligible={len(report['newly_ineligible'])} "
			f"lost=${report['lost_amount']:.0f}"
		)
	except Exception:
		frappe.log_error(
			title=f"ISTL refund report ({when}) failed",
			message=frappe.get_traceback(),
		)


@frappe.whitelist()
def run_report_now(
	when: str = "morning",
	send_email: int = 1,
	on_date: str | None = None,
	post_chat: int = 0,
):
	"""Manual / test entry. Sales User+.

	``when``      ``morning`` | ``eod``
	``send_email`` 1 = actually email it
	``post_chat``  1 = actually post to #acq (defaults OFF so a backtest can't
	               spam the channel)
	``on_date``    YYYY-MM-DD, freezes "today" for backtesting
	"""
	if not _can_run_manual():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	when = (when or "morning").strip().lower()
	if when not in ("morning", "eod"):
		frappe.throw(_("when must be 'morning' or 'eod'"))
	day = getdate(on_date) if on_date else _today()
	report = build_report(when=when, on_date=day)
	if int(send_email or 0):
		_send_email(report)
	if int(post_chat or 0):
		_send_mattermost(report)
	# Strip nothing sensitive; this is the same payload the email uses.
	return report


@frappe.whitelist()
def preview_chat_post(when: str = "morning", on_date: str | None = None):
	"""Exact text that WOULD be posted to #acq, without posting it."""
	if not _can_run_manual():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	when = (when or "morning").strip().lower()
	day = getdate(on_date) if on_date else _today()
	return _chat_text(build_report(when=when, on_date=day))


def _can_run_manual() -> bool:
	user = frappe.session.user
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	return bool(roles & {"System Manager", "Sales Manager", "Sales User"})


# ---------------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------------


def build_report(when: str = "morning", on_date=None) -> dict:
	"""Pure builder — no email side effects. Safe to call from bench/console."""
	today = getdate(on_date) if on_date else _today()
	prev_biz = _prev_business_day(today)

	leads = _load_istl_leads(today)
	rows = [_enrich(lead, today) for lead in leads]

	# Only chase leads we're still trying to reach. In-deal (underwriting →
	# dispo) means the lead already paid off; dead/lost/won means dialing is
	# over. Both are excluded from the chase lists AND the $ tally.
	in_window = [
		r
		for r in rows
		if r["in_window"]
		and r["double_dials"] < REQUIRED_DOUBLE_DIALS
		and r["is_workable"]
	]
	due = [r for r in in_window if r["due_today"]]
	due_names = {r["name"] for r in due}
	# Behind pace but not necessarily "due" today (e.g. called yesterday, still short)
	behind = [r for r in in_window if r["behind_pace"] and r["name"] not in due_names]
	uncalled_today = [r for r in due if not r["called_today"]]

	# $ loss only on the morning digest — EOD would otherwise re-list the same
	# leads (prev_business_day is unchanged between morning and eod the same day).
	if when == "morning":
		newly_ineligible = _newly_ineligible(rows, today, prev_biz)
		gave_up_early = _gave_up_early(rows, today, prev_biz)
	else:
		newly_ineligible = []
		gave_up_early = []
	lost_amount = sum(r["refund_amount"] for r in newly_ineligible)
	gave_up_amount = sum(r["refund_amount"] for r in gave_up_early)

	# Sort: fewest days left, then fewest dials, then oldest.
	def _sort_key(r):
		return (r["days_left"], r["double_dials"], r["creation"])

	due.sort(key=_sort_key)
	behind.sort(key=_sort_key)
	uncalled_today.sort(key=_sort_key)
	called_today = [r for r in due if r["called_today"]]
	called_today.sort(key=_sort_key)
	newly_ineligible.sort(key=lambda r: r["window_end"], reverse=True)
	gave_up_early.sort(key=lambda r: (r["double_dials"], r["lead_name"]))

	return {
		"when": when,
		"date": str(today),
		"prev_business_day": str(prev_biz),
		"window_days": WINDOW_DAYS,
		"required_double_dials": REQUIRED_DOUBLE_DIALS,
		"default_refund_amount": DEFAULT_REFUND_AMOUNT,
		"in_window_count": len(in_window),
		"due": due,
		"behind": behind,
		"uncalled_today": uncalled_today,
		"called_today": called_today,
		"newly_ineligible": newly_ineligible,
		"lost_amount": lost_amount,
		"lost_count": len(newly_ineligible),
		"gave_up_early": gave_up_early,
		"gave_up_amount": gave_up_amount,
		"gave_up_count": len(gave_up_early),
	}


def _load_istl_leads(today) -> list[dict]:
	"""ISTL leads whose window is still open OR just closed since a lookback.

	Lookback = WINDOW_DAYS + 4 so a Monday morning still sees Friday/Sat/Sun
	expiries (newly ineligible), without scanning the whole lead table.
	"""
	lookback_start = today - timedelta(days=WINDOW_DAYS + 4)
	# Also keep a little future-proofing if creation timestamps are ahead.
	fields = [
		"name",
		"lead_name",
		"first_name",
		"last_name",
		"creation",
		"modified",
		"status",
		"lead_cost",
		"campaign_name",
		"property_address",
		"mobile_no",
		"lead_owner",
	]
	# lead_cost / campaign_name are custom — guard so an unprovisioned site
	# still runs (just without those columns).
	meta = frappe.get_meta("CRM Lead")
	standard = (
		"name", "lead_name", "first_name", "last_name", "creation",
		"modified", "status", "mobile_no", "lead_owner",
	)
	fields = [f for f in fields if f in standard or meta.has_field(f)]

	return frappe.get_all(
		"CRM Lead",
		filters={
			"source": SOURCE,
			"creation": [">=", f"{lookback_start} 00:00:00"],
		},
		fields=fields,
		order_by="creation asc",
		limit_page_length=500,
	)


def _enrich(lead: dict, today) -> dict:
	created = getdate(lead.get("creation"))
	age_days = (today - created).days  # 0 on delivery day
	in_window = 0 <= age_days < WINDOW_DAYS
	days_left = max(0, WINDOW_DAYS - age_days)  # includes today while in window
	window_end = created + timedelta(days=WINDOW_DAYS - 1)

	calls = _outbound_calls(lead["name"])
	clusters = _cluster_calls(calls)
	double_dials = sum(1 for c in clusters if c["dials"] >= 2)
	single_dials = sum(1 for c in clusters if c["dials"] == 1)
	# Did we ever actually TALK WITH them? Voicemails don't count, no matter how
	# long. Short-circuits on the first hit so a lead we reached early costs one
	# transcript read, not one per call.
	longest_call = max([c["duration"] for c in calls], default=0)
	connected = False
	for call in calls:
		if _had_conversation(call):
			connected = True
			break
	attempt_dates = [c["date"] for c in clusters if c["dials"] >= 2]
	last_double_dial_date = max(attempt_dates) if attempt_dates else None
	call_dates = sorted({getdate(c["start"]) for c in calls}) if calls else []
	called_today = today in call_dates
	last_call_date = call_dates[-1] if call_dates else None

	remaining_attempts = max(0, REQUIRED_DOUBLE_DIALS - double_dials)
	# Every-other-day pace: by the morning of day `age_days` we should already
	# have floor(age_days / 2) double-dials done (called on days 0,2,4,…).
	expected_by_start_of_day = min(REQUIRED_DOUBLE_DIALS, age_days // 2)
	behind_pace = in_window and double_dials < expected_by_start_of_day

	# Due today if we still need dials and either:
	#   - never double-dialed,
	#   - last double-dial was ≥2 days ago (every-other-day cadence),
	#   - behind pace, or
	#   - remaining attempts ≥ remaining days (must call every day to finish).
	due_today = False
	if in_window and remaining_attempts > 0:
		days_since_dd = (
			(today - last_double_dial_date).days if last_double_dial_date else None
		)
		must_call_daily = remaining_attempts >= days_left
		cadence_due = days_since_dd is None or days_since_dd >= 2
		due_today = must_call_daily or cadence_due or behind_pace

	refund_amount = _refund_amount(lead)
	display = (
		lead.get("lead_name")
		or " ".join(x for x in [lead.get("first_name"), lead.get("last_name")] if x)
		or lead["name"]
	)
	status = lead.get("status") or ""
	in_deal = status in IN_DEAL_STATUSES
	is_closed = status in CLOSED_STATUSES
	# Once we've had a real conversation the lead is off the chase list — we
	# reached the seller, which is the whole point of the dials. (A voicemail is
	# not a conversation, so those leads keep getting chased.)
	# Unknown/new statuses default to workable rather than silently dropping a
	# lead we paid for (a renamed status shouldn't make it invisible).
	is_workable = not in_deal and not is_closed and not connected

	return {
		"name": lead["name"],
		"lead_name": display,
		"link": _lead_url(lead["name"]),
		"status": status,
		"creation": str(lead.get("creation")),
		"modified": str(lead.get("modified") or lead.get("creation")),
		"created_date": str(created),
		"age_days": age_days,
		"days_left": days_left,
		"window_end": str(window_end),
		"in_window": in_window,
		"double_dials": double_dials,
		"single_dials": single_dials,
		"total_outbound_dials": len(calls),
		"remaining_attempts": remaining_attempts,
		"expected_by_start_of_day": expected_by_start_of_day,
		"behind_pace": behind_pace,
		"due_today": due_today,
		"called_today": called_today,
		"last_double_dial_date": str(last_double_dial_date) if last_double_dial_date else None,
		"last_call_date": str(last_call_date) if last_call_date else None,
		"refund_amount": refund_amount,
		"campaign_name": lead.get("campaign_name") or "",
		"property_address": lead.get("property_address") or "",
		"lead_owner": lead.get("lead_owner") or "",
		"longest_call": longest_call,
		"connected": connected,
		"in_deal": in_deal,
		"is_closed": is_closed,
		"is_workable": is_workable,
		# kept for back-compat with anything reading the old key
		"is_active_deal": in_deal,
	}


def _newly_ineligible(rows: list[dict], today, prev_biz) -> list[dict]:
	"""Leads whose 10-day window ended since the previous business-day report
	and who finished with fewer than 5 double-dials.

	Window ended on ``window_end`` (creation + 9 days); the first ineligible
	day is the next calendar day. A Monday report (prev_biz=Friday) therefore
	picks up Fri/Sat/Sun expiries. EOD on the last eligible day still treats
	them as in-window — ineligible only flips the morning after ``window_end``.

	Only counts leads that were still WORKABLE when the window closed. A lead
	that reached underwriting/dispo got what we paid for, and one already
	closed out (dead/lost/won) is covered by the separate "gave up early"
	section — counting it here would double-bill the same $29.
	"""
	out = []
	for r in rows:
		if r["double_dials"] >= REQUIRED_DOUBLE_DIALS:
			continue
		if not r["is_workable"]:
			continue
		window_end = getdate(r["window_end"])
		if window_end < today and window_end >= prev_biz:
			item = dict(r)
			item["reason"] = _ineligible_reason(r)
			out.append(item)
	return out


def _gave_up_early(rows: list[dict], today, prev_biz) -> list[dict]:
	"""Leads marked Dead/Lost since the last business day that we never actually
	talked to AND never dialed enough to earn the refund.

	This is the expensive pattern: we paid for the lead, never reached a human,
	gave up before the 5 double-dials, and forfeited the refund on the way out —
	so we ate the cost twice. Won is excluded (a win is a win). It's a coaching
	signal, not a chase list; the leads are already closed.
	"""
	candidates = [
		r
		for r in rows
		if r["status"] in ("Dead Lead", "Lost")
		and r["double_dials"] < REQUIRED_DOUBLE_DIALS
		# Reached them and they said no → a legitimate close, not a give-up.
		and not r["connected"]
	]
	if not candidates:
		return []

	# Report each lead once, on the day it was actually closed out. `modified`
	# is useless for this (any later edit bumps it), so use the status log.
	closed_at = _status_since([r["name"] for r in candidates])

	out = []
	for r in candidates:
		closed_on = closed_at.get(r["name"])
		if not closed_on:
			continue
		# Half-open [prev_biz, today), same as _newly_ineligible — an inclusive
		# end would re-report the same lead on two consecutive days.
		if closed_on < prev_biz or closed_on >= today:
			continue
		item = dict(r)
		item["reason"] = _ineligible_reason(r)
		item["closed_on"] = str(closed_on)
		out.append(item)
	return out


# ---------------------------------------------------------------------------------
# Kanban tint (shared with crm.api.doc.apply_counts so the board and the email
# can never disagree about who's in danger)
# ---------------------------------------------------------------------------------
def prefetch_outbound_calls(lead_names: list[str]) -> dict[str, list[dict]]:
	"""``{lead: outbound calls}`` for many leads in one query.

	Same shape ``_outbound_calls`` returns per lead — it exists so the kanban can
	color a whole board of ISTL leads without one call-log query per card. Pass
	the result into ``refund_card_color(..., calls=...)``.
	"""
	if not lead_names:
		return {}

	rows = frappe.get_all(
		"CRM Call Log",
		filters={
			"reference_doctype": "CRM Lead",
			"reference_docname": ("in", lead_names),
			"type": "Outgoing",
		},
		fields=["name", "reference_docname", "start_time", "creation", "duration", "status"],
		order_by="creation asc",
		limit_page_length=0,
	)

	by_lead: dict[str, list[dict]] = {}
	for r in rows:
		start = r.get("start_time") or r.get("creation")
		if not start:
			continue
		by_lead.setdefault(r["reference_docname"], []).append(
			{
				"name": r["name"],
				"start": get_datetime(start),
				"duration": int(r.get("duration") or 0),
				"status": r.get("status") or "",
			}
		)
	for calls in by_lead.values():
		calls.sort(key=lambda c: c["start"])
	return by_lead


def refund_card_color(
	lead_name: str, status: str, creation, source: str, calls: list[dict] | None = None
) -> str:
	"""Refund standing of one ISTL lead, as a kanban tint.

	``green``  reached them / refund already earned / today's dial is done
	``red``    running out of runway — must dial every remaining day, or behind pace
	``amber``  due for a double-dial today, still comfortably on track
	``''``     not an ISTL lead / not workable / outside the window / nothing due

	Deliberately mirrors ``_enrich`` so "in danger" on the board means exactly
	what "due" means in the email. ``calls`` lets a caller coloring many leads
	supply pre-fetched outbound calls (see ``prefetch_outbound_calls``) instead of
	paying a query per lead.
	"""
	if not is_istl(source) or not creation:
		return ""
	if status not in WORKABLE_STATUSES:
		return ""

	today = _today()
	age_days = (today - getdate(creation)).days
	if not (0 <= age_days < WINDOW_DAYS):
		return ""

	if calls is None:
		calls = _outbound_calls(lead_name)
	clusters = _cluster_calls(calls)
	double_dials = sum(1 for c in clusters if c["dials"] >= 2)

	# We actually spoke with them — done chasing, regardless of dial count.
	if any(_had_conversation(c) for c in calls):
		return "green"

	# Refund secured — nothing left to chase on this lead.
	if double_dials >= REQUIRED_DOUBLE_DIALS:
		return "green"

	# A double-dial logged today = handled for the day.
	if any(c["date"] == today for c in clusters if c["dials"] >= 2):
		return "green"

	days_left = max(0, WINDOW_DAYS - age_days)
	remaining = REQUIRED_DOUBLE_DIALS - double_dials
	attempt_dates = [c["date"] for c in clusters if c["dials"] >= 2]
	last_dd = max(attempt_dates) if attempt_dates else None
	days_since = (today - last_dd).days if last_dd else None
	behind = double_dials < min(REQUIRED_DOUBLE_DIALS, age_days // 2)

	due_today = days_since is None or days_since >= 2 or behind or remaining >= days_left
	if not due_today:
		return ""
	# No slack left (or already behind) → this is the one that gets forfeited.
	if remaining >= days_left or behind:
		return "red"
	return "amber"


def _status_since(lead_names: list[str]) -> dict:
	"""``{lead: date the lead entered its CURRENT status}`` (Chicago dates).

	Reads the open `CRM Status Change Log` row (the one with no `to`), whose
	``from_date`` is when the lead landed in the status it's in now. Stored in
	UTC while the rest of the app works in Chicago wall clock, so convert —
	otherwise anything closed after 7pm CT lands on the wrong day.
	"""
	if not lead_names or not frappe.db.exists("DocType", "CRM Status Change Log"):
		return {}
	rows = frappe.get_all(
		"CRM Status Change Log",
		filters={
			"parenttype": "CRM Lead",
			"parent": ["in", lead_names],
			"to": ["in", ["", None]],
		},
		fields=["parent", "from_date"],
		limit_page_length=0,
	)
	out = {}
	for r in rows:
		if not r.get("from_date"):
			continue
		stamp = get_datetime(r["from_date"]).replace(tzinfo=ZoneInfo("UTC"))
		out[r["parent"]] = stamp.astimezone(TZ).date()
	return out


def _ineligible_reason(r: dict) -> str:
	if r["double_dials"] == 0 and r["total_outbound_dials"] == 0:
		return "no outbound calls logged"
	if r["double_dials"] == 0:
		return f"{r['total_outbound_dials']} single dial(s), no double-dial"
	return f"only {r['double_dials']}/{REQUIRED_DOUBLE_DIALS} double-dials"


# ---------------------------------------------------------------------------------
# Call clustering
# ---------------------------------------------------------------------------------


def _outbound_calls(lead_name: str) -> list[dict]:
	"""Outbound CRM Call Log rows linked to this lead, oldest first."""
	rows = frappe.get_all(
		"CRM Call Log",
		filters={
			"reference_doctype": "CRM Lead",
			"reference_docname": lead_name,
			"type": "Outgoing",
		},
		fields=["name", "start_time", "creation", "duration", "status"],
		order_by="creation asc",
		limit_page_length=200,
	)
	out = []
	for r in rows:
		start = r.get("start_time") or r.get("creation")
		if not start:
			continue
		out.append(
			{
				"name": r["name"],
				"start": get_datetime(start),
				"duration": int(r.get("duration") or 0),
				"status": r.get("status") or "",
			}
		)
	out.sort(key=lambda c: c["start"])
	return out


def _cluster_calls(calls: list[dict]) -> list[dict]:
	"""Group successive dials within DOUBLE_DIAL_GAP_SECONDS into attempts."""
	if not calls:
		return []
	clusters: list[dict] = []
	current = [calls[0]]
	for call in calls[1:]:
		gap = (call["start"] - current[-1]["start"]).total_seconds()
		if gap <= DOUBLE_DIAL_GAP_SECONDS:
			current.append(call)
		else:
			clusters.append(_cluster_summary(current))
			current = [call]
	clusters.append(_cluster_summary(current))
	return clusters


def _had_conversation(call: dict) -> bool:
	"""True when the other party actually TALKED WITH the rep on this call.

	A voicemail — however long — is not a conversation. Reads the diarized
	transcript and judges the lead-side speech; falls back to duration only when
	no transcript exists.
	"""
	try:
		doc = frappe.get_cached_doc("CRM Call Log", call["name"])
	except Exception:
		return False

	if not (doc.get("custom_transcript") or "").strip():
		# No transcript to judge (~9% of calls) — only a long call is assumed to
		# be a real conversation.
		return int(call.get("duration") or 0) >= NO_TRANSCRIPT_CONVERSATION_SECONDS

	try:
		from crm.api.call_transcript import _build_transcript

		data = _build_transcript(doc)
	except Exception:
		return int(call.get("duration") or 0) >= NO_TRANSCRIPT_CONVERSATION_SECONDS

	their_lines = [d for d in (data.get("dialogue") or []) if d.get("speaker") == "lead"]
	if not their_lines:
		return False  # rep talked, nobody answered

	opening = " ".join(
		d["content"] for d in their_lines
		if float(d.get("start") or 0) <= GREETING_WINDOW_SECONDS
	)
	if VOICEMAIL_RE.search(opening):
		# A greeting played. Only a human talking substantively AFTER it rescues
		# this (screening service / call assistant, then the seller picked up).
		after = [d for d in their_lines if float(d.get("start") or 0) > GREETING_WINDOW_SECONDS]
		return len(_substantive_words(after)) >= MIN_POST_GREETING_WORDS

	seconds = (data.get("talk_ratio") or {}).get("lead_seconds") or 0
	words = _substantive_words(their_lines)
	# Both thresholds must fail to rule it out, so a terse but real answer
	# ("we already sold it") still counts.
	return seconds >= MIN_CONVERSATION_SECONDS or len(words) >= MIN_CONVERSATION_WORDS


def _substantive_words(lines: list[dict]) -> list[str]:
	"""Words that carry meaning — greetings/acknowledgements stripped out."""
	text = " ".join(d.get("content") or "" for d in lines).lower()
	return [w for w in re.findall(r"[a-z']+", text) if w not in _FILLER_WORDS]


def _cluster_summary(group: list[dict]) -> dict:
	return {
		"dials": len(group),
		"date": getdate(group[0]["start"]),
		"start": group[0]["start"],
		"names": [g["name"] for g in group],
	}


# ---------------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------------


def _send_email(report: dict):
	recipients = _recipients()
	if not recipients:
		frappe.logger("istl_refund_report").warning("no recipients configured; skipping send")
		return

	when = report["when"]
	day = report["date"]
	if when == "morning":
		subject = _("ISTL refund watch — morning {0}").format(day)
	else:
		subject = _("ISTL refund watch — afternoon check {0}").format(day)

	# Headline numbers in the subject when something needs attention.
	bits = []
	if report["lost_count"]:
		bits.append(f"${report['lost_amount']:.0f} lost")
	if report.get("gave_up_count"):
		bits.append(f"{report['gave_up_count']} gave up early")
	if when == "morning" and report["due"]:
		bits.append(f"{len(report['due'])} due")
	if when == "eod" and report["uncalled_today"]:
		bits.append(f"{len(report['uncalled_today'])} uncalled")
	if bits:
		subject = f"{subject} ({', '.join(bits)})"

	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		template="crm_istl_refund_report",
		args=_template_args(report),
		now=True,
	)


# ---------------------------------------------------------------------------------
# Mattermost post (#acq)
# ---------------------------------------------------------------------------------
def _send_mattermost(report: dict):
	"""Post the call list to #acq. Best-effort — chat is a convenience, so a
	failure here must never take down the (authoritative) email.

	The point of this post is ONE thing: who do we need to reach out to. Detail
	that doesn't drive a call today stays in the email.
	"""
	url = (frappe.conf.get(MATTERMOST_WEBHOOK_KEY) or "").strip()
	if not url:
		return
	try:
		import requests

		# username/icon overrides make the post read as the report bot rather than
		# the human who happens to own the webhook (needs EnablePostUsernameOverride
		# / EnablePostIconOverride on the Mattermost server — both enabled).
		resp = requests.post(
			url,
			json={
				"text": _chat_text(report),
				"username": "ISTL Refund Watch",
				"icon_emoji": ":telephone_receiver:",
			},
			timeout=MATTERMOST_TIMEOUT,
		)
		if resp.status_code >= 300:
			frappe.log_error(
				title="ISTL report: Mattermost post failed",
				message=f"HTTP {resp.status_code}\n{resp.text[:500]}",
			)
	except Exception:
		frappe.log_error(
			title="ISTL report: Mattermost post failed",
			message=frappe.get_traceback(),
		)


def _chat_text(report: dict) -> str:
	"""The #acq message: a call list, in priority order."""
	when = report["when"]
	label = "Morning" if when == "morning" else "Afternoon check"
	# Morning = everything still owed a dial today. Afternoon = only what's still
	# not done, so the 3pm post is a genuinely shorter "these are left" list.
	rows = report["due"] if when == "morning" else report["uncalled_today"]

	lines = [f"#### iSpeedToLead — {label} · {report['date']}"]

	if not rows:
		lines.append(
			"**Nobody to call.** Every ISTL lead in the 10-day window is on pace."
			if when == "morning"
			else "**All clear** — every lead due today has a call logged."
		)
	else:
		headline = (
			f"**Call these {len(rows)} today**"
			if when == "morning"
			else f"**{len(rows)} still not called today**"
		)
		lines.append(f"{headline} — each needs a double-dial (2 calls back-to-back).")
		lines.append("")
		lines.append("| Lead | Dials | Days left | Last try |")
		lines.append("|:--|:--|:--|:--|")
		for r in rows[:MAX_CHAT_ROWS]:
			name = f"[{_md(r['lead_name'])}]({r['link']})"
			# ⚠️ only when the window is about to shut. Flagging every behind-pace
			# lead marked ~everything and turned the column into noise.
			if r["days_left"] <= 2:
				name = f"⚠️ {name}"
			if r["days_left"] <= 1:
				days = "**last day**"
			else:
				days = f"{r['days_left']} days"
			last = r["last_double_dial_date"] or r["last_call_date"] or "never called"
			lines.append(
				f"| {name} | {r['double_dials']}/{REQUIRED_DOUBLE_DIALS} | {days} | {last} |"
			)
		if len(rows) > MAX_CHAT_ROWS:
			lines.append(f"| _+{len(rows) - MAX_CHAT_ROWS} more — see email_ | | | |")

	# Money notes: short, and only when there's something to say.
	tail = []
	if report.get("lost_count"):
		tail.append(
			f"💸 **{report['lost_count']} lost the refund** since "
			f"{report['prev_business_day']} — ${report['lost_amount']:,.0f}"
		)
	if report.get("gave_up_count"):
		tail.append(
			f"🔎 **{report['gave_up_count']} closed without ever reaching them** "
			f"— ${report['gave_up_amount']:,.0f}"
		)
	if tail:
		lines.append("")
		lines.extend(tail)

	return "\n".join(lines)


def _md(text) -> str:
	"""Escape the markdown that breaks a table cell (pipes, brackets)."""
	out = str(text or "")
	for ch in ("|", "[", "]"):
		out = out.replace(ch, "\\" + ch)
	return out


def _template_args(report: dict) -> dict:
	"""Flatten for the Jinja email template (keep it dumb / presentation-only)."""
	return {
		"when": report["when"],
		"date": report["date"],
		"prev_business_day": report["prev_business_day"],
		"window_days": report["window_days"],
		"required": report["required_double_dials"],
		"in_window_count": report["in_window_count"],
		"due": report["due"],
		"due_count": len(report["due"]),
		"behind": report["behind"],
		"behind_count": len(report["behind"]),
		"uncalled_today": report["uncalled_today"],
		"uncalled_count": len(report["uncalled_today"]),
		"called_today": report.get("called_today") or [],
		"called_count": len(report.get("called_today") or []),
		"newly_ineligible": report["newly_ineligible"],
		"lost_count": report["lost_count"],
		"lost_amount": report["lost_amount"],
		"lost_amount_fmt": f"${report['lost_amount']:,.0f}",
		"gave_up_early": report.get("gave_up_early") or [],
		"gave_up_count": report.get("gave_up_count") or 0,
		"gave_up_amount_fmt": f"${(report.get('gave_up_amount') or 0):,.0f}",
		"greeting_window": int(GREETING_WINDOW_SECONDS),
		"default_refund": report["default_refund_amount"],
	}


def _recipients() -> list[str]:
	raw = frappe.conf.get("istl_report_recipients")
	if not raw:
		return list(DEFAULT_RECIPIENTS)
	if isinstance(raw, (list, tuple)):
		return [str(x).strip() for x in raw if str(x).strip()]
	return [p.strip() for p in str(raw).split(",") if p.strip()]


# ---------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------


def _today():
	"""America/Chicago calendar date — matches how the team thinks about 'today'."""
	return datetime.now(TZ).date()


def _prev_business_day(d):
	"""Most recent Mon–Fri strictly before ``d`` (skips Sat/Sun only)."""
	cur = d - timedelta(days=1)
	while cur.weekday() >= 5:
		cur -= timedelta(days=1)
	return cur


def _refund_amount(lead: dict) -> float:
	"""Per-lead refund $. Prefer the stored lead_cost; fall back to $29."""
	raw = lead.get("lead_cost")
	if raw not in (None, ""):
		try:
			n = flt(raw)
			if n > 0:
				return float(n)
		except Exception:
			pass
	return float(DEFAULT_REFUND_AMOUNT)


def _lead_url(lead_name: str) -> str:
	"""Absolute lead URL. Force https — site_config host_name is scheme-less so
	``get_url`` otherwise emits http:// which breaks email clients."""
	url = get_url(f"/crm/leads/{lead_name}")
	if url.startswith("http://"):
		url = "https://" + url[len("http://") :]
	return url
