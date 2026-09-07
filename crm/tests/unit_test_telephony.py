"""Telnyx desk: E.164, line access, recording resolution, ring fan-out,
conference payloads, call state, endpoint gating and webhook leg routing."""

import json
import unittest
from unittest import mock

from crm.tests.frappe_shim import install

shim = install()

from crm.integrations.telnyx import desk  # noqa: E402
from crm.api import telephony  # noqa: E402


class NumberTests(unittest.TestCase):
	def test_e164(self):
		self.assertEqual(desk.e164("(612) 555-1234"), "+16125551234")
		self.assertEqual(desk.e164("1 612 555 1234"), "+16125551234")
		self.assertEqual(desk.e164("+16125551234"), "+16125551234")
		self.assertEqual(desk.e164("+44 20 7946 0958"), "+442079460958")
		self.assertEqual(desk.e164("sip:exe@sip.telnyx.com"), "sip:exe@sip.telnyx.com")
		self.assertEqual(desk.e164("555-1234"), "")
		self.assertEqual(desk.e164(None), "")

	def test_client_state_roundtrip_drops_empties(self):
		blob = desk.encode_client_state(kind="rep_leg", desk="abc", user="a@x", lead=None, to="")
		self.assertEqual(desk.decode_client_state(blob), {"kind": "rep_leg", "desk": "abc", "user": "a@x"})
		self.assertEqual(desk.decode_client_state("not base64!"), {})
		self.assertEqual(desk.decode_client_state(None), {})


LINE = {
	"name": "+16125550100", "number": "+16125550100", "owner": "exe@x.com", "recording": "inherit", "active": True,
	"members": [
		{"user": "dennis@x.com", "view": 1, "use": 1, "ring": 0},
		{"user": "german@x.com", "view": 1, "use": 0, "ring": 1},
	],
}


class AccessTests(unittest.TestCase):
	def test_owner_has_everything(self):
		self.assertEqual(desk.line_access(LINE, "Exe@x.com"), {"view": True, "use": True, "ring": True})

	def test_members_are_separate_grants(self):
		self.assertEqual(desk.line_access(LINE, "dennis@x.com"), {"view": True, "use": True, "ring": False})
		self.assertEqual(desk.line_access(LINE, "german@x.com"), {"view": True, "use": False, "ring": True})
		self.assertEqual(desk.line_access(LINE, "nobody@x.com"), {"view": False, "use": False, "ring": False})
		self.assertTrue(desk.can(LINE, "dennis@x.com", "use"))
		self.assertFalse(desk.can(LINE, "dennis@x.com", "ring"))

	def test_ring_members_owner_first_then_ring_flag(self):
		self.assertEqual(desk.ring_members(LINE), ["exe@x.com", "german@x.com"])


class RecordingTests(unittest.TestCase):
	def test_resolution(self):
		self.assertTrue(desk.resolve_recording("inherit", True))
		self.assertFalse(desk.resolve_recording("inherit", False))
		self.assertFalse(desk.resolve_recording(None, False))
		self.assertTrue(desk.resolve_recording("on", False))
		self.assertFalse(desk.resolve_recording("off", True))
		self.assertTrue(desk.resolve_recording(" ON ", False))


class RingTests(unittest.TestCase):
	def test_targets_softphone_then_cell_only_with_fallback(self):
		members = ["exe@x.com", "german@x.com", "ghost@x.com"]
		sips = {"exe@x.com": "crm-exe", "german@x.com": None}
		mobiles = {"exe@x.com": "612-555-0001", "german@x.com": "6125550002"}
		self.assertEqual(
			desk.ring_targets(members, sips, mobiles, cell_fallback=False),
			[{"user": "exe@x.com", "to": "sip:crm-exe@sip.telnyx.com", "via": "softphone"}],
		)
		with_cells = desk.ring_targets(members, sips, mobiles, cell_fallback=True)
		self.assertEqual([t["to"] for t in with_cells], ["sip:crm-exe@sip.telnyx.com", "+16125550001", "+16125550002"])
		self.assertEqual([t["via"] for t in with_cells], ["softphone", "cell", "cell"])

	def test_first_answer_wins_and_losers(self):
		state = desk.new_state("d1", "inbound", "+16125550100")
		state["ring_legs"] = {"c1": {"user": "exe@x.com", "via": "softphone"}, "c2": {"user": "german@x.com", "via": "cell"}}
		self.assertTrue(desk.first_answer_wins(state, "c1"))
		self.assertEqual(state["answered_by"], "exe@x.com")
		self.assertEqual(state["rep_leg"], "c1")
		self.assertEqual(state["state"], "active")
		self.assertFalse(desk.first_answer_wins(state, "c2"), "second answer loses")
		self.assertEqual(desk.losing_ring_legs(state, "c1"), ["c2"])
		self.assertFalse(desk.first_answer_wins(state, "c9"), "unknown leg cannot claim")

	def test_all_ring_legs_gone_only_while_ringing(self):
		state = desk.new_state("d1", "inbound", "+1")
		self.assertTrue(desk.all_ring_legs_gone(state))
		state["ring_legs"] = {"c1": {}}
		self.assertFalse(desk.all_ring_legs_gone(state))
		state["ring_legs"] = {}
		state["state"] = "active"
		self.assertFalse(desk.all_ring_legs_gone(state))


class PayloadTests(unittest.TestCase):
	def test_dial_leg(self):
		self.assertEqual(
			desk.dial_leg_payload("conn", "sip:x@sip.telnyx.com", "+1612", "cs", 25),
			{"connection_id": "conn", "to": "sip:x@sip.telnyx.com", "from": "+1612", "client_state": "cs", "timeout_secs": 25},
		)
		self.assertNotIn("timeout_secs", desk.dial_leg_payload("c", "t", "f", "cs"))

	def test_conference_create_never_beeps(self):
		body = desk.create_conference_payload("abc", "ccid1")
		self.assertEqual(body["name"], "crm-abc")
		self.assertEqual(body["beep_enabled"], "never")
		self.assertTrue(body["start_conference_on_create"])

	def test_join_roles(self):
		self.assertEqual(desk.join_payload("p"), {"call_control_id": "p", "beep_enabled": "never"})
		self.assertEqual(
			desk.join_payload("s", "whisper", "rep1"),
			{"call_control_id": "s", "beep_enabled": "never", "supervisor_role": "whisper", "whisper_call_control_ids": ["rep1"]},
		)
		self.assertEqual(desk.join_payload("s", "monitor", "rep1")["supervisor_role"], "monitor")
		self.assertNotIn("whisper_call_control_ids", desk.join_payload("s", "monitor", "rep1"))
		self.assertEqual(desk.join_payload("s", "barge")["supervisor_role"], "barge")
		with self.assertRaises(ValueError):
			desk.join_payload("s", "listen")

	def test_update_mode(self):
		self.assertEqual(desk.update_mode_payload("s", "barge"), {"call_control_id": "s", "supervisor_role": "barge"})
		self.assertEqual(desk.update_mode_payload("s", "whisper", "r")["whisper_call_control_ids"], ["r"])

	def test_hold_is_peer_only(self):
		action, body = desk.hold_payload(["peer1"], True)
		self.assertEqual((action, body), ("hold", {"call_control_ids": ["peer1"]}))
		action, body = desk.hold_payload(["peer1"], False)
		self.assertEqual(action, "unhold")
		with self.assertRaises(ValueError):
			desk.hold_payload([])


		action, body = desk.tone_payload("rep1", "https://x/tone.mp3")
		self.assertEqual((action, body), ("play", {"audio_url": "https://x/tone.mp3", "call_control_ids": ["rep1"]}))
		action, body = desk.tone_payload("rep1")
		self.assertEqual(action, "speak")
		self.assertEqual(body["call_control_ids"], ["rep1"])
		self.assertEqual(body["payload"], desk.DEFAULT_JOIN_TONE_TEXT)

	def test_record_is_dual_channel(self):
		self.assertEqual(desk.record_payload()["channels"], "dual")
		self.assertFalse(desk.record_payload()["play_beep"])
		self.assertFalse(desk.record_payload()["transcription"])
		live = desk.live_transcription_payload()
		self.assertEqual(live["transcription_tracks"], "both")
		self.assertTrue(live["transcription_engine_config"]["interimResults"])


class StateTests(unittest.TestCase):
	def test_leg_kind_and_row(self):
		state = desk.new_state("d1", "outbound", "+1line", rep="exe@x.com", lead="CRM-LEAD-1", to="+1seller")
		state.update(rep_leg="r", peer_leg="p", conference_id="conf", supervisors={"s": {"user": "dennis@x.com", "mode": "whisper"}})
		for ccid, kind in (("r", "rep_leg"), ("p", "peer_leg"), ("s", "supervisor_leg"), ("zz", None)):
			self.assertEqual(desk.leg_kind(state, ccid), kind)
		self.assertEqual(desk.external_leg(state), "p")
		row = desk.active_call_row(state, "Jordan Ellis")
		self.assertEqual(row["number"], "+1seller")
		self.assertEqual(row["lead_name"], "Jordan Ellis")
		self.assertEqual(row["supervisors"], [{"user": "dennis@x.com", "mode": "whisper"}])
		inbound = desk.new_state("d2", "inbound", "+1line", frm="+1caller")
		self.assertEqual(desk.active_call_row(inbound)["number"], "+1caller")


class SettingsTests(unittest.TestCase):
	def setUp(self):
		shim.db.doctypes.clear()
		shim.conf.clear()

	def test_defaults_before_ops_script(self):
		s = telephony.phone_settings()
		self.assertTrue(s["recording_default"])
		self.assertFalse(s["ring_cell_fallback"])
		self.assertEqual(s["ring_timeout_secs"], 25)
		self.assertIn("does not obtain consent", s["consent_note"])
		self.assertIsNone(s["join_tone_url"])
		self.assertEqual(telephony.lines(), [])
		self.assertEqual(telephony.active_calls(), [])


class StateStoreTests(unittest.TestCase):
	def test_save_load_index_drop(self):
		shim._cache.hashes.clear()
		state = desk.new_state("d9", "outbound", "+1")
		state["call_log"] = "CL-1"
		telephony._save(state)
		self.assertEqual(telephony._load("d9")["desk_id"], "d9")
		self.assertEqual(telephony._by_call_log("CL-1")["desk_id"], "d9")
		self.assertEqual([s["desk_id"] for s in telephony._all_states()], ["d9"])
		telephony._drop(state)
		self.assertIsNone(telephony._load("d9"))
		self.assertIsNone(telephony._by_call_log("CL-1"))


class EndpointGatingTests(unittest.TestCase):
	def test_all_session_only(self):
		for fn in (telephony.lines, telephony.dial, telephony.active_calls, telephony.join, telephony.set_mode, telephony.inbox,
		           telephony.live_one, telephony.history, telephony.send_text, telephony.hangup, telephony.hold,
		           telephony.invite, telephony.transfer, telephony.lookup, telephony.link_lead,
		           telephony.get_phone_settings, telephony.save_phone_settings):
			self.assertTrue(fn._whitelisted, fn.__name__)
			self.assertFalse(fn._allow_guest, fn.__name__)

	def test_join_rejects_bad_mode_and_missing_call(self):
		shim._cache.hashes.clear()
		with self.assertRaises(shim.ValidationError):
			telephony.join("CL-x", "listen")
		with self.assertRaises(shim.ValidationError):
			telephony.join("CL-x", "monitor")

	def test_history_empty_for_bad_number(self):
		self.assertEqual(telephony.history("12"), [])


class WebhookRoutingTests(unittest.TestCase):
	"""Internal legs never create a CRM Call Log; the external one does."""

	def setUp(self):
		shim.conf["telnyx_public_key"] = "k"
		shim.db.doctypes = {"CRM Call Log"}
		shim._cache.hashes.clear()
		from crm.integrations.telnyx import webhook

		self.webhook = webhook
		self.webhook._verify = lambda raw: True
		shim.request = mock.MagicMock()
		shim.request.headers = {}
		shim.get_doc = mock.MagicMock()

	def _event(self, event, payload):
		shim.request.get_data.return_value = json.dumps({"data": {"event_type": event, "payload": payload}}).encode()
		return self.webhook.voice()

	def test_internal_leg_is_not_logged(self):
		cs = desk.encode_client_state(kind="ring_leg", desk="none", user="exe@x.com")
		out = self._event("call.initiated", {"call_control_id": "c1", "call_session_id": "s1", "client_state": cs, "direction": "outgoing"})
		self.assertEqual(out, {"ok": True, "leg": "ring_leg"})
		shim.get_doc.assert_not_called()

	def test_supervisor_answer_joins_with_role_and_plays_rep_only_tone(self):
		from crm.integrations.telnyx import api as telnyx_api

		state = desk.new_state("d5", "outbound", "+1line", rep="exe@x.com")
		state.update(conference_id="conf5", rep_leg="rep5", peer_leg="peer5", state="active", call_log="CL-5")
		telephony._save(state)
		calls = []
		telnyx_api.conference_command = lambda conf, action, body=None: calls.append((conf, action, body)) or {}
		cs = desk.encode_client_state(kind="supervisor_leg", desk="d5", user="dennis@x.com", mode="whisper")
		self._event("call.answered", {"call_control_id": "sup5", "client_state": cs, "direction": "outgoing"})
		self.assertEqual(calls[0], ("conf5", "join", {"call_control_id": "sup5", "beep_enabled": "never", "supervisor_role": "whisper", "whisper_call_control_ids": ["rep5"]}))
		self.assertEqual(calls[1][1], "speak")
		self.assertEqual(calls[1][2]["call_control_ids"], ["rep5"], "tone goes to the rep leg only")
		self.assertEqual(telephony._load("d5")["supervisors"]["sup5"], {"user": "dennis@x.com", "mode": "whisper", "joined": True})

	def test_ring_race_second_answer_hung_up(self):
		from crm.integrations.telnyx import api as telnyx_api

		state = desk.new_state("d6", "inbound", "+1line", frm="+1caller")
		state.update(caller_leg="caller6", call_log="CL-6", ring_legs={"r1": {"user": "exe@x.com", "via": "softphone"}, "r2": {"user": "german@x.com", "via": "softphone"}})
		telephony._save(state)
		commands = []
		telnyx_api.command = lambda ccid, action, body=None: commands.append((ccid, action)) or {}
		telnyx_api.create_conference = lambda body: {"id": "conf6"}
		telnyx_api.conference_command = lambda *a, **k: {}
		self._event("call.answered", {"call_control_id": "r1", "client_state": desk.encode_client_state(kind="ring_leg", desk="d6", user="exe@x.com")})
		self.assertIn(("caller6", "answer"), commands)
		self.assertIn(("r2", "hangup"), commands, "the losing ring leg is hung up")
		self.assertIn(("caller6", "record_start"), commands, "recording defaults on")
		after = telephony._load("d6")
		self.assertEqual(after["answered_by"], "exe@x.com")
		self.assertEqual(after["conference_id"], "conf6")
		commands.clear()
		self._event("call.answered", {"call_control_id": "r2", "client_state": desk.encode_client_state(kind="ring_leg", desk="d6", user="german@x.com")})
		self.assertEqual(commands, [("r2", "hangup")], "a late answer is just hung up")


class HistoryShapeTests(unittest.TestCase):
	def test_peer_picks_the_number_that_is_not_ours(self):
		ours = {"6125550100"}
		self.assertEqual(telephony._history_peer("+16125550100", "+16125559999", ours, inbound=False), "+16125559999")
		self.assertEqual(telephony._history_peer("+16125559999", "+16125550100", ours, inbound=True), "+16125559999")

	def test_history_requires_ten_digits_when_a_number_is_given(self):
		self.assertEqual(telephony.history("nope"), [])

	def test_decline_exists(self):
		self.assertTrue(callable(telephony.decline))


if __name__ == "__main__":
	unittest.main()
