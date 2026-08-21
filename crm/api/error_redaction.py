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

_PATTERNS = (
	# `Bearer eyJhbGciOi...` anywhere at all, including inside a quoted dict repr.
	# This is the shape that actually leaked, so it is matched on its own rather
	# than relying on the surrounding key being recognised.
	(re.compile(r"(Bearer\s+)([A-Za-z0-9._\-]{8,})", re.I), r"\1" + PLACEHOLDER),
	# `'Authorization': 'Bearer xyz'` / `"api_key": "xyz"` / `token = 'xyz'`
	# Keeps the NAME and the quotes so the traceback still reads naturally.
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


def on_error_log_insert(doc, method=None):
	"""`Error Log` before_insert — scrub before the row is ever written."""
	try:
		for field in ("error", "method"):
			value = doc.get(field)
			if not value:
				continue
			cleaned = redact(value)
			if cleaned != value:
				doc.set(field, cleaned)
	except Exception:
		# Deliberately silent, and deliberately NOT frappe.log_error: we are inside
		# the creation of an Error Log, and logging from here risks recursion.
		pass


@frappe.whitelist()
def scrub_existing(dry_run=1, limit=None, batch=200):
	"""Redact secrets already sitting in the Error Log.

	REDACTS rather than deletes. The rows are real diagnostics — the BatchData 403
	that started this is exactly the kind of thing you want to still be able to
	read next month — and deleting them to hide a token would throw away the
	evidence along with the secret.

	Written with raw SQL on purpose: `doc.save()` on an Error Log would stamp
	`modified`, fire hooks and generate Version rows for a thousand records, none
	of which is wanted for a cleanup pass.
	"""
	if not frappe.has_permission("Error Log", "write"):
		frappe.throw(frappe._("Not permitted."), frappe.PermissionError)
	dry = int(dry_run or 0)

	rows = frappe.db.sql(
		"""SELECT name, error, method FROM `tabError Log`
		   WHERE error LIKE %(b)s OR error LIKE %(a)s OR error LIKE %(k)s
		      OR method LIKE %(b)s OR method LIKE %(a)s OR method LIKE %(k)s
		   ORDER BY creation DESC""",
		{"b": "%Bearer %", "a": "%uthorization%", "k": "%api_key%"},
		as_dict=True,
	)
	if limit:
		rows = rows[: int(limit)]

	changed, checked = 0, 0
	for row in rows:
		checked += 1
		updates = {}
		for field in ("error", "method"):
			value = row.get(field)
			if value and redact(value) != value:
				updates[field] = redact(value)
		if not updates:
			continue
		changed += 1
		if dry:
			continue
		frappe.db.sql(
			"UPDATE `tabError Log` SET "
			+ ", ".join(f"`{f}` = %({f})s" for f in updates)
			+ " WHERE name = %(name)s",
			{**updates, "name": row.name},
		)
		if changed % int(batch) == 0:
			frappe.db.commit()
	if not dry:
		frappe.db.commit()
	return {
		"scanned": checked,
		"redacted": changed,
		"dry_run": bool(dry),
		# Counted, never echoed: printing the offending text to prove it was found
		# would leak the secret into whatever read the result.
		"note": "values replaced with " + PLACEHOLDER,
	}
