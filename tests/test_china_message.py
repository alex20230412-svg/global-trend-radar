"""The separate China message is sent silently after the main brief and never changes its result."""

from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from radar import live
from radar.pipeline import china_parts
from radar.storage import json_bytes


class MemoryStore:
    def __init__(self, files=None):
        self.files = files or {}

    def read(self, path):
        return self.files.get(path)

    def publish(self, files, message):
        self.files.update(files)


class ChinaMessageTests(unittest.TestCase):
    report_id = "daily-2026-11-27"
    path = "reports/2026/11/27/daily-2026-11-27.json"

    def run_send(self, store, status="SENT", sender=None):
        calls = []

        def fake_send(report_id, parts, telegram, load, save, **options):
            calls.append((report_id, parts, options))
            if sender:
                return sender()
            return "SENT"

        output = StringIO()
        with patch.object(live, "send_parts", fake_send), redirect_stdout(output):
            live._send_china_message(store, self.report_id, status, telegram=object())
        return calls, output.getvalue()

    def test_sent_silently_with_its_own_delivery_id(self):
        store = MemoryStore({self.path: json_bytes({"parts": ["main"], "china_parts": ["china one"]})})
        calls, output = self.run_send(store)
        self.assertEqual([("daily-2026-11-27-china", ["china one"],
                           {"retry_rate_limit": False, "silent": True})], calls)
        self.assertEqual("china status=ok sent=SENT\n", output)

    def test_skipped_when_main_undelivered_or_nothing_to_send(self):
        store = MemoryStore({self.path: json_bytes({"parts": ["main"], "china_parts": ["china one"]})})
        calls, output = self.run_send(store, status="UNKNOWN")
        self.assertEqual([], calls)
        self.assertIn("status=main_not_sent", output)
        for payload in ({"parts": ["main"]}, {"parts": ["main"], "china_parts": "not a list"}):
            calls, output = self.run_send(MemoryStore({self.path: json_bytes(payload)}))
            self.assertEqual([], calls)
            self.assertIn("status=empty", output)

    def test_errors_are_reported_as_codes(self):
        store = MemoryStore({self.path: json_bytes({"parts": ["main"], "china_parts": ["china one"]})})

        def boom():
            raise RuntimeError("private detail")

        _calls, output = self.run_send(store, sender=boom)
        self.assertEqual("china status=error_RuntimeError sent=UNKNOWN\n", output)
        self.assertNotIn("private detail", output)

    def test_reads_saved_parts_only(self):
        self.assertEqual([], china_parts(MemoryStore(), self.report_id))
        store = MemoryStore({self.path: json_bytes({"china_parts": ["a", "b"]})})
        self.assertEqual(["a", "b"], china_parts(store, self.report_id))


if __name__ == "__main__":
    unittest.main()
