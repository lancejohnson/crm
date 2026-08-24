# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Per-source lead assignment rules — the storage and resolution half.

`lead_round_robin.py` decides *who is next* among a set of people. This module
decides *which set of people a lead belongs to in the first place*, keyed on
`CRM Lead.source`, so "German and Exe split the iSpeedToLead feed but every
Leadzolo lead goes to Lance" is a thing you configure in Settings rather than a
constant somebody has to deploy.

Why not the upstream "Assignment Rules" page
--------------------------------------------
Frappe's core `Assignment Rule` doctype does something adjacent, and the CRM
ships a settings page for it — but it writes `_assign` (a ToDo) on
**after_insert**, while this CRM keys everything off `lead_owner` (Today board
scoping, the standup, the dashboards, the ring alert, sequence call-tasks) and
sets it on **before_insert**. Running both means two deciders racing across two
hooks, and a lead carrying both fields is the double-assignment bug
`lead_import` warns about. So the upstream page stays hidden and this owns the
decision. `CRM Lead.after_insert` still derives `_assign` from `lead_owner` by
itself, exactly as before.

Where the rules live
--------------------
One JSON blob in a **global Frappe default** (`frappe.db.get_default`), the same
no-new-doctype trick the Team Activity goals use. That matters for three
reasons: there is no ops script to run before this works, the inbound webhooks
insert as **Guest** and a global default is readable by anyone, and the whole
config is one row that can be read in a single query on a hot insert path.

Shape::

    {
      "enabled": true,
      "default": {"mode": "rotate", "users": ["german@…", "exe@…"]},
      "sources": {
        "Leadzolo":     {"mode": "fixed",  "users": ["lance@…"]},
        "iSpeedToLead": {"mode": "rotate", "users": ["german@…", "exe@…"]}
      }
    }

Modes:

* ``rotate`` — round-robin between `users` (fewest-today-wins, see
  `lead_round_robin._choose`).
* ``fixed``  — always the one user. (Not just a one-person rotation: it says so
  out loud, so the UI can render it as a choice rather than as a degenerate
  case, and adding a second name is then a deliberate switch.)
* ``off``    — assign nobody. The lead saves ownerless and the legacy
  `Lead Default Owner` server script stamps its default, which is exactly what
  happened before any of this existed.

Nothing configured
------------------
`rule_for()` returns None until someone saves in Settings, and the hook then
falls back to the site_config roster (`lead_round_robin_users`) it has always
used. So deploying this changes no behaviour whatsoever — the rules only take
over once a human has written some.
"""

import json

import frappe

#: Global default key holding the whole rules blob. Global, not per-user: the
#: webhooks insert as Guest, and "who gets Leadzolo" is a property of the
#: business, not of whoever happens to be logged in.
RULES_KEY = "crm_lead_assignment_rules"

MODES = ("rotate", "fixed", "off")

#: Sales roles that may *read* the settings; writing additionally needs manager.
READ_ROLES = ("System Manager", "Sales Manager", "Sales User")
WRITE_ROLES = ("System Manager", "Sales Manager")


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def get_rules() -> dict | None:
	"""The stored rules, or None if nobody has configured any yet.

	None and "configured but empty" are deliberately different: the first means
	*fall back to the old site_config roster*, the second means *a human decided
	this*. Collapsing them would make clearing every rule silently resurrect the
	roster somebody had just replaced.
	"""
	raw = frappe.db.get_default(RULES_KEY)
	if not raw:
		return None
	try:
		rules = json.loads(raw)
	except (ValueError, TypeError):
		# Never let a corrupt blob break lead creation; behave as unconfigured.
		return None
	return rules if isinstance(rules, dict) else None


def _rule_users(rule: dict | None) -> list[str]:
	if not isinstance(rule, dict):
		return []
	users = rule.get("users")
	if not isinstance(users, list):
		return []
	out = []
	for user in users:
		user = (user or "").strip()
		if user and user not in out:
			out.append(user)
	return out


def is_enabled() -> bool:
	"""The everyday on/off switch, owned by the settings page.

	Distinct from site_config's `lead_round_robin_enabled`, which stays as the
	break-glass kill switch: this one can be flipped by a manager in the UI, that
	one needs a shell and survives whatever the UI does.
	"""
	rules = get_rules()
	if rules is None:
		return True
	return bool(rules.get("enabled", True))


def rule_for(source: str | None) -> dict | None:
	"""The rule governing a lead from `source`, or None if unconfigured.

	Source-specific first, then the catch-all default. A source with no rule of
	its own is not special — it is simply "everything else".
	"""
	rules = get_rules()
	if rules is None:
		return None

	sources = rules.get("sources")
	if isinstance(sources, dict) and source:
		rule = sources.get(source)
		if isinstance(rule, dict):
			return _normalize_rule(rule)

	default = rules.get("default")
	if isinstance(default, dict):
		return _normalize_rule(default)
	return None


def _normalize_rule(rule: dict) -> dict:
	mode = rule.get("mode")
	if mode not in MODES:
		mode = "rotate"
	users = _rule_users(rule)
	if mode == "fixed":
		users = users[:1]
	return {"mode": mode, "users": users}


# ---------------------------------------------------------------------------
# Reading it back for the UI
# ---------------------------------------------------------------------------


def _assignable_users() -> list[dict]:
	"""Everyone who can own a lead — the Today board's hand-over list, reused
	verbatim rather than re-derived.

	One definition of "who works leads here" for both surfaces: the board's picker
	and this page must not be able to disagree about whether someone exists, and
	that helper already excludes Administrator/Guest and disabled logins (the
	first pass of this module did not, and offered `Administrator` as a setter).
	"""
	from crm.api.today_board import _assignable_users as board_users

	return [
		{"name": u["user"], "full_name": u["full_name"]} for u in board_users()
	]


def _known_sources() -> list[str]:
	return frappe.get_all("CRM Lead Source", pluck="name", order_by="name asc")


@frappe.whitelist()
def get_lead_assignment_settings():
	"""Everything the settings page needs in one call: the rules, the people who
	may appear in them, the sources they may key on, and — because "why did that
	lead go to Exe?" is the question this page exists to answer — who each rule
	would hand the next lead to right now."""
	frappe.only_for(READ_ROLES)

	from crm.api import lead_round_robin

	rules = get_rules()
	configured = rules is not None
	if not configured:
		# Show the effective behaviour, not an empty page: the site_config roster
		# is what is actually deciding today, so seed the form with it.
		rules = {
			"enabled": True,
			"default": {"mode": "rotate", "users": lead_round_robin.get_roster()},
			"sources": {},
		}

	sources = rules.get("sources") if isinstance(rules.get("sources"), dict) else {}
	preview = {}
	for key, rule in list(sources.items()) + [("__default__", rules.get("default"))]:
		normalized = _normalize_rule(rule) if isinstance(rule, dict) else None
		preview[key] = lead_round_robin.preview_for_rule(normalized)

	return {
		"configured": configured,
		"enabled": bool(rules.get("enabled", True)),
		"default": _normalize_rule(rules.get("default") or {}),
		"sources": {k: _normalize_rule(v) for k, v in sources.items() if isinstance(v, dict)},
		"users": _assignable_users(),
		"available_sources": _known_sources(),
		"next_owner": preview,
		# The break-glass switch lives outside the UI; say so rather than letting
		# the page claim to be on while site_config has it off.
		"kill_switch_off": not bool(frappe.conf.get("lead_round_robin_enabled", True)),
	}


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _validate_rule(rule, label: str, valid_users: set[str]) -> dict:
	if not isinstance(rule, dict):
		frappe.throw(f"{label}: not a rule.")

	mode = rule.get("mode")
	if mode not in MODES:
		frappe.throw(f"{label}: unknown mode '{mode}'.")

	users = _rule_users(rule)
	unknown = [u for u in users if u not in valid_users]
	if unknown:
		frappe.throw(f"{label}: not an assignable user — {', '.join(unknown)}.")

	if mode == "off":
		# Nobody is meant to be listed; drop rather than throw, so switching a
		# rule to "off" in the UI doesn't require clearing the picker first.
		return {"mode": "off", "users": []}

	if not users:
		# A rule with no one in it would silently fall through to the default,
		# which looks identical on screen to a rule that is working. Refuse.
		frappe.throw(f"{label}: pick at least one person, or set it to 'No one'.")

	if mode == "fixed":
		users = users[:1]
	return {"mode": mode, "users": users}


@frappe.whitelist()
def set_lead_assignment_settings(settings):
	"""Replace the whole rules blob. Manager-only.

	Whole-blob replace rather than per-rule edits: the page shows every rule at
	once, so a partial write could only ever mean the UI and the store disagree
	about a rule the user was looking at.
	"""
	frappe.only_for(WRITE_ROLES)

	if isinstance(settings, str):
		try:
			settings = json.loads(settings)
		except (ValueError, TypeError):
			settings = None
	if not isinstance(settings, dict):
		frappe.throw("Invalid assignment settings.")

	valid_users = {u["name"] for u in _assignable_users()}
	valid_sources = set(_known_sources())

	default = _validate_rule(settings.get("default") or {}, "Default", valid_users)

	sources = {}
	raw_sources = settings.get("sources")
	if isinstance(raw_sources, dict):
		for source, rule in raw_sources.items():
			source = (source or "").strip()
			if not source:
				continue
			if source not in valid_sources:
				frappe.throw(f"Unknown lead source '{source}'.")
			sources[source] = _validate_rule(rule, source, valid_users)

	cleaned = {
		"enabled": bool(settings.get("enabled", True)),
		"default": default,
		"sources": sources,
	}
	frappe.db.set_default(RULES_KEY, json.dumps(cleaned))
	# GOTCHA — `frappe.db.get_default` is served from a cache that a `set_default`
	# in the SAME process does not reliably invalidate, so the re-read below (and
	# any hook running later in this request) can see the PREVIOUS blob. Observed:
	# saving `enabled: false` and immediately inserting a lead still assigned an
	# owner, while the identical write in a fresh process paused correctly — i.e.
	# it fails intermittently and looks like a logic bug. Clearing explicitly is
	# the only thing that makes the write readable straight away.
	#
	# NOTE the helper is `frappe.defaults._clear_cache(parent)` — private, and the
	# only one there is. `frappe.defaults.clear_cache` does not exist, and calling
	# it raises INSIDE the whitelisted method, where `bench execute` swallows the
	# AttributeError and re-raises a completely unrelated `NameError: name 'crm'
	# is not defined`. Do not trust that message; it means "this function threw".
	frappe.defaults._clear_cache("__default")
	return get_lead_assignment_settings()
