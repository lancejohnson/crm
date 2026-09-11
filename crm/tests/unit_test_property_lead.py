"""Optional CRM Property ↔ CRM Lead link. Blank is the default."""
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
		self.saved = False

	def __getattr__(self, k):
		try:
			return self[k]
		except KeyError:
			raise AttributeError(k)

	def __setattr__(self, k, v):
		if k in ("name", "owner", "creation", "modified", "inserted", "saved"):
			object.__setattr__(self, k, v)
		else:
			self[k] = v

	def insert(self, ignore_permissions=False):
		self.inserted = True
		frappe.inserted.append(dict(self, doctype=self.get("doctype")))

	def save(self):
		self.saved = True


class PropertyLeadLink(unittest.TestCase):
	def setUp(self):
		frappe.inserted.clear()
		self.columns = {
			"status", "listing_url", "lead", "source", "external_id", "adc_evidence",
		}
		self.has_column = patch.object(
			frappe.db, "has_column", side_effect=lambda dt, col: col in self.columns,
		)
		self.has_column.start()
		self.exists = patch.object(frappe.db, "exists", side_effect=self._exists)
		self.exists.start()
		self.get_value = patch.object(frappe.db, "get_value", side_effect=self._get_value)
		self.get_value.start()
		self.set_value = patch.object(frappe.db, "set_value")
		self.set_value.start()
		self.get_all = patch.object(frappe, "get_all", side_effect=self._get_all)
		self.get_all.start()
		self.get_doc = patch.object(frappe, "get_doc", side_effect=self._get_doc)
		self.get_doc.start()
		patch.object(properties, "_guard", lambda: None).start()
		patch.object(properties, "_need", lambda: None).start()
		patch.object(properties, "_user_label", lambda u: u).start()
		self.leads = {"CRM-LEAD-00001": {"lead_name": "Jane Seller"}}
		self.docs = {}
		self.listed = []
		self.lead_rows = []

	def tearDown(self):
		patch.stopall()

	def _exists(self, doctype, name=None):
		if doctype == "CRM Lead":
			return name in self.leads
		if doctype == "DocType":
			return True
		return name in self.docs

	def _get_value(self, doctype, name=None, field=None, *a, **k):
		if doctype == "CRM Lead" and name in self.leads:
			row = self.leads[name]
			if field == "lead_name":
				return row["lead_name"]
			return row.get(field)
		return None

	def _get_all(self, doctype, *a, **k):
		if doctype == "CRM Lead":
			if k.get("fields") == ["name", "lead_name"]:
				ids = set()
				filt = k.get("filters") or {}
				if isinstance(filt.get("name"), (list, tuple)) and filt["name"][0] == "in":
					ids = set(filt["name"][1])
				return [
					{"name": n, "lead_name": self.leads[n]["lead_name"]}
					for n in ids if n in self.leads
				]
			return self.lead_rows
		if k.get("pluck") == "name":
			return [d.name for d in self.listed]
		return self.listed

	def _get_doc(self, spec, name=None):
		if isinstance(spec, dict):
			return _Doc(**spec)
		if name in self.docs:
			return self.docs[name]
		return _Doc(name=name, doctype=spec)

	def _prop(self, **kw):
		d = _Doc(
			doctype="CRM Property",
			name=kw.pop("name", "PROP-00001"),
			property_address=kw.pop("property_address", "412 Maple Ave"),
			property_city="",
			property_state="",
			property_zip="",
			notes="",
			status="New",
			listing_url="",
			source="",
			lead=kw.pop("lead", ""),
			comps_selected="[]",
			**kw,
		)
		self.docs[d.name] = d
		return d

	def test_shape_blank_when_unlinked(self):
		out = properties._shape(self._prop())
		self.assertEqual(out["lead"], "")
		self.assertEqual(out["lead_name"], "")
		self.assertTrue(out["lead_supported"])

	def test_shape_names_the_lead(self):
		out = properties._shape(self._prop(lead="CRM-LEAD-00001"))
		self.assertEqual(out["lead"], "CRM-LEAD-00001")
		self.assertEqual(out["lead_name"], "Jane Seller")

	def test_shape_hides_lead_when_column_missing(self):
		self.columns.remove("lead")
		out = properties._shape(self._prop(lead="CRM-LEAD-00001"))
		self.assertEqual(out["lead"], "")
		self.assertEqual(out["lead_name"], "")
		self.assertFalse(out["lead_supported"])

	def test_create_stamps_lead(self):
		out = properties.create_property("412 Maple Ave", lead="CRM-LEAD-00001")
		self.assertEqual(out["lead"], "CRM-LEAD-00001")
		self.assertEqual(out["lead_name"], "Jane Seller")
		self.assertEqual(frappe.inserted[0]["lead"], "CRM-LEAD-00001")

	def test_create_without_lead_stays_blank(self):
		out = properties.create_property("412 Maple Ave")
		self.assertEqual(out["lead"], "")
		self.assertFalse(frappe.inserted[0].get("lead"))

	def test_create_ignores_lead_when_column_missing(self):
		self.columns.remove("lead")
		out = properties.create_property("412 Maple Ave", lead="CRM-LEAD-00001")
		self.assertEqual(out["lead"], "")
		self.assertEqual(len(frappe.inserted), 1)

	def test_create_refuses_unknown_lead(self):
		with self.assertRaises(Exception):
			properties.create_property("412 Maple Ave", lead="CRM-LEAD-NOPE")
		self.assertEqual(frappe.inserted, [])

	def test_update_links_and_unlinks(self):
		doc = self._prop()
		out = properties.update_property(doc.name, lead="CRM-LEAD-00001")
		self.assertEqual(out["lead"], "CRM-LEAD-00001")
		self.assertTrue(doc.saved)
		out = properties.update_property(doc.name, lead="")
		self.assertEqual(out["lead"], "")

	def test_set_property_lead_does_not_save_the_address(self):
		doc = self._prop()
		out = properties.set_property_lead(doc.name, "CRM-LEAD-00001")
		self.assertEqual(out["lead"], "CRM-LEAD-00001")
		self.assertFalse(doc.saved)
		frappe.db.set_value.assert_called_once()
		args = frappe.db.set_value.call_args
		self.assertEqual(args[0][2], "lead")
		self.assertEqual(args[0][3], "CRM-LEAD-00001")

	def test_set_property_lead_blank_unlinks(self):
		doc = self._prop(lead="CRM-LEAD-00001")
		out = properties.set_property_lead(doc.name, "")
		self.assertEqual(out["lead"], "")

	def test_list_filters_by_lead(self):
		a = self._prop(name="PROP-00001", lead="CRM-LEAD-00001")
		self.listed = [a]
		out = properties.list_properties(lead="CRM-LEAD-00001")
		self.assertEqual([p["name"] for p in out["properties"]], ["PROP-00001"])
		self.assertEqual(out["properties"][0]["lead_name"], "Jane Seller")
		prop_call = next(
			c for c in frappe.get_all.call_args_list if c.args and c.args[0] == "CRM Property"
		)
		self.assertEqual(prop_call.kwargs["filters"].get("lead"), "CRM-LEAD-00001")

	def test_list_lead_filter_empty_when_column_missing(self):
		self.columns.remove("lead")
		self.listed = [self._prop(name="PROP-00001")]
		out = properties.list_properties(lead="CRM-LEAD-00001")
		self.assertEqual(out["properties"], [])
		self.assertFalse(out["lead_supported"])

	def test_search_leads_passes_query(self):
		self.lead_rows = [{"name": "CRM-LEAD-00001", "lead_name": "Jane Seller"}]
		rows = properties.search_leads("jane")
		self.assertEqual(rows[0]["name"], "CRM-LEAD-00001")
		kwargs = frappe.get_all.call_args.kwargs
		self.assertIn("%jane%", kwargs["or_filters"]["lead_name"][1])


if __name__ == "__main__":
	unittest.main()
