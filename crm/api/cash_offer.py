"""Save a cash-offer calc to the lead's activity timeline.

This is the comps-page calculator, not the desk rail. The rail is
90% ARV − 2×repairs − fee and lives in `price_determination`. This is
ARV × % − rehab − assignment fee, twice (Scenario 1 / Scenario 2). They
must not write the same field or a re-price on one surface silently
rewrites the other.
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


def _street(addr):
	return (addr or "").split(",")[0].strip()


def _zillow(addr):
	slug = re.sub(r"[^A-Za-z0-9]+", "-", addr or "").strip("-")
	return f"https://www.zillow.com/homes/{slug}_rb/" if slug else ""


def _scene(raw, sqft):
	if not isinstance(raw, dict):
		return None
	arv = _num(raw.get("arv"))
	if arv <= 0:
		return None
	pct = _num(raw.get("pct"))
	if pct > 1:
		pct = pct / 100.0
	if pct <= 0:
		return None
	rehab_psf = _num(raw.get("rehabPsf") or raw.get("rehab_psf"))
	fee = _num(raw.get("fee"))
	after = round(arv * pct)
	rehab = round(rehab_psf * _num(sqft))
	wholesale = after - rehab
	offer = wholesale - fee
	return {
		"arv": arv,
		"pct": pct,
		"rehab_psf": rehab_psf,
		"fee": fee,
		"after": after,
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


def _payload(lead, scenes, comps, sqft, notes=""):
	return {
		"lead": lead,
		"sqft": sqft,
		"notes": (notes or "").strip(),
		"scenarios": [
			{
				"arv": sc["arv"],
				"pct": sc["pct"],
				"rehab_psf": sc["rehab_psf"],
				"fee": sc["fee"],
				"after": sc["after"],
				"rehab": sc["rehab"],
				"offer": sc["offer"],
			}
			for sc in scenes
		],
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
	parts = [
		'<div class="cash-offer" data-cash-offer="{}">'.format(attr),
		"<div><b>{}</b></div>".format(escape_html(_("Cash offer"))),
	]
	for i, sc in enumerate(scenes):
		label = _("Scenario {0}").format(i + 1)
		parts.append(
			"<div>{label} ({pct:.0f}%)</div>"
			"<div>{arv} × {pct:.0f}% = {after}</div>"
			"<div>− rehab {rehab} ({psf}/sf × {sf} sf)</div>"
			'<div>− fee {fee} = <b style="white-space:nowrap">{offer}</b></div>'.format(
				label=escape_html(label),
				pct=sc["pct"] * 100,
				arv=_money(sc["arv"]),
				after=_money(sc["after"]),
				rehab=_money(sc["rehab"]),
				psf=_money(sc["rehab_psf"]),
				sf=f"{int(sqft):,}" if sqft else "—",
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
	"""Write the current calc onto the lead timeline. Does not touch the desk rail."""
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
		frappe.throw(_("Type an ARV in at least one scenario first."))

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
