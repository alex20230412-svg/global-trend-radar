"""Offline tests for browser-and-Telegram pairing and the activation gate."""

import json
import unittest

from radar.binding import (
    ACKNOWLEDGEMENT, BINDING_KEY, BINDING_MAX_AGE, START_MAX_AGE, bind_chat, bound_chat_id, confirm_bind,
)
from radar.delivery import DeliveryError


TOKEN = "1234567:" + "A" * 25
ROTATED_TOKEN = "1234567:" + "B" * 25
OTHER_TOKEN = "7654321:" + "C" * 25
FIRST = 901
SECOND = 902
NOW = 1_801_234_000


def start(chat_id=FIRST, at=NOW, *, text="/start", chat_type="private", sender_id=None, bot=False, **extra):
    return {"message": {"text": text, "date": at, "chat": {"type": chat_type, "id": chat_id},
                        "from": {"id": chat_id if sender_id is None else sender_id, "is_bot": bot},
                        **extra}}


class MemoryStore:
    def __init__(self):
        self.files = {}

    def read(self, key):
        return self.files.get(key)

    def publish(self, files, message):
        self.files.update(files)

    def state(self):
        return json.loads(self.files[BINDING_KEY])


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.calls = []
        self.updates = [start()]
        self.now = NOW
        self.send_response = None

    def request(self, token, method, payload):
        self.calls.append((method, payload))
        if method == "getUpdates":
            self.assertNotIn("offset", payload)
            return 200, {"ok": True, "result": self.updates}
        candidate = self.store.state()
        chat_id = payload["chat_id"]
        chat = {"type": "private", "id": chat_id}
        self.assertEqual(candidate["chat_id"], chat_id)
        self.assertEqual(candidate["state"], "PENDING")
        if method == "getChat":
            return 200, {"ok": True, "result": chat}
        self.assertEqual(method, "sendMessage")
        self.assertFalse(payload["allow_paid_broadcast"])
        self.assertEqual(payload["text"].split("\n\n", 1)[1], ACKNOWLEDGEMENT)
        return self.send_response or (200, {"ok": True, "result": {"chat": chat, "message_id": 44}})

    def arm(self, token=TOKEN):
        return bind_chat(self.store, token, request=self.request, now=lambda: self.now)

    def activate(self, dispatched_at=None, token=TOKEN):
        return confirm_bind(self.store, token, requested_at=self.now if dispatched_at is None else dispatched_at,
                            now=lambda: self.now)

    def test_generic_ack_remains_pending_until_explicit_owner_confirmation(self):
        self.assertIsNone(bound_chat_id(self.store, TOKEN))
        self.assertEqual(self.arm(), "ACK_SENT")
        self.assertIsNone(bound_chat_id(self.store, TOKEN))
        self.assertEqual(self.store.state()["state"], "PENDING")
        self.assertEqual([method for method, _ in self.calls], ["getUpdates", "getChat", "sendMessage"])
        self.assertEqual(self.activate(), "BOUND")
        self.assertEqual(bound_chat_id(self.store, TOKEN), str(FIRST))
        self.assertEqual(self.activate(), "ALREADY_BOUND")
        self.assertEqual(self.arm(), "ALREADY_BOUND")
        self.assertEqual(len(self.calls), 3)
        for contents in self.store.files.values():
            self.assertNotIn(TOKEN.encode(), contents)
            self.assertNotIn(b"/start", contents)

    def test_ambiguous_distinct_private_senders_fail_closed(self):
        self.updates = [start(), start(SECOND)]
        with self.assertRaisesRegex(DeliveryError, "binding_ambiguous_start"):
            self.arm()
        self.assertEqual(self.store.files, {})
        self.assertEqual([method for method, _ in self.calls], ["getUpdates"])

    def test_duplicate_starts_count_as_one_candidate(self):
        self.updates = [start(), start()]
        self.assertEqual(self.arm(), "ACK_SENT")
        self.assertEqual(self.store.state()["chat_id"], FIRST)

    def test_filters_nonprivate_forged_bot_forwarded_old_and_future_updates(self):
        self.updates = [
            {}, start(chat_type="group"), start(sender_id=SECOND), start(bot=True),
            start(text="/start other"), start(at=NOW - START_MAX_AGE - 1), start(at=NOW + 20),
            start(forward_origin={}), start(sender_chat={}), start(chat_id=-12),
        ]
        with self.assertRaisesRegex(DeliveryError, "binding_private_start_required"):
            self.arm()
        self.assertEqual(self.store.files, {})
        self.assertEqual([method for method, _ in self.calls], ["getUpdates"])

    def test_full_update_batch_could_hide_another_sender(self):
        self.updates = [start()] * 100
        with self.assertRaisesRegex(DeliveryError, "binding_updates_incomplete"):
            self.arm()
        self.assertEqual(self.store.files, {})

    def test_retry_keeps_recipient_and_does_not_duplicate_acknowledgement(self):
        self.assertEqual(self.arm(), "ACK_SENT")
        original = self.store.state()
        self.updates = [start(SECOND)]
        self.assertEqual(self.arm(), "ACK_SENT")
        self.assertEqual(self.store.state(), original)
        self.assertEqual(len(self.calls), 3)

    def test_unknown_ack_blocks_activation_and_resend(self):
        self.send_response = (0, None)
        self.assertEqual(self.arm(), "UNKNOWN")
        with self.assertRaisesRegex(DeliveryError, "binding_ack_unconfirmed"):
            self.activate()
        self.assertIsNone(bound_chat_id(self.store, TOKEN))
        self.assertEqual(self.arm(), "UNKNOWN")
        self.assertEqual(len(self.calls), 3)

    def test_stale_pending_requires_a_fresh_start_and_fresh_confirm_run(self):
        self.assertEqual(self.arm(), "ACK_SENT")
        self.now += BINDING_MAX_AGE + 5
        with self.assertRaisesRegex(DeliveryError, "binding_confirmation_expired"):
            self.activate()
        with self.assertRaisesRegex(DeliveryError, "binding_private_start_required"):
            self.arm()
        self.updates = [start(SECOND, at=self.now)]
        self.assertEqual(self.arm(), "ACK_SENT")
        with self.assertRaisesRegex(DeliveryError, "binding_ack_unconfirmed"):
            self.activate(dispatched_at=self.now - 1)
        self.assertEqual(self.activate(), "BOUND")
        self.assertEqual(bound_chat_id(self.store, TOKEN), str(SECOND))

    def test_rotating_same_bot_preserves_active_binding_and_other_bot_is_rejected(self):
        self.assertEqual(self.arm(), "ACK_SENT")
        self.assertEqual(self.activate(), "BOUND")
        self.assertEqual(bound_chat_id(self.store, ROTATED_TOKEN), str(FIRST))
        with self.assertRaisesRegex(DeliveryError, "binding_bot_changed"):
            bound_chat_id(self.store, OTHER_TOKEN)

    def test_early_confirmation_in_same_second_as_ack_is_rejected(self):
        self.now = NOW + 0.5
        self.assertEqual(self.arm(), "ACK_SENT")
        with self.assertRaisesRegex(DeliveryError, "binding_ack_unconfirmed"):
            self.activate(dispatched_at=NOW)
        self.now = NOW + 1
        self.assertEqual(self.activate(), "BOUND")

    def test_corrupted_ack_fingerprint_cannot_activate(self):
        self.assertEqual(self.arm(), "ACK_SENT")
        key = f"deliveries/{self.store.state()['ack_id']}.json"
        ledger = json.loads(self.store.files[key])
        ledger["destination_fingerprint"] = "0" * 64
        self.store.files[key] = json.dumps(ledger).encode()
        with self.assertRaisesRegex(DeliveryError, "binding_ack_unconfirmed"):
            self.activate()
        self.assertIsNone(bound_chat_id(self.store, TOKEN))


if __name__ == "__main__":
    unittest.main()
