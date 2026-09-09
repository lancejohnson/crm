"""Sequence status gating (pure parts) + the Today cadence's daily closer card."""

import unittest
from datetime import date, datetime
from types import SimpleNamespace

from crm.tests.frappe_shim import install

shim = install()

from crm.api import daily_standup as ds  # noqa: E402
from crm.api import sequence_status as ss  # noqa: E402


class StatusGateTests(unittest.TestCase):
	def test_blank_means_any_status(self):
		self.assertIsNone(ss.parse_statuses(""))
		self.assertIsNone(ss.parse_statuses(None))
		self.assertIsNone(ss.parse_statuses("  \n \n"))
		self.assertFalse(ss.status_excluded(None, "Dead Lead"))

	def test_one_per_line_trimmed(self):
		allowed = ss.parse_statuses(" New \nCalled No Answer\n\n")
		self.assertEqual(allowed, frozenset({"New", "Called No Answer"}))
		self.assertFalse(ss.status_excluded(allowed, "New"))
		self.assertTrue(ss.status_excluded(allowed, "Follow Up"))
		self.assertTrue(ss.status_excluded(allowed, ""))
		self.assertTrue(ss.status_excluded(allowed, None))

	def test_pause_only_the_gated_sequences(self):
		shim.db.has_column = lambda dt, col: True
		values = {"Seq A": "New\nCalled No Answer", "Seq B": ""}
		shim.db.get_value = lambda dt, name, field=None, *a, **k: values.get(name)
		shim.get_all = lambda *a, **k: [
			SimpleNamespace(name="ENR-A", sequence="Seq A"),
			SimpleNamespace(name="ENR-B", sequence="Seq B"),
		]
		writes = []
		shim.db.set_value = lambda dt, name, vals, **k: writes.append((name, vals))
		paused = ss.pause_excluded_enrollments("LEAD-1", "Follow Up")
		self.assertEqual(paused, ["ENR-A"])
		self.assertEqual(writes[0][0], "ENR-A")
		self.assertEqual(writes[0][1]["status"], "Paused")
		self.assertIn("auto-paused", writes[0][1]["last_log"])
		self.assertIn("Follow Up", writes[0][1]["last_log"])

	def test_hook_ignores_saves_that_did_not_change_status(self):
		shim.db.has_column = lambda dt, col: True
		calls = []
		shim.get_all = lambda *a, **k: calls.append(1) or []
		doc = SimpleNamespace(name="LEAD-1", status="New", has_value_changed=lambda f: False)
		ss.on_lead_update(doc)
		self.assertEqual(calls, [])

	def test_unprovisioned_column_is_a_noop(self):
		shim.db.has_column = lambda dt, col: False
		shim.get_all = lambda *a, **k: self.fail("must not query enrollments")
		self.assertEqual(ss.pause_excluded_enrollments("LEAD-1", "Dead Lead"), [])
		self.assertTrue(
			ss.check_before_step(SimpleNamespace(name="E", sequence="S", lead="L"))
		)


def _row(status, **kw):
	base = dict(
		name="LEAD-1",
		lead_name="Test",
		status=status,
		creation=datetime(2026, 8, 3, 9, 0),
		first_call=datetime(2026, 8, 3, 10, 0),
		last_call=datetime(2026, 8, 3, 10, 0),  # weeks ago → monthly-sweep territory
		calls_today=0,
		next_future_due=None,
		tasks_due_now=0,
		due_task_title=None,
	)
	base.update(kw)
	return SimpleNamespace(**base)


class CloserCardTests(unittest.TestCase):
	today = date(2026, 9, 7)

	def test_closer_status_without_task_is_due_daily(self):
		for status in ds.CLOSER_STATUSES:
			phase, need, due, reason = ds._classify(_row(status, last_call=datetime(2026, 9, 4, 10, 0)), self.today)
			self.assertEqual((phase, need, due), ("closer", 1, True), status)
			self.assertIn("no follow-up scheduled", reason)

	def test_future_task_clears_it(self):
		phase, _, due, _ = ds._classify(
			_row("Make Offer", next_future_due=datetime(2026, 9, 9, 9, 0)), self.today
		)
		self.assertEqual((phase, due), ("scheduled", False))

	def test_task_due_today_keeps_it_and_names_the_task(self):
		phase, _, due, reason = ds._classify(
			_row("Contract Sent", tasks_due_now=1, due_task_title="Send DD docs"), self.today
		)
		self.assertEqual((phase, due), ("closer", True))
		self.assertIn("Send DD docs", reason)

	def test_non_closer_statuses_follow_the_call_ladder(self):
		phase, _, _, _ = ds._classify(_row("Follow Up"), self.today)
		self.assertNotEqual(phase, "closer")
		self.assertIn("closer", ds.CADENCE_PHASES)


if __name__ == "__main__":
	unittest.main()
