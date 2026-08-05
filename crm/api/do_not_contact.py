"""Do-not-contact: the durable record that a buyer asked to be left alone.

WHY THIS EXISTS (gw296 — the Danny Stoica incident, 2026-08-05)
---------------------------------------------------------------
A buyer replied "remove". Exe moved his Dispo card to Not Interested, which the
bulk-text modal excludes by default, so the intent was recorded correctly. The
InvestorLift sync then silently moved the card back to Attempted to Contact, and
a later bulk text included him.

The lesson is not "fix that one sync bug" (that is fixed separately, in
investorlift_ingest). It is that **the board column was the wrong place to store
a removal request**. `interest_stage` is shared state with a third party: IL can
move it, and IL has no idea anyone asked us to stop texting. A compliance
decision has to live somewhere no integration writes.

That place is `CRM Buyer.do_not_contact`. No InvestorLift code path touches it —
the sync only ever writes the identity/telemetry keys built in `_upsert_buyer`,
and this field is deliberately not among them. `bulk_text.send_buyer_text`
refuses outright, server-side, so the block holds even if a UI filter regresses.

Set three ways:
  * automatically, when an inbound text reads as an opt-out (see `is_opt_out`);
  * manually, from the buyer page / directory;
  * by an operator running `mark_do_not_contact` in bench.

Deliberately NOT wired to the dispo board: a buyer can be perfectly interested in
one property and still have asked us to stop texting, so the two are different
statements and collapsing them is what caused this bug in the first place.
"""

import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from crm.api.investorlift_ingest import BUYER_DOCTYPE

SALES_ROLES = ("System Manager", "Sales Manager", "Sales User")

# Carrier-standard opt-out keywords. Matched only when the WHOLE message is the
# keyword (after stripping punctuation/whitespace) — "cancel" and "end" are words
# that occur naturally in a real-estate conversation ("cancel the contract"), so a
# substring match on them would block buyers who never asked for anything.
OPT_OUT_KEYWORDS = frozenset({
	"stop", "stopall", "stop all", "unsubscribe", "end", "quit",
	"cancel", "revoke", "optout", "opt out", "remove", "removeme",
})

# Unambiguous phrases, matched anywhere in the message. Each one has to be a
# request to stop contacting — NOT a statement of disinterest. "not interested"
# is deliberately absent: that is a board-stage judgement, not an opt-out, and
# conflating the two is exactly the mistake this module exists to undo.
OPT_OUT_PHRASES = (
	"remove me", "take me off", "take my number off", "stop texting",
	"stop contacting", "stop messaging", "stop sending", "do not contact",
	"dont contact", "do not text", "dont text", "do not message",
	"dont message", "opt me out", "unsubscribe me", "lose my number",
	"delete my number", "remove my number", "remove from your list",
	"remove me from your list",
)

_PUNCT_RE = re.compile(r"[^\w\s]+")
_WS_RE = re.compile(r"\s+")


def _normalize(text):
	"""Lowercase, drop punctuation, collapse whitespace. 'STOP!!' -> 'stop'."""
	t = (text or "").lower()
	t = t.replace("’", "'").replace("`", "'")
	t = t.replace("'", "")  # don't -> dont, so one phrase form covers both
	t = _PUNCT_RE.sub(" ", t)
	return _WS_RE.sub(" ", t).strip()


def is_opt_out(text):
	"""True when an inbound message is a request to stop being contacted.

	Two tiers, because the two kinds of opt-out look nothing alike:

	  * the whole message is a carrier keyword ("STOP", "Remove.", "UNSUBSCRIBE")
	  * the message contains an unambiguous phrase ("please remove me from your
	    list", "stop texting me")

	Kept deliberately conservative in the direction that matters: a false positive
	costs one buyer being dropped from bulk texts until someone clears the flag; a
	false negative is texting a person who told us to stop.

	That asymmetry decides the genuinely ambiguous case too. "Take me off this
	property but keep sending others" flags, even though it is scoped to one deal:
	the flag is global, so we over-apply it, and someone clears it from the buyer
	page. That is cheap and self-correcting precisely because `do_not_contact_reason`
	stores the message verbatim -- whoever reviews it sees the sentence that
	tripped it and can judge in one glance. Guessing the narrow reading and
	guessing wrong is the failure that costs us.
	"""
	norm = _normalize(text)
	if not norm:
		return False
	if norm in OPT_OUT_KEYWORDS:
		return True
	return any(phrase in norm for phrase in OPT_OUT_PHRASES)


def is_blocked(buyer):
	"""Does this buyer carry a do-not-contact flag? False on a pre-provision site."""
	if not frappe.get_meta(BUYER_DOCTYPE).has_field("do_not_contact"):
		return False
	return bool(frappe.db.get_value(BUYER_DOCTYPE, buyer, "do_not_contact"))


def mark_do_not_contact(buyer, reason=None, set_by=None, enabled=True):
	"""Set/clear the flag. Written with db.set_value + update_modified=False so it
	never fights the IL sync's own writes or bumps `modified` on a machine touch.

	Returns True when the stored value actually changed."""
	meta = frappe.get_meta(BUYER_DOCTYPE)
	if not meta.has_field("do_not_contact"):
		return False
	current = frappe.db.get_value(BUYER_DOCTYPE, buyer, "do_not_contact")
	want = 1 if enabled else 0
	if int(current or 0) == want:
		return False

	values = {"do_not_contact": want}
	if meta.has_field("do_not_contact_reason"):
		values["do_not_contact_reason"] = (reason or "")[:1000] if enabled else None
	if meta.has_field("do_not_contact_by"):
		values["do_not_contact_by"] = (set_by or frappe.session.user) if enabled else None
	if meta.has_field("do_not_contact_at"):
		values["do_not_contact_at"] = now_datetime() if enabled else None
	frappe.db.set_value(BUYER_DOCTYPE, buyer, values, update_modified=False)

	frappe.publish_realtime(
		"crm_buyer_update", {"buyer": buyer}, after_commit=True
	)
	return True


@frappe.whitelist()
def set_buyer_do_not_contact(buyer, enabled=1, reason=None):
	"""UI entry point: toggle the flag from the buyer page / directory."""
	if not any(r in SALES_ROLES for r in frappe.get_roles()):
		frappe.throw(_("Only sales users can change this."), frappe.PermissionError)
	if not frappe.db.exists(BUYER_DOCTYPE, buyer):
		frappe.throw(_("Buyer not found"), frappe.DoesNotExistError)
	enabled = str(enabled) not in ("0", "false", "False", "")
	changed = mark_do_not_contact(
		buyer, reason=reason or (_("Set by hand") if enabled else None), enabled=enabled
	)
	return {"ok": True, "do_not_contact": 1 if enabled else 0, "changed": changed}


def check_inbound_opt_out(doc, method=None):
	"""after_insert on Quo Message — auto-flag a buyer who texts an opt-out.

	Only inbound buyer messages are considered. Wrapped so a detector failure can
	never break message storage or the realtime emit that rides on the same hook.
	"""
	try:
		if (doc.get("direction") or "").lower() not in ("incoming", "inbound"):
			return
		if doc.get("reference_doctype") != BUYER_DOCTYPE or not doc.get("reference_docname"):
			return
		if not is_opt_out(doc.get("content")):
			return
		snippet = (doc.get("content") or "").strip()[:200]
		if mark_do_not_contact(
			doc.reference_docname,
			reason=_("Replied: {0}").format(snippet),
			set_by="Automatic (inbound text)",
		):
			frappe.logger("do_not_contact").info(
				f"auto do-not-contact {doc.reference_docname}: {snippet!r}"
			)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "do-not-contact opt-out check failed")


@frappe.whitelist()
def backfill_opt_outs(dry_run=1, limit=None):
	"""Sweep stored inbound buyer texts and flag anyone who already asked to stop.

	The detector is new; the requests it looks for are not. Bench-executable:

	    bench execute crm.api.do_not_contact.backfill_opt_outs --kwargs '{"dry_run":1}'
	"""
	dry_run = str(dry_run) not in ("0", "false", "False", "")
	if not frappe.db.exists("DocType", "Quo Message"):
		return {"ok": False, "reason": "Quo Message not provisioned"}
	if not frappe.get_meta(BUYER_DOCTYPE).has_field("do_not_contact"):
		return {"ok": False, "reason": "do_not_contact not provisioned"}

	rows = frappe.get_all(
		"Quo Message",
		filters={"reference_doctype": BUYER_DOCTYPE, "direction": ("in", ("Incoming", "Inbound"))},
		fields=["name", "reference_docname", "content", "message_date"],
		order_by="creation asc",
		limit_page_length=int(limit) if limit else 0,
	)
	hits, flagged = [], 0
	for r in rows:
		if not r.reference_docname or not is_opt_out(r.content):
			continue
		snippet = (r.content or "").strip()[:200]
		hits.append({"buyer": r.reference_docname, "text": snippet, "at": str(r.message_date)})
		if not dry_run and mark_do_not_contact(
			r.reference_docname,
			reason=_("Replied: {0}").format(snippet),
			set_by="Automatic (backfill)",
		):
			flagged += 1
	if not dry_run:
		frappe.db.commit()
	return {
		"ok": True, "dry_run": dry_run, "scanned": len(rows),
		"matches": len(hits), "newly_flagged": flagged, "hits": hits[:100],
	}
