# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""What a property's price history says about it: time to sell, and flips.

Why this exists
---------------
Three things a rep needs from a comp, none of which the search row can answer:

  1. **How long it took to sell.** Zillow's `daysOnZillow` is NOT this. On a
     ForSale row it is days on market; on a RecentlySold row it is days SINCE
     the sale. Measured on 1128 Pleasant St, Indianapolis: `daysOnZillow` = 4,
     while the house was listed 2026-07-16 and sold 2026-08-21 — 36 days. The
     same field, two meanings, and the map was rendering the sold one as
     "Listed · 4d on market". Time-to-sell has to be derived from the listing
     chain, and only `priceHistory` carries it.

  2. **How long ago it sold.** Recency is what makes a comp good evidence, and
     it is a different number from (1). Both belong on a sold pin, said
     differently, or "99 days" is ambiguous.

  3. **Whether it is a FLIP.** A house bought at $31,201 and resold ten months
     later at $129,900 (15644 Carlisle St, Detroit — one block from a live
     lead of ours) is not a comp for an unrenovated wholesale deal. Measured
     over 48 sold comps across our markets, **6 (12.5%)** are flips by the
     thresholds below. Pricing off one silently inflates ARV.

The chain, and why price drops belong inside it
-----------------------------------------------
A marketing run is `Listed for sale` → any number of `Price change` /
`Pending sale` → `Sold`. Time on market is measured from the FIRST listing of
that run, not from the last price cut — a seller who cut twice sat on the
market the whole time, and reading the latest event would flatter them.

The run is bounded by the PREVIOUS sale: everything back to it belongs to this
owner's attempt to sell, everything before it belongs to the last owner. That
boundary is what makes "first time they were listed in that chain" well
defined.

Everything here is pure: no frappe, no I/O, no network. It parses a list of
dicts and returns a dict, so it is safe to call from anywhere and cheap to test.
"""

from __future__ import annotations

import datetime

#: Below this a "Sold" row is a TRANSFER, not a purchase — quitclaims,
#: intra-family deeds and $1 title corrections all appear as Sold events with a
#: real date. Treating one as a purchase invents a spectacular fake flip
#: ($1 -> $120,000). Deliberately low rather than a percentage of value: our
#: markets genuinely trade at $25-45k (828 River Ave sold for $28,000 in 2018),
#: so anything higher would discard real sales in exactly the areas we buy in.
MIN_REAL_SALE = 5_000

#: A flip is a resale, soon, for materially more. Both halves are required:
#: a quick resale at the same price is a wash sale or a correction, and a big
#: gain over eight years is just the market.
#:
#: 730 days is deliberately generous for the word "quickly" — a gut renovation
#: routinely takes a year to buy, permit, build and re-list. Measured holds in
#: the sample that this flags: 75, 129, 305, 312, 462, 610 days. The raw
#: `hold_days` rides in the result so the UI can show it and the rep can judge;
#: this constant only decides when we volunteer the warning.
FLIP_MAX_HOLD_DAYS = 730
FLIP_MIN_GAIN_PCT = 0.30

#: An ACTIVE listing asking far more than it last sold for is the same story
#: caught mid-flight: someone bought it and is now trying to resell. Not proof —
#: the ask is not a sale — so it is labelled as an ask, never counted as one.
ASK_MAX_HOLD_DAYS = 730
ASK_MIN_GAIN_PCT = 0.30

_SOLD = "sold"
_LISTED = "listed for sale"
_PRICE_CHANGE = "price change"


def _date(value):
	"""`YYYY-MM-DD...` -> date, or None. priceHistory dates are date-only."""
	if not value:
		return None
	try:
		return datetime.date.fromisoformat(str(value)[:10])
	except (TypeError, ValueError):
		return None


def _price(value):
	try:
		n = float(value)
	except (TypeError, ValueError):
		return None
	return n if n > 0 else None


def _kind(event) -> str:
	"""`event` is a display string ("Sold", "Listed for sale"), not a code."""
	return str((event or {}).get("event") or "").strip().lower()


def _clean(price_history):
	"""Usable events, newest first — the order Zillow already returns them in."""
	out = []
	for e in price_history or []:
		if isinstance(e, dict) and _date(e.get("date")):
			out.append(e)
	# Sort defensively rather than trusting the order: a single out-of-order row
	# would otherwise put the "previous" sale after the last one and invert a flip.
	out.sort(key=lambda e: _date(e["date"]), reverse=True)
	return out


#: A relisting after this long is a NEW attempt to sell, not a continuation.
#:
#: Without a bound, "first listing since the last sale" reaches back forever.
#: Measured on 15256 Edmore Dr, Detroit: listed for sale in Mar 2023, withdrawn
#: three weeks later, rented out twice, and finally sold in 2026 -- reported as
#: **1,115 days to sell**. The owner did not spend three years trying to sell it;
#: they gave up, let it, and started again. Six months is deliberately generous,
#: so an ordinary withdraw-over-Christmas-and-relist-in-spring still counts as
#: one continuous effort, which is what Lance asked for.
MAX_CHAIN_GAP_DAYS = 180


def _is_rental(event) -> bool:
	"""Rental activity ends a sale run: the owner stopped trying to sell.

	NOTE `postingIsRental` is not always set, so the event text is checked too.
	(`zillow._price_history` matches listings with a bare `"list" in kind`, which
	does catch "Listed for rent" — a separate, pre-existing looseness there.)
	"""
	if (event or {}).get("postingIsRental"):
		return True
	return "rent" in _kind(event)


def _trim_run(events, anchor):
	"""Cut a candidate run down to ONE continuous marketing effort.

	`events` is newest-first and already bounded by the previous sale; `anchor` is
	when the run ended (the sale date, or today for a listing still running). Walks
	back in time and stops at the first thing that means "they were not trying to
	sell during this period": a rental, or a gap too long to be one campaign.
	"""
	out = []
	prev = anchor
	for e in events:
		if _is_rental(e):
			break
		d = _date(e.get("date"))
		if prev and d and (prev - d).days > MAX_CHAIN_GAP_DAYS:
			break
		out.append(e)
		prev = d or prev
	return out


def _first_listing_in(events):
	"""The EARLIEST `Listed for sale` in an already-trimmed run.

	Earliest, not latest: a run with two listings in it (withdrawn and relisted
	within the gap window, without an intervening sale) is still one continuous
	attempt to sell, and the seller's clock started at the first one. This is the
	half of "first time they were listed in that chain" that price drops rely on —
	a `Price change` never restarts the clock.
	"""
	listings = [e for e in events if _kind(e) == _LISTED]
	return listings[-1] if listings else None


def _sale(event):
	if not event:
		return None
	return {
		"date": str(_date(event.get("date"))),
		"price": _price(event.get("price")),
		# "Public Record" is a stronger claim than "Agent Provided"; the UI prints
		# it so a weak source is never mistaken for a verified transaction.
		"source": event.get("source") or None,
	}


def _gain(older_price, newer_price):
	if not older_price or not newer_price:
		return None, None
	return newer_price - older_price, (newer_price - older_price) / older_price


def parse(price_history, today=None, home_status=None):
	"""priceHistory -> what it says about selling and about flipping.

	Returns None when there is nothing usable to say. Never raises: a comp with a
	malformed history must render without its extras, not break the map.

	`home_status` is Zillow's own word for the property now. It decides which
	chain is the CURRENT one — for a sold house that is the run that ended in the
	sale, for a listed house it is the run still in progress.
	"""
	today = today or datetime.date.today()
	if isinstance(today, str):
		today = _date(today) or datetime.date.today()
	events = _clean(price_history)
	if not events:
		return None

	sold_ix = [i for i, e in enumerate(events) if _kind(e) == _SOLD]
	status = str(home_status or "").strip().upper()
	# Trust the row's own status where we have it; otherwise infer from whether a
	# sale is the most recent thing that happened.
	is_listed = status in {"FOR_SALE", "PENDING", "CONTINGENT", "COMING_SOON"} or (
		not status and (not sold_ix or sold_ix[0] != 0)
	)

	out = {
		"days_to_sell": None,
		"first_listed": None,
		"sold_days_ago": None,
		"days_on_market": None,
		"price_cuts": 0,
		"cut_pct": None,
		"last_sale": None,
		"prior_sale": None,
		"flip": None,
	}

	last_sale_ix = sold_ix[0] if sold_ix else None
	if last_sale_ix is not None:
		last = events[last_sale_ix]
		out["last_sale"] = _sale(last)
		sold_on = _date(last["date"])
		if sold_on:
			out["sold_days_ago"] = max(0, (today - sold_on).days)

		# The run that ENDED in this sale: everything older, back to the sale
		# before it. That boundary is the previous owner's business, not this one's.
		stop = sold_ix[1] if len(sold_ix) > 1 else len(events)
		run = _trim_run(events[last_sale_ix + 1 : stop], sold_on)
		listed = _first_listing_in(run)
		if listed:
			listed_on = _date(listed["date"])
			out["first_listed"] = str(listed_on)
			if sold_on and listed_on and sold_on >= listed_on:
				out["days_to_sell"] = (sold_on - listed_on).days
			out["price_cuts"] = sum(1 for e in run if _kind(e) == _PRICE_CHANGE)
			asked, got = _price(listed.get("price")), _price(last.get("price"))
			if asked and got:
				out["cut_pct"] = (got - asked) / asked

	# --- flip: the sale BEFORE the last one, when both are real purchases ------
	if last_sale_ix is not None:
		last_price = _price(events[last_sale_ix].get("price"))
		prior = None
		for j in sold_ix[1:]:
			if _price(events[j].get("price")) and _price(events[j]["price"]) >= MIN_REAL_SALE:
				prior = events[j]
				break
		if prior and last_price and last_price >= MIN_REAL_SALE:
			out["prior_sale"] = _sale(prior)
			bought_on, sold_on = _date(prior["date"]), _date(events[last_sale_ix]["date"])
			hold = (sold_on - bought_on).days if (bought_on and sold_on) else None
			gain, pct = _gain(_price(prior["price"]), last_price)
			if (
				hold is not None
				and 0 <= hold <= FLIP_MAX_HOLD_DAYS
				and pct is not None
				and pct >= FLIP_MIN_GAIN_PCT
			):
				out["flip"] = {
					"kind": "resale",
					"hold_days": hold,
					"bought_price": _price(prior["price"]),
					"bought_date": str(bought_on),
					"sold_price": last_price,
					"gain": gain,
					"pct": pct,
				}

	if not is_listed:
		return out

	# --- currently listed: the run in progress, and the ask against the sale ---
	run = _trim_run(events[:last_sale_ix] if last_sale_ix is not None else events, today)
	listed = _first_listing_in(run)
	if listed:
		listed_on = _date(listed["date"])
		out["first_listed"] = str(listed_on)
		if listed_on:
			out["days_on_market"] = max(0, (today - listed_on).days)
		out["price_cuts"] = sum(1 for e in run if _kind(e) == _PRICE_CHANGE)
	# A live listing has not sold, so time-to-sell is not a thing it has yet.
	out["days_to_sell"] = None

	# Asking far above the last sale, soon after it — a flip in progress. Priced
	# off the newest event that carries a price, which is the current ask.
	if out["last_sale"] and out["last_sale"].get("price"):
		ask = None
		for e in run:
			p = _price(e.get("price"))
			if p:
				ask = p
				break
		bought_on = _date((out["last_sale"] or {}).get("date"))
		hold = (today - bought_on).days if bought_on else None
		gain, pct = _gain(out["last_sale"]["price"], ask)
		if (
			ask
			and ask >= MIN_REAL_SALE
			and hold is not None
			and 0 <= hold <= ASK_MAX_HOLD_DAYS
			and pct is not None
			and pct >= ASK_MIN_GAIN_PCT
		):
			out["flip"] = {
				# Deliberately its own kind: this is an ASK, not a completed
				# resale, and the UI must not word it as one.
				"kind": "relist",
				"hold_days": hold,
				"bought_price": out["last_sale"]["price"],
				"bought_date": out["last_sale"]["date"],
				"ask_price": ask,
				"gain": gain,
				"pct": pct,
			}
	return out
