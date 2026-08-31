# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""5am spend lines — BatchData wallet + ISTL day-over-day.

The old calling-list DM carried one BatchData line (`standup_line`). That DM is
gone, so the line would have vanished with it. This module is the dedicated
place those numbers now live: appended under the Today recap, never mixed into
the streak copy.

RealEstateAPI has no usage/balance endpoint (User / Account / Credits all 404).
Lux is the only consumer. Until they grow one, there is nothing honest to print.

ISTL wallet is read through LeadMarket (`GET /api/istl-balance`), which already
stays logged in. CRM never holds the ISTL password. The day-over-day delta is a
snapshot in a Frappe default, so a preview does not move it.

Refunds are the Refunds-board columns: To Request (CRM, not sent), Requested +
Waiting (sent to ISTL), Complete × `lead_cost` (amount received).
"""

import json

import frappe
import requests
from frappe.utils import getdate, now_datetime

from crm.api.daily_standup import previous_business_day

ISTL_SNAP_KEY = "crm_istl_balance_snap"
DEFAULT_LEADMARKET_URL = "https://app.groundworkpro.com/leadmarket"
TIMEOUT = 20


def render_spend(commit_snapshot=False):
	"""One line per vendor that we can actually read. Empty string if none."""
	lines = []
	try:
		from crm.api import batchdata_wallet

		line = batchdata_wallet.standup_line()
		if line:
			lines.append(line)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "spend: BatchData line failed")
	try:
		line = istl_line(commit_snapshot=commit_snapshot)
		if line:
			lines.append(line)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "spend: ISTL line failed")
	try:
		line = refund_line()
		if line:
			lines.append(line)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "spend: refund line failed")
	return "\n".join(lines)


#: In-flight with the vendor — same columns as `Refunds.vue` minus To Request / Complete.
REQUESTED_STATUSES = ("Requested", "Waiting on us", "Waiting on them")


def refund_line():
	"""`Refunds: 19 to request · 28 in ISTL · $754 received (26)`."""
	if not frappe.db.has_column("CRM Lead", "custom_refundable"):
		return ""
	has_status = frappe.db.has_column("CRM Lead", "custom_refund_status")
	has_requested = frappe.db.has_column("CRM Lead", "custom_refund_requested")
	has_cost = frappe.db.has_column("CRM Lead", "lead_cost")
	status_expr = "'To Request'"
	if has_status and has_requested:
		status_expr = """CASE
			WHEN custom_refund_status IN ('To Request','Requested','Waiting on us','Waiting on them','Complete')
				THEN custom_refund_status
			WHEN IFNULL(custom_refund_requested,0)=1 THEN 'Requested'
			ELSE 'To Request'
		END"""
	elif has_status:
		status_expr = "IFNULL(NULLIF(custom_refund_status,''), 'To Request')"
	elif has_requested:
		status_expr = "IF(IFNULL(custom_refund_requested,0)=1, 'Requested', 'To Request')"
	cost_expr = "0"
	if has_cost:
		cost_expr = "CAST(NULLIF(lead_cost,'') AS DECIMAL(12,2))"
	rows = frappe.db.sql(
		f"""SELECT {status_expr} AS st, COUNT(*) AS n, COALESCE(SUM({cost_expr}), 0) AS cost
		   FROM `tabCRM Lead`
		   WHERE IFNULL(custom_refundable,0)=1
		   GROUP BY st""",
		as_dict=True,
	)
	by_status = {r.st: r for r in rows}
	to_request = int((by_status.get("To Request") or {}).get("n") or 0)
	in_istl = sum(int((by_status.get(s) or {}).get("n") or 0) for s in REQUESTED_STATUSES)
	complete = by_status.get("Complete") or {}
	received_n = int(complete.get("n") or 0)
	received = float(complete.get("cost") or 0)
	bits = [f"**{to_request}** to request", f"**{in_istl}** in ISTL"]
	if received_n:
		bits.append(f"**${received:,.0f}** received ({received_n})")
	else:
		bits.append("$0 received")
	return "Refunds: " + " · ".join(bits)


def istl_line(commit_snapshot=False):
	"""`ISTL **$1,479** left (−$120 yesterday)`.

	Money balance = card + refund (the app's "Money balance"). Bonus is promo
	credit with no cost basis — shown only when it is not zero. Delta is against
	the last committed snapshot, labelled "yesterday" when that snapshot is the
	previous business day and "since <date>" otherwise.
	"""
	wallet = _istl_wallet()
	if not wallet:
		return ""
	try:
		money = int(wallet.get("money") or 0)
		bonus = int(wallet.get("bonus") or 0)
	except (TypeError, ValueError):
		return ""
	today = getdate(now_datetime())
	snap = _read_istl_snap()
	delta_bit = ""
	if snap and snap.get("money") is not None:
		try:
			prev = int(snap["money"])
		except (TypeError, ValueError):
			prev = None
		if prev is not None:
			delta = prev - money
			when = snap.get("date") or ""
			label = "yesterday"
			try:
				if when and getdate(when) != previous_business_day(today):
					label = f"since {when}"
			except Exception:
				if when:
					label = f"since {when}"
			if delta > 0:
				delta_bit = f" (−${delta:,} {label})"
			elif delta < 0:
				delta_bit = f" (+${-delta:,} {label})"
			else:
				delta_bit = f" (unchanged {label})"
	if commit_snapshot:
		_write_istl_snap({"date": str(today), "money": money, "bonus": bonus})
	bonus_bit = f" · ${bonus:,} bonus" if bonus else ""
	return f"ISTL **${money:,}** left{delta_bit}{bonus_bit}"


def _istl_wallet():
	"""Ask LeadMarket, which already holds a live ISTL JWT.

	`leadmarket_token` is `LEADMARKET_GMAIL_WEBHOOK_TOKEN` or `LEADMARKET_WEB_SECRET`
	— the same machine token that endpoint accepts. Absent, this is a no-op.
	"""
	token = frappe.conf.get("leadmarket_token") or ""
	if not token:
		return None
	base = (frappe.conf.get("leadmarket_url") or DEFAULT_LEADMARKET_URL).rstrip("/")
	r = requests.get(
		base + "/api/istl-balance",
		headers={"Authorization": "Bearer " + token},
		timeout=TIMEOUT,
	)
	r.raise_for_status()
	return r.json()


def _read_istl_snap():
	raw = frappe.db.get_default(ISTL_SNAP_KEY)
	if not raw:
		return None
	if isinstance(raw, dict):
		return raw
	try:
		return json.loads(raw)
	except (TypeError, ValueError):
		return None


def _write_istl_snap(snap):
	frappe.db.set_default(ISTL_SNAP_KEY, json.dumps(snap))
	# Same GOTCHA as lead_assignment: get_default in this process can stay stale
	# unless the private cache is cleared.
	try:
		frappe.defaults._clear_cache("__default")
	except Exception:
		pass
