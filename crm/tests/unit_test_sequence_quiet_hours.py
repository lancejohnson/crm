"""Drainer quiet hours: scheduled Text/Call steps never fire at night."""

import unittest
from datetime import datetime

from crm.tests.frappe_shim import install

shim = install()

from crm.api import sequence_drain as sd  # noqa: E402


def step(step_type="Text", wait_value=1, wait_unit="Days"):
	return {"step_type": step_type, "wait_value": wait_value, "wait_unit": wait_unit}


class QuietHoursTests(unittest.TestCase):
	def test_daytime_runs_now(self):
		self.assertIsNone(sd.quiet_hold_until(datetime(2026, 9, 9, 14, 30), step()))
		self.assertIsNone(sd.quiet_hold_until(datetime(2026, 9, 9, 8, 0), step()))
		self.assertIsNone(sd.quiet_hold_until(datetime(2026, 9, 9, 19, 59), step()))

	def test_late_night_waits_for_tomorrow_morning(self):
		self.assertEqual(
			sd.quiet_hold_until(datetime(2026, 9, 9, 23, 5), step()),
			datetime(2026, 9, 10, 8, 0),
		)
		self.assertEqual(
			sd.quiet_hold_until(datetime(2026, 9, 9, 20, 0), step("Call")),
			datetime(2026, 9, 10, 8, 0),
		)

	def test_early_morning_waits_for_today(self):
		self.assertEqual(
			sd.quiet_hold_until(datetime(2026, 9, 9, 6, 15), step()),
			datetime(2026, 9, 9, 8, 0),
		)

	def test_instant_burst_is_never_held(self):
		night = datetime(2026, 9, 9, 23, 5)
		self.assertIsNone(sd.quiet_hold_until(night, step(wait_value=0)))
		self.assertIsNone(sd.quiet_hold_until(night, step(wait_value=5, wait_unit="Seconds")))
		self.assertIsNone(sd.quiet_hold_until(night, step(wait_value=3, wait_unit="Minutes")))
		self.assertEqual(
			sd.quiet_hold_until(night, step(wait_value=1, wait_unit="Hours")),
			datetime(2026, 9, 10, 8, 0),
		)

	def test_non_seller_steps_are_never_held(self):
		night = datetime(2026, 9, 9, 23, 5)
		self.assertIsNone(sd.quiet_hold_until(night, step("Pushover")))
		self.assertIsNone(sd.quiet_hold_until(night, step("Email")))
		self.assertIsNone(sd.quiet_hold_until(night, None))


class CalendarDueTests(unittest.TestCase):
	def test_one_day_lands_next_morning_not_plus_24h(self):
		self.assertEqual(
			sd.calendar_due(datetime(2026, 9, 9, 11, 39), step()),
			datetime(2026, 9, 10, 8, 0),
		)
		self.assertEqual(
			sd.calendar_due(datetime(2026, 9, 9, 23, 5), step()),
			datetime(2026, 9, 10, 8, 0),
		)

	def test_zero_and_non_day_waits_are_left_alone(self):
		now = datetime(2026, 9, 9, 11, 39)
		self.assertIsNone(sd.calendar_due(now, step(wait_value=0)))
		self.assertIsNone(sd.calendar_due(now, step(wait_value=30, wait_unit="Minutes")))
		self.assertIsNone(sd.calendar_due(now, None))

	def test_weeks_and_multi_day(self):
		now = datetime(2026, 9, 9, 14, 0)
		self.assertEqual(
			sd.calendar_due(now, step(wait_value=2)),
			datetime(2026, 9, 11, 8, 0),
		)
		self.assertEqual(
			sd.calendar_due(now, step(wait_value=1, wait_unit="Weeks")),
			datetime(2026, 9, 16, 8, 0),
		)


if __name__ == "__main__":
	unittest.main()
