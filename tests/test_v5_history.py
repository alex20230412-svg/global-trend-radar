"""Delivered-only novelty and a redacted, optional PAT expiry reminder."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from io import StringIO
import unittest
from unittest.mock import patch

import httpx

from radar import live
from radar.expiry import EXPIRATION_HEADER, token_expiry_notice
from radar.history import previous_brief_keys, read_daily_entries
from radar.layout import entry_key
from radar.storage import DATA_REPO, GITHUB_API_ROOT, json_bytes


class MemoryStore:
    def __init__(self):
        self.files = {}

    def read(self, path):
        return self.files.get(path)

    def record(self, day, payload, *, state="SENT", prefix="daily"):
        report_id = f"{prefix}-{day.isoformat()}"
        self.files[f"reports/{day:%Y/%m/%d}/{report_id}.json"] = json_bytes(payload)
        self.files[f"deliveries/{report_id}.json"] = json_bytes({"parts": [{"delivery_state": state}]})


class HistoryTests(unittest.TestCase):
    def test_exact_lookback_counts_delivered_daily_reports_only(self):
        today = date(2026, 11, 28)
        store = MemoryStore()
        for age, state, prefix in ((0, "SENT", "daily"), (1, "UNKNOWN", "daily"),
                                   (2, "SENT", "preview-0800"), (6, "CONFIRMED", "daily"),
                                   (7, "SENT", "daily"), (8, "SENT", "daily")):
            row = {"key": f"topic:synthetic-{age}", "section": "malaysia", "title": f"Sample {age}"}
            store.record(today - timedelta(days=age), {"parts": ["valid"], "brief_entries": [row]},
                         state=state, prefix=prefix)
        self.assertEqual({"topic:synthetic-6", "topic:synthetic-7"}, previous_brief_keys(store, today))
        self.assertIsNone(read_daily_entries(store, today - timedelta(days=1)))

    def test_legacy_only_counts_links_present_in_delivered_parts(self):
        today = date(2026, 11, 28)
        yesterday = today - timedelta(days=1)
        store = MemoryStore()
        url = "https://example.org/shown"
        store.record(yesterday, {
            "parts": [f'Old <a href="{url}">link</a>'],
            "ranking": {"malaysia": [
                {"title": "A cited original", "url": "https://example.org/trend", "context": {"url": url}},
                {"title": "A ranking candidate only", "url": "https://example.org/not-shown"},
            ]},
        })
        self.assertIsNone(read_daily_entries(store, yesterday))
        self.assertEqual({entry_key("A cited original")}, previous_brief_keys(store, today))


class NoHistoryTests(unittest.TestCase):
    def test_no_delivered_brief_means_no_comparison(self):
        today = date(2026, 11, 28)
        store = MemoryStore()
        self.assertIsNone(previous_brief_keys(store, today))
        store.record(today - timedelta(days=1), {"parts": ["valid"], "brief_entries": []}, prefix="preview-0800")
        self.assertIsNone(previous_brief_keys(store, today))
        store.record(today - timedelta(days=2), {"parts": ["valid"], "brief_entries": []})
        self.assertEqual(set(), previous_brief_keys(store, today))


class ExpiryTests(unittest.TestCase):
    now = datetime(2026, 11, 27, 0, tzinfo=timezone.utc)
    token = "synthetic-private-key-probe"

    def probe(self, status, header=None):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(status, headers={EXPIRATION_HEADER: header} if header else {},
                                  content=b"synthetic response body")

        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            result = token_expiry_notice(self.token, self.now, client=client)
        [request] = requests
        self.assertEqual(request.method, "GET")
        self.assertEqual(str(request.url), f"{GITHUB_API_ROOT}/repos/{DATA_REPO}")
        self.assertEqual(request.headers["Authorization"], f"Bearer {self.token}")
        return result

    def test_threshold_and_absent_or_invalid_header(self):
        self.assertEqual(self.probe(200, "2026-12-12 00:00:00 UTC"), ("ok", None))
        self.assertEqual(self.probe(200, "2026-12-11 00:00:00 UTC"), (
            "expiring", "⚠️ 私库钥匙 14 天后到期（2026-12-11），请到 GitHub 更新 DATA_REPO_TOKEN",
        ))
        for header in ("2026-12-11 00:00:00 +0000", "2026-12-11 08:00:00 +08:00", "2026-12-11T00:00:00Z"):
            self.assertEqual(self.probe(200, header)[0], "expiring", header)
        self.assertEqual(self.probe(200), ("missing_header", None))
        self.assertEqual(self.probe(200, "invalid"), ("invalid_header", None))

    def test_failure_logs_fixed_status_only(self):
        self.assertEqual(self.probe(403), ("http_403", None))

        def fail(request):
            raise httpx.ReadTimeout(f"private diagnostic {self.token}", request=request)

        with httpx.Client(transport=httpx.MockTransport(fail)) as client:
            code, notice = token_expiry_notice(self.token, self.now, client=client)
        self.assertEqual((code, notice), ("request_failed", None))
        stdout, stderr = StringIO(), StringIO()
        with (patch.object(live, "token_expiry_notice", return_value=(code, notice)),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            self.assertIsNone(live._token_notice({"DATA_REPO_TOKEN": self.token}, self.now))
        self.assertEqual(stdout.getvalue(), "token_expiry status=request_failed\n")
        self.assertEqual(stderr.getvalue(), "")
