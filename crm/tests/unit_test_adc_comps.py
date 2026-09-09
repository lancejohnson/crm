"""ADC provenance must survive CRM pool reads and optional photo/status refresh."""
import unittest
from unittest.mock import patch

from crm.tests.frappe_shim import install
install()

from crm.api.comp_provenance import shape_pool_row, is_adc, qualified_address
from crm.api import comps, zillow_comps


def adc():
	return {"name": "comp-1", "source_lead": "auction:2175110", "address": "5 Main St, Minneapolis, MN 55401",
		"price": 200000, "removed_date": "2025-12-11", "status": "Inactive", "lat": 45, "lng": -93}


class ADCReadContract(unittest.TestCase):
	def test_pool_retains_sale_not_ask_and_unknown_current_status(self):
		raw = adc()
		row = shape_pool_row(raw)
		self.assertEqual(row["source"], "auction_com")
		self.assertEqual(row["sale_price"], 200000)
		self.assertEqual(row["sale_date"], "2025-12-11")
		self.assertEqual(row["price_basis"], "adc_sale")
		self.assertEqual(row["listing_state"], "unknown")
		self.assertIsNone(row["current_status_source"])
		self.assertEqual(raw["status"], "Inactive")  # read normalization never mutates storage

	def test_legacy_and_manual_rows_unchanged(self):
		for source in (None, "istl-123", "manual", "auction:not-an-id"):
			raw = {**adc(), "source_lead": source}
			self.assertEqual(shape_pool_row(raw), raw)
			self.assertFalse(is_adc(raw))

	def test_verified_live_ask_does_not_overwrite_historical_adc_sale(self):
		row = shape_pool_row(adc())
		zillow_comps._apply_listing(row, 250000, 10, "pending")
		self.assertEqual(row["source"], "auction_com")
		self.assertEqual(row["source_lead"], "auction:2175110")
		self.assertEqual(row["current_status_source"], "zillow")
		self.assertEqual(row["listing_state"], "pending")
		self.assertEqual(row["price"], 250000)
		self.assertEqual(row["price_basis"], "current_ask")
		self.assertEqual(row["sale_price"], 200000)
		self.assertEqual(row["sale_date"], "2025-12-11")

	def test_newer_verified_sale_retains_original_adc_evidence(self):
		row = shape_pool_row(adc())
		zillow_comps._apply_sale(row, 225000, "2026-05-01")
		self.assertEqual(row["price_basis"], "zillow_sale")
		self.assertEqual(row["listing_state"], "sold")
		self.assertEqual(row["sale_price"], 200000)
		self.assertEqual(row["sale_date"], "2025-12-11")

	def test_street_only_detail_never_enters_photo_ladder(self):
		row = {**adc(), "address": "5 Main St"}
		self.assertFalse(qualified_address(row))
		with patch.object(comps, "_zillow_detail") as lookup:
			result = comps._shape_detail(row)
		lookup.assert_not_called()
		self.assertFalse(result["available"])
		self.assertEqual(result["comp"]["listing_state"], "unknown")

	def test_qualified_adc_row_reuses_cached_photo_status_ladder(self):
		from crm.api import redfin
		with patch.object(comps, "_zillow_detail", return_value=({"home_status":"PENDING"}, ["https://photo/1", "https://photo/2"])), \
			 patch.object(redfin, "redfin_listing_url", return_value="https://redfin/property"):
			result = comps._shape_detail(adc())
		self.assertEqual(result["photo_source"], "zillow")
		self.assertEqual(len(result["photos"]), 2)
		self.assertEqual(result["comp"]["source"], "auction_com")
		self.assertEqual(result["comp"]["sale_price"], 200000)
		self.assertEqual(result["comp"]["listing_state"], "pending")
		self.assertEqual(result["comp"]["current_status_source"], "zillow")

	def test_unverified_photo_response_keeps_unknown_status(self):
		from crm.api import redfin
		with patch.object(comps, "_zillow_detail", return_value=({"home_status":"OTHER"}, ["https://photo/1", "https://photo/2"])), \
			 patch.object(redfin, "redfin_listing_url", return_value=None):
			result = comps._shape_detail(adc())
		self.assertEqual(result["comp"]["listing_state"], "unknown")
		self.assertIsNone(result["comp"]["current_status_source"])
