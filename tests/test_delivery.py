"""Offline tests. All Telegram traffic is mocked."""

from copy import deepcopy
from html import escape
import http.client
import json
import unittest
from unittest.mock import Mock, patch

from radar.delivery import (
    DeliveryError, TelegramClient, _message_text, reconcile_delivery, send_parts,
    split_parts, telegram_request,
)
from tools.get_chat_id import private_probe_ids


TOKEN = "1:" + "mock-token-characters" * 2
CHAT = 2 ** 36
REPORT = "daily-2030-01-02"
PARTS = ["<b>测试甲</b>", "<b>测试乙</b>"]


def destination(chat_id=CHAT, chat_type="private"):
    return {"id": chat_id, "type": chat_type}


def verified(chat_id=CHAT, chat_type="private"):
    return 200, {"ok": True, "result": destination(chat_id, chat_type)}


def sent(message_id=1, chat_id=CHAT):
    return 200, {"ok": True, "result": {"message_id": message_id, "chat": destination(chat_id)}}


def rate_limit(delay):
    return 429, {"ok": False, "error_code": 429, "parameters": {"retry_after": delay}}


class Clock:
    def __init__(self):
        self.timestamp = 1000.0
        self.waits = []

    def now(self):
        return self.timestamp

    def sleep(self, delay):
        self.timestamp += delay
        self.waits.append(delay)


class Ledger:
    def __init__(self):
        self.documents = {}
        self.snapshots = []
        self.reject_state = None

    def load(self, report_id):
        return deepcopy(self.documents.get(report_id))

    def save(self, report_id, ledger):
        states = [row["delivery_state"] for row in ledger["parts"]]
        if self.reject_state and self.reject_state in states:
            raise OSError("synthetic store failure")
        self.documents[report_id] = deepcopy(ledger)
        self.snapshots.append(states)

    @property
    def rows(self):
        return self.documents[REPORT]["parts"]


class SplitTest(unittest.TestCase):
    def test_preserves_whole_entries_bounds_utf16_and_escapes(self):
        labels = ["华语😀&<>\"'" * 245 + str(index) for index in range(3)]
        full_blocks = [
            (f'<a href="https://example.test/a?x=1&amp;y=2">{escape(label)}</a>', label)
            for label in labels
        ]
        parts = split_parts(full_blocks, label=REPORT)
        self.assertEqual(len(parts), 3)
        for index, (part, label) in enumerate(zip(parts, labels, strict=True), 1):
            self.assertEqual(_message_text(part), f"{REPORT} · 分段 {index}/3\n\n{label}")
            self.assertLessEqual(len(_message_text(part).encode("utf-16-le")) // 2, 4096)
            self.assertEqual(part.count("<a "), 1)
            self.assertEqual(part.count("</a>"), 1)
            self.assertNotIn('<>\\"', part)

    def test_budget_counts_visible_not_escaped_length(self):
        text = "<" * 3000
        parts = split_parts([(escape(text), text)], label=REPORT)
        self.assertEqual(len(parts), 1)
        self.assertGreater(len(parts[0]), 4096)
        self.assertTrue(_message_text(parts[0]).endswith(text))

    def test_combines_short_blocks_and_escapes_label(self):
        parts = split_parts([("<b>一</b>", "一"), ("二", "二")], label="日期<甲>")
        self.assertEqual(_message_text(parts[0]), "日期<甲> · 分段 1/1\n\n一\n\n二")

    def test_rejects_unsupported_markup_and_wrong_length(self):
        for fragment, plain in [
            ("<script>evil</script>", "evil"),
            ('<a href="javascript:evil">x</a>', "x"),
            ('<a href="https://user@example.test">x</a>', "x"),
            ('<a href="https://example.test">x', "x"),
            ("<b>not the plain text</b>", "wrong"),
            ("😀" * 2049, "😀" * 2049),
        ]:
            with self.subTest(fragment=fragment[:80]), self.assertRaises(DeliveryError):
                split_parts([(fragment, plain)])


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.ledger = Ledger()

    def client(self, *responses, chat_id=CHAT):
        request = Mock(side_effect=responses)
        return TelegramClient(TOKEN, str(chat_id), request=request), request

    def deliver(self, telegram, parts=PARTS):
        return send_parts(REPORT, parts, telegram, self.ledger.load, self.ledger.save,
                          now=self.clock.now, sleep=self.clock.sleep)

    def reconcile(self, part, **kwargs):
        reconcile_delivery(
            REPORT, part, self.ledger.rows[part - 1]["payload_hash"],
            self.ledger.load, self.ledger.save, now=self.clock.now, **kwargs,
        )

    def test_success_persists_intent_before_each_send_and_skips_rerun(self):
        events = []

        def request(token, method, payload):
            self.assertEqual(token, TOKEN)
            self.assertEqual(payload["chat_id"], CHAT)
            if method == "getChat":
                return verified()
            last_states = self.ledger.snapshots[-1]
            events.append(last_states)
            self.assertEqual(payload["parse_mode"], "HTML")
            self.assertTrue(payload["link_preview_options"]["is_disabled"])
            self.assertFalse(payload["allow_paid_broadcast"])
            return sent(len(events))

        self.assertEqual(self.deliver(TelegramClient(TOKEN, str(CHAT), request=request)), "SENT")
        self.assertEqual(events, [["SENDING", "PENDING"], ["SENT", "SENDING"]])
        self.assertEqual(self.ledger.snapshots[-1], ["SENT", "SENT"])
        self.assertEqual([row["message_id"] for row in self.ledger.rows], [1, 2])
        self.assertEqual([row["attempts"] for row in self.ledger.rows], [1, 1])
        self.assertEqual(len(self.clock.waits), 1)
        self.assertAlmostEqual(self.clock.waits[0], 1.05)
        second, mocked_request = self.client()
        self.assertEqual(self.deliver(second), "SENT")
        mocked_request.assert_not_called()
        self.assertNotIn(TOKEN, json.dumps(self.ledger.documents))
        self.assertNotIn(str(CHAT), json.dumps(self.ledger.documents))

    def test_part_one_acknowledged_then_timeout_halts_without_resend(self):
        part = "本地模拟数据😀"
        telegram, request = self.client(verified(), sent(), TimeoutError(f"{TOKEN} {part}"))
        self.assertEqual(self.deliver(telegram, [*PARTS, part]), "UNKNOWN")
        self.assertEqual(request.call_count, 3)
        self.assertEqual(self.ledger.snapshots[-1], ["SENT", "UNKNOWN", "PENDING"])
        self.assertIsNone(self.ledger.rows[1]["message_id"])
        self.assertEqual(self.ledger.rows[1]["failure_code"], "telegram_outcome_unconfirmed")
        self.assertNotIn(TOKEN, json.dumps(self.ledger.documents))
        self.assertNotIn(part, json.dumps(self.ledger.documents, ensure_ascii=False))
        telegram, request = self.client()
        self.assertEqual(self.deliver(telegram, [*PARTS, part]), "UNKNOWN")
        request.assert_not_called()

    def test_interrupted_ack_persistence_does_not_repeat_send(self):
        self.ledger.reject_state = "SENT"
        telegram, request = self.client(verified(), sent())
        with self.assertRaisesRegex(OSError, "synthetic store failure"):
            self.deliver(telegram)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(self.ledger.snapshots[-1], ["SENDING", "PENDING"])
        self.ledger.reject_state = None
        telegram, request = self.client()
        self.assertEqual(self.deliver(telegram), "UNKNOWN")
        request.assert_not_called()
        self.assertEqual(self.ledger.rows[0]["failure_code"], "interrupted_send")

    def test_no_send_if_intent_cannot_be_persisted(self):
        self.ledger.reject_state = "SENDING"
        telegram, request = self.client(verified())
        with self.assertRaises(OSError):
            self.deliver(telegram)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[1], "getChat")

    def test_owner_confirmed_received_is_not_forged_api_receipt(self):
        telegram, _ = self.client(verified(), TimeoutError())
        self.assertEqual(self.deliver(telegram), "UNKNOWN")
        self.reconcile(1, confirmed_sent=True)
        telegram, request = self.client(verified(), sent(42))
        self.assertEqual(self.deliver(telegram), "CONFIRMED")
        self.assertEqual(request.call_args.args[2]["text"], PARTS[1])
        self.assertEqual(self.ledger.rows[0]["delivery_state"], "CONFIRMED")
        self.assertIsNone(self.ledger.rows[0]["message_id"])
        self.assertEqual(self.ledger.rows[1]["message_id"], 42)

    def test_owner_confirmed_unsent_allows_explicit_retry(self):
        telegram, _ = self.client(verified(), TimeoutError())
        self.assertEqual(self.deliver(telegram), "UNKNOWN")
        self.reconcile(1, confirmed_unsent=True)
        telegram, _ = self.client(verified(), sent(), sent(2))
        self.assertEqual(self.deliver(telegram), "SENT")
        self.assertEqual(self.ledger.rows[0]["attempts"], 2)
        self.assertEqual(self.ledger.rows[0]["owner_confirmation"], "not_received")

    def test_reconciliation_requires_exact_hash_and_ambiguous_state(self):
        telegram, _ = self.client(verified(), TimeoutError())
        self.assertEqual(self.deliver(telegram), "UNKNOWN")
        with self.assertRaisesRegex(DeliveryError, "delivery_confirmation_mismatch"):
            reconcile_delivery(REPORT, 1, "0" * 64, self.ledger.load, self.ledger.save, confirmed_sent=True)
        with self.assertRaisesRegex(DeliveryError, "delivery_confirmation_mismatch"):
            self.reconcile(2, confirmed_unsent=True)
        with self.assertRaisesRegex(DeliveryError, "invalid_delivery_confirmation"):
            self.reconcile(1, confirmed_sent=True, confirmed_unsent=True)

    def test_rate_limit_short_wait_after_durable_record(self):
        telegram, _ = self.client(verified(), rate_limit(3), sent(7), sent(8))
        self.assertEqual(self.deliver(telegram), "SENT")
        self.assertIn(["RATE_LIMITED", "PENDING"], self.ledger.snapshots)
        self.assertEqual(self.clock.waits[0], 3)
        self.assertEqual(self.ledger.rows[0]["attempts"], 2)

    def test_rate_limit_long_wait_carried_across_reruns(self):
        telegram, _ = self.client(verified(), rate_limit(90))
        self.assertEqual(self.deliver(telegram), "RATE_LIMITED")
        self.assertEqual(self.ledger.rows[0]["retry_at"], 1090)
        telegram, request = self.client()
        self.assertEqual(self.deliver(telegram), "RATE_LIMITED")
        request.assert_not_called()
        self.clock.timestamp += 90
        telegram, request = self.client(verified(), sent(), sent(2))
        self.assertEqual(self.deliver(telegram), "SENT")
        self.assertEqual(request.call_count, 3)

    def test_rate_limit_preflight_has_no_send_intent(self):
        telegram, request = self.client(rate_limit(120))
        self.assertEqual(self.deliver(telegram), "RATE_LIMITED")
        self.assertEqual(request.call_args.args[1], "getChat")
        self.assertEqual(self.ledger.rows[0]["attempts"], 0)
        self.assertEqual(self.ledger.rows[0]["retry_at"], 1120)

    def test_nonprivate_wrong_chat_and_nonnumeric_chat_never_send(self):
        for response in [verified(chat_type="channel"), verified(chat_id=CHAT + 1)]:
            telegram, request = self.client(response)
            self.assertEqual(self.deliver(telegram), "REJECTED")
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[1], "getChat")
        self.assertEqual(self.ledger.documents, {})
        for invalid in ["@" + "channel", "-100", "0", "01", "1\n", str(2 ** 52)]:
            with self.assertRaisesRegex(DeliveryError, "invalid_private_chat_id"):
                TelegramClient(TOKEN, invalid, request=Mock())

    def test_api_rejection_resumes_only_the_unsent_parts(self):
        telegram, _ = self.client(verified(), sent(), (403, {"ok": False, "error_code": 403}))
        self.assertEqual(self.deliver(telegram), "REJECTED")
        self.assertEqual(self.ledger.snapshots[-1], ["SENT", "REJECTED"])
        telegram, request = self.client(verified(), sent(2))
        self.assertEqual(self.deliver(telegram), "SENT")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[2]["text"], PARTS[1])

    def test_ambiguous_responses_remain_unknown(self):
        for bad in [
            (502, {"ok": False, "error_code": 502}),
            (200, None), sent(chat_id=CHAT + 13), sent(message_id=True), (429, None),
        ]:
            with self.subTest(bad=bad):
                self.ledger = Ledger()
                telegram, _ = self.client(verified(), bad)
                self.assertEqual(self.deliver(telegram), "UNKNOWN")
                self.assertIsNone(self.ledger.rows[0]["message_id"])

    def test_frozen_payload_and_destination_cannot_change(self):
        telegram, _ = self.client(verified(), TimeoutError())
        self.assertEqual(self.deliver(telegram), "UNKNOWN")
        telegram, request = self.client(chat_id=CHAT + 1)
        with self.assertRaisesRegex(DeliveryError, "delivery_destination_changed"):
            self.deliver(telegram)
        request.assert_not_called()
        telegram, request = self.client()
        with self.assertRaisesRegex(DeliveryError, "delivery_payload_changed"):
            self.deliver(telegram, ["changed", PARTS[1]])
        request.assert_not_called()

    def test_corrupted_ledger_never_restores_pending(self):
        self.ledger.documents[REPORT] = {}
        telegram, request = self.client()
        with self.assertRaisesRegex(DeliveryError, "invalid_delivery_ledger"):
            self.deliver(telegram)
        request.assert_not_called()


class TransportTest(unittest.TestCase):
    def test_uses_fixed_host_no_redirect_and_bounded_body(self):
        with patch("radar.delivery.http.client.HTTPSConnection") as build_connection:
            connection = build_connection.return_value
            response = connection.getresponse.return_value.__enter__.return_value
            response.read.return_value = b"x" * (128 * 1024 + 1)
            response.status = 302
            self.assertEqual(telegram_request(TOKEN, "getChat", {}), (302, None))
        build_connection.assert_called_once_with("api.telegram.org", timeout=8)
        response.read.assert_called_once_with(128 * 1024 + 1)
        self.assertEqual(connection.request.call_count, 1)
        connection.close.assert_called_once()

    def test_network_failure_returns_no_token_or_exception_message(self):
        with patch("radar.delivery.http.client.HTTPSConnection") as build_connection:
            build_connection.return_value.request.side_effect = http.client.HTTPException(TOKEN)
            self.assertEqual(telegram_request(TOKEN, "getChat", {}), (0, None))

    def test_local_id_helper_accepts_only_unique_matching_private_self_sender(self):
        probe = "GTR-PROBE-synthetic"
        messages = [
            {"chat": destination(), "text": probe, "from": {"id": CHAT, "is_bot": False}},
            {"chat": destination(), "text": probe, "from": {"id": CHAT + 1, "is_bot": False}},
            {"chat": destination(chat_type="group"), "text": probe, "from": {"id": CHAT, "is_bot": False}},
            {"chat": destination(CHAT + 9), "text": "not probe", "from": {"id": CHAT + 9, "is_bot": False}},
            {"chat": destination(CHAT + 2), "text": probe, "from": {"id": CHAT + 2, "is_bot": True}},
        ]
        self.assertEqual(private_probe_ids([{"message": msg} for msg in messages], probe), {CHAT})


if __name__ == "__main__":
    unittest.main()
