"""Carry observed Redfin URLs without another request or a cache rebuy."""

import unittest
from unittest.mock import Mock, patch

from crm.api import redfin


class RedfinLinkTests(unittest.TestCase):
	def gallery(self, body):
		response = Mock(status_code=200)
		response.json.return_value = body
		with patch.object(redfin, "_base_url", return_value="https://service.test"), patch.object(
			redfin.requests, "get", return_value=response
		) as get:
			result = redfin.redfin_gallery("4236 Foxcroft Rd", 35.1, -80.8)
			self.assertEqual(get.call_count, 1)
			return result

	def test_listing_url_uses_dedicated_endpoint(self):
		response = Mock(status_code=200)
		response.json.return_value = {
			"matched": True,
			"url": "https://www.redfin.com/MN/Saint-Paul/1620-Iowa-Ave-E-55106/home/49895096",
		}
		with patch.object(redfin, "_base_url", return_value="https://service.test"), patch.object(
			redfin.requests, "get", return_value=response
		) as get:
			url = redfin.redfin_listing_url("1620 Iowa Ave E", 44.99, -93.03)
			self.assertTrue(get.call_args.args[0].endswith("/url"))
		self.assertEqual(
			url, "https://www.redfin.com/MN/Saint-Paul/1620-Iowa-Ave-E-55106/home/49895096"
		)

	def test_listing_url_404_falls_back_to_photos(self):
		missing = Mock(status_code=404)
		photos = Mock(status_code=200)
		photos.json.return_value = {"matched": True, "url": "/MN/Saint-Paul/1620-Iowa-Ave-E-55106/home/49895096", "photos": []}
		with patch.object(redfin, "_base_url", return_value="https://service.test"), patch.object(
			redfin.requests, "get", side_effect=[missing, photos]
		):
			self.assertEqual(
				redfin.redfin_listing_url("1620 Iowa Ave E", 44.99, -93.03),
				"/MN/Saint-Paul/1620-Iowa-Ave-E-55106/home/49895096",
			)

	def test_matched_url_survives_without_photos(self):
		url = "/NC/Charlotte/4236-Foxcroft-Rd-28211/home/43999203"
		self.assertEqual(self.gallery({"matched": True, "url": url, "photos": []}), {"url": url, "photos": []})

	def test_unmatched_url_is_not_used(self):
		self.assertIsNone(self.gallery({"matched": False, "url": "/home/1"})["url"])

	def test_old_service_still_returns_photos(self):
		self.assertEqual(self.gallery({"matched": True, "photos": ["https://photo.test/1"]}), {
			"photos": ["https://photo.test/1"], "url": None,
		})

	def test_properties_fallback_keeps_only_matching_street_url(self):
		missing = Mock(status_code=404)
		rows = Mock(status_code=200)
		rows.json.return_value = {"features": [
			{"properties": {"address": "4238 Foxcroft Rd", "url": "/home/2"}},
			{"properties": {"address": "4236 Foxcroft Road", "url": "/home/1"}},
		]}
		holder = {}
		with patch.object(redfin.requests, "get", side_effect=[missing, rows]):
			redfin._fetch_subject_record("https://service.test", "4236 Foxcroft Rd", 35.1, -80.8, holder)
		self.assertEqual(holder["result"]["url"], "/home/1")
		self.assertTrue(holder["result"]["matched"])
