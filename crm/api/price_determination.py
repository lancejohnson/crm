"""The saved price determination — what we told a seller, and what produced it.

The lead desk computes an offer live while the rep is on the phone. This module
is where that number stops being a screen state and becomes part of the record.

WHY THE SNAPSHOT KEEPS THE INPUTS *AND* THE CONSTANTS.

"We offered $35,300" is close to useless three weeks later. What anyone actually
asks is *why* — which comps, at what $/sf, against what repair level, and with
what margin and fee. So the snapshot carries the whole derivation, including the
formula constants (`margin`, `fee`) that were in force at the time.

That last part is the load-bearing one: constants change. If the fee moves from
$10,000 to $12,000 and we had stored only the inputs, every historical
determination would silently re-derive to a number nobody ever said out loud.
Storing the constants makes a saved determination a fact about the past rather
than a formula re-run against the present.

WHY THE SERVER RE-DERIVES ANYWAY.

Not to impose today's formula — it uses the snapshot's own constants — but to
catch a client that sends an offer its own inputs do not produce. A wrong number
here is a wrong number said to a seller, and the failure mode is silent: it looks
exactly like a right one. Consistency is cheap to check and expensive to miss.

WHERE IT LIVES.

  CRM Lead.price_determination      the current snapshot, JSON
  CRM Lead.price_determination_at   when it was saved

plus a Comment on the lead's activity timeline for every save. The field is the
CURRENT price; the timeline is the HISTORY. A rep who re-prices after a repair
walkthrough should not overwrite the record of what was said before — but the
lead also has to be able to answer "what is our number" without replaying a feed.

Both fields are added by the ops repo (`scripts/setup_price_determination.py`)
and every write is column-guarded, so this module is safe to deploy before them:
with the fields absent the timeline entry still lands (the durable half) and the
response says `stored: false` rather than pretending it saved.
"""

import json

import frappe
from frappe import _
from frappe.utils import escape_html, flt

FIELDS = ("price_determination", "price_determination_at")

# Repair levels the desk offers. Kept server-side as a vocabulary check only —
# the costs live in the rail, because the sheet they come from is the team's, not
# ours, and a snapshot records the amount that was used rather than a lookup key.
LEVELS = ("smooth", "shiver", "abandon")

# How far the re-derived offer may sit from the client's before we refuse it.
# Not zero: the rail rounds ARV to $1,000 and JSON round-trips floats.
OFFER_TOLERANCE = 1.0


def _enabled():
	return all(frappe.db.has_column("CRM Lead", f) for f in FIELDS)


def _num(v):
	return flt(v or 0)


def _clean_comps(raw):
	"""Keep only what a determination needs to be re-read later.

	Deliberately a copy, not a list of `CRM Comp` names: a comp is a projection
	of an upstream feed that is re-synced nightly, and a BatchData fallback comp
	has no CRM row at all. A determination that resolved its comps by reference
	would quietly change — or empty out — as the inventory moved underneath it.
	"""
	out = []
	for c in raw or []:
		if not isinstance(c, dict):
			continue
		out.append(
			{
				"name": c.get("name") or "",
				"address": (c.get("address") or "").strip(),
				"price": _num(c.get("price")),
				"square_footage": _num(c.get("square_footage")),
				"status": c.get("status") or "",
				"removed_date": c.get("removed_date") or None,
				"source": c.get("source") or "",
			}
		)
	return out


def _derive(snap):
	"""The offer the snapshot's own numbers produce. Mirrors OfferRail.vue."""
	gross = round(_num(snap.get("arv")) * _num(snap.get("margin")) / 100)
	return max(0, gross - _num(snap.get("repairs")) * 2 - _num(snap.get("fee")))


def _shape(payload):
	"""Validate the incoming determination and return the snapshot we store."""
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except ValueError:
			frappe.throw(_("Determination must be a JSON object."))
	if not isinstance(payload, dict):
		frappe.throw(_("Determination must be a JSON object."))

	level = (payload.get("level") or "").strip().lower()
	if level not in LEVELS:
		frappe.throw(_("Unknown repair level {0}.").format(level or "''"))

	majors = [str(m).strip() for m in (payload.get("majors") or []) if str(m).strip()]

	snap = {
		"arv": _num(payload.get("arv")),
		"psf": _num(payload.get("psf")),
		"subject_sqft": _num(payload.get("subject_sqft")),
		"level": level,
		"majors": majors,
		"repairs": _num(payload.get("repairs")),
		"margin": _num(payload.get("margin")),
		"fee": _num(payload.get("fee")),
		"offer": _num(payload.get("offer")),
		"comps": _clean_comps(payload.get("comps")),
		"read": {
			"motivated": (payload.get("read") or {}).get("motivated") or "",
			"on_price": (payload.get("read") or {}).get("on_price") or "",
		},
	}

	if snap["arv"] <= 0:
		frappe.throw(_("There is no ARV to save — tick some comps first."))
	if snap["margin"] <= 0:
		frappe.throw(_("A determination needs the margin it was calculated with."))

	derived = _derive(snap)
	if abs(derived - snap["offer"]) > OFFER_TOLERANCE:
		# Refuse rather than silently store the server's answer: the two
		# disagreeing means the rail and this module have drifted apart, and the
		# rep already read their number out loud. Fix the code, don't paper over it.
		frappe.throw(
			_("Offer {0} does not follow from these inputs (expected {1}).").format(
				snap["offer"], derived
			)
		)
	return snap


@frappe.whitelist()
def save_price_determination(lead: str, determination):
	"""Save the desk's current price determination onto the lead.

	Returns `{stored, at, by, determination}`. `stored` is False when the ops
	fields are not yet present — the timeline entry still lands, so nothing the
	rep did is lost, and the caller can say so instead of showing a saved state
	that will vanish on reload.
	"""
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead {0} not found.").format(lead))
	frappe.has_permission("CRM Lead", "write", lead, throw=True)

	snap = _shape(determination)
	# Stamped server-side, always: who said this number and when is the part of a
	# determination most likely to be asked about, and a client is free to lie.
	snap["by"] = frappe.session.user
	snap["at"] = frappe.utils.now()
	snap["source"] = "lead desk"

	stored = _enabled()
	if stored:
		# `modified` is deliberately allowed to move here (unlike the Zillow and
		# BatchData caches, which write with update_modified=False). Those are the
		# machine remembering something; this is a person pricing a deal, and a
		# lead whose `modified` hides that would misreport when it was last worked.
		frappe.db.set_value(
			"CRM Lead",
			lead,
			{
				"price_determination": json.dumps(snap),
				"price_determination_at": snap["at"],
			},
		)

	_log_determination_comment(lead, snap)

	frappe.publish_realtime(
		"crm_price_determination",
		{"reference_doctype": "CRM Lead", "reference_docname": lead, "determination": snap},
		after_commit=True,
	)
	return {"stored": stored, "determination": snap}


@frappe.whitelist()
def get_price_determination(lead: str):
	"""The lead's current determination, or None. Never throws on bad stored JSON —
	a corrupt cache must not take the desk down mid-call."""
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead {0} not found.").format(lead))
	frappe.has_permission("CRM Lead", "read", lead, throw=True)
	if not _enabled():
		return None
	raw = frappe.db.get_value("CRM Lead", lead, "price_determination")
	if not raw:
		return None
	try:
		snap = json.loads(raw)
	except ValueError:
		return None
	return snap if isinstance(snap, dict) else None


def _money(n):
	"""`$120,000`. Deliberately not `fmt_money`, which renders `$ 120,000` with a
	space — the rail beside this timeline writes it without one, and one screen
	must not spell the same number two ways."""
	return "${:,.0f}".format(_num(n))


def _short_address(addr):
	"""Street line only — a comp list of eight full addresses is unreadable in a
	timeline entry, and the city is the subject's city in every case that matters."""
	return (addr or "").split(",")[0].strip()


def _log_determination_comment(lead, snap):
	"""Put the determination on the lead's own activity timeline.

	This is the durable half. The field holds the CURRENT number; the timeline is
	the only place that keeps what we said BEFORE we re-priced, which is exactly
	what gets asked about when a seller says "you told me a different number".

	Best-effort, like the Today board's outcome comment: a timeline write is never
	worth failing a save the rep is watching.
	"""
	try:
		head = _("Price determination — ARV {0} · repairs {1} · max offer {2}").format(
			_money(snap["arv"]), _money(snap["repairs"]), _money(snap["offer"])
		)

		comps = snap.get("comps") or []
		bits = []
		if comps:
			addrs = ", ".join(escape_html(_short_address(c.get("address"))) for c in comps[:8])
			more = _(" +{0} more").format(len(comps) - 8) if len(comps) > 8 else ""
			bits.append(
				_("{0} comps at {1}/sf: {2}{3}").format(
					len(comps), _money(snap.get("psf")), addrs, more
				)
			)
		# Title-cased to match the rail's own buttons (Smooth / Shiver / Abandon);
		# the stored value stays the lowercase key.
		level = escape_html((snap.get("level") or "").title())
		majors = ", ".join(escape_html(m) for m in (snap.get("majors") or []))
		if level:
			bits.append(level + (" + " + majors if majors else ""))
		read = snap.get("read") or {}
		if read.get("motivated") or read.get("on_price"):
			bits.append(
				_("read: motivated {0} · on price {1}").format(
					read.get("motivated") or "—", read.get("on_price") or "—"
				)
			)

		content = "<div><b>{0}</b>{1}</div>".format(
			escape_html(head), "<br><span>{0}</span>".format(" · ".join(bits)) if bits else ""
		)
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Comment",
				"reference_doctype": "CRM Lead",
				"reference_name": lead,
				"content": content,
				"comment_email": frappe.session.user,
				"comment_by": frappe.session.user,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Price determination comment failed")
