"""listing_state: auction flag, live homeStatus, $0 ForSale rows."""

import unittest

from crm.tests.frappe_shim import install

install()

from crm.api.zillow_comps import (  # noqa: E402
	_apply_listing,
	_is_auction,
	_shape_search,
	_state_from_facts,
	listing_state,
)


def _search_prop(**kw):
	base = {
		"address": "1623 Nevada Ave E, Saint Paul, MN 55106",
		"latitude": 44.9859,
		"longitude": -93.0319,
		"price": 190400,
		"zpid": 2107713,
		"listingStatus": "RECENTLY_SOLD",
		"dateSold": 1780459200000,
		"listingSubType": {},
		"imgSrc": "https://example.com/p.jpg",
	}
	base.update(kw)
	return base


class ListingStateTests(unittest.TestCase):
	def test_auction_flag_beats_recently_sold(self):
		prop = _search_prop(listingSubType={"is_forAuction": True})
		self.assertTrue(_is_auction(prop))
		self.assertEqual(listing_state(prop, "sold"), "auction")

	def test_plain_recently_sold(self):
		self.assertEqual(listing_state(_search_prop(), "sold"), "sold")

	def test_for_sale_fsba(self):
		prop = _search_prop(
			listingStatus="FOR_SALE",
			price=249000,
			listingSubType={"is_FSBA": True},
			dateSold=None,
		)
		self.assertEqual(listing_state(prop, "sale"), "for_sale")

	def test_pending(self):
		prop = _search_prop(listingStatus="PENDING", listingSubType={"is_FSBA": True})
		self.assertEqual(listing_state(prop, "sale"), "pending")

	def test_shape_keeps_zero_price_auction(self):
		row = _shape_search(
			_search_prop(
				price=0,
				listingStatus="FOR_SALE",
				listingSubType={"is_forAuction": True},
				dateSold=None,
			),
			"sale",
		)
		self.assertIsNotNone(row)
		self.assertEqual(row["listing_state"], "auction")
		self.assertEqual(row["status"], "Active")
		self.assertEqual(row["price"], 0)

	def test_shape_drops_sold_without_price(self):
		self.assertIsNone(_shape_search(_search_prop(price=0), "sold"))

	def test_facts_live_auction(self):
		self.assertEqual(
			_state_from_facts({"home_status": "FOR_SALE", "is_for_auction": True}),
			"auction",
		)

	def test_facts_for_sale_not_inferred(self):
		self.assertEqual(_state_from_facts({"home_status": "FOR_SALE"}), "for_sale")
		self.assertIsNone(_state_from_facts({"home_status": "RECENTLY_SOLD"}))

	def test_apply_listing_auction_does_not_keep_sale_price(self):
		row = {"price": 190400, "status": "Inactive", "listing_state": "sold", "removed_date": "2026-06-03"}
		_apply_listing(row, 0, None, "auction")
		self.assertEqual(row["listing_state"], "auction")
		self.assertEqual(row["status"], "Active")
		self.assertEqual(row["price"], 0)
		self.assertIsNone(row["removed_date"])


if __name__ == "__main__":
	unittest.main()
