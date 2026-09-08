"""Listing URL → address: Zillow, Redfin, Realtor, Auction.com slugs."""

import unittest

from crm.tests.frappe_shim import install

install()

from crm.api.listing_url import looks_like_url, parse_listing_url  # noqa: E402


class ParseTests(unittest.TestCase):
	def test_zillow_homedetails(self):
		out = parse_listing_url(
			"https://www.zillow.com/homedetails/3820-N-Illinois-St-Indianapolis-IN-46208/1023_zpid/"
		)
		self.assertEqual(out["address"], "3820 N Illinois St, Indianapolis, IN 46208")
		self.assertEqual(out["street"], "3820 N Illinois St")
		self.assertEqual(out["city"], "Indianapolis")
		self.assertEqual(out["state"], "IN")
		self.assertEqual(out["zip"], "46208")
		self.assertEqual(out["zpid"], "1023")
		self.assertEqual(out["source"], "zillow")

	def test_zillow_two_word_city_and_unit(self):
		out = parse_listing_url(
			"https://www.zillow.com/homedetails/412-Maple-Ave-UNIT-2-Saint-Paul-MN-55102/99_zpid/"
		)
		self.assertEqual(out["street"], "412 Maple Ave Unit 2")
		self.assertEqual(out["city"], "Saint Paul")
		self.assertEqual(out["address"], "412 Maple Ave Unit 2, Saint Paul, MN 55102")

	def test_zillow_search_slug(self):
		out = parse_listing_url("https://www.zillow.com/homes/2538-N-Talbott-St-Indianapolis-IN-46205_rb/")
		self.assertEqual(out["address"], "2538 N Talbott St, Indianapolis, IN 46205")

	def test_zillow_no_suffix_stays_unsplit(self):
		out = parse_listing_url("https://www.zillow.com/homedetails/4205-NC-210-Bunnlevel-NC-28323/5_zpid/")
		self.assertEqual(out["city"], "")
		self.assertEqual(out["address"], "4205 Nc 210 Bunnlevel, NC 28323")

	def test_redfin(self):
		out = parse_listing_url("https://www.redfin.com/IN/Indianapolis/3820-N-Illinois-St-46208/home/1023")
		self.assertEqual(out["address"], "3820 N Illinois St, Indianapolis, IN 46208")
		self.assertEqual(out["source"], "redfin")

	def test_redfin_two_word_city(self):
		out = parse_listing_url("https://www.redfin.com/MN/Saint-Paul/412-Maple-Ave-55102/home/7")
		self.assertEqual(out["city"], "Saint Paul")

	def test_realtor(self):
		out = parse_listing_url(
			"https://www.realtor.com/realestateandhomes-detail/3820-N-Illinois-St_Indianapolis_IN_46208_M10-23"
		)
		self.assertEqual(out["address"], "3820 N Illinois St, Indianapolis, IN 46208")
		self.assertEqual(out["source"], "realtor")

	def test_auction(self):
		out = parse_listing_url(
			"https://www.auction.com/details/3820-n-illinois-st-indianapolis-in-46208-1023-e_12345/"
		)
		self.assertEqual(out["address"], "3820 N Illinois St, Indianapolis, IN 46208")
		self.assertEqual(out["source"], "auction")

	def test_auction_ordinal_street(self):
		out = parse_listing_url("https://www.auction.com/details/16-s-5th-st-w-aurora-mn-55705-42-e_1/")
		self.assertEqual(out["street"], "16 S 5th St W")
		self.assertEqual(out["city"], "Aurora")

	def test_bare_host_without_scheme(self):
		out = parse_listing_url("zillow.com/homedetails/1-Main-St-Olivia-MN-56277/1_zpid/")
		self.assertEqual(out["address"], "1 Main St, Olivia, MN 56277")

	def test_unsupported_and_garbage(self):
		self.assertIsNone(parse_listing_url("https://example.com/whatever"))
		self.assertIsNone(parse_listing_url("https://www.zillow.com/indianapolis-in/"))
		self.assertIsNone(parse_listing_url("3820 N Illinois St, Indianapolis, IN 46208"))
		self.assertIsNone(parse_listing_url(""))

	def test_looks_like_url(self):
		self.assertTrue(looks_like_url("https://www.zillow.com/x"))
		self.assertTrue(looks_like_url("www.redfin.com/x"))
		self.assertTrue(looks_like_url("auction.com/details/x"))
		self.assertFalse(looks_like_url("3820 N Illinois St"))


if __name__ == "__main__":
	unittest.main()
