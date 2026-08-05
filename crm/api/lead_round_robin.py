# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Round-robin the owner of every new inbound lead between the setters.

Until now every ownerless lead was stamped with a single hardcoded owner by the
ops server script `Lead Default Owner` (Dennis), which is why `lead_owner` said
Dennis on ~99% of leads even though German and Exe do the calling. This hands
each new inbound lead to one of the setters in turn, so the two of them split
the day's intake instead of sharing one undifferentiated pile.

Setting `lead_owner` is the whole job — `CRM Lead.after_insert` then shares the
lead with that user and creates the `_assign` ToDo, so the lead shows up as
theirs on the board without us touching `_assign` ourselves. (Assigning
separately is exactly the bug `lead_import` warns about: the lead ends up
assigned to *both* the default owner and the intended caller.)

Why this runs as a `before_insert` hook in app code
---------------------------------------------------
Frappe composes doc events as
``doc_events[doctype][method] + doc_events["*"][method]`` (see
`Document.hook.composer`), and Server Scripts are run by the wildcard entry.
So a doctype-specific app hook runs BEFORE `Lead Default Owner`, which only
fires ``if not doc.lead_owner``. We claim the owner first; the server script
degrades into a safety net that still stamps Dennis if the roster is empty,
the feature is switched off, or this code raises. Nothing here may ever block
a lead from being created — a webhook lead that fails to save is a lost lead.

Who is eligible
---------------
* Only leads created with **no owner** — i.e. the inbound webhooks (iSpeedToLead
  / Red Panda / PropertyLeads / Leadzolo), which insert as Guest with
  `lead_owner` unset. A lead created in the UI already carries
  `lead_owner = current user` (`LeadModal.vue`), so hand-created leads are left
  alone.
* Bulk imports are **excluded** (`import_hidden`). The importer has its own
  explicit "split between" picker and writes `lead_owner` itself; a 500-row
  LeadPack landing in the daily rotation would swamp it, and those leads are
  parked rather than worked anyway.

How the turn is decided
-----------------------
Not a stored counter. The rotation is **derived from the leads themselves**:
whoever holds fewer of *today's* leads gets the next one, ties broken by
strict alternation from whoever got the most recent one. That means:

* No state to drift, migrate, or reset — and no read-modify-write to race on.
  Two webhook leads landing in the same second can both pick the same person;
  the very next lead sees the imbalance and self-corrects.
* The count resets daily, so a week off doesn't create a debt that dumps the
  next hundred leads on whoever came back. Alternation still carries across
  midnight via the "who got the last one" tiebreak.
* Turning someone off is just disabling their CRM user (or editing the roster):
  disabled users drop out and everything goes to whoever is left.

Manually-created and reassigned leads count toward the day's tally on purpose —
the goal is an even share of real work, not an even share of webhook events.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Count

LEAD = "CRM Lead"

#: The setters, in rotation order. Overridable per-site with the site_config
#: key `lead_round_robin_users` (a JSON list of user emails) so the roster can
#: change without a deploy.
DEFAULT_ROSTER = (
	"german.haikazounian@groundworkpro.com",
	"exe.ortiz@groundworkpro.com",
)

#: site_config flag to switch the rotation off without a deploy. Absent = on.
ENABLED_KEY = "lead_round_robin_enabled"
ROSTER_KEY = "lead_round_robin_users"

#: Transitional catch-up ramp: hand the first N leads after a given moment to one
#: person before normal alternation begins. Exists because the backfill splits
#: existing leads by who has actually been calling them, which is honest but
#: lopsided (70/36 when it ran), so the person behind gets the next few.
#: All three keys are set together in site_config; absent = no ramp.
RAMP_USER_KEY = "lead_round_robin_ramp_user"
RAMP_COUNT_KEY = "lead_round_robin_ramp_count"
RAMP_SINCE_KEY = "lead_round_robin_ramp_since"


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
	"""False only if the site explicitly switches the rotation off."""
	return bool(frappe.conf.get(ENABLED_KEY, True))


def get_roster() -> list[str]:
	"""The rotation, in order, filtered to users who actually exist and are
	enabled. Disabling a CRM user is the intended way to take someone out of
	the rotation (vacation, offboarding) — the leads then all go to whoever
	remains rather than piling up on a login nobody is reading."""
	configured = frappe.conf.get(ROSTER_KEY) or list(DEFAULT_ROSTER)
	if isinstance(configured, str):
		configured = frappe.parse_json(configured)

	roster = []
	for user in configured:
		user = (user or "").strip()
		if not user or user in roster:
			continue
		if frappe.db.get_value("User", user, "enabled"):
			roster.append(user)
	return roster


# ---------------------------------------------------------------------------
# Choosing the next owner
# ---------------------------------------------------------------------------


def _exclude_parked(query, Lead):
	"""Drop parked bulk-import leads from a rotation query.

	NULL means visible (a lead predating the custom field is not parked), and
	`!= 1` alone would silently drop those rows — the trap `leads_dashboard.live()`
	documents. has_column-guarded so this works before the ops field exists.
	"""
	if not frappe.db.has_column(LEAD, "import_hidden"):
		return query
	return query.where(Lead.import_hidden.isnull() | (Lead.import_hidden != 1))


def _ramp_state(roster: list[str]) -> dict | None:
	"""The catch-up ramp's progress, or None when no ramp is configured/active.

	Defined by (user, count, since) in site_config and **derived from the leads**,
	like the rest of the rotation: the ramp leads are simply the first `count`
	leads owned by `user` created at or after `since`. Nothing is decremented, so
	there is no counter to drift and no read-modify-write to race on — two
	simultaneous inserts can at worst deliver one extra ramp lead.

	It is self-expiring: once `count` leads have landed, this returns
	`remaining == 0` forever after and the rotation goes back to plain
	alternation. The config keys can then be removed at leisure.
	"""
	user = frappe.conf.get(RAMP_USER_KEY)
	since = frappe.conf.get(RAMP_SINCE_KEY)
	if not user or not since or user not in roster:
		return None
	try:
		count = int(frappe.conf.get(RAMP_COUNT_KEY) or 0)
	except (TypeError, ValueError):
		return None
	if count <= 0:
		return None

	Lead = frappe.qb.DocType(LEAD)
	query = (
		frappe.qb.from_(Lead)
		.select(Lead.name, Lead.creation)
		.where(Lead.lead_owner == user)
		.where(Lead.creation >= since)
		.orderby(Lead.creation)
		.limit(count)
	)
	delivered = _exclude_parked(query, Lead).run(as_dict=True)

	today = frappe.utils.getdate()
	return {
		"user": user,
		"count": count,
		"since": str(since),
		"delivered": len(delivered),
		"remaining": max(0, count - len(delivered)),
		"delivered_today": sum(
			1 for row in delivered if frappe.utils.getdate(row["creation"]) == today
		),
	}


def _todays_counts(roster: list[str]) -> dict[str, int]:
	"""How many leads each roster member has picked up so far today."""
	counts = {user: 0 for user in roster}

	Lead = frappe.qb.DocType(LEAD)
	query = (
		frappe.qb.from_(Lead)
		.select(Lead.lead_owner, Count(Lead.name).as_("total"))
		.where(Lead.lead_owner.isin(roster))
		.where(Lead.creation >= frappe.utils.today())
		.groupby(Lead.lead_owner)
	)
	query = _exclude_parked(query, Lead)

	for row in query.run(as_dict=True):
		if row.get("lead_owner") in counts:
			counts[row["lead_owner"]] = int(row.get("total") or 0)

	# Ramp leads are a deliberate imbalance, so they must not read as one the
	# balancer should correct. Without this the ramp is undone within the same
	# day: ten leads go to Exe, the tally then shows Exe 10 / German 0, and the
	# next ten all go to German — net effect of the ramp, zero.
	ramp = _ramp_state(roster)
	if ramp and ramp["delivered_today"]:
		user = ramp["user"]
		counts[user] = max(0, counts.get(user, 0) - ramp["delivered_today"])
	return counts


def _last_owner(roster: list[str]) -> str | None:
	"""Whoever owns the most recently created lead in the rotation. This is what
	makes an empty day (or a fresh tie) alternate instead of always restarting
	at the top of the roster.

	Parked import leads are excluded here for the same reason they are excluded
	from the tally, and it matters more than it looks: the June LeadPack put 514
	parked leads on the two setters with recent `creation` stamps, so without this
	the "most recent lead" is whoever happened to be last in that import — a
	months-old bulk job silently deciding today's tiebreak.
	"""
	Lead = frappe.qb.DocType(LEAD)
	query = (
		frappe.qb.from_(Lead)
		.select(Lead.lead_owner)
		.where(Lead.lead_owner.isin(roster))
		.orderby(Lead.creation, order=frappe.qb.desc)
		.limit(1)
	)
	query = _exclude_parked(query, Lead)
	rows = query.run(as_dict=True)
	return rows[0]["lead_owner"] if rows else None


def _pick(roster: list[str], counts: dict[str, int], last_owner: str | None) -> str:
	"""Fewest leads today wins; ties go to whoever is next in the rotation after
	`last_owner`. Generalises to any roster size, not just two."""
	fewest = min(counts[user] for user in roster)
	tied = [user for user in roster if counts[user] == fewest]
	if len(tied) == 1:
		return tied[0]

	if last_owner in roster:
		start = roster.index(last_owner) + 1
		order = roster[start:] + roster[:start]
	else:
		order = roster

	for user in order:
		if user in tied:
			return user
	return tied[0]


def _choose(roster: list[str]) -> str:
	"""The single decision function. The hook, the preview and the status endpoint
	all route through this so they cannot possibly disagree about whose turn it is.

	The ramp takes precedence while it has leads left to deliver; after that it is
	ordinary fewest-today-wins alternation.
	"""
	ramp = _ramp_state(roster)
	if ramp and ramp["remaining"] > 0:
		return ramp["user"]
	return _pick(roster, _todays_counts(roster), _last_owner(roster))


def next_owner() -> str | None:
	"""The user the next inbound lead should go to, or None if the rotation is
	off / unconfigured. Pure read — safe to call for previews."""
	if not is_enabled():
		return None
	roster = get_roster()
	if not roster:
		return None
	return _choose(roster)


# ---------------------------------------------------------------------------
# The hook
# ---------------------------------------------------------------------------


def _skip_reason(doc) -> str | None:
	"""Why this lead is not part of the rotation, or None if it is."""
	if doc.get("lead_owner"):
		# Hand-created in the UI, or an importer that already chose. Respect it.
		return "owner already set"
	if doc.get("import_hidden"):
		return "bulk import"
	if frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch:
		return "migration"
	if not is_enabled():
		return "disabled"
	return None


def assign_round_robin_owner(doc, method=None):
	"""`CRM Lead` before_insert hook: hand an ownerless new lead to the next
	setter in the rotation.

	Deliberately swallows every error. If anything here goes wrong the lead
	still saves and the `Lead Default Owner` server script stamps the old
	default — a lost lead is far worse than a misrouted one.
	"""
	try:
		if _skip_reason(doc):
			return

		roster = get_roster()
		if not roster:
			return

		doc.lead_owner = _choose(roster)
	except Exception:
		frappe.log_error("Lead round robin failed", frappe.get_traceback())


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


@frappe.whitelist()
def round_robin_status():
	"""Who is in the rotation, what today's split looks like, and who is up
	next — so "why did that lead go to Exe?" has an answer that doesn't require
	a database session."""
	frappe.only_for(("System Manager", "Sales Manager", "Sales User"))

	roster = get_roster()
	if not roster:
		return {
			"enabled": is_enabled(),
			"roster": [],
			"today": [],
			"last_owner": None,
			"next_owner": None,
		}

	counts = _todays_counts(roster)
	ramp = _ramp_state(roster)
	return {
		"enabled": is_enabled(),
		"roster": roster,
		"today": [
			{
				"user": user,
				"full_name": frappe.db.get_value("User", user, "full_name"),
				# Ramp deliveries are already netted out of `counts`, so this is
				# the number the balancer is actually reasoning about.
				"leads": counts[user],
			}
			for user in roster
		],
		"last_owner": _last_owner(roster),
		"ramp": ramp,
		"next_owner": _choose(roster) if is_enabled() else None,
		"why": (
			_("catch-up ramp: {0} of {1} delivered").format(ramp["delivered"], ramp["count"])
			if ramp and ramp["remaining"] > 0
			else _("normal rotation")
		),
	}
