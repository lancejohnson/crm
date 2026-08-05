# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""One-time redistribution of existing leads onto the setters.

The round robin (`crm.api.lead_round_robin`) only routes leads created from now
on. Everything already in the CRM still sits on the old hardcoded default owner,
which matters more than it sounds: the Today board is now scoped to the viewer's
own leads, so without this backfill German and Exe open the board and see
nothing at all.

Scope: **live, workable leads only.** Converted deals, dead/lost leads, won
leads and parked import batches (`import_hidden`) are all left alone \u2014 handing
someone 500 parked LeadPack rows or a pile of dead leads is not giving them
work, it is giving them noise. Measured on prod 2026-08-05: 747 leads total, of
which only **107** are actually live and workable.

Only leads on the *default* owner (or with no owner at all) are moved. A lead
somebody deliberately took is left where it is \u2014 this undoes an automatic
default, it does not overrule a human.

Two strategies, because the data is lopsided
--------------------------------------------
Prior contact on those 107 leads: 78 have calls from a setter, and where one
setter clearly leads it is **70 German / 6 Exe**. So the two obvious approaches
pull in opposite directions:

* ``continuity`` (default) \u2014 a setter who has clearly been calling a lead keeps
  it, and everything else is dealt out to even the totals up as far as it can.
  A seller who has spoken to German twice should not suddenly be Exe's problem.
  With this data that lands roughly 70/37, not 50/50: lopsided, but it is an
  honest reflection of who has been doing the calling.
* ``even`` \u2014 ignore history and split as close to 50/50 as possible. Use this
  if an even starting workload matters more than relationship continuity.

Run it dry first; the dry run reports the resulting split and exactly how many
relationships each strategy preserves or breaks::

    bench --site <site> execute crm.api.lead_owner_backfill.backfill_lead_owners
    bench --site <site> execute crm.api.lead_owner_backfill.backfill_lead_owners \\
        --kwargs '{"dry_run": 0}'

Writes
------
`lead_owner` is written with ``db.set_value(..., update_modified=False)`` rather
than ``doc.save()``, following the same rule as the other backfills here: a full
save would re-run SLA application on every lead and disturb the ``modified``
timestamp the activity timeline anchors on. The consequence is that this leaves
no Version row, so a moved lead shows no "changed Lead Owner" entry on its
timeline \u2014 deliberate for a bulk admin action, but worth knowing when someone
later asks why a lead changed hands.

Assignment is then fixed up explicitly, which `doc.save()` would NOT have done
correctly anyway: `CRM Lead.assign_agent` only ever ADDS an assignee. Left to
itself it would leave every moved lead assigned to the old owner *and* the new
one \u2014 exactly the double-assignment `lead_import` warns about.
"""

import frappe
from frappe.desk.form.assign_to import add as assign_todo
from frappe.desk.form.assign_to import remove as unassign_todo

from crm.api.lead_round_robin import get_roster

LEAD = "CRM Lead"

#: Owners whose leads are considered "unclaimed" and therefore movable. The
#: empty string / None cover leads that never got an owner at all.
DEFAULT_FROM_OWNERS = ("dennis.szafran@groundworkpro.com", "", None)


def _terminal_statuses() -> set[str]:
	"""Lead statuses that mean the lead is finished, either way.

	Keyed on `CRM Lead Status.type` rather than on names, for the same reason
	`task_hygiene` is: "Dead Lead" and "Lost" are both type Lost, and a renamed
	or newly added dead status keeps working.
	"""
	return set(
		frappe.get_all(
			"CRM Lead Status", filters={"type": ["in", ("Lost", "Won")]}, pluck="name"
		)
	)


def _eligible_leads(from_owners) -> list[dict]:
	"""Live, workable, currently-unclaimed leads, oldest first."""
	terminal = _terminal_statuses()
	has_hidden = frappe.db.has_column(LEAD, "import_hidden")

	fields = ["name", "lead_name", "lead_owner", "status", "creation", "converted"]
	if has_hidden:
		fields.append("import_hidden")

	rows = frappe.get_all(LEAD, fields=fields, order_by="creation asc", limit_page_length=0)

	out = []
	for row in rows:
		if (row.lead_owner or "") not in [o or "" for o in from_owners]:
			continue
		if row.get("converted"):
			continue
		if has_hidden and row.get("import_hidden"):
			continue
		if row.status in terminal:
			continue
		out.append(row)
	return out


def _quo_number_map() -> dict[str, str]:
	"""last-10 digits of each user's Quo line -> that user."""
	out = {}
	for user in frappe.get_all(
		"User", filters={"custom_quo_number": ["is", "set"]},
		fields=["name", "custom_quo_number"],
	):
		digits = "".join(ch for ch in (user.custom_quo_number or "") if ch.isdigit())
		if len(digits) >= 10:
			out[digits[-10:]] = user.name
	return out


def _prior_contact(lead_names, roster) -> dict[str, str]:
	"""lead -> the setter who has clearly been working it, where there is one.

	Attribution reuses the same chain the activity report uses (`caller` ->
	`receiver` -> `User.custom_quo_number`) so this cannot disagree with the
	reporting about whose call it was. A lead is only claimed when ONE setter
	leads outright; an even split between two of them is left to the balancer.
	"""
	if not lead_names:
		return {}

	quo = _quo_number_map()
	rows = frappe.db.sql(
		"""
		select reference_docname lead, caller, receiver, count(*) c
		from `tabCRM Call Log`
		where reference_doctype='CRM Lead' and reference_docname in %(names)s
		group by reference_docname, caller, receiver
		""",
		{"names": lead_names},
		as_dict=True,
	)

	tally = {}
	for row in rows:
		who = None
		for field in ("caller", "receiver"):
			value = (row.get(field) or "").strip()
			if value and "@" in value:
				who = value
				break
		if not who:
			for field in ("caller", "receiver"):
				digits = "".join(ch for ch in (row.get(field) or "") if ch.isdigit())
				if len(digits) >= 10 and digits[-10:] in quo:
					who = quo[digits[-10:]]
					break
		if who in roster:
			tally.setdefault(row.lead, {})
			tally[row.lead][who] = tally[row.lead].get(who, 0) + row.c

	claimed = {}
	for lead, counts in tally.items():
		ranked = sorted(counts.items(), key=lambda kv: -kv[1])
		if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
			claimed[lead] = ranked[0][0]
	return claimed


def _plan(leads, roster, strategy, contact):
	"""Decide the new owner for each lead. Pure — no writes, easy to dry-run."""
	claimed = contact if strategy == "continuity" else {}

	# Seed the running totals with what each setter already holds among LIVE
	# leads, so "even" means even overall rather than even within this batch.
	totals = {user: 0 for user in roster}
	for lead in leads:
		if lead.lead_owner in totals:
			totals[lead.lead_owner] += 1

	plan = []
	# Continuity assignments first: they are fixed, and the balancer then deals
	# the free leads against the imbalance they created.
	for lead in leads:
		owner = claimed.get(lead.name)
		if owner:
			totals[owner] += 1
			plan.append({"lead": lead, "to": owner, "why": "prior contact"})

	free = [lead for lead in leads if lead.name not in claimed]
	for lead in free:
		# Fewest first; ties by roster order, so the outcome is deterministic and
		# a dry run matches the apply exactly.
		owner = min(roster, key=lambda u: (totals[u], roster.index(u)))
		totals[owner] += 1
		plan.append({"lead": lead, "to": owner, "why": "balance"})

	return plan, totals, claimed


def _reassign(lead_name, old_owner, new_owner):
	"""Move ownership and make the assignment match, without double-assigning."""
	frappe.db.set_value(LEAD, lead_name, "lead_owner", new_owner, update_modified=False)

	# Share first: a user who cannot read the lead cannot be assigned it. Mirrors
	# CRM Lead.share_with_agent, including its exists-check.
	if not frappe.db.exists(
		"DocShare", {"user": new_owner, "share_name": lead_name, "share_doctype": LEAD}
	):
		frappe.share.add_docshare(
			LEAD, lead_name, new_owner, write=1, flags={"ignore_share_permission": True}
		)

	current = frappe.parse_json(frappe.db.get_value(LEAD, lead_name, "_assign") or "[]")
	if new_owner not in current:
		assign_todo(
			{"assign_to": [new_owner], "doctype": LEAD, "name": lead_name},
			ignore_permissions=True,
		)

	# Drop the OLD owner's assignment, but only when it was the automatic one
	# (i.e. they were the lead_owner). Anyone else on the lead was put there by a
	# person and is left alone.
	if old_owner and old_owner != new_owner and old_owner in current:
		try:
			unassign_todo(LEAD, lead_name, old_owner)
		except Exception:
			frappe.log_error(
				f"lead owner backfill: could not unassign {old_owner} from {lead_name}",
				frappe.get_traceback(),
			)


@frappe.whitelist()
def backfill_lead_owners(dry_run=1, strategy="continuity", from_owners=None, limit=None):
	"""Redistribute live unclaimed leads across the round-robin roster.

	Dry run by default: reports the plan and the resulting split without writing.
	"""
	if isinstance(dry_run, str):
		dry_run = dry_run.strip().lower() not in ("0", "false", "no", "")
	else:
		dry_run = bool(dry_run)

	if strategy not in ("continuity", "even"):
		frappe.throw("strategy must be 'continuity' or 'even'")

	roster = get_roster()
	if len(roster) < 2:
		return {"error": "Round-robin roster needs at least two enabled users.", "roster": roster}

	owners = from_owners or DEFAULT_FROM_OWNERS
	if isinstance(owners, str):
		owners = frappe.parse_json(owners)

	leads = _eligible_leads(owners)
	if limit:
		leads = leads[: int(limit)]

	# Measured once and reused for both the plan and the report, so the "broken
	# relationships" number describes exactly the plan that would be applied.
	continuity_truth = _prior_contact([lead.name for lead in leads], roster)
	plan, totals, claimed = _plan(leads, roster, strategy, continuity_truth)

	preserved = sum(
		1 for entry in plan if continuity_truth.get(entry["lead"].name) == entry["to"]
	)
	broken = sum(
		1
		for entry in plan
		if entry["lead"].name in continuity_truth
		and continuity_truth[entry["lead"].name] != entry["to"]
	)

	applied = 0
	if not dry_run:
		for entry in plan:
			lead = entry["lead"]
			try:
				_reassign(lead.name, lead.lead_owner, entry["to"])
				applied += 1
			except Exception:
				frappe.log_error(
					f"lead owner backfill failed for {lead.name}", frappe.get_traceback()
				)
		frappe.db.commit()

	return {
		"dry_run": dry_run,
		"strategy": strategy,
		"roster": roster,
		"eligible": len(leads),
		"applied": applied,
		"resulting_split": totals,
		"by_reason": {
			"prior contact": sum(1 for e in plan if e["why"] == "prior contact"),
			"balance": sum(1 for e in plan if e["why"] == "balance"),
		},
		"relationships_preserved": preserved,
		"relationships_broken": broken,
		"sample": [
			{
				"lead": e["lead"].name,
				"name": e["lead"].lead_name,
				"status": e["lead"].status,
				"from": e["lead"].lead_owner or "(none)",
				"to": e["to"],
				"why": e["why"],
			}
			for e in plan[:15]
		],
	}
