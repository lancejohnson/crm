# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Keep API keys out of the Error Log.

The problem, found live
-----------------------
A BatchData tax pull 403'd and Frappe wrote the traceback to the Error Log —
including the local variable holding the request headers, which is to say the
live `Authorization: Bearer <token>` for our BatchData account, in plain text, in
a table any System Manager can read. It was not one row: **106 of 1,040** Error
Log rows carried a bearer token or an auth header, spanning two weeks and at
least three integrations (BatchData, Quo, and a long tail of generic handler
tracebacks).

Why Frappe's own sanitiser missed it
------------------------------------
Frappe DOES sanitise tracebacks (`frappe.utils._get_traceback_sanitizer`), with a
blocklist of `password / passwd / secret / token / key / pwd`. But it matches
those against **variable names** and **exact dict keys**. The leak was a variable
called `headers` holding a key called `Authorization` — neither is in the list,
and `Authorization` is not the literal string `token`. So the redaction ran and
sailed straight past the one thing that mattered.

Patching Frappe is not an option worth taking: `apps/frappe` is upstream and the
image is rebuilt `FROM ghcr.io/frappe/crm`, so any edit there is reverted on the
next deploy — silently, which is the worst way to lose a security control.

What this does instead
----------------------
A `before_insert` hook on Error Log, in OUR app, that redacts secrets out of the
text on the way in. That placement is deliberate:

  * it survives image rebuilds, because it lives in this repo;
  * it catches EVERY source — our code, Frappe internals, and any integration
    added later — rather than the handful of call sites we happen to know about;
  * it runs before the row exists, so the secret is never written at all, rather
    than written and cleaned up afterwards.

It is written to be impossible to fail loudly. This runs inside exception
handling, so a redactor that raises would swallow the very error somebody is
trying to debug. Every path is wrapped and falls back to the original text.
"""

import re

import frappe

PLACEHOLDER = "********"

#: Header/JSON/kwarg names whose VALUE is a secret. Matched case-insensitively
#: and only when followed by a `:` or `=`, so ordinary prose about "the token" is
#: left alone — the goal is to keep tracebacks debuggable, not to censor them.
_SECRET_NAMES = (
	"authorization",
	"x-rapidapi-key",
	"x-api-key",
	"apikey",
	"api_key",
	"api-key",
	"access_token",
	"refresh_token",
	"private_key",
	"client_secret",
	"password",
	"passwd",
	"pwd",
	"secret",
	"token",
)

_NAMES_RE = "|".join(re.escape(n) for n in _SECRET_NAMES)

#: Words that make an IDENTIFIER a secret holder, matched as a SUFFIX so
#: `QUO_KEY`, `PUSHOVER_TOKEN`, `RAPIDAPI_ZILLOW_KEY` and `DOCUSEAL_API_TOKEN`
#: are all caught without having to enumerate them.
#:
#: This is the rule that was missing, and it is the one that mattered most. The
#: ops server scripts hold their credentials as module-level constants
#: (`QUO_KEY = "..."`), and `frappe.utils.safe_exec` puts the ENTIRE script source
#: into the traceback of any error raised inside it — so a single failing script
#: reprints its own key on every exception. That is 839 of the leaked rows, and
#: none of them said "Authorization" anywhere, which is why the first pass missed
#: them completely.
_IDENT_SUFFIX = r"[A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD)"

_PATTERNS = (
	# `QUO_KEY = "..."` / `TOKEN = '...'` / escaped `TOKEN = \"...\"` inside JSON.
	# The trailing quote is matched loosely so an escaped \" closes correctly.
	(
		re.compile(r"(\b" + _IDENT_SUFFIX + r"\s*=\s*\\?['\"])([^'\"\\\n]{8,})", re.I),
		r"\1" + PLACEHOLDER,
	),
	# `Bearer eyJhbGciOi...` anywhere at all, including inside a quoted dict repr.
	# This is the shape that actually leaked, so it is matched on its own rather
	# than relying on the surrounding key being recognised.
	(re.compile(r"(Bearer\s+)([A-Za-z0-9._\-]{8,})", re.I), r"\1" + PLACEHOLDER),
	# `'Authorization': 'Bearer xyz'` / `"api_key": "xyz"` / `token = 'xyz'`
	# Keeps the NAME and the quotes so the traceback still reads naturally.
	# NOTE the value here has NO `Bearer` prefix requirement: Quo/OpenPhone sends
	# the raw key as the Authorization value, which is exactly why a Bearer-only
	# rule reported a clean log while 839 rows still held a live key.
	(
		re.compile(
			r"(['\"]?(?:" + _NAMES_RE + r")['\"]?\s*[:=]\s*)(['\"])([^'\"\n]{4,})(['\"])",
			re.I,
		),
		r"\1\2" + PLACEHOLDER + r"\4",
	),
	# Same, unquoted: `api_key=abc123` in a URL or a repr.
	(
		re.compile(r"((?:" + _NAMES_RE + r")\s*[:=]\s*)([^\s,;&'\"\)\}\n]{6,})", re.I),
		r"\1" + PLACEHOLDER,
	),
	# Query strings: `?key=...&token=...`
	(
		re.compile(r"([?&](?:" + _NAMES_RE + r")=)([^&\s'\"\n]{4,})", re.I),
		r"\1" + PLACEHOLDER,
	),
)


def redact(text):
	"""Strip secret values out of one blob of text. Never raises."""
	if not text:
		return text
	try:
		out = str(text)
		for pattern, replacement in _PATTERNS:
			out = pattern.sub(replacement, out)
		return out
	except Exception:
		# A redactor that throws inside exception handling would swallow the error
		# it was meant to protect. Returning the original is the safe failure: the
		# row is no worse than it is today.
		return text


def has_secret(text):
	"""True when redaction would change anything. Used by the sweep and by tests."""
	if not text:
		return False
	return redact(text) != str(text)


#: Every place a secret was actually found, and the fields that held it.
#: Derived from a known-plaintext audit: the real site_config values were
#: searched for across all 286 tables / 3,525 text columns of production.
REDACTED_FIELDS = {
	"Error Log": ("error", "method"),
	"Scheduled Job Log": ("details",),
	"Deleted Document": ("data",),
}

#: NOT redacted, deliberately: `Server Script.script` IS the credential's home.
#: The ops sync substitutes `__INFISICAL:QUO_API_KEY__` into the source because
#: the script sandbox cannot reach site_config, so blanking it there would simply
#: break texting and the webhooks. That is a real exposure, but it is an ops
#: design question (rotate the keys, restrict Server Script read), not something
#: a log scrubber gets to decide by breaking production.
NEVER_REDACT = ("Server Script",)


def _scrub_doc(doc, fields):
	for field in fields:
		value = doc.get(field)
		if not value:
			continue
		cleaned = redact(value)
		if cleaned != value:
			doc.set(field, cleaned)


def on_error_log_insert(doc, method=None):
	"""before_insert for the log doctypes — scrub before the row is ever written."""
	try:
		fields = REDACTED_FIELDS.get(doc.doctype)
		if fields:
			_scrub_doc(doc, fields)
	except Exception:
		# Deliberately silent, and deliberately NOT frappe.log_error: we may be
		# inside the creation of an Error Log, and logging from here risks recursion.
		pass


def on_version_insert(doc, method=None):
	"""`Version` before_insert, gated on the one doctype whose history holds keys.

	Version rows are written on essentially every save in the system, so running a
	handful of regexes over every one of them would be a real cost for no benefit.
	The audit found secrets in Version only where the versioned document was a
	Server Script -- whose source legitimately contains the credential -- so the
	gate is a single string compare and the regex work happens on the rare edit of
	a script rather than on every lead update.

	The HISTORY is safe to redact even though the live script is not: nothing
	executes a Version row, it is an audit trail.
	"""
	try:
		if doc.get("ref_doctype") in NEVER_REDACT:
			_scrub_doc(doc, ("data",))
	except Exception:
		pass


def _site_secrets(min_len=12):
	"""The literal secret values this site holds, from site_config.

	Used as a KNOWN-PLAINTEXT search. Pattern matching alone is what produced a
	false all-clear the first time round; searching for the actual strings is the
	only check that cannot be fooled by a shape nobody thought of.
	"""
	words = ("key", "token", "secret", "password", "pwd")
	out = {}
	for name, value in (frappe.conf or {}).items():
		if not isinstance(value, str) or len(value) < min_len:
			continue
		if any(w in name.lower() for w in words):
			out[name] = value
	return out


@frappe.whitelist()
def scrub_existing(dry_run=1, limit=None, batch=200):
	"""Redact secrets already sitting in the log tables.

	Covers every table a known-plaintext audit actually found secrets in, not just
	Error Log — the first pass cleaned one table with one pattern and reported a
	clean bill of health while 839 rows still held a live Quo key.

	Rows are selected by searching for the REAL secret values as well as by shape,
	so a credential in a form nobody anticipated is still found.

	REDACTS rather than deletes. These are real diagnostics and deleting them to
	hide a token would throw away the evidence with the secret.

	Raw SQL on purpose: `doc.save()` here would stamp `modified`, fire hooks and
	generate Version rows for thousands of records — and, for Version itself, would
	recurse.
	"""
	if not frappe.has_permission("Error Log", "write"):
		frappe.throw(frappe._("Not permitted."), frappe.PermissionError)
	dry = int(dry_run or 0)
	secrets = list(_site_secrets().values())

	targets = dict(REDACTED_FIELDS)
	targets["Version"] = ("data",)

	result = {"dry_run": bool(dry), "tables": {}, "redacted": 0, "scanned": 0}
	for doctype, fields in targets.items():
		table = f"tab{doctype}"
		if not frappe.db.table_exists(doctype):
			continue
		# Shape-based OR value-based. The value clauses are what catch the shapes
		# we have not thought of yet.
		clauses, params = [], {}
		for field in fields:
			for i, needle in enumerate(["%Bearer %", "%uthorization%", "%api_key%"]):
				key = f"p_{field}_{i}"
				clauses.append(f"`{field}` LIKE %({key})s")
				params[key] = needle
			for i, value in enumerate(secrets):
				key = f"s_{field}_{i}"
				clauses.append(f"`{field}` LIKE %({key})s")
				params[key] = f"%{value}%"
		select = ", ".join(["name"] + [f"`{f}`" for f in fields])
		rows = frappe.db.sql(
			f"SELECT {select} FROM `{table}` WHERE " + " OR ".join(clauses),
			params,
			as_dict=True,
		)
		if limit:
			rows = rows[: int(limit)]

		changed = 0
		for row in rows:
			result["scanned"] += 1
			updates = {}
			for field in fields:
				value = row.get(field)
				if not value:
					continue
				cleaned = redact(value)
				# Belt and braces: if a real secret survived the patterns, replace it
				# literally. This is what makes the sweep verifiable rather than hopeful.
				for secret in secrets:
					if secret in cleaned:
						cleaned = cleaned.replace(secret, PLACEHOLDER)
				if cleaned != value:
					updates[field] = cleaned
			if not updates:
				continue
			changed += 1
			if dry:
				continue
			frappe.db.sql(
				f"UPDATE `{table}` SET "
				+ ", ".join(f"`{f}` = %({f})s" for f in updates)
				+ " WHERE name = %(name)s",
				{**updates, "name": row.name},
			)
			if changed % int(batch) == 0:
				frappe.db.commit()
		if not dry:
			frappe.db.commit()
		result["tables"][doctype] = changed
		result["redacted"] += changed

	# Counted, never echoed: printing the offending text to prove it was found
	# would leak the secret into whatever read the result.
	result["note"] = "values replaced with " + PLACEHOLDER
	result["server_script_excluded"] = (
		"Server Script.script holds the live credential by design; redacting it "
		"would break texting and the webhooks. Rotate + restrict instead."
	)
	return result
