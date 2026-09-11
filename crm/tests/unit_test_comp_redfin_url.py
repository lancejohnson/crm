"""The Redfin listing link must never hold a gallery open hostage.

Measured on prod 2026-09-10: Zillow facts + photos 0.39s, then the Redfin
`/url` lookup 6.3s run serially after them -- a rep waited ~7s for photos
that were ready, to get a link. The lookup now runs on a thread started
before Zillow and is joined with a short budget; a late answer is filled in
by a background job that patches the cached entry.
"""
import threading
import time
import unittest
from unittest.mock import patch

from crm.tests.frappe_shim import install
install()

from crm.api import comps, redfin


def row():
	return {"name": "zillow::1", "address": "5 Main St, Minneapolis, MN 55401", "lat": 45.0, "lng": -93.0}


class RedfinUrlBudget(unittest.TestCase):
	def test_no_service_falls_back_to_inline_lookup(self):
		with patch.object(redfin, "_base_url", return_value=None), \
			 patch.object(redfin, "redfin_listing_url", return_value="https://redfin/x") as inline:
			job = comps._start_redfin_url("5 Main St", 45, -93)
			self.assertIsNone(job)
			url, pending = comps._finish_redfin_url(job, "5 Main St", 45, -93)
		inline.assert_called_once()
		self.assertEqual((url, pending), ("https://redfin/x", False))

	def test_fast_answer_rides_the_request(self):
		with patch.object(redfin, "_base_url", return_value="http://svc"), \
			 patch.object(redfin, "_fetch_listing_url", return_value="https://redfin/fast"):
			job = comps._start_redfin_url("5 Main St", 45, -93)
			self.assertIsNotNone(job)
			url, pending = comps._finish_redfin_url(job, "5 Main St", 45, -93, budget=1.0)
		self.assertEqual((url, pending), ("https://redfin/fast", False))

	def test_slow_answer_is_pending_not_waited_for(self):
		release = threading.Event()

		def slow(*a):
			release.wait(5)
			return "https://redfin/slow"

		with patch.object(redfin, "_base_url", return_value="http://svc"), \
			 patch.object(redfin, "_fetch_listing_url", side_effect=slow):
			job = comps._start_redfin_url("5 Main St", 45, -93)
			t = time.time()
			url, pending = comps._finish_redfin_url(job, "5 Main St", 45, -93, budget=0.1)
			self.assertLess(time.time() - t, 1.0)
		release.set()
		self.assertEqual((url, pending), (None, True))

	def test_thread_error_is_swallowed(self):
		with patch.object(redfin, "_base_url", return_value="http://svc"), \
			 patch.object(redfin, "_fetch_listing_url", side_effect=RuntimeError("boom")):
			job = comps._start_redfin_url("5 Main St", 45, -93)
			url, pending = comps._finish_redfin_url(job, "5 Main St", 45, -93, budget=1.0)
		self.assertEqual((url, pending), (None, False))

	def test_shape_detail_reports_pending_point_for_the_fill_job(self):
		release = threading.Event()

		def slow(*a):
			release.wait(5)
			return "https://redfin/slow"

		with patch.object(redfin, "_base_url", return_value="http://svc"), \
			 patch.object(redfin, "_fetch_listing_url", side_effect=slow), \
			 patch.object(comps, "REDFIN_URL_BUDGET", 0.1), \
			 patch.object(comps, "_zillow_detail", return_value=({"address": "5 Main St"}, ["p1", "p2"])):
			result = comps._shape_detail(row())
		release.set()
		self.assertEqual(result["photos"], ["p1", "p2"])
		self.assertIsNone(result["redfin_url"])
		self.assertTrue(result["redfin_url_pending"])
		self.assertEqual(result["redfin_url_point"][1:], [45.0, -93.0])


if __name__ == "__main__":
	unittest.main()
