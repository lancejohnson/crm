# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt
"""
Person-name formatter for leads coming in with odd casing.

Inbound leads (iSpeedToLead webhook, manual entry, imports) frequently arrive
with names like "joe cholock", "priscilla Diaz", or "JOHN SMITH". This module
normalizes a person's name to proper title case while *preserving* names that
were already deliberately cased (McDonald, DeAngelo, DiCaprio, O'Brien-Smith).

Design notes
------------
- We only reformat a *word* when it is entirely lowercase or entirely
  uppercase. A word that already contains internal capitals (McDonald,
  DeAngelo, LaToya) is assumed to be intentional and is left untouched. This is
  what makes the formatter safe to run as a creation hook AND idempotent for
  backfill — re-running never mangles a good name.
- Reformatting a "bad" word handles the common structural cases: Mc-, the
  O'/D' apostrophe family, hyphenated double names, and generational
  suffixes / Roman numerals (Jr, Sr, III, IV ...).
- We do NOT lowercase nobiliary particles (de/del/la/van/von). For US lead
  data those are overwhelmingly capitalized (De La Cruz, Del Toro, Van Dyke),
  so simple per-word title case is both simpler and more correct here.

The wiring (creation hook + backfill) lives at the bottom of the file.
"""

import frappe

# lowercase form -> canonical form
_SUFFIXES = {
	"jr": "Jr",
	"jr.": "Jr.",
	"sr": "Sr",
	"sr.": "Sr.",
	"ii": "II",
	"iii": "III",
	"iv": "IV",
	"vi": "VI",
	"vii": "VII",
	"viii": "VIII",
	"ix": "IX",
}

_APOSTROPHES = ("'", "’")  # straight + curly

# Connector words kept lowercase when they appear mid-name, e.g. for couples
# stored in one field: "Carol and Charles Edwards".
_CONNECTORS = {"and", "or", "of", "the", "nor"}


def _cap(s: str) -> str:
	"""Upper-case the first character, lower-case the rest. Empty-safe."""
	return s[:1].upper() + s[1:].lower() if s else s


def _is_suspect(atom: str) -> bool:
	"""
	True when a chunk looks machine-mangled (all lower or all upper) and is
	therefore safe to reformat. A chunk with any internal capital is treated as
	intentional and left alone. Decided at the smallest unit so that, e.g.,
	"Smith-jones" fixes only the lowercase half.
	"""
	if not any(c.isalpha() for c in atom):
		return False  # pure punctuation / digits — leave it
	return atom == atom.lower() or atom == atom.upper()


def _recase_atom(atom: str) -> str:
	"""Re-case one mangled chunk that has no spaces, hyphens, or apostrophes."""
	low = atom.lower()
	if low in _SUFFIXES:
		return _SUFFIXES[low]
	# McDonald (only when there's a real remainder of letters after "mc")
	if low.startswith("mc") and len(atom) > 2 and atom[2:].isalpha():
		return "Mc" + _cap(atom[2:])
	return _cap(atom)


def _format_atom(atom: str) -> str:
	"""Re-case a chunk only if it looks mangled; otherwise preserve it."""
	return _recase_atom(atom) if _is_suspect(atom) else atom


def _format_segment(seg: str) -> str:
	"""A hyphen-free chunk; handles the O'Brien / D'Angelo apostrophe family."""
	for ap in _APOSTROPHES:
		if ap in seg:
			return ap.join(_format_atom(p) for p in seg.split(ap))
	return _format_atom(seg)


def _format_word(word: str) -> str:
	"""One whitespace-delimited token, preserving hyphens (Mary-Jane)."""
	return "-".join(_format_segment(s) for s in word.split("-"))


def format_person_name(raw):
	"""
	Title-case a person name, fixing odd casing while preserving names that
	were already deliberately cased.

	Idempotent. Returns the input unchanged for falsy / non-string values.

	>>> format_person_name("joe cholock")
	'Joe Cholock'
	>>> format_person_name("priscilla Diaz")
	'Priscilla Diaz'
	>>> format_person_name("JOHN MCDONALD")
	'John McDonald'
	>>> format_person_name("o'brien-smith")
	"O'Brien-Smith"
	>>> format_person_name("DeAngelo")   # already cased -> untouched
	'DeAngelo'
	"""
	if not raw or not isinstance(raw, str):
		return raw

	words = raw.split()  # collapses runs of whitespace and trims ends
	out = []
	for i, w in enumerate(words):
		# connectors stay lowercase mid-name ("Carol and Charles" couples)
		if i > 0 and w.lower() in _CONNECTORS:
			out.append(w.lower())
		else:
			out.append(_format_word(w))
	return " ".join(out)


# ---------------------------------------------------------------------------
# Lead wiring
# ---------------------------------------------------------------------------

_NAME_PARTS = ("first_name", "middle_name", "last_name")


def normalize_lead_names(doc, method=None):
	"""
	`CRM Lead` before_validate hook. Normalizes the stored name parts on
	creation only, so later manual edits are respected. `validate()` rebuilds
	`lead_name`/`title` from the (now normalized) parts.
	"""
	if not doc.is_new():
		return
	for field in _NAME_PARTS:
		current = doc.get(field)
		formatted = format_person_name(current)
		if formatted != current:
			doc.set(field, formatted)


def _rebuild_lead_name(salutation, first, middle, last):
	"""Mirror CRMLead.set_full_name's join order."""
	return " ".join(p for p in (salutation, first, middle, last) if p)


@frappe.whitelist()
def backfill_lead_names(dry_run=1, limit=None):
	"""
	Re-case existing leads whose name parts look machine-mangled.

	Read-only when `dry_run` is truthy (the default): returns a summary plus a
	sample of proposed changes without writing. Pass `dry_run=0` to apply.

	Writes go through `frappe.db.set_value(..., update_modified=False)` (no
	`doc.save`) so we don't trigger status logs / SLA / assignment side-effects
	or disturb each lead's `modified` timestamp (which the activity timeline
	anchors on) — mirroring the first_call.py writeback pattern.

	Run via bench:
	    bench --site <site> execute crm.api.name_format.backfill_lead_names
	    bench --site <site> execute crm.api.name_format.backfill_lead_names \
	        --kwargs '{"dry_run": 0}'
	"""
	dry_run = frappe.utils.cint(dry_run)
	limit = frappe.utils.cint(limit) or None

	leads = frappe.get_all(
		"CRM Lead",
		filters={"first_name": ["is", "set"]},
		fields=[
			"name",
			"salutation",
			"first_name",
			"middle_name",
			"last_name",
			"lead_name",
		],
		limit=limit,
	)

	changes = []
	for lead in leads:
		new_parts = {f: format_person_name(lead.get(f)) for f in _NAME_PARTS}
		part_changed = any((new_parts[f] or "") != (lead.get(f) or "") for f in _NAME_PARTS)

		new_lead_name = _rebuild_lead_name(
			lead.get("salutation"),
			new_parts["first_name"],
			new_parts["middle_name"],
			new_parts["last_name"],
		)
		name_changed = (new_lead_name or "") != (lead.get("lead_name") or "")

		if not part_changed and not name_changed:
			continue

		update = {f: new_parts[f] for f in _NAME_PARTS if (new_parts[f] or "") != (lead.get(f) or "")}
		if name_changed:
			update["lead_name"] = new_lead_name

		changes.append(
			{
				"name": lead["name"],
				"old_lead_name": lead.get("lead_name"),
				"new_lead_name": new_lead_name,
				"update": update,
			}
		)

	if not dry_run:
		for c in changes:
			frappe.db.set_value("CRM Lead", c["name"], c["update"], update_modified=False)
		frappe.db.commit()

	return {
		"dry_run": bool(dry_run),
		"scanned": len(leads),
		"to_change": len(changes),
		"applied": 0 if dry_run else len(changes),
		"sample": [
			{"name": c["name"], "from": c["old_lead_name"], "to": c["new_lead_name"]}
			for c in changes[:50]
		],
	}


def _selftest():
	"""Quick assertion suite, runnable via `bench execute`."""
	cases = {
		"joe cholock": "Joe Cholock",
		"priscilla Diaz": "Priscilla Diaz",
		"JOHN SMITH": "John Smith",
		"john mcdonald": "John McDonald",
		"JOHN MCDONALD": "John McDonald",
		"o'brien": "O'Brien",
		"d'angelo russell": "D'Angelo Russell",
		"mary-jane watson": "Mary-Jane Watson",
		"robert downey jr": "Robert Downey Jr",
		"henry viii": "Henry VIII",
		"  extra   spaces  ": "Extra Spaces",
		"carol and charles edwards": "Carol and Charles Edwards",
		"CAROL AND CHARLES": "Carol and Charles",
		"DeAngelo": "DeAngelo",  # already cased -> preserved
		"McDonald": "McDonald",  # already cased -> preserved
		"Priscilla Diaz": "Priscilla Diaz",  # already correct -> unchanged
		"": "",
		None: None,
	}
	failures = []
	for raw, expected in cases.items():
		got = format_person_name(raw)
		if got != expected:
			failures.append({"input": raw, "expected": expected, "got": got})
	return {"passed": len(cases) - len(failures), "total": len(cases), "failures": failures}
