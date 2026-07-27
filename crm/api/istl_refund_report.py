"""iSpeedToLead refund-eligibility call report (Groundwork).

ISTL refunds a lead (typically $29) when it was NOT bought on a sale balance
and the team placed **five double-dials within ten days** of delivery. The
operating cadence is one double-dial every other day for those ten days.

This module emails a short digest twice on business days:

  * **Morning** — which in-window leads are due / behind pace (call them today),
    plus any leads that *became* refund-ineligible since the last business-day
    report and the $ lost on them.
  * **End of day** — which of today's due leads still have no outbound call
    logged today, plus the same newly-ineligible $ loss section.

Double-dial counting: outbound `CRM Call Log` rows on the lead are clustered
when successive dials are ≤ ``DOUBLE_DIAL_GAP_SECONDS`` apart; a cluster of
≥2 dials counts as one double-dial attempt. Lone single dials are shown but
do not count toward the five (ISTL wants double dials).

Sale-balance purchases: the iSpeedToLead webhook does not currently flag
them, so every `source=iSpeedToLead` lead is treated as refund-eligible.
If that signal lands later, filter in ``_is_refund_eligible``.

Scheduler (hooks.py cron, UTC → America/Chicago wall clock):
  morning  13:00 UTC Mon–Fri  ≈ 8:00am CDT
  eod      23:00 UTC Mon–Fri  ≈ 6:00pm CDT

After deploy: ``bench execute frappe.utils.scheduler.sync_jobs`` (or the
scheduled_job_type.sync_jobs form) so the new cron rows land — same gotcha
as the integrity-report / seqdrain hooks.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, get_url, getdate

# --- config -------------------------------------------------------------------

SOURCE = "iSpeedToLead"
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

# Statuses where a refund is irrelevant (deal is alive / closed-won). Still
# shown in the "due today" list so dialing cadence isn't dropped mid-deal, but
# excluded from the "money lost" tally when the window expires.
# Pipeline statuses where a refund is irrelevant (deal is alive / closed-won).
# Dropped from the due/uncalled lists AND from the newly-ineligible $ tally.
ACTIVE_DEAL_STATUSES = {
	"Underwriting",
	"Make Offer",
	"Signed Contract",
	"Closed",
	"Won",
	"Assigned",
	"Dispo",
	"Marketing to Buyer",
	"Offer Accepted",
	"Under Contract",
}


# ---------------------------------------------------------------------------------
# Scheduler entry points
# ---------------------------------------------------------------------------------


def run_morning_report():
	"""Weekday morning cron: due / at-risk leads + newly ineligible $ loss."""
	_run_safe("morning")


def run_eod_report():
	"""Weekday end-of-day cron: still-uncalled due leads + newly ineligible $ loss."""
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
def run_report_now(when: str = "morning", send_email: int = 1, on_date: str | None = None):
	"""Manual / test entry. Sales User+; emails only when send_email=1.

	``when`` = ``morning`` | ``eod``. ``on_date`` (YYYY-MM-DD) freezes "today"
	for backtesting.
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
	# Strip nothing sensitive; this is the same payload the email uses.
	return report


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

	# Operational lists skip active deals — refund cadence only matters for leads
	# we might still want to return. Active deals still appear in newly_ineligible
	# filtering via is_active_deal (excluded from $ loss).
	in_window = [
		r
		for r in rows
		if r["in_window"]
		and r["double_dials"] < REQUIRED_DOUBLE_DIALS
		and not r["is_active_deal"]
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
	else:
		newly_ineligible = []
	lost_amount = sum(r["refund_amount"] for r in newly_ineligible)

	# Sort: fewest days left, then fewest dials, then oldest.
	def _sort_key(r):
		return (r["days_left"], r["double_dials"], r["creation"])

	due.sort(key=_sort_key)
	behind.sort(key=_sort_key)
	uncalled_today.sort(key=_sort_key)
	called_today = [r for r in due if r["called_today"]]
	called_today.sort(key=_sort_key)
	newly_ineligible.sort(key=lambda r: r["window_end"], reverse=True)

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
	fields = [f for f in fields if f in ("name", "lead_name", "first_name", "last_name", "creation", "status", "mobile_no", "lead_owner") or meta.has_field(f)]

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

	return {
		"name": lead["name"],
		"lead_name": display,
		"link": _lead_url(lead["name"]),
		"status": lead.get("status") or "",
		"creation": str(lead.get("creation")),
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
		"is_active_deal": (lead.get("status") or "") in ACTIVE_DEAL_STATUSES,
	}


def _newly_ineligible(rows: list[dict], today, prev_biz) -> list[dict]:
	"""Leads whose 10-day window ended since the previous business-day report
	and who finished with fewer than 5 double-dials.

	Window ended on ``window_end`` (creation + 9 days); the first ineligible
	day is the next calendar day. A Monday report (prev_biz=Friday) therefore
	picks up Fri/Sat/Sun expiries. Active-deal statuses are dropped from the
	$ tally (we wouldn't file a refund on an underwriting/closed lead).
	EOD on the last eligible day still treats them as in-window — ineligible
	only flips the morning after ``window_end``.
	"""
	out = []
	for r in rows:
		if r["double_dials"] >= REQUIRED_DOUBLE_DIALS:
			continue
		if r["is_active_deal"]:
			continue
		window_end = getdate(r["window_end"])
		if window_end < today and window_end >= prev_biz:
			item = dict(r)
			item["reason"] = _ineligible_reason(r)
			out.append(item)
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
		subject = _("ISTL refund watch — end of day {0}").format(day)

	# Headline numbers in the subject when something needs attention.
	bits = []
	if report["lost_count"]:
		bits.append(f"${report['lost_amount']:.0f} lost")
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
