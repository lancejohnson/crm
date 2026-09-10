"""Auction.com import creates a CRM Property — never a CRM Lead — idempotently."""
import unittest
from unittest.mock import MagicMock, patch

from crm.tests.frappe_shim import install
frappe = install()

from crm.api import properties


class _Doc(dict):
	def __init__(self, **kw):
		super().__init__(**kw)
		self.name = kw.get("name", "PROP-00001")
		self.owner = "lance.johnson@groundworkpro.com"
		self.creation = self.modified = "2026-09-09"
		self.inserted = False

	def __getattr__(self, k):
		try:
			return self[k]
		except KeyError:
			raise AttributeError(k)

	def __setattr__(self, k, v):
		if k in ("name", "owner", "creation", "modified", "inserted"):
			object.__setattr__(self, k, v)
		else:
			self[k] = v

	def insert(self, ignore_permissions=False):
		self.inserted = True
		frappe.inserted.append(dict(self, doctype=self.get("doctype")))


class AuctionPropertyImport(unittest.TestCase):
	def setUp(self):
		frappe.inserted.clear()
		self.has_column = patch.object(frappe.db, "has_column", return_value=True)
		self.has_column.start()
		self.get_value = patch.object(frappe.db, "get_value", side_effect=self._get_value)
		self.get_value.start()
		self.get_doc = patch.object(frappe, "get_doc", side_effect=lambda *a, **k: self._get_doc(*a, **k))
		self.get_doc.start()
		patch.object(properties, "_guard", lambda: None).start()
		patch.object(properties, "_need", lambda: None).start()
		patch.object(properties, "_user_label", lambda u: u).start()
		self.existing = {}

	def tearDown(self):
		patch.stopall()

	def _get_value(self, doctype, filters=None, field=None, *a, **k):
		if isinstance(filters, dict) and "external_id" in filters:
			return self.existing.get(filters["external_id"])
		return None

	def _get_doc(self, spec, name=None):
		if isinstance(spec, dict):
			return _Doc(**spec)
		return _Doc(name=name, doctype=spec, external_id="auction:2128351")

	def test_creates_property_not_lead(self):
		out = properties.import_auction_property(
			"2128351", "10547 East Briarcliff Road", "Jacksonville", "fl", "32218",
			lat=30.42, lng=-81.66, listing_url="https://www.auction.com/details/x-2128351",
			evidence={"comps": [{"address": "1 A St", "lat": 30.4, "lon": -81.6}]},
		)
		self.assertTrue(out["created"])
		self.assertEqual(out["external_id"], "auction:2128351")
		self.assertEqual(len(frappe.inserted), 1)
		row = frappe.inserted[0]
		self.assertEqual(row["doctype"], "CRM Property")
		self.assertNotEqual(row["doctype"], "CRM Lead")
		self.assertEqual(row["property_state"], "FL")
		self.assertEqual(row["source"], "Auction.com")
		self.assertEqual(row["property_lat"], 30.42)
		self.assertIn('"comps"', row["adc_evidence"])
		self.assertEqual(row["listing_url"], "https://www.auction.com/details/x-2128351")

	def test_second_push_returns_existing_without_insert(self):
		self.existing["auction:2128351"] = "PROP-00042"
		out = properties.import_auction_property("2128351", "10547 East Briarcliff Road")
		self.assertFalse(out["created"])
		self.assertEqual(out["name"], "PROP-00042")
		self.assertEqual(frappe.inserted, [])

	def test_rejects_bad_id_url_and_coordinates(self):
		for kw in (
			dict(listing_id="abc", address="1 A St"),
			dict(listing_id="1", address="1 A St", listing_url="https://evil.example/x"),
			dict(listing_id="1", address="1 A St", lat=95, lng=0),
			dict(listing_id="1", address="1 A St", lat=10, lng=None),
			dict(listing_id="1", address=""),
		):
			with self.assertRaises(Exception):
				properties.import_auction_property(**kw)
		self.assertEqual(frappe.inserted, [])

	def test_import_adc_comps_insert_only(self):
		exists = {"already": True}
		patch.object(
			frappe.db, "exists",
			side_effect=lambda dt, name=None: bool(isinstance(name, dict) and exists.get(name.get("address_key"))),
		).start()
		out = properties.import_adc_comps([
			{"address_key": "already", "address": "1 Old St"},
			{"address_key": "new-one", "address": "2 New St", "lat": 42.0, "lng": -88.0, "price": 100},
			{"address": "no key"},
		])
		self.assertEqual(out, {"inserted": 1, "existing_untouched": 1, "failed": 1})
		self.assertEqual(frappe.inserted[0]["doctype"], "CRM Comp")
		self.assertEqual(frappe.inserted[0]["address_key"], "new-one")

	def test_missing_schema_fails_closed(self):
		self.has_column.stop()
		with patch.object(frappe.db, "has_column", return_value=False):
			with self.assertRaises(Exception):
				properties.import_auction_property("1", "1 A St")
		self.assertEqual(frappe.inserted, [])


if __name__ == "__main__":
	unittest.main()
