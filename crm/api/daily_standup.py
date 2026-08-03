# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""The 5am daily standup list.

ONE definition of "what has to happen today", rendered two ways: a Mattermost DM
at 5am CT, and (via `get_standup_lead_names`) the same set of leads drilled into
the CRM Leads list. The two cannot drift, because they are the same query — that
was the explicit design requirement. The previous attempt at this report was
abandoned because its lists were wrong ("the due list had 33 leads, but most were
Dead Lead"), so every rule here is written down and every exclusion is explicit.

The cadence is Dennis's, posted in the Acq channel 2026-07-31:

    1. Call/Text 2x's per day for 1 week
    2. After the first week, call once per week for 3 weeks.
    3. Then move to once a month until they tell us to stop.

with two clarifications from Lance:

  * "Call/Text" means call AND text, but **only calls are metered here**. Texts
    are fast and don't compete for the same capacity, so they never gate a lead
    and never count against the daily number.
  * "1 week" means **5 BUSINESS days**. Nobody calls on weekends (the call log
    is flat every Sat/Sun), so counting calendar days silently burned ~2 days of
    a lead's most valuable week. Business-day counting also makes a lead cost 13
    calls in month one instead of 17.

Suppression rule (Lance): a lead with an open task whose due date is in the
FUTURE is scheduled, and is therefore NOT on today's list — the cadence only
governs leads nobody has explicitly booked. A task due today or overdue puts the
lead ON the list. This is what stops the report telling a rep to cold-dial a
seller Dennis already booked for Tuesday.

Roles, not owners. `lead_owner`/`_assign` say Dennis owns ~99% of leads, but the
calling is done by German and Exe while Dennis closes. Splitting by owner would
hand the setters an empty list, so the report emits ONE shared setter queue plus
a separate closer list.
"""

import json
from datetime import datetime, timedelta

import frappe
import requests
from frappe.utils import get_datetime, getdate, now_datetime

# ── cadence ────────────────────────────────────────────────────────────────────

#: statuses that are actively chased on the phone
CHASE_STATUSES = ("New", "Called No Answer", "Follow Up", "Future Follow Up")

#: statuses Dennis works (closest-to-closing first — this order is the report order)
CLOSER_STATUSES = ("Contract Sent", "Make Offer", "Underwriting")

#: phase 1 — first N business days after first contact, 2 calls per business day
PHASE1_BUSINESS_DAYS = 5
PHASE1_CALLS_PER_DAY = 2

#: phase 2 — through business-day N, one call per business week
PHASE2_BUSINESS_DAYS = 20
PHASE2_INTERVAL = 5

#: phase 3 — one call per business month
PHASE3_INTERVAL = 22

#: calls a lead costs in its first month (10 in week 1 + 3 weekly) — the divisor
#: behind the "how many new leads can we take" number.
CALLS_PER_LEAD_MONTH1 = PHASE1_BUSINESS_DAYS * PHASE1_CALLS_PER_DAY + 3

#: obvious non-leads that must never reach a call list
EXCLUDE_LEAD_NAMES = ("lance test",)

#: who gets the DM
DEFAULT_DM_USER = "lancejohnson"
DEFAULT_MM_BASE = "https://app.groundworkpro.com/mattermost/api/v4"


# ── business-day helpers ───────────────────────────────────────────────────────


def is_business_day(d) -> bool:
	return getdate(d).weekday() < 5


def business_days_between(a, b) -> int:
	"""Whole business days from `a` to `b` (weekends excluded, endpoints exclusive
	of the start). Returns a large number when `a` is missing, so 'never called'
	sorts as maximally overdue."""
	if a is None:
		return 9999
	a, b = getdate(a), getdate(b)
	if a > b:
		return 0
	n, cur = 0, a
	while cur < b:
		cur += timedelta(days=1)
		if cur.weekday() < 5:
			n += 1
	return n


def previous_business_day(d):
	d = getdate(d) - timedelta(days=1)
	while d.weekday() >= 5:
		d -= timedelta(days=1)
	return d


# ── the list ───────────────────────────────────────────────────────────────────


def _live_lead_filter() -> str:
	"""Parked import leads are invisible everywhere else (the board, the
	dashboard); they must be invisible here too or the list is instantly wrong."""
	if frappe.db.has_column("CRM Lead", "import_hidden"):
		return " and (l.import_hidden is null or l.import_hidden != 1)"
	return ""


def _fetch_chase_rows(today):
	"""Every chase-status lead with the three facts the cadence needs: when we
	first tried, when we last called, and how many calls it has had today."""
	rows = frappe.db.sql(
		f"""
		select l.name, l.lead_name, l.status, l.creation, l.property_address,
		       l.lead_owner, l.mobile_no
		from `tabCRM Lead` l
		where l.status in %(statuses)s
		  and (l.converted is null or l.converted != 1)
		  {_live_lead_filter()}
		""",
		{"statuses": CHASE_STATUSES},
		as_dict=True,
	)
	rows = [r for r in rows if (r.lead_name or "").strip().lower() not in EXCLUDE_LEAD_NAMES]
	if not rows:
		return []

	names = [r.name for r in rows]

	calls = frappe.db.sql(
		"""
		select reference_docname n, min(creation) first_call, max(creation) last_call,
		       sum(case when date(creation) = %(today)s then 1 else 0 end) calls_today
		from `tabCRM Call Log`
		where reference_doctype = 'CRM Lead' and reference_docname in %(names)s
		group by reference_docname
		""",
		{"names": names, "today": today},
		as_dict=True,
	)
	call_map = {c.n: c for c in calls}

	# next scheduled task (future due date) = the suppression signal;
	# overdue/due-today tasks are a reason to call, not to skip.
	tasks = frappe.db.sql(
		"""
		select reference_docname n,
		       min(case when due_date > %(now)s then due_date end) next_future_due,
		       sum(case when due_date is not null and due_date <= %(eod)s then 1 else 0 end) due_now,
		       min(case when due_date is not null and due_date <= %(eod)s then title end) due_title
		from `tabCRM Task`
		where reference_doctype = 'CRM Lead' and reference_docname in %(names)s
		  and status not in ('Done', 'Canceled')
		group by reference_docname
		""",
		{
			"names": names,
			"now": now_datetime(),
			"eod": datetime.combine(getdate(today), datetime.max.time()),
		},
		as_dict=True,
	)
	task_map = {t.n: t for t in tasks}

	for r in rows:
		c = call_map.get(r.name)
		t = task_map.get(r.name)
		r.first_call = c.first_call if c else None
		r.last_call = c.last_call if c else None
		r.calls_today = int(c.calls_today or 0) if c else 0
		r.next_future_due = t.next_future_due if t else None
		r.tasks_due_now = int(t.due_now or 0) if t else 0
		r.due_task_title = t.due_title if t else None
	return rows


def _classify(row, today):
	"""Return (phase, calls_needed, due, reason) for one chase lead.

	Phase comes from the CADENCE ONLY. An overdue task is a *reason* to call, not
	a phase of its own — an early version made "has a due task" the top-ranked
	phase and, because ~45 leads carry an auto-created task literally titled
	"Follow up", the queue became 50 identical rows that buried all 18
	never-called leads. A generic overdue task must never outrank a lead nobody
	has ever dialled.
	"""
	# scheduled for later -> not today's problem
	if row.next_future_due and not row.tasks_due_now:
		return ("scheduled", 0, False,
		        f"booked {frappe.utils.format_datetime(row.next_future_due, 'd MMM')}")

	started = row.first_call or row.creation
	age = business_days_between(started, today)
	never = row.last_call is None
	since = business_days_between(row.last_call, today) if row.last_call else 9999

	def ago(n):
		return f"{n} business day{'' if n == 1 else 's'} since last call"

	if never:
		phase, need, due = "never", PHASE1_CALLS_PER_DAY - row.calls_today, row.calls_today < PHASE1_CALLS_PER_DAY
		reason = "never called"
	elif age < PHASE1_BUSINESS_DAYS:
		need = PHASE1_CALLS_PER_DAY - row.calls_today
		phase, due = "week1", need > 0
		reason = f"{row.calls_today} of {PHASE1_CALLS_PER_DAY} calls today"
	elif age < PHASE2_BUSINESS_DAYS:
		phase, due, need = "weekly", since >= PHASE2_INTERVAL, 1
		reason = ago(since)
	else:
		phase, due, need = "monthly", since >= PHASE3_INTERVAL, 1
		reason = ago(since)

	# An overdue / due-today task pulls a lead onto the list even when the cadence
	# says it could wait. When that is the ONLY reason it is here, it goes in its
	# own group at the bottom rather than being filed under a sweep it isn't due
	# for — otherwise a lead called yesterday shows up under "Monthly sweep",
	# which reads as broken and costs the list its credibility.
	if row.tasks_due_now:
		title = (row.due_task_title or "").strip()
		generic = title.lower() in ("", "follow up", "follow up call", "call back", "call")
		if not due:
			phase, due, need = "task", True, 1
			reason = ("task due" if generic else f"task: {title}") + f" · {ago(since)}"
		else:
			need = max(need, 1)
			reason += " · task due" if generic else f" · task: {title}"

	return (phase, max(0, need), due, reason)


#: display order — the leak first (never called), then freshest, then sweeps,
#: then leads pulled in only by a leftover task
_PHASE_RANK = {"never": 0, "week1": 1, "weekly": 2, "monthly": 3, "task": 4}

_PHASE_LABEL = {
	"never": "Never called",
	"week1": "Week 1 — 2 calls/day",
	"weekly": "Weekly sweep",
	"monthly": "Monthly sweep",
	"task": "Task due (not yet due by cadence)",
}


def build_setter_queue(today=None):
	today = getdate(today or now_datetime())
	out = []
	for r in _fetch_chase_rows(today):
		phase, need, due, reason = _classify(r, today)
		r.phase, r.calls_needed, r.due, r.reason = phase, need, due, reason
		r.days_silent = business_days_between(r.last_call, today) if r.last_call else 9999
		out.append(r)
	due_rows = [r for r in out if r.due]
	due_rows.sort(key=lambda r: (_PHASE_RANK.get(r.phase, 9), -r.days_silent, r.lead_name or ""))
	return {"all": out, "due": due_rows}


def build_closer_list(today=None):
	"""Dennis's side: everything close to money, ordered closest-first, with the
	reason it needs attention today."""
	today = getdate(today or now_datetime())
	has_dd = frappe.db.has_column("CRM Lead", "dd_expiration_date")
	dd = "l.dd_expiration_date" if has_dd else "null"
	rows = frappe.db.sql(
		f"""
		select l.name, l.lead_name, l.status, l.property_address, {dd} dd_expiration_date,
		       l.modified
		from `tabCRM Lead` l
		where l.status in %(statuses)s
		  and (l.converted is null or l.converted != 1)
		  {_live_lead_filter()}
		""",
		{"statuses": CLOSER_STATUSES},
		as_dict=True,
	)
	if not rows:
		return []
	names = [r.name for r in rows]

	act = frappe.db.sql(
		"""
		select n, max(ts) last_touch from (
		  select reference_docname n, max(creation) ts from `tabCRM Call Log`
		    where reference_doctype='CRM Lead' and reference_docname in %(names)s group by n
		  union all
		  select reference_docname n, max(creation) ts from `tabQuo Message`
		    where reference_doctype='CRM Lead' and reference_docname in %(names)s group by n
		) x group by n
		""",
		{"names": names},
		as_dict=True,
	) if frappe.db.exists("DocType", "Quo Message") else frappe.db.sql(
		"""
		select reference_docname n, max(creation) last_touch from `tabCRM Call Log`
		where reference_doctype='CRM Lead' and reference_docname in %(names)s group by n
		""",
		{"names": names},
		as_dict=True,
	)
	touch = {a.n: a.last_touch for a in act}

	tasks = frappe.db.sql(
		"""
		select reference_docname n, count(*) due_now, min(title) title
		from `tabCRM Task`
		where reference_doctype='CRM Lead' and reference_docname in %(names)s
		  and status not in ('Done','Canceled') and due_date is not null and due_date <= %(eod)s
		group by reference_docname
		""",
		{"names": names, "eod": datetime.combine(today, datetime.max.time())},
		as_dict=True,
	)
	task_map = {t.n: t for t in tasks}

	for r in rows:
		r.last_touch = touch.get(r.name)
		r.days_silent = business_days_between(r.last_touch, today) if r.last_touch else 9999
		t = task_map.get(r.name)
		r.task_due = t.title if t else None
		flags = []
		if r.task_due:
			flags.append(f"task due: {r.task_due}")
		if r.dd_expiration_date:
			left = (getdate(r.dd_expiration_date) - today).days
			if left <= 3:
				flags.append(f"**DD {'expired' if left < 0 else 'expires in ' + str(left) + 'd'}**")
		if r.days_silent >= 3:
			flags.append("no contact " + ("ever" if r.days_silent > 900 else f"in {r.days_silent} business days"))
		r.flags = flags
	rows.sort(key=lambda r: (CLOSER_STATUSES.index(r.status), -r.days_silent))
	return rows


def build_capacity(today=None):
	"""Yesterday's calling vs what the cadence owes today, and what that implies
	for how many new leads we can actually take on."""
	today = getdate(today or now_datetime())
	prev = previous_business_day(today)
	per_rep = frappe.db.sql(
		"""
		select caller, count(*) calls,
		       sum(case when duration >= 60 then 1 else 0 end) conversations
		from `tabCRM Call Log`
		where type='Outgoing' and reference_doctype='CRM Lead'
		  and date(creation) = %(d)s and caller is not null and caller != ''
		group by caller order by calls desc
		""",
		{"d": prev},
		as_dict=True,
	)
	return {
		"prev_day": prev,
		"per_rep": per_rep,
		"calls_made": sum(r.calls for r in per_rep),
		"conversations": sum(r.conversations or 0 for r in per_rep),
	}


def build_standup(today=None):
	today = getdate(today or now_datetime())
	setter = build_setter_queue(today)
	closer = build_closer_list(today)
	cap = build_capacity(today)

	by_status = {}
	for r in setter["all"]:
		by_status[r.status] = by_status.get(r.status, 0) + 1
	closer_counts = {}
	for r in closer:
		closer_counts[r.status] = closer_counts.get(r.status, 0) + 1

	calls_owed = sum(r.calls_needed for r in setter["due"])
	headroom = max(0, cap["calls_made"] - calls_owed)
	return {
		"date": today,
		"setter": setter,
		"closer": closer,
		"capacity": cap,
		"by_status": by_status,
		"closer_counts": closer_counts,
		"calls_owed": calls_owed,
		"intake": round(max(0, (cap["calls_made"] - 9)) / CALLS_PER_LEAD_MONTH1, 1),
		"headroom": headroom,
	}


# ── rendering ──────────────────────────────────────────────────────────────────

CRM = "https://crm.groundworkpro.com/crm"


def _lead_link(r):
	return f"[{r.lead_name or r.name}]({CRM}/leads/{r.name})"


def render_markdown(d, limit=25):
	today = d["date"]
	L = []
	L.append(f"## Standup — {today.strftime('%a %-d %b %Y')}")

	bs, cc = d["by_status"], d["closer_counts"]
	L.append(
		"**New** {n} · **No answer + Follow ups** {f} · **Underwriting** {u} · "
		"**Make offer** {m} · **Contract sent** {c}".format(
			n=bs.get("New", 0),
			f=bs.get("Called No Answer", 0) + bs.get("Follow Up", 0) + bs.get("Future Follow Up", 0),
			u=cc.get("Underwriting", 0),
			m=cc.get("Make Offer", 0),
			c=cc.get("Contract Sent", 0),
		)
	)

	# 1. closest to closing first
	closer = [r for r in d["closer"] if r.flags]
	L.append(f"\n### :moneybag: Dennis — {len(closer)} need attention")
	if not closer:
		L.append("_Nothing flagged. Everything close to money was touched recently._")
	for r in closer:
		L.append(f"- **{r.status}** · {_lead_link(r)} — " + "; ".join(r.flags))

	# 2. the shared calling queue, grouped so the top of the list is the right
	#    work rather than whichever 25 rows happened to sort first
	due = d["setter"]["due"]
	L.append(f"\n### :telephone_receiver: Calling queue — {len(due)} leads, {d['calls_owed']} calls")
	if not due:
		L.append("_Nobody is due. Everything in the chase columns is either called today or booked._")

	per_group = {"never": 99, "week1": 12, "weekly": 8, "monthly": 5, "task": 5}
	for phase in ("never", "week1", "weekly", "monthly", "task"):
		group = [r for r in due if r.phase == phase]
		if not group:
			continue
		calls = sum(r.calls_needed for r in group)
		head = f"\n**{_PHASE_LABEL[phase]}** — {len(group)} leads, {calls} calls"
		if phase == "never":
			head += "  :warning: _start here_"
		L.append(head)
		cap = per_group[phase]
		for r in group[:cap]:
			L.append(f"- {_lead_link(r)} · {r.status} · needs {r.calls_needed} — {r.reason}")
		if len(group) > cap:
			L.append(f"- _…and {len(group) - cap} more_")

	# 3. capacity / intake
	cap = d["capacity"]
	L.append(f"\n### :chart_with_upwards_trend: Capacity")
	who = ", ".join(f"{r.caller.split('@')[0]} {r.calls}" for r in cap["per_rep"]) or "nobody logged a call"
	L.append(
		f"Last business day ({cap['prev_day'].strftime('%a %-d %b')}): **{cap['calls_made']} calls**, "
		f"**{int(cap['conversations'])} real conversations** ({who})."
	)
	L.append(
		f"Today the cadence owes **{d['calls_owed']} calls**. At that rate we can carry "
		f"**~{d['intake']} new leads per business day**."
	)
	return "\n".join(L)


# ── delivery ───────────────────────────────────────────────────────────────────


def _mm_conf():
	base = (frappe.conf.get("mattermost_base") or DEFAULT_MM_BASE).rstrip("/")
	return base, frappe.conf.get("mattermost_token"), (
		frappe.conf.get("standup_dm_user") or DEFAULT_DM_USER
	)


def _mm(path, token, base, method="GET", body=None):
	r = requests.request(
		method,
		base + path,
		headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
		data=json.dumps(body) if body is not None else None,
		timeout=20,
	)
	r.raise_for_status()
	return r.json()


def send_dm(text):
	"""DM the standup to the configured user as the `pi` bot. Returns the post id.

	Absent a token this is a no-op rather than an error, so the feature lies
	dormant on any site that has not been configured (same shape as the contract
	parser's `notify_mini`)."""
	base, token, user = _mm_conf()
	if not token:
		frappe.log_error(title="standup: no mattermost_token in site_config", message="skipped DM")
		return None
	me = _mm("/users/me", token, base)
	target = _mm(f"/users/username/{user}", token, base)
	ch = _mm("/channels/direct", token, base, "POST", [me["id"], target["id"]])
	post = _mm("/posts", token, base, "POST", {"channel_id": ch["id"], "message": text})
	return post["id"]


def send_daily_standup():
	"""Scheduler entry point — 5am CT on business days.

	Wrapped so a delivery failure is logged rather than crashing the scheduler
	(which would silently take the whole cron slot down)."""
	try:
		today = getdate(now_datetime())
		if not is_business_day(today):
			return
		data = build_standup(today)
		send_dm(render_markdown(data))
	except Exception:
		frappe.log_error(title="standup: send_daily_standup failed", message=frappe.get_traceback())


@frappe.whitelist()
def preview_standup(today=None, send=0, note=None):
	"""Dry run. Returns the exact markdown the 5am job would send; only actually
	DMs when send=1. `note` prefixes the DM so a preview can never be mistaken for
	the real 5am post."""
	data = build_standup(getdate(today) if today else None)
	text = render_markdown(data)
	if note:
		text = f"_{note}_\n\n{text}"
	post = send_dm(text) if int(send or 0) else None
	return {
		"markdown": text,
		"sent": bool(post),
		"post_id": post,
		"counts": {
			"setter_due": len(data["setter"]["due"]),
			"setter_total": len(data["setter"]["all"]),
			"calls_owed": data["calls_owed"],
			"closer_flagged": len([r for r in data["closer"] if r.flags]),
		},
	}


@frappe.whitelist()
def get_standup_lead_names(bucket="setter", today=None):
	"""The same list the DM is built from, as bare lead names, so the CRM Leads
	view can drill to exactly what standup discussed. This is why the report and
	the board cannot disagree — one definition, two renderers."""
	data = build_standup(getdate(today) if today else None)
	if bucket == "closer":
		return [r.name for r in data["closer"] if r.flags]
	if bucket == "never":
		return [r.name for r in data["setter"]["due"] if r.days_silent > 900]
	return [r.name for r in data["setter"]["due"]]
