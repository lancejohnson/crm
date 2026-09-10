"""Non-refundable leads: flagged by order id, kept off the Refunds board."""

import unittest
from unittest import mock

from crm.tests.frappe_shim import install

shim = install()

from crm.api import refunds  # noqa: E402


class _Meta:
	def __init__(self, fields):
		self._fields = set(fields)

	def has_field(self, name):
		return name in self._fields


class _Lead:
	def __init__(self, fields, **values):
		self.name = values.pop("name", "CRM-LEAD-1")
		self.meta = _Meta(fields)
		self._values = values

	def get(self, key, default=None):
		return self._values.get(key, default)

	def check_permission(self, *_):
		return True


ALL_FIELDS = (
	"custom_refundable",
	"custom_refund_requested",
	"custom_refund_requested_on",
	"custom_refund_not_in_provider",
	"custom_refund_manual_ticket",
	"custom_refund_status",
	refunds.NON_REFUNDABLE_FIELD,
	refunds.NON_REFUNDABLE_REASON_FIELD,
)


class MarkNonRefundableTests(unittest.TestCase):
	def setUp(self):
		shim.db.columns["CRM Lead"] = set(ALL_FIELDS) | {"custom_refund_updated_on"}
		shim.db.set_value.reset_mock()
		shim.get_all.reset_mock()
		shim.errors.clear()

	def test_matches_on_order_id_and_reports_the_rest(self):
		shim.get_all.return_value = [
			{"name": "CRM-LEAD-1", "vendor_lead_id": "o1", "custom_non_refundable": 0, "custom_refundable": 0},
		]
		out = refunds.mark_non_refundable(["o1", "o2"])
		self.assertEqual(out["matched"], ["o1"])
		self.assertEqual(out["unmatched"], ["o2"])
		self.assertEqual(out["leads"], {"o1": "CRM-LEAD-1"})
		args = shim.db.set_value.call_args[0]
		self.assertEqual(args[:2], ("CRM Lead", "CRM-LEAD-1"))
		self.assertEqual(args[2][refunds.NON_REFUNDABLE_FIELD], 1)
		self.assertEqual(args[2][refunds.NON_REFUNDABLE_REASON_FIELD], refunds.DEFAULT_NON_REFUNDABLE_REASON)

	def test_idempotent_for_already_flagged(self):
		shim.get_all.return_value = [
			{"name": "CRM-LEAD-1", "vendor_lead_id": "o1", "custom_non_refundable": 1, "custom_refundable": 0},
		]
		out = refunds.mark_non_refundable('["o1"]')
		self.assertEqual(out["matched"], ["o1"])
		shim.db.set_value.assert_not_called()

	def test_already_queued_lead_is_flagged_not_removed(self):
		shim.get_all.return_value = [
			{"name": "CRM-LEAD-9", "vendor_lead_id": "o9", "custom_non_refundable": 0, "custom_refundable": 1},
		]
		out = refunds.mark_non_refundable(["o9"])
		self.assertEqual(out["already_on_board"], ["CRM-LEAD-9"])
		updates = shim.db.set_value.call_args[0][2]
		self.assertNotIn("custom_refundable", updates)
		self.assertTrue(shim.errors)

	def test_empty_input_is_a_noop(self):
		out = refunds.mark_non_refundable([])
		self.assertEqual(out, {"matched": [], "unmatched": [], "leads": {}})
		shim.get_all.assert_not_called()


class SetRefundStateGuardTests(unittest.TestCase):
	def setUp(self):
		shim.db.columns["CRM Lead"] = set(ALL_FIELDS) | {"custom_refund_updated_on"}
		shim.db.set_value.reset_mock()

	def _lead(self, **values):
		lead = _Lead(ALL_FIELDS, **values)
		shim.get_doc = mock.MagicMock(return_value=lead)
		return lead

	def test_non_refundable_cannot_be_marked_refundable(self):
		self._lead(custom_non_refundable=1, custom_non_refundable_reason="bonus wallet")
		with self.assertRaises(shim.ValidationError) as cm:
			refunds.set_refund_state("CRM-LEAD-1", refundable=1)
		self.assertIn("bonus wallet", str(cm.exception))
		shim.db.set_value.assert_not_called()

	def test_every_on_board_path_is_blocked(self):
		self._lead(custom_non_refundable=1)
		for kwargs in ({"not_in_provider": 1}, {"manual_ticket": 1}, {"status": "Requested"}):
			with self.assertRaises(shim.ValidationError):
				refunds.set_refund_state("CRM-LEAD-1", **kwargs)

	def test_clearing_refundable_still_works(self):
		"""Withdrawing a request queued before the flag landed must be allowed."""
		self._lead(custom_non_refundable=1, custom_refundable=1, custom_refund_status="Requested")
		out = refunds.set_refund_state("CRM-LEAD-1", refundable=0)
		self.assertEqual(out["custom_refundable"], 0)

	def test_refundable_lead_is_unaffected(self):
		self._lead(custom_non_refundable=0)
		out = refunds.set_refund_state("CRM-LEAD-1", refundable=1)
		self.assertEqual(out["custom_refundable"], 1)
		self.assertEqual(out["custom_refund_status"], "To Request")


if __name__ == "__main__":
	unittest.main()
