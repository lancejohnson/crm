"""Read-only interpretation of ADC sale evidence in the shared CRM Comp pool.

Legacy columns price/removed_date hold the reported sale for auction:<id>
imports, NOT an ISTL last ask/removal. Never write these interpretations back
onto manual or other providers' records.
"""
import re


def is_adc(row):
	return bool(re.fullmatch(r"auction:\d+", str(row.get("source_lead") or "")))


def shape_pool_row(row):
	out = dict(row)
	if not is_adc(out):
		return out
	out["source"] = "auction_com"
	out["sale_source"] = "Auction.com"
	out["sale_price"] = out.get("sale_price", out.get("price"))
	out["sale_date"] = str(out.get("sale_date") or out.get("removed_date") or "") or None
	out["price_basis"] = "adc_sale"
	# An old transaction does not establish today's sale/listing status.
	out["status"] = "Unknown"
	out["listing_state"] = "unknown"
	out["current_status_source"] = None
	return out


def mark_verified(row, state, price_basis):
	"""Called only by the existing Zillow match/refresh path."""
	if is_adc(row):
		row["source"] = "auction_com"
		row["current_status_source"] = "zillow"
		row["price_basis"] = price_basis
	else:
		row["source"] = "zillow"


def qualified_address(row):
	# Fail closed for earlier or manual ADC imports missing locality. Never
	# manufacture a comp city/ZIP from the subject's address.
	return bool(re.search(r",\s*[^,]+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?\s*$", str(row.get("address") or "")))
