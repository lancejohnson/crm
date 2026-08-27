# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""The end-of-day outreach report — one post to the Acq channel, per person.

Three reports already exist and this is deliberately none of them:

  * `daily_standup` (5am DM to Lance) says what the day SHOULD look like
  * `today_pulse` (every 30 min to the channel) says how the day is GOING
  * `activity_progress` (Lance-only board) says who did what, live, on one screen

This one closes the day out in the team's own channel: what yesterday's dialing
actually produced, split per person.

**Per person is the whole point, and it was a deliberate reversal.** This first
shipped as an aggregate, on the reasoning that a scoreboard in a shared channel
turns into surveillance. Rendering the same two days per person is what killed
that argument — the aggregate was actively hiding the things worth acting on:

  * "51 texts out" on 2026-08-11 was 46 from Lance and 5 from Dennis. The two
    setters sent **zero**, on a cadence whose first line is "Call AND Text".
  * On 2026-08-12 Exe made the most calls on the team (47) and had the least
    talk time (20m, one conversation over 2 minutes). Ranking on call count
    rewards exactly the behaviour nobody wants.
  * Over ten business days Exe booked **0** appointments against German's 15,
    at an equal-or-better connect rate. The team total just reads "15 booked".

Definitions are REUSED, never re-derived, so this cannot disagree with the pulse
or the activity board about whose call it was or what counted:

  * call/text classification — `activity_progress`'s lead / buyer / outside /
    internal rule, including `_workspace_lines()` for teammate-to-teammate calls
    and the `reference_docname` (never `reference_doctype`) link test
  * card state + outcomes — `CRM Today Item`, the same rows the board serves
  * business days + delivery — `daily_standup` / `today_pulse`

**Attribution asymmetry, which is a real trap.** On an OUTGOING call `caller` is
the dialer, so falling back to the line's owner is safe. On an INCOMING call it
is NOT: `receiver` names whoever actually answered, and an unanswered call names
nobody. Falling back to the line owner there is the bug gw303 fixed, which put 47
inbound calls on one person. So inbound has no line-owner fallback and unclaimed
inbound calls are reported as `unattributed` instead — which is also why the
per-person rows deliberately do not sum to the team total, and the report says so.

Four things this says out loud rather than papering over, all measured on prod:

  * **A Done card often carries no outcome** (240 of 583 over ten business days,
    essentially all of them before 2026-08-05 when the outcome modal started
    being used). Rendering only the five known outcomes would imply the split
    covers every call.
  * **Most skips have no reason** on older days, and pre-gw292 skipped cards
    carry no owner at all, so they can be counted but never attributed.
  * **Skip reasons are free text**, so themes here are keyword-derived and
    anything unmatched is printed VERBATIM. The point of an open-ended box is
    the answer nobody anticipated.
  * **Dennis and Lance work no Today cards.** Dennis closes and Lance is not a
    setter, so a bare "0 done" next to the setters would read as idleness.
"""

import re
from collections import Counter, defaultdict

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime

from crm.api.activity_progress import _digits, _workspace_lines
from crm.api.calendar_appointments import get_appointments
from crm.api.daily_standup import is_business_day, previous_business_day
from crm.api.today_board import DONE_OUTCOMES
from crm.api.today_pulse import _fmt_minutes, _plural, send_to_channel

DOCTYPE = "CRM Today Item"

#: A call this long or longer is a conversation rather than a dial. Lance's
#: number, and the honest headline for "who did we actually speak to" — counting
#: any talk time at all made German read as 39 sellers "spoken with" on a day
#: only 7 were real conversations; the rest were 15-45 second voicemails.
LONG_CALL_SECONDS = 120

#: Users who never work the Today board, so "0 cards" is their normal and not a
#: gap. Dennis closes; Lance is not a setter.
NON_BOARD_USERS = (
	"dennis.szafran@groundworkpro.com",
	"lance.johnson@groundworkpro.com",
)

#: Conversations listed by name per person before collapsing the tail.
MAX_CONVERSATIONS = 8

#: Appointments named per person before collapsing the tail.
MAX_APPOINTMENTS = 6

#: A warm transfer — a setter getting a motivated seller on the phone and
#: bringing Dennis in — is logged by Quo as TWO rows: an outgoing leg and an
#: incoming leg, same number, same instant, same duration. Both people really
#: were on that call, so both keep it in their own row; but the team total must
#: count the conversation once or a single 28-minute call lands as 56 minutes.
#: Measured over ten business days: only 6 occurrences (1.1% of rows) but 4.8%
#: of all talk time, because they are exactly the long calls.
MIRROR_START_TOLERANCE = 5
MIRROR_DURATION_TOLERANCE = 2

#: Distinct un-themed skip reasons printed verbatim before collapsing the tail.
MAX_VERBATIM_REASONS = 4

#: Skip notes are a free-text box and people write paragraphs in them (one real
#: entry ran 104 characters). Clipped for the channel post only — the full text
#: is always on the card and on the lead's timeline.
MAX_REASON_CHARS = 58

#: Keyword themes for the free-text skip box, in priority order — first match
#: wins, so the specific ones come first. Anything unmatched is shown verbatim;
#: nothing is silently swept into "Other".
#: NOTE the order is load-bearing. "Do not call" sits above "Dead lead" because
#: a real note read "not selling. asked to be removed" — both match, and an
#: explicit removal request is the more consequential of the two to surface.
SKIP_THEMES = (
	("Do not call", ("do not call", "dnc", "asked to stop", "remove me",
	                 "asked to be removed", "stop calling", "take me off")),
	("Already booked", ("scheduled", "appointment", "booked")),
	("Already spoke", ("already spoke", "already talked", "already connected",
	                   "already reached", "already contacted", "already called",
	                   "already texting", "already tried")),
	("Needs Dennis", ("with dennis", "check with dennis", "ask dennis")),
	("Dead lead", ("dead lead", "dead", "not interested", "not selling", "no longer")),
	("Bad number", ("wrong number", "bad number", "no phone number", "no number",
	                "disconnected", "not in service", "don't go through",
	                "dont go through", "invalid")),
)


def _available() -> bool:
	return bool(frappe.db.exists("DocType", DOCTYPE))


def _bounds(day):
	return f"{day} 00:00:00", f"{day} 23:59:59.999999"


def _bucket(external, reference_doctype, reference_docname, lines):
	"""The house four-way split, applied identically to calls and texts.

	`reference_doctype` is NOT a link test — it carries a doctype default of
	"CRM Lead" on every row whether or not anything matched, so only a non-empty
	`reference_docname` means genuinely linked. Reading the wrong field is what
	once made 101 outside-CRM calls report as zero.

	Only `lead` and `outside` are seller outreach. `internal` is teammate-to-
	teammate on our own Quo lines and `buyer` is dispo — both are real work, but
	neither is the acquisitions team dialing sellers, so both are counted out of
	the headline and reported separately so the numbers still reconcile.
	"""
	if external and external in lines:
		return "internal"
	if (reference_docname or "").strip():
		return "buyer" if reference_doctype == "CRM Buyer" else "lead"
	return "outside"


def _blank_person():
	return {
		"calls_out": 0, "calls_in": 0, "talk_out": 0, "talk_in": 0,
		"sellers_out": set(), "sellers_in": set(), "sellers": set(),
		"long_calls": 0, "longest": 0,
		"conversations": defaultdict(lambda: {"calls": 0, "talk": 0, "longest": 0}),
		"texts_out": 0, "texts_in": 0, "text_sellers": set(),
		"internal": 0, "buyer_calls": 0,
		"done": 0, "skipped": 0, "outcomes": Counter(), "no_outcome": 0,
		"skip_themes": Counter(), "skip_verbatim": Counter(), "skip_no_reason": 0,
		"new_leads": 0, "new_lead_statuses": Counter(),
		"appointments": [],
	}


def _line_owners():
	rows = frappe.get_all(
		"User", filters={"enabled": 1}, fields=["name", "custom_quo_number"],
		limit_page_length=500,
	)
	return {
		_digits(r.custom_quo_number): r.name
		for r in rows if r.custom_quo_number and _digits(r.custom_quo_number)
	}


def _find_mirrors(rows, lines):
	"""Names of rows that are the second leg of one mirrored conversation, plus
	how many of those pairs put two DIFFERENT people on the call (a real warm
	transfer, as opposed to Quo simply logging both legs for one person)."""
	by_number = defaultdict(list)
	for row in rows:
		incoming = row.type == "Incoming"
		external = _digits(row.get("from") if incoming else row.get("to"))
		if external and external not in lines:
			by_number[external].append(row)

	mirrors, transfers = set(), 0
	for group in by_number.values():
		group.sort(key=lambda r: r.start_time)
		for i, a in enumerate(group):
			if a.name in mirrors:
				continue
			for b in group[i + 1:]:
				if b.name in mirrors or a.type == b.type:
					continue
				if abs((b.start_time - a.start_time).total_seconds()) > MIRROR_START_TOLERANCE:
					break
				if abs(int(a.duration or 0) - int(b.duration or 0)) > MIRROR_DURATION_TOLERANCE:
					continue
				mirrors.add(b.name)
				if (a.caller or a.receiver) != (b.caller or b.receiver):
					transfers += 1
				break
	return mirrors, transfers


def _collect_calls(day, people, un, lines, owners):
	start, end = _bounds(day)
	rows = frappe.get_all(
		"CRM Call Log",
		filters={"start_time": ["between", [start, end]]},
		fields=["name", "type", "duration", "from", "to", "caller", "receiver",
		        "start_time", "reference_doctype", "reference_docname"],
		limit_page_length=50000,
	)
	mirrors, transfers = _find_mirrors(rows, lines)
	team = {"calls": 0, "talk": 0, "long_calls": 0, "sellers": set(),
	        "transfers": transfers}

	for row in rows:
		incoming = row.type == "Incoming"
		external = _digits(row.get("from") if incoming else row.get("to"))
		workspace = _digits(row.get("to") if incoming else row.get("from"))
		bucket = _bucket(external, row.get("reference_doctype"),
		                 row.get("reference_docname"), lines)
		duration = int(row.duration or 0)

		# See the module docstring: no line-owner fallback on inbound, ever.
		if incoming:
			user = row.get("receiver") or row.get("caller")
		else:
			user = row.get("caller") or row.get("receiver") or owners.get(workspace)

		if bucket == "internal":
			if user:
				people[user]["internal"] += 1
			continue
		if bucket == "buyer":
			if user:
				people[user]["buyer_calls"] += 1
			continue
		# Team totals count each conversation once; the mirror leg is still
		# credited to its own person below.
		if row.name not in mirrors:
			team["calls"] += 1
			team["talk"] += duration
			if duration >= LONG_CALL_SECONDS:
				team["long_calls"] += 1
			if external:
				team["sellers"].add(external)

		if not user:
			un["calls"] += 1
			continue

		p = people[user]
		side = "in" if incoming else "out"
		p[f"calls_{side}"] += 1
		p[f"talk_{side}"] += duration
		p["longest"] = max(p["longest"], duration)
		if external:
			p[f"sellers_{side}"].add(external)
			p["sellers"].add(external)
		if duration >= LONG_CALL_SECONDS:
			p["long_calls"] += 1
			key = (row.get("reference_docname") or "").strip() or f"#{external}"
			conv = p["conversations"][key]
			conv["calls"] += 1
			conv["talk"] += duration
			conv["longest"] = max(conv["longest"], duration)
	return team


def _collect_texts(day, people, un, lines, owners):
	if not frappe.db.exists("DocType", "Quo Message"):
		return False
	meta = frappe.get_meta("Quo Message")
	fields = ["direction", "reference_doctype", "reference_docname"]
	for extra in ("activity_source", "from", "to", "sent_by"):
		if meta.has_field(extra):
			fields.append(extra)
	has_numbers = meta.has_field("from") and meta.has_field("to")

	start, end = _bounds(day)
	for row in frappe.get_all(
		"Quo Message", filters={"message_date": ["between", [start, end]]},
		fields=fields, limit_page_length=50000,
	):
		incoming = row.direction == "Incoming"
		external = _digits(row.get("from") if incoming else row.get("to")) \
			if has_numbers else ""
		workspace = _digits(row.get("to") if incoming else row.get("from")) \
			if has_numbers else ""
		bucket = _bucket(external, row.get("reference_doctype"),
		                 row.get("reference_docname"), lines)
		if bucket == "internal":
			continue
		if bucket == "buyer":
			un["buyer_texts"] += 1
			continue
		# A sequence step is real outreach but nobody *did* it — never credit a rep.
		if row.get("activity_source") == "Sequence" and not incoming:
			un["automated_texts"] += 1
			continue

		# THE LINE IS THE TRUTH, not `sent_by`. Quo's `userId` on a text sent from
		# the OpenPhone app resolves to the workspace owner rather than the person
		# who typed it, so `sent_by` credited 309 of the setters' texts to Lance
		# (187 off German's line, 122 off Exe's) and zero the other way. Every
		# CRM-sent (`Manual`) and sequence text agrees with the line owner, so the
		# line is right in every observed case and `sent_by` only survives as a
		# fallback for a shared line nobody owns. Same class of bug as the inbound
		# `userId` trap on calls, and it is still live in `activity_progress`.
		user = owners.get(workspace) or (row.get("sent_by") or None)
		if not user:
			un["texts_in" if incoming else "texts_out"] += 1
			continue
		p = people[user]
		p["texts_in" if incoming else "texts_out"] += 1
		key = external or (row.get("reference_docname") or "").strip()
		if key:
			p["text_sellers"].add(key)
	return True


def _normalize_reason(note):
	return re.sub(r"\s+", " ", (note or "").strip().lower()).strip(" .!,;:-")


def _theme(reason):
	for label, keywords in SKIP_THEMES:
		if any(word in reason for word in keywords):
			return label
	return None


def _collect_cards(day, people, un):
	"""Board totals plus each person's outcome split.

	`resolved_*` (Done AND Skipped) is preferred over `done_*` (Done only) so a
	skip — a real judgement someone made — is credited too. Skipped cards from
	before the gw292 ops script carry no owner at all and are counted as
	unattributed rather than dropped or guessed at.
	"""
	board = {"available": False, "total": 0, "done": 0, "skipped": 0, "remaining": 0}
	if not _available():
		return board
	board["available"] = True
	meta = frappe.get_meta(DOCTYPE)
	supports = meta.has_field("outcome") and meta.has_field("outcome_note")
	resolved = meta.has_field("resolved_by")
	fields = ["state", "done_by"] + (["outcome", "outcome_note"] if supports else []) \
	         + (["resolved_by"] if resolved else [])

	for row in frappe.get_all(
		DOCTYPE, filters={"for_date": day}, fields=fields, limit_page_length=50000
	):
		board["total"] += 1
		if row.state not in ("Done", "Skipped"):
			board["remaining"] += 1
			continue
		who = (row.get("resolved_by") if resolved else None) or row.get("done_by")
		if row.state == "Done":
			board["done"] += 1
			if not who:
				un["cards_done"] += 1
				continue
			p = people[who]
			p["done"] += 1
			outcome = (row.get("outcome") or "").strip() if supports else ""
			if outcome in DONE_OUTCOMES:
				p["outcomes"][outcome] += 1
			else:
				p["no_outcome"] += 1
		else:
			board["skipped"] += 1
			if not who:
				un["cards_skipped"] += 1
				continue
			p = people[who]
			p["skipped"] += 1
			reason = _normalize_reason(row.get("outcome_note") if supports else "")
			if not reason:
				p["skip_no_reason"] += 1
			elif _theme(reason):
				p["skip_themes"][_theme(reason)] += 1
			else:
				p["skip_verbatim"][reason] += 1
	return board


def _collect_leads(day, people, un):
	start, end = _bounds(day)
	fields = ["status", "lead_owner"]
	parked = frappe.get_meta("CRM Lead").has_field("import_hidden")
	if parked:
		fields.append("import_hidden")
	total = 0
	statuses = Counter()
	for row in frappe.get_all(
		"CRM Lead", filters={"creation": ["between", [start, end]]},
		fields=fields, limit_page_length=50000,
	):
		# Parked bulk-import leads are inventory, not intake; a 500-row LeadPack
		# would otherwise swamp the number the team reads as "what came in".
		if parked and row.get("import_hidden"):
			un["parked_leads"] += 1
			continue
		total += 1
		statuses[row.status or "(none)"] += 1
		if row.lead_owner:
			p = people[row.lead_owner]
			p["new_leads"] += 1
			p["new_lead_statuses"][row.status or "(none)"] += 1
		else:
			un["unowned_leads"] += 1
	return {"total": total, "by_status": statuses.most_common(),
	        "untouched": statuses.get("New", 0)}


def build_report(for_date=None):
	"""Everything one post needs. Pure read — safe to call for a preview."""
	day = getdate(for_date) if for_date else previous_business_day(now_datetime())
	people = defaultdict(_blank_person)
	un = Counter()
	lines = _workspace_lines()
	owners = _line_owners()

	team_calls = _collect_calls(day, people, un, lines, owners)
	_collect_texts(day, people, un, lines, owners)
	board = _collect_cards(day, people, un)
	leads = _collect_leads(day, people, un)

	# Appointments come from the closer's calendar, never from the card outcome.
	# See `calendar_appointments`: the outcome captured 13 of 53 real bookings.
	appts = get_appointments(day)
	for user, booked in (appts["by_user"] or {}).items():
		people[user]["appointments"] = booked

	# Names, and the leads behind each person's conversations, in two queries.
	users = {
		u.name: (u.full_name or u.name)
		for u in frappe.get_all("User", filters={"name": ["in", list(people)]},
		                        fields=["name", "full_name"], limit_page_length=500)
	} if people else {}
	wanted = set()
	for p in people.values():
		wanted |= {k for k in p["conversations"] if not k.startswith("#")}
	lead_names = {
		r.name: (r.lead_name or r.name)
		for r in frappe.get_all("CRM Lead", filters={"name": ["in", list(wanted)]},
		                        fields=["name", "lead_name"], limit_page_length=5000)
	} if wanted else {}

	rows = []
	for user, p in people.items():
		if not any((p["calls_out"], p["calls_in"], p["texts_out"], p["texts_in"],
		            p["done"], p["skipped"], p["new_leads"], p["appointments"])):
			continue
		convs = sorted(p["conversations"].items(), key=lambda kv: -kv[1]["talk"])
		rows.append({
			"user": user,
			"name": users.get(user, user.split("@")[0]),
			"works_board": user not in NON_BOARD_USERS,
			"calls": p["calls_out"] + p["calls_in"],
			"calls_out": p["calls_out"], "calls_in": p["calls_in"],
			"sellers": len(p["sellers"]),
			"sellers_out": len(p["sellers_out"]), "sellers_in": len(p["sellers_in"]),
			"talk": p["talk_out"] + p["talk_in"],
			"talk_out": p["talk_out"], "talk_in": p["talk_in"],
			"long_calls": p["long_calls"], "longest": p["longest"],
			"conversations": [
				{"label": (_phone(k[1:]) if k.startswith("#")
				           else lead_names.get(k, k)),
				 "in_crm": not k.startswith("#"), **v}
				for k, v in convs
			],
			"texts_out": p["texts_out"], "texts_in": p["texts_in"],
			"text_sellers": len(p["text_sellers"]),
			"internal": p["internal"], "buyer_calls": p["buyer_calls"],
			"done": p["done"], "skipped": p["skipped"],
			"outcomes": [(n, p["outcomes"][n]) for n in DONE_OUTCOMES if p["outcomes"][n]],
			"booked": p["outcomes"]["Booked an Appointment"],
			"no_outcome": p["no_outcome"],
			"skip_themes": p["skip_themes"].most_common(),
			"skip_verbatim": p["skip_verbatim"].most_common(),
			"skip_no_reason": p["skip_no_reason"],
			"new_leads": p["new_leads"],
			"new_lead_statuses": p["new_lead_statuses"].most_common(),
			"appointments": p["appointments"],
		})
	rows.sort(key=lambda r: (-r["calls"], -r["talk"]))

	# Calls come from the deduped team accumulator, NOT from summing the person
	# rows: a warm transfer is in two people's rows and is one conversation.
	team = {
		"calls": team_calls["calls"],
		"talk": team_calls["talk"],
		"long_calls": team_calls["long_calls"],
		"sellers": len(team_calls["sellers"]),
		"transfers": team_calls["transfers"],
		"texts_out": sum(r["texts_out"] for r in rows),
		"texts_in": sum(r["texts_in"] for r in rows),
		"booked": sum(r["booked"] for r in rows),
		"appointments": appts["total"],
	}
	return {"date": str(day), "generated_at": now_datetime(), "people": rows,
	        "team": team, "board": board, "leads": leads,
	        "appointments": appts, "unattributed": dict(un)}


# ── rendering ──────────────────────────────────────────────────────────────────


def _clip(text, limit=MAX_REASON_CHARS):
	text = text.strip()
	return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _phone(digits):
	"""A bare 10-digit string sitting in a list of people's names reads as noise;
	formatted and labelled, it reads as what it is — a real conversation with
	someone who wasn't in the CRM when they were called."""
	if len(digits) == 10:
		return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
	return digits or "unknown number"


def _counts(pairs):
	return " · ".join(f"{label} **{n}**" for label, n in pairs)


def _person_block(r):
	L = [f"**{r['name']}**"]

	if r["calls"]:
		line = (f"📞 {_plural(r['calls'], 'call')} ({r['calls_out']} out / "
		        f"{r['calls_in']} in) · {r['sellers']} sellers · "
		        f"{_fmt_minutes(r['talk'])} talk")
		if r["long_calls"]:
			line += (f" · **{r['long_calls']}** over 2m "
			         f"(longest {_fmt_minutes(r['longest'])})")
		L.append(line)
	if r["texts_out"] or r["texts_in"]:
		L.append(f"💬 {r['texts_out']} texts out / {r['texts_in']} in · "
		         f"{r['text_sellers']} sellers")
	elif r["calls"]:
		# Silence here is the finding, not an omission — the cadence is
		# "Call AND Text", and both setters sat at zero for days.
		L.append("💬 no texts sent")

	if r["works_board"]:
		L.append(f"🗂 {r['done']} done · {r['skipped']} skipped")
		if r["outcomes"]:
			L.append("　outcomes: " + _counts(r["outcomes"]))
		if r["no_outcome"]:
			L.append(f"　_{r['no_outcome']} done with no outcome recorded_")
		skips = list(r["skip_themes"])
		if skips:
			L.append("　skips: " + _counts(skips))
		if r["skip_verbatim"]:
			L.append("　also: " + " · ".join(
				f"“{_clip(t)}” ({n})" if n > 1 else f"“{_clip(t)}”"
				for t, n in r["skip_verbatim"][:MAX_VERBATIM_REASONS]
			))
		if r["skip_no_reason"]:
			L.append(f"　_{r['skip_no_reason']} skipped with no reason_")
	elif r["done"] or r["skipped"]:
		L.append(f"🗂 {r['done']} done · {r['skipped']} skipped")

	if r["appointments"]:
		shown = r["appointments"][:MAX_APPOINTMENTS]
		extra = len(r["appointments"]) - len(shown)
		names = " · ".join(a["summary"] for a in shown if a["summary"])
		L.append(f"📅 **{_plural(len(r['appointments']), 'appointment')} booked**"
		         + (f": {names}" if names else "")
		         + (f" · +{extra} more" if extra > 0 else ""))

	if r["new_leads"]:
		L.append(f"🆕 {_plural(r['new_leads'], 'new lead')}: "
		         + _counts(r["new_lead_statuses"]))

	if r["conversations"]:
		shown = r["conversations"][:MAX_CONVERSATIONS]
		bits = [
			f"{c['label']}{'' if c['in_crm'] else ' (not in CRM)'} "
			f"{_fmt_minutes(c['talk'])}"
			for c in shown
		]
		extra = len(r["conversations"]) - len(shown)
		L.append("　conversations: " + " · ".join(bits)
		         + (f" · +{extra} more" if extra > 0 else ""))
	return L


def render_markdown(d):
	day = getdate(d["date"])
	team, board, leads = d["team"], d["board"], d["leads"]
	L = [f"**Outreach — {day.strftime('%A, %b %-d')}**", ""]

	head = []
	if team["calls"]:
		head.append(f"{_plural(team['calls'], 'call')}")
		head.append(f"{team['sellers']} sellers")
		head.append(f"{_fmt_minutes(team['talk'])} talk")
		head.append(f"{team['long_calls']} over 2m")
	if team["texts_out"]:
		head.append(f"{team['texts_out']} texts out")
	if board["available"] and board["total"]:
		head.append(f"{board['done']}/{board['total']} cards done")
	if team.get("appointments"):
		head.append(f"**{_plural(team['appointments'], 'appointment')} booked**")
	if leads["total"]:
		head.append(f"{_plural(leads['total'], 'new lead')}")
	L.append(" · ".join(head) if head else "_No recorded outreach._")

	if not d["people"]:
		return "\n".join(L)

	for r in d["people"]:
		L.append("")
		L += _person_block(r)

	if leads["total"]:
		L += ["", f"**New leads — {leads['total']}**",
		      "Status now: " + _counts(leads["by_status"])]
		if leads["untouched"]:
			L.append(f"⚠️ **{leads['untouched']}** still on New — nobody has "
			         "worked them yet.")

	# Reconciliation. Per-person rows deliberately do not sum to the board or to
	# the raw call count, and a report that doesn't say so looks broken.
	un = d["unattributed"]
	notes = []
	if un.get("calls"):
		notes.append(f"{_plural(un['calls'], 'inbound call')} nobody answered "
		             "(not credited to the line owner)")
	if un.get("cards_skipped"):
		notes.append(f"{un['cards_skipped']} skipped cards with no owner recorded")
	if un.get("cards_done"):
		notes.append(f"{un['cards_done']} done cards with no owner recorded")
	if un.get("automated_texts"):
		notes.append(f"{un['automated_texts']} automated sequence texts")
	if un.get("buyer_texts"):
		notes.append(f"{un['buyer_texts']} buyer texts")
	if un.get("parked_leads"):
		notes.append(f"{un['parked_leads']} parked import leads")
	if notes:
		L += ["", "_Not counted above: " + " · ".join(notes) + "._"]
	if team.get("transfers"):
		L.append(
			f"_{_plural(team['transfers'], 'call')} involved two people (warm "
			"transfer) — counted in both their rows, once in the team total._"
		)

	# Appointments are the one number here that does NOT come from the CRM, so
	# say so when it is missing rather than letting a silent zero read as "nobody
	# booked anything" — which is exactly how the card outcome misled for weeks.
	appts = d.get("appointments") or {}
	if not appts.get("available"):
		L.append(f"_Appointments unavailable ({appts.get('reason') or 'not configured'})._")
	elif appts.get("unmatched"):
		L.append(
			f"_{_plural(appts['unmatched'], 'calendar event')} skipped for not being "
			"titled “(S) …” — check the naming convention._"
		)
	return "\n".join(L)


# ── delivery ───────────────────────────────────────────────────────────────────


def send_daily_outreach():
	"""Scheduler entry — one post per business morning, covering the day before.

	Wrapped so a delivery failure is logged rather than crashing the scheduler and
	taking the whole cron slot down with it (the standup job learned this first).
	"""
	try:
		if not is_business_day(getdate(now_datetime())):
			return
		return send_to_channel(render_markdown(build_report()))
	except Exception:
		frappe.log_error(
			title="daily outreach: send_daily_outreach failed",
			message=frappe.get_traceback(),
		)


@frappe.whitelist()
def preview_outreach(for_date=None, send=0, note=None):
	"""Dry run. Returns the exact markdown the scheduler would post, and only
	actually posts when send=1."""
	if frappe.session.user != "Administrator":
		roles = set(frappe.get_roles())
		if not roles & {"System Manager", "Sales Manager"}:
			frappe.throw(_("Not permitted"), frappe.PermissionError)

	data = build_report(for_date)
	text = render_markdown(data)
	if note:
		text = f"_{note}_\n\n{text}"
	post = send_to_channel(text) if int(send or 0) else None
	return {"markdown": text, "sent": bool(post), "post_id": post,
	        "date": data["date"], "people": data["people"],
	        "team": data["team"], "board": data["board"],
	        "leads": data["leads"], "unattributed": data["unattributed"]}
