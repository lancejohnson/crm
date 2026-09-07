"""Mattermost sync: loop guard, channel mapping, HMAC verification, apply_event."""

import json
import unittest
from unittest import mock

from crm.tests.frappe_shim import install

shim = install()

from crm.integrations.mattermost import sync, webhook  # noqa: E402


class LoopGuardTests(unittest.TestCase):
	def test_crm_origin_props_skip(self):
		self.assertTrue(sync.is_crm_origin({"props": {"crm_origin": 1}}))
		self.assertTrue(sync.is_crm_origin({"props": {"crm_origin": "1"}}))
		self.assertTrue(sync.is_crm_origin({"props": json.dumps({"crm_origin": True})}))
		self.assertFalse(sync.is_crm_origin({"props": {"crm_origin": 0}}))
		self.assertFalse(sync.is_crm_origin({"props": {"crm_origin": "false"}}))
		self.assertFalse(sync.is_crm_origin({"props": {}}))
		self.assertFalse(sync.is_crm_origin({}))

	def test_known_post_id_skips(self):
		self.assertTrue(sync.should_skip_inbound({"id": "p1"}, {"p1"}))
		self.assertFalse(sync.should_skip_inbound({"id": "p2"}, {"p1"}))
		self.assertTrue(sync.should_skip_inbound({"id": "p2", "props": {"crm_origin": 1}}, set()))


class MappingTests(unittest.TestCase):
	def test_kind_from_mm_type(self):
		self.assertEqual(sync.kind_for_mm_type("O"), "channel")
		self.assertEqual(sync.kind_for_mm_type("p"), "channel")
		self.assertEqual(sync.kind_for_mm_type("D"), "dm")
		self.assertEqual(sync.kind_for_mm_type("G"), "channel")
		self.assertEqual(sync.kind_for_mm_type(None), "channel")

	def test_channel_slug(self):
		self.assertEqual(sync.channel_slug({"id": "abc123", "type": "O", "name": "Acquisitions"}), "acquisitions")
		self.assertEqual(sync.channel_slug({"id": "abcdefghijklmnop", "type": "D", "name": "u1__u2"}), "dm-abcdefghijkl")
		self.assertEqual(sync.channel_slug({"id": "abcdefghijklmnop", "type": "G", "name": "u1__u2"}), "mm-abcdefghijkl")

	def test_bot_prefix(self):
		self.assertEqual(sync.bot_prefixed("Exe Ortiz", "hi"), "**Exe Ortiz:** hi")
		self.assertEqual(sync.bot_prefixed("", "hi"), "hi")

	def test_inbound_row_shape(self):
		row = sync.inbound_row(
			{"id": "p9", "message": "hello", "create_at": 1788751442000, "root_id": "", "edit_at": 0},
			"acquisitions", "exe@x.com", None,
		)
		self.assertEqual(row["origin"], "mattermost")
		self.assertEqual(row["mm_post_id"], "p9")
		self.assertIsNone(row["mm_root_id"])
		self.assertIsNone(row["edited_at"])
		self.assertEqual(row["deleted"], 0)
		self.assertEqual(row["posted_at"].year, 2026)
		self.assertEqual(json.loads(row["props"]), {"mirror": False}, "inbound rows are never mirrored back")

	def test_status_normalised(self):
		self.assertEqual(sync.status_for("online"), "online")
		self.assertEqual(sync.status_for("banana"), "offline")


class SignatureTests(unittest.TestCase):
	def test_verify_roundtrip_and_refusals(self):
		body = b'{"event":"posted"}'
		sig = webhook.compute_signature("s3cret", body)
		self.assertTrue(webhook.verify_signature("s3cret", body, sig))
		self.assertTrue(webhook.verify_signature("s3cret", body, sig[len("sha256="):]), "bare hex accepted")
		self.assertFalse(webhook.verify_signature("s3cret", body + b" ", sig), "any byte change fails")
		self.assertFalse(webhook.verify_signature("other", body, sig))
		self.assertFalse(webhook.verify_signature("", body, sig), "no secret = refuse")
		self.assertFalse(webhook.verify_signature("s3cret", body, None), "no header = refuse")
		self.assertFalse(webhook.verify_signature("s3cret", body, ""))

	def test_event_is_guest_and_verifies(self):
		self.assertTrue(webhook.event._allow_guest)
		shim.conf["mattermost_sync_secret"] = ""
		shim.request = mock.MagicMock()
		shim.request.get_data.return_value = b"{}"
		shim.request.headers = {"X-Groundwork-Signature": "sha256=deadbeef"}
		shim.local.response = {}
		self.assertEqual(webhook.event(), {"ok": False})
		self.assertEqual(shim.local.response.get("http_status_code"), 403)


class ApplyEventTests(unittest.TestCase):
	def setUp(self):
		shim.db.doctypes = {"CRM Message", "CRM Channel", "CRM Channel Read", "User"}
		shim.db.get_value = mock.MagicMock(return_value=None)
		shim.get_doc = mock.MagicMock()
		shim.errors.clear()

	def test_unknown_event_ignored(self):
		self.assertEqual(sync.apply_event({"event": "typing"}), {"ok": True, "skipped": "ignored typing"})

	def test_posted_with_crm_origin_skipped(self):
		out = sync.apply_event({"event": "posted", "post": {"id": "p1", "props": {"crm_origin": 1}}})
		self.assertEqual(out["skipped"], "loop guard")
		shim.get_doc.assert_not_called()

	def test_posted_duplicate_skipped(self):
		shim.db.get_value = mock.MagicMock(return_value="MSG-existing")
		out = sync.apply_event({"event": "posted", "post": {"id": "p1", "channel_id": "c1"}})
		self.assertEqual(out["skipped"], "loop guard")

	def test_posted_inserts_mapped_author(self):
		# channel already mapped; user mapped by email
		shim.db.get_value = mock.MagicMock(side_effect=lambda dt, f, *a, **k: "acquisitions" if dt == "CRM Channel" else None)
		shim.db.values[("User", "exe@x.com")] = True
		inserted = mock.MagicMock()
		inserted.insert.return_value = mock.MagicMock(name="MSG-1")
		inserted.insert.return_value.name = "MSG-1"
		shim.get_doc.return_value = inserted
		out = sync.apply_event(
			{
				"event": "posted",
				"post": {"id": "p7", "channel_id": "c1", "user_id": "u1", "message": "hey", "create_at": 1788751442000},
				"channel": {"id": "c1", "type": "O", "name": "acquisitions"},
				"user": {"id": "u1", "email": "exe@x.com", "username": "exe"},
			}
		)
		self.assertEqual(out, {"ok": True, "action": "insert", "name": "MSG-1"})
		row = shim.get_doc.call_args[0][0]
		self.assertEqual(row["author"], "exe@x.com")
		self.assertIsNone(row["author_label"])
		self.assertEqual(row["origin"], "mattermost")

	def test_posted_unmapped_author_becomes_bot_with_label(self):
		shim.db.get_value = mock.MagicMock(side_effect=lambda dt, f, *a, **k: "acquisitions" if dt == "CRM Channel" else None)
		inserted = mock.MagicMock()
		inserted.insert.return_value.name = "MSG-2"
		shim.get_doc.return_value = inserted
		sync.apply_event(
			{
				"event": "posted",
				"post": {"id": "p8", "channel_id": "c1", "user_id": "u9", "message": "yo", "create_at": 1},
				"channel": {"id": "c1", "type": "O", "name": "acquisitions"},
				"user": {"id": "u9", "email": "stranger@else.com", "username": "stranger"},
			}
		)
		row = shim.get_doc.call_args[0][0]
		self.assertEqual(row["author"], "Administrator")
		self.assertEqual(row["author_label"], "stranger")

	def test_edit_and_delete_unknown_post_skipped(self):
		self.assertEqual(sync.apply_event({"event": "post_edited", "post": {"id": "nope"}})["skipped"], "unknown post")
		self.assertEqual(sync.apply_event({"event": "post_deleted", "post": {"id": "nope"}})["skipped"], "unknown post")

	def test_status_change_sets_presence(self):
		shim.db.values[("User", "exe@x.com")] = True
		shim.published.clear()
		out = sync.apply_event({"event": "status_change", "user": {"id": "u1", "email": "exe@x.com"}, "status": {"user_id": "u1", "status": "away"}})
		self.assertEqual(out["action"], "status")
		self.assertEqual(shim._cache.get_value("crm:talk:mm_status")["exe@x.com"], "away")
		self.assertEqual(shim.published[-1][0][0], "crm_presence")


if __name__ == "__main__":
	unittest.main()
