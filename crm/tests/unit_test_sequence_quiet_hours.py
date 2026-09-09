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


if __name__ == "__main__":
	unittest.main()
