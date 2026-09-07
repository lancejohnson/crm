"""Talk: unread math, ordering, DM slugs, presence merge, guards."""

import unittest
from datetime import datetime

from crm.tests.frappe_shim import install

shim = install()

from crm.api import talk  # noqa: E402


class UnreadTests(unittest.TestCase):
	def test_counts_only_others_newer_than_stamp(self):
		me = "lance@x.com"
		messages = [
			{"channel": "acq", "author": "exe@x.com", "posted_at": "2026-09-07 10:00:00"},
			{"channel": "acq", "author": "exe@x.com", "posted_at": "2026-09-07 11:00:00"},
			{"channel": "acq", "author": me, "posted_at": "2026-09-07 12:00:00"},
			{"channel": "dispo", "author": "dennis@x.com", "posted_at": "2026-09-07 09:00:00"},
			{"channel": "dispo", "author": "dennis@x.com", "posted_at": "2026-09-07 09:30:00", "deleted": 1},
		]
		reads = {"acq": "2026-09-07 10:30:00"}
		self.assertEqual(talk.unread_counts(messages, reads, me), {"acq": 1, "dispo": 1})

	def test_no_stamp_means_all_unread(self):
		messages = [{"channel": "c", "author": "a@x", "posted_at": datetime(2026, 9, 7, 1)}] * 3
		self.assertEqual(talk.unread_counts(messages, {}, "me@x"), {"c": 3})

	def test_equal_stamp_is_read(self):
		messages = [{"channel": "c", "author": "a@x", "posted_at": "2026-09-07 10:00:00"}]
		self.assertEqual(talk.unread_counts(messages, {"c": "2026-09-07 10:00:00"}, "me@x"), {})


class OrderingTests(unittest.TestCase):
	def test_standup_pinned_then_channels_then_dms_newest_first(self):
		rows = [
			{"name": "dm-1", "kind": "dm", "title": "Exe", "last_at": "2026-09-07 10:00:00"},
			{"name": "dispo", "kind": "channel", "title": "dispo"},
			{"name": "dm-2", "kind": "dm", "title": "Dennis", "last_at": "2026-09-07 12:00:00"},
			{"name": "acquisitions", "kind": "channel", "title": "acquisitions"},
			{"name": "standup", "kind": "bot", "title": "Standup"},
			{"name": "ops-bot", "kind": "bot", "title": "ops-bot"},
			{"name": "dm-3", "kind": "dm", "title": "Nobody", "last_at": None},
		]
		self.assertEqual(
			[r["name"] for r in talk.order_channels(rows)],
			["standup", "ops-bot", "acquisitions", "dispo", "dm-2", "dm-1", "dm-3"],
		)


class SlugTests(unittest.TestCase):
	def test_dm_slug_is_order_independent_and_stable(self):
		a = talk.dm_slug("Lance@x.com", "exe@x.com")
		b = talk.dm_slug("exe@x.com", "lance@x.com ")
		self.assertEqual(a, b)
		self.assertTrue(a.startswith("dm-"))
		self.assertEqual(len(a), 15)
		self.assertNotEqual(a, talk.dm_slug("lance@x.com", "dennis@x.com"))


class PresenceTests(unittest.TestCase):
	def test_call_wins_and_unknown_status_is_offline(self):
		out = talk.presence_for({"a@x": "online", "b@x": "weird", "c@x": "away"}, {"a@x", "d@x"})
		self.assertEqual(out, {"a@x": "on_call", "b@x": "offline", "c@x": "away", "d@x": "on_call"})


class GuardTests(unittest.TestCase):
	def setUp(self):
		shim.db.doctypes.clear()
		shim.session.user = "lance.johnson@groundworkpro.com"

	def test_disabled_without_doctypes(self):
		self.assertFalse(talk.enabled())
		self.assertEqual(talk.list_channels(), [])
		self.assertEqual(talk.thread("acquisitions"), {"messages": [], "has_more": False})
		self.assertEqual(talk.mark_read("acquisitions"), {"unread": 0})
		self.assertIsNone(talk.post_as_bot("standup", "hi"))

	def test_membership_rules(self):
		class Doc(dict):
			def __getattr__(self, k):
				return self.get(k)

		def member(u):
			return Doc(user=u)

		public = Doc(kind="channel", members=[])
		private = Doc(kind="channel", members=[member("a@x")])
		dm = Doc(kind="dm", members=[member("a@x"), member("b@x")])
		self.assertTrue(talk._is_member(public, "anyone@x"))
		self.assertTrue(talk._is_member(private, "a@x"))
		self.assertFalse(talk._is_member(private, "z@x"))
		self.assertTrue(talk._is_member(dm, "b@x"))
		self.assertFalse(talk._is_member(dm, "z@x"))

	def test_endpoints_session_only(self):
		for fn in (talk.list_channels, talk.thread, talk.post, talk.mark_read, talk.ensure_dm, talk.presence):
			self.assertTrue(fn._whitelisted, fn.__name__)
			self.assertFalse(fn._allow_guest, fn.__name__)


if __name__ == "__main__":
	unittest.main()
