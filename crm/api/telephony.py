"""Who owns which phone line, and which provider a row came from.

This exists because Telnyx is coming and Quo is not leaving on the same day. The
plan is to run both in parallel, and the plan's own warning is the reason this
module is written BEFORE any Telnyx traffic exists:

    every report must union both providers or it silently under-counts.

The Team Activity report, the intraday pulse, the standup and the lead-owner
backfill all answer "whose call was that?" by walking `caller` -> `receiver` ->
the user's sending line. During parallel running, half the calls are invisible to
a chain that only knows about Quo — no error, just a smaller number that looks
plausible. That is the same failure family as the `reference_doctype` trap and
the incoming-`userId` trap, both of which cost weeks of wrong figures.

So: ONE place that knows which numbers belong to which people, across providers,
and ONE normaliser.

WHY LAST-10. There were NINE separate `_last10`/`_digits` helpers in this app
(activity_progress, sms, quo_contacts, do_not_contact, agreement_adopt,
call_transcript, investorlift_ingest, investorlift_2fa, lead_import) and they did
not agree: `activity_progress` and `today_pulse` matched a user's line by EXACT
STRING against `User.custom_quo_number`, so a line stored as "+16125551234" never
matched a call log carrying "6125551234". A number is the same number however it
was typed, and last-10 is what every other part of this codebase already settled
on.

CALLS ALREADY CARRY THEIR PROVIDER — and it is NOT the field the plan assumed.
The plan proposed re-stamping `telephony_medium` (every row says "Manual",
upstream's default). Measured on prod first: all 4,192 rows are
`medium = "Quo"`, `telephony_medium = "Manual"`. The ops webhook has been
writing `medium` since the mirror was built, so the discriminator exists, is
100% populated and is correct — no migration, no re-stamp, nothing to run.
Telnyx writes `medium = "Telnyx"` and every downstream reader works.
`telephony_medium` is read only as a fallback, because it is what upstream's own
telephony framework sets and a call placed through that path would carry it.

TEXTS have no equivalent, hence `Quo Message.provider` (ops:
setup_provider_columns.py). The doctype keeps its name: renaming one with 4,357
rows buys nothing a column does not.

Nothing here writes. It is deliberately a read model: the providers' own webhooks
own their rows.
"""

import frappe

QUO = "Quo"
TELNYX = "Telnyx"
PROVIDERS = (QUO, TELNYX)

#: What an unstamped row means. Every call log and text that exists today came
#: from Quo, so a blank/"Manual" medium is Quo — not "unknown". Guessing the
#: other way would drop all 4,000 historical rows out of every report the moment
#: a provider filter was applied.
LEGACY_PROVIDER = QUO

#: Per-provider sending line on CRM Telephony Agent. `custom_quo_number` on User
#: predates this and stays authoritative for Quo (it is what the compose box and
#: the send scripts read); the agent row is where a SECOND line lives, because a
#: rep will hold a Quo line and a Telnyx line at the same time.
AGENT_FIELDS = {TELNYX: "custom_telnyx_number"}


def last10(value) -> str:
	"""The last ten digits of a phone number, or "".

	The one normaliser. `+1 (612) 555-1234`, `16125551234` and `6125551234` are
	the same line, and every part of this codebase that has ever compared numbers
	has had to learn that separately.
	"""
	digits = "".join(ch for ch in str(value or "") if ch.isdigit())
	return digits[-10:] if len(digits) >= 10 else digits


def normalize_provider(value) -> str:
	"""Map whatever is stored to one of PROVIDERS.

	"Manual" is what every historical CRM Call Log row carries — upstream's
	default, never set by us — so it means "before we recorded this", which is Quo.
	"""
	text = (value or "").strip()
	if not text or text.lower() == "manual":
		return LEGACY_PROVIDER
	for provider in PROVIDERS:
		if text.lower() == provider.lower():
			return provider
	return text


def call_provider(row) -> str:
	"""Which provider handled a CRM Call Log row.

	`medium` first: the Quo mirror has always written it, so it is populated on
	every historical row. `telephony_medium` is the fallback for a call placed
	through upstream's own telephony framework, which sets that one instead.
	"""
	return normalize_provider(_get(row, "medium") or _get(row, "telephony_medium"))


def message_provider(row) -> str:
	"""Which provider carried a Quo Message row.

	The doctype keeps its name — renaming a doctype with 4,357 rows to say
	"Message" buys nothing that a column does not.
	"""
	return normalize_provider(_get(row, "provider"))


def _get(row, field):
	if row is None:
		return None
	if isinstance(row, dict):
		return row.get(field)
	return getattr(row, field, None)


def _agent_lines():
	"""Per-provider lines from CRM Telephony Agent, as {user: {provider: number}}.

	Guarded on the columns existing: the agent doctype ships with upstream but our
	per-provider fields are added by ops, and a report must not fail because a
	site has not run a setup script yet.
	"""
	fields = ["user"]
	for provider, field in AGENT_FIELDS.items():
		if frappe.db.has_column("CRM Telephony Agent", field):
			fields.append(field)
	if len(fields) == 1:
		return {}
	rows = frappe.get_all("CRM Telephony Agent", fields=fields, limit_page_length=500)
	out = {}
	for row in rows:
		for provider, field in AGENT_FIELDS.items():
			value = (row.get(field) or "").strip() if field in fields else ""
			if value:
				out.setdefault(row.user, {})[provider] = value
	return out


def line_owners(users=None, providers=None) -> dict:
	"""{last10 number: user} across every provider a user sends from.

	`users` optionally restricts to a set of logins (the pulse reports on a
	subset). `providers` optionally restricts which lines count, which is what
	makes a per-provider breakdown possible later without a second mapping.
	"""
	wanted = set(providers or PROVIDERS)
	out = {}

	if QUO in wanted and frappe.db.has_column("User", "custom_quo_number"):
		for row in frappe.get_all(
			"User", filters={"enabled": 1}, fields=["name", "custom_quo_number"],
			limit_page_length=500,
		):
			number = last10(row.custom_quo_number)
			if number and (not users or row.name in users):
				out[number] = row.name

	for user, lines in _agent_lines().items():
		if users and user not in users:
			continue
		for provider, value in lines.items():
			if provider not in wanted:
				continue
			number = last10(value)
			if number:
				out[number] = user
	return out


def user_lines(user, providers=None) -> dict:
	"""{provider: number} for one user — what they can send from."""
	wanted = set(providers or PROVIDERS)
	out = {}
	if QUO in wanted and frappe.db.has_column("User", "custom_quo_number"):
		value = (frappe.db.get_value("User", user, "custom_quo_number") or "").strip()
		if value:
			out[QUO] = value
	for provider, value in _agent_lines().get(user, {}).items():
		if provider in wanted:
			out[provider] = value
	return out


def sending_line(user, provider=None):
	"""The number `user` sends from on `provider` (default: whatever they have).

	Deliberately returns the stored string, not the normalised form: it is going
	back out to an API that wants E.164, and last10 is for COMPARING numbers, not
	for dialling them.
	"""
	lines = user_lines(user)
	if provider:
		return lines.get(provider)
	for candidate in PROVIDERS:
		if lines.get(candidate):
			return lines[candidate]
	return None


def our_numbers(providers=None) -> set:
	"""Every line WE own, as last10 — the configured ones.

	Used to tell a teammate-to-teammate call apart from real outreach. Callers
	that can afford a live provider lookup should union this with it:
	`activity_progress._workspace_lines()` reads Quo's own phone-number list
	because shared lines (the "Backup Number") belong to no user and so appear
	nowhere in the mapping above.
	"""
	return set(line_owners(providers=providers))
