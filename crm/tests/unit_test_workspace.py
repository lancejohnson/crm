"""Workspace gating: allowlist parsing, version normalisation, refusal."""

import unittest

from crm.tests.frappe_shim import install

shim = install()

from crm.api import workspace  # noqa: E402


class AllowlistTests(unittest.TestCase):
	def setUp(self):
		shim.conf.clear()
		shim.session.user = "lance.johnson@groundworkpro.com"
		shim.defaults_set.clear()

	def test_default_is_lance_only(self):
		self.assertEqual(workspace.allowlist(), {"lance.johnson@groundworkpro.com"})
		self.assertTrue(workspace.is_allowed())
		self.assertFalse(workspace.is_allowed("exe@groundworkpro.com"))

	def test_list_and_json_string_both_accepted(self):
		shim.conf["crm_next_users"] = ["A@x.com", " b@x.com "]
		self.assertEqual(workspace.allowlist(), {"a@x.com", "b@x.com"})
		shim.conf["crm_next_users"] = '["c@x.com"]'
		self.assertEqual(workspace.allowlist(), {"c@x.com"})

	def test_malformed_config_never_widens(self):
		for bad in ("not json", "", [], 42, None):
			shim.conf["crm_next_users"] = bad
			self.assertEqual(workspace.allowlist(), {"lance.johnson@groundworkpro.com"}, bad)

	def test_normalize(self):
		self.assertEqual(workspace.normalize_version("next", True), "next")
		self.assertEqual(workspace.normalize_version("next", False), "classic")
		self.assertEqual(workspace.normalize_version("NEXT", True), "classic")
		self.assertEqual(workspace.normalize_version(None, True), "classic")

	def test_get_reports_allowed_and_version(self):
		shim.db.get_default.return_value = "next"
		self.assertEqual(workspace.get(), {"version": "next", "allowed": True})
		shim.session.user = "exe@groundworkpro.com"
		self.assertEqual(workspace.get(), {"version": "classic", "allowed": False})

	def test_set_refuses_next_for_others(self):
		shim.session.user = "exe@groundworkpro.com"
		with self.assertRaises(shim.PermissionError):
			workspace.set_version("next")
		self.assertEqual(shim.defaults_set, [])
		self.assertEqual(workspace.set_version("classic"), {"version": "classic"})
		self.assertEqual(shim.defaults_set, [("crm_workspace_version", "classic", "exe@groundworkpro.com")])

	def test_set_rejects_unknown(self):
		with self.assertRaises(shim.ValidationError):
			workspace.set_version("beta")

	def test_endpoints_are_whitelisted_not_guest(self):
		for fn in (workspace.get, workspace.set_version):
			self.assertTrue(fn._whitelisted)
			self.assertFalse(fn._allow_guest)


if __name__ == "__main__":
	unittest.main()
