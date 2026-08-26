"""Save an offer calc to the lead's activity timeline.

This is the comps-page calculator, not the desk rail. The rail is
90% ARV − 2×repairs − fee and lives in `price_determination`. Cash runs
ARV × % − (mult × repairs) − assignment fee per scenario, where `mult` is
1 (the classic 70% rule) or 2 (the same shape the rail uses). Novation is
Current value − 10% − fee ($40k default) — no repairs. They must not write
the same field or a re-price on one surface silently rewrites the other.

The numbers are recomputed here rather than trusted from the client, so the
timeline card and the calculator cannot disagree about what an offer was. A
scenario saved before the cash-formula toggle existed carries no `mult` and
is read as 1 — which is what its numbers meant when they were written. A
scenario with no `kind` is cash, for the same reason.
"""

import html as html_lib
import json
import re

import frappe
from frappe import _
from frappe.utils import escape_html, flt, get_url

from crm.api.comps import _guard


def _num(v):
	return flt(v or 0)


def _money(n):
	return "$" + f"{int(round(_num(n))):,}"


def _psf_money(n):
	"""$/sf, with cents only when it has them.

	A repair bill typed as a round number rarely divides evenly into the square
	footage ($45,000 over 1,260 sf is $35.714…), and the calculator keeps that
	remainder on the RATE so the bill stays exactly what was typed. Rounding it
	here would print "$36/sf × 1,260 sf = $45,000" on the timeline, which is off
	by $360 and reads as the card contradicting itself.
	"""
	v = _num(n)
	return _money(v) if float(v).is_integer() else f"${v:,.2f}"


def _street(addr):
	return (addr or "").split(",")[0].strip()


def _zillow(addr):
	slug = re.sub(r"[^A-Za-z0-9]+", "-", addr or "").strip("-")
	return f"https://www.zillow.com/homes/{slug}_rb/" if slug else ""


def _kind(raw):
	k = (raw.get("kind") or "cash") if isinstance(raw, dict) else "cash"
	return "novation" if k == "novation" else "cash"


def _pct(raw, default=0):
	if "pct" not in raw or raw.get("pct") in (None, ""):
		return default
	pct = _num(raw.get("pct"))
	if pct > 1:
		pct = pct / 100.0
	return pct


def _scene(raw, sqft):
	if not isinstance(raw, dict):
		return None
	arv = _num(raw.get("arv") or raw.get("value") or raw.get("current_value"))
	if arv <= 0:
		return None
	kind = _kind(raw)
	fee = _num(raw.get("fee"))
	if kind == "novation":
		pct = _pct(raw, 0.10)
		if pct < 0 or pct >= 1:
			return None
		cut = round(arv * pct)
		after = round(arv - cut)
		return {
			"kind": "novation",
			"arv": arv,
			"pct": pct,
			"fee": fee,
			"cut": cut,
			"after": after,
			"offer": after - fee,
		}
	pct = _pct(raw, 0)
	if pct <= 0:
		return None
	rehab_psf = _num(raw.get("rehabPsf") or raw.get("rehab_psf"))
	mult = 2 if int(_num(raw.get("mult")) or 1) == 2 else 1
	after = round(arv * pct)
	repairs = round(rehab_psf * _num(sqft))
	rehab = repairs * mult
	wholesale = after - rehab
	offer = wholesale - fee
	return {
		"kind": "cash",
		"arv": arv,
		"pct": pct,
		"mult": mult,
		"rehab_psf": rehab_psf,
		"fee": fee,
		"after": after,
		"repairs": repairs,
		"rehab": rehab,
		"wholesale": wholesale,
		"offer": offer,
	}


def _comps(raw):
	out = []
	for c in raw or []:
		if not isinstance(c, dict):
			continue
		addr = (c.get("address") or "").strip()
		if not addr:
			continue
		out.append(
			{
				"name": c.get("name") or "",
				"address": addr,
				"price": _num(c.get("price")),
				"square_footage": _num(c.get("square_footage")),
				"distance_mi": _num(c.get("distance_mi")),
				"status": c.get("status") or "",
			}
		)
	return out


def _comp_facts(c):
	psf = (
		round(c["price"] / c["square_footage"])
		if c["price"] and c["square_footage"]
		else 0
	)
	bits = [_money(c["price"])]
	if c["square_footage"]:
		bits.append(f"{int(c['square_footage']):,} sf")
	if psf:
		bits.append(_money(psf) + "/sf")
	if c["distance_mi"]:
		bits.append(f"{c['distance_mi']:.2f} mi")
	return " · ".join(bits)


def _scene_payload(sc):
	if sc.get("kind") == "novation":
		return {
			"kind": "novation",
			"arv": sc["arv"],
			"pct": sc["pct"],
			"fee": sc["fee"],
			"cut": sc["cut"],
			"after": sc["after"],
			"offer": sc["offer"],
		}
	return {
		"kind": "cash",
		"arv": sc["arv"],
		"pct": sc["pct"],
		"mult": sc["mult"],
		"rehab_psf": sc["rehab_psf"],
		"fee": sc["fee"],
		"after": sc["after"],
		"repairs": sc["repairs"],
		"rehab": sc["rehab"],
		"offer": sc["offer"],
	}


def _payload(lead, scenes, comps, sqft, notes=""):
	kind = scenes[0]["kind"] if scenes else "cash"
	return {
		"lead": lead,
		"kind": kind,
		"sqft": sqft,
		"notes": (notes or "").strip(),
		"scenarios": [_scene_payload(sc) for sc in scenes],
		"comps": [
			{
				"name": c.get("name") or "",
				"address": c["address"],
				"price": c["price"],
				"square_footage": c["square_footage"],
				"distance_mi": c["distance_mi"],
				"status": c.get("status") or "",
			}
			for c in comps
		],
	}


def _html(lead, scenes, comps, sqft, notes=""):
	# Vertical on purpose: the activity bubble is ~20rem and `prose-f` is
	# `break-all`, so a single "Comps: A · B" line wraps mid-number and reads
	# as a text blob. One row per comp, each a real link. `data-cash-offer` is
	# the structured copy the timeline card hydrates; the HTML is the fallback
	# for email / edit-source / anything that is not CommentArea.
	page = get_url(f"/crm/leads/{lead}/comps")
	attr = html_lib.escape(
		json.dumps(_payload(lead, scenes, comps, sqft, notes), separators=(",", ":")),
		quote=True,
	)
	title = _("Novation offer") if scenes and scenes[0].get("kind") == "novation" else _("Cash offer")
	parts = [
		'<div class="cash-offer" data-cash-offer="{}">'.format(attr),
		"<div><b>{}</b></div>".format(escape_html(title)),
	]
	for i, sc in enumerate(scenes):
		label = _("Scenario {0}").format(i + 1)
		if sc.get("kind") == "novation":
			parts.append(
				"<div>{label} ({pct:.0f}%)</div>"
				"<div>{arv} − {pct:.0f}% = {after}</div>"
				'<div>− fee {fee} = <b style="white-space:nowrap">{offer}</b></div>'.format(
					label=escape_html(label),
					pct=sc["pct"] * 100,
					arv=_money(sc["arv"]),
					after=_money(sc["after"]),
					fee=_money(sc["fee"]),
					offer=_money(sc["offer"]),
				)
			)
			continue
		# The formula is named on the card. Without it a doubled deduction reads
		# as an arithmetic mistake to anyone reading the timeline later.
		shape = (
			_("{0:.0f}% · 2× repairs").format(sc["pct"] * 100)
			if sc["mult"] == 2
			else _("{0:.0f}%").format(sc["pct"] * 100)
		)
		bill = "{psf}/sf × {sf} sf".format(
			psf=_psf_money(sc["rehab_psf"]), sf=f"{int(sqft):,}" if sqft else "—"
		)
		if sc["mult"] == 2:
			bill += " = {0} × 2".format(_money(sc["repairs"]))
		parts.append(
			"<div>{label} ({shape})</div>"
			"<div>{arv} × {pct:.0f}% = {after}</div>"
			"<div>− {word} {rehab} ({bill})</div>"
			'<div>− fee {fee} = <b style="white-space:nowrap">{offer}</b></div>'.format(
				label=escape_html(label),
				shape=escape_html(shape),
				word=escape_html(_("repairs") if sc["mult"] == 2 else _("rehab")),
				pct=sc["pct"] * 100,
				arv=_money(sc["arv"]),
				after=_money(sc["after"]),
				rehab=_money(sc["rehab"]),
				bill=escape_html(bill),
				fee=_money(sc["fee"]),
				offer=_money(sc["offer"]),
			)
		)
	if comps:
		parts.append("<div><b>{}</b></div>".format(escape_html(_("Comps"))))
		for c in comps:
			z = _zillow(c["address"])
			label = escape_html(_street(c["address"]) or c["address"])
			href = z or page
			parts.append(
				'<div><a href="{href}" target="_blank" rel="noopener noreferrer">'
				"{label}</a> {facts}</div>".format(
					href=escape_html(href),
					label=label,
					facts=escape_html(_comp_facts(c)),
				)
			)
	else:
		parts.append("<div>{}</div>".format(escape_html(_("No comps picked."))))
	note = (notes or "").strip()
	if note:
		parts.append(
			"<div><b>{}</b><br>{}</div>".format(
				escape_html(_("Notes")),
				escape_html(note).replace("\n", "<br>"),
			)
		)
	parts.append(
		'<div><a href="{href}" target="_blank" rel="noopener noreferrer">{label}</a></div>'.format(
			href=escape_html(page),
			label=escape_html(_("Tweak calcs")),
		)
	)
	parts.append("</div>")
	return "".join(parts)


@frappe.whitelist()
def save_cash_offer(lead, scenarios=None, comps=None, subject_sqft=None, notes=None):
	"""Write the current cash or novation calc onto the lead timeline. Does not touch the desk rail."""
	_guard()
	if not frappe.db.exists("CRM Lead", lead):
		frappe.throw(_("Lead {0} does not exist.").format(lead), frappe.DoesNotExistError)
	if not frappe.has_permission("CRM Lead", "write", lead):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if isinstance(scenarios, str):
		scenarios = json.loads(scenarios or "[]")
	if isinstance(comps, str):
		comps = json.loads(comps or "[]")

	sqft = _num(subject_sqft)
	scenes = [s for s in (_scene(x, sqft) for x in (scenarios or [])) if s]
	if not scenes:
		frappe.throw(_("Type a value in at least one scenario first."))

	used = _comps(comps)
	content = _html(lead, scenes, used, sqft, notes or "")
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
	return {"ok": True, "comps": len(used), "scenarios": len(scenes)}
