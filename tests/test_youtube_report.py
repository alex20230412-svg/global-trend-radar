"""Offline integration tests for the transient YouTube delivery."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import gzip
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
import yaml

from radar import live, pipeline, storage, youtube
from radar.brief import GeminiWriter
from radar.delivery import TelegramClient
from radar.sources import Source


NOW = datetime(2026, 11, 27, 0, 37, tzinfo=timezone.utc)
REPORT_ID = "smoke-2026-11-27"
YOUTUBE_LEDGER = f"deliveries/{REPORT_ID}-youtube.json"
MAIN_LEDGER = f"deliveries/{REPORT_ID}.json"
VIDEO_ID = "ZZqYY____01"
VIDEO_TITLE = "示例视频 A YT_SYNTHETIC_TITLE"
CHANNEL_TITLE = "示例频道甲 YT_SYNTHETIC_CHANNEL"
YOUTUBE_KEY = "mock_youtube_key_for_issue28_test"
GEMINI_KEY = "mock_gemini_key_for_issue28_test"
BODY_SENTINEL = "YT_SYNTHETIC_RESPONSE_BODY"
TOKEN = "123456789:" + "a" * 32
CHAT = {"id": 812345678, "type": "private"}
MAIN_TOPIC = "示例马来西亚科技设备"
SENSITIVE_VALUES = (VIDEO_ID, VIDEO_TITLE, CHANNEL_TITLE, YOUTUBE_KEY, BODY_SENTINEL)
YOUTUBE_PAYLOAD = {
    "items": [{
        "id": VIDEO_ID,
        "snippet": {"title": VIDEO_TITLE, "channelTitle": CHANNEL_TITLE, "categoryId": "10"},
        "statistics": {"viewCount": "1234567"},
        "ignored": BODY_SENTINEL,
    }]
}
GEMINI_TEXT = (
    "📅 11月27日 热点早报\n"
    "🔥 马来西亚现在最热门的话题\n"
    "[m1] 示例马来西亚科技设备：这是用于核对安排行为的合成示例。\n"
    "⚠️ 天气\n"
    "本测试使用合成数据，天气和其他栏目均仅用于离线核对原始标题及出处。"
)


class JournalStore:
    size_kib = 1

    def __init__(self):
        self.files = {}
        self.writes = []
        self.fail_publication_state = None

    def read(self, key):
        return self.files.get(key)

    def publish(self, files, message):
        for name, content in files.items():
            if not name.startswith("deliveries/") or not name.endswith("-youtube.json"):
                continue
            state = json.loads(content)["delivery_state"]
            if state == self.fail_publication_state:
                raise storage.PublicationError("git_operation_unconfirmed")
        self.writes.extend(files.items())
        self.files.update(files)


class ReportHarness:
    def __init__(self):
        self.store = JournalStore()
        self.sources = [Source("trends_my", "trends", "MY", "en", "https://example.org/trends",
                               True, "long_term")]
        self.approved = {"trends_my"}
        self.enabled = True
        self.config_error = None
        self.main_status = 200
        self.supplement_status = 200
        self.api_status = 200
        self.api_body = YOUTUBE_PAYLOAD
        self.api_error = None
        self.events = []
        self.messages = []
        self.model_requests = []
        self.aux_send_states = []
        self.fetch_calls = []
        self.run_count = 0
        row = {"title": MAIN_TOPIC, "url": "https://example.org/topic", "content_id": "mock-main-topic",
               "volume_raw": "5K+", "rank": 1, "published_at": NOW.isoformat(), "related": []}
        pipeline.collect_slot(
            self.store, self.sources, self.approved, NOW, "mock-collect", fetch=lambda source: [row],
            clock=lambda: NOW,
        )

    def load_config(self):
        if self.config_error is not None:
            raise self.config_error
        return youtube.YouTubeConfig(self.enabled)

    def call_model(self, request):
        self.events.append("gemini")
        self.model_requests.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": GEMINI_TEXT}]}}]})

    def call_youtube(self, request):
        self.events.append("youtube_fetch")
        if self.api_error is not None:
            raise self.api_error
        return httpx.Response(self.api_status, json=self.api_body)

    def call_telegram(self, token, method, payload):
        if method == "getChat":
            return 200, {"ok": True, "result": CHAT}
        if method != "sendMessage":
            raise AssertionError(f"Unexpected Telegram method {method}")
        self.messages.append(payload)
        is_youtube = VIDEO_ID in payload["text"]
        self.events.append("youtube_send" if is_youtube else "main_send")
        if is_youtube:
            self.aux_send_states.append([
                json.loads(content)["delivery_state"] for name, content in self.store.files.items()
                if name.startswith("deliveries/") and name.endswith("-youtube.json")
            ])
        status = self.supplement_status if is_youtube else self.main_status
        if status == 429:
            return 429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 1}}
        if status == 200:
            return 200, {"ok": True, "result": {"chat": CHAT, "message_id": len(self.messages)}}
        return status, {"ok": False, "error_code": status, "description": BODY_SENTINEL}

    def run_report(self, action="send", *, report_id="", key=YOUTUBE_KEY):
        self.run_count += 1
        output, errors = StringIO(), StringIO()
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "RADAR_STAGE": "b-manual",
               "RADAR_REPORT_ACTION": action, "RADAR_REPORT_ID": report_id,
               "GEMINI_API_KEY": GEMINI_KEY, "YOUTUBE_API_KEY": key}
        writer = GeminiWriter(GEMINI_KEY, transport=httpx.MockTransport(self.call_model),
                              models=("gemini-flash-synthetic",))
        telegram = TelegramClient(TOKEN, str(CHAT["id"]), request=self.call_telegram)
        with httpx.Client(transport=httpx.MockTransport(self.call_youtube), trust_env=False) as client:
            def fetch(config, api_key):
                self.fetch_calls.append((config, api_key))
                return youtube.fetch_youtube(config, api_key, client=client)

            with (patch.object(live, "_telegram", return_value=telegram),
                  patch.object(live, "GeminiWriter", return_value=writer),
                  patch.object(live, "load_youtube_config", side_effect=self.load_config),
                  patch.object(live, "fetch_youtube", side_effect=fetch),
                  redirect_stdout(output), redirect_stderr(errors)):
                code = live._report(self.store, self.sources, self.approved, env, f"mock-report-{self.run_count}",
                                    NOW, NOW, None)
        return code, output.getvalue(), errors.getvalue()


class YouTubeReportTests(unittest.TestCase):
    def assert_status(self, stdout, code, items=0):
        lines = [line for line in stdout.splitlines() if line.startswith("youtube ")]
        self.assertEqual(1, len(lines), stdout)
        self.assertRegex(lines[0], rf"^youtube status={code} items={items} sent=[A-Za-z_]+$")

    def assert_no_youtube_values(self, value):
        for marker in SENSITIVE_VALUES:
            self.assertNotIn(marker, value)

    def test_send_calls_gemini_and_main_then_sends_unarchived_youtube_once(self):
        harness = ReportHarness()
        code, stdout, stderr = harness.run_report()
        self.assertEqual(0, code)
        self.assertEqual(["gemini", "main_send", "youtube_fetch", "youtube_send"], harness.events)
        self.assertEqual([["SENDING"]], harness.aux_send_states)
        main, supplement = harness.messages
        self.assert_no_youtube_values(main["text"])
        for marker in (VIDEO_ID, VIDEO_TITLE, CHANNEL_TITLE):
            self.assertIn(marker, supplement["text"])
        self.assertEqual("HTML", supplement["parse_mode"])
        self.assertEqual({"is_disabled": True}, supplement["link_preview_options"])
        self.assertIn("youtube status=ok items=1 sent=SENT", stdout)
        self.assert_no_youtube_values(stdout + stderr)

        [request] = harness.model_requests
        system = request["systemInstruction"]["parts"][0]["text"]
        prompt = request["contents"][0]["parts"][0]["text"]
        self.assertIn(MAIN_TOPIC, prompt)
        self.assert_no_youtube_values(system + prompt)

        for name, data in harness.store.writes:
            self.assert_no_youtube_values(name)
            content = gzip.decompress(data) if name.endswith(".gz") else data
            self.assert_no_youtube_values(content.decode("utf-8"))
        ledgers = [json.loads(data) for name, data in harness.store.writes if name == YOUTUBE_LEDGER]
        digest = sha256(supplement["text"].encode("utf-8")).hexdigest()
        self.assertEqual([
            {"payload_hash": digest, "delivery_state": "SENDING"},
            {"payload_hash": digest, "delivery_state": "SENT"},
        ], ledgers)
        self.assertEqual({"status": "ok", "items": 1, "sent": "SENT"},
                         json.loads(harness.store.read("runs/mock-report-1-youtube.json")))
        self.assertEqual("SENT", json.loads(harness.store.read(MAIN_LEDGER))["parts"][0]["delivery_state"])

    def test_preview_uses_its_own_delivery_id(self):
        harness = ReportHarness()
        code, stdout, _ = harness.run_report("preview")
        self.assertEqual(0, code)
        self.assert_status(stdout, "ok", items=1)
        self.assertEqual(1, harness.events.count("youtube_send"))
        self.assertIn("deliveries/preview-0837-2026-11-27-youtube.json", harness.store.files)
        self.assertNotIn(YOUTUBE_LEDGER, harness.store.files)

    def test_resume_can_add_youtube_after_an_earlier_no_key_run(self):
        harness = ReportHarness()
        code, stdout, _ = harness.run_report(key="")
        self.assertEqual(0, code)
        self.assert_status(stdout, "no_key")
        self.assertNotIn(YOUTUBE_LEDGER, harness.store.files)
        code, stdout, _ = harness.run_report("resume", report_id=REPORT_ID)
        self.assertEqual(0, code)
        self.assert_status(stdout, "ok", items=1)
        self.assertEqual(["gemini", "main_send", "youtube_fetch", "youtube_send"], harness.events)

    def test_any_existing_attempt_marker_skips_fetch_and_send(self):
        for state in ("SENT", "UNKNOWN", "SENDING", "REJECTED", "RATE_LIMITED", None):
            with self.subTest(state=state):
                harness = ReportHarness()
                original = b"" if state is None else storage.json_bytes({
                    "payload_hash": "a" * 64, "delivery_state": state,
                })
                harness.store.files[YOUTUBE_LEDGER] = original
                code, stdout, _ = harness.run_report()
                self.assertEqual(0, code)
                self.assert_status(stdout, "already_attempted")
                self.assertEqual([], harness.fetch_calls)
                self.assertEqual(["gemini", "main_send"], harness.events)
                self.assertEqual(original, harness.store.read(YOUTUBE_LEDGER))

    def test_main_undelivered_skips_fetch_and_preserves_main_failure(self):
        harness = ReportHarness()
        harness.main_status = 503
        code, stdout, stderr = harness.run_report()
        self.assertEqual(1, code)
        self.assert_status(stdout, "main_not_sent")
        self.assert_no_youtube_values(stdout + stderr)
        self.assertEqual([], harness.fetch_calls)
        self.assertNotIn(YOUTUBE_LEDGER, harness.store.files)
        self.assertEqual("UNKNOWN", json.loads(harness.store.read(MAIN_LEDGER))["parts"][0]["delivery_state"])

    def test_disabled_is_a_no_op_even_when_the_main_report_fails(self):
        harness = ReportHarness()
        harness.enabled = False
        harness.main_status = 503
        code, stdout, stderr = harness.run_report()
        self.assertEqual(1, code)
        self.assert_status(stdout, "disabled")
        self.assertEqual([], harness.fetch_calls)
        self.assertEqual([], [name for name, _ in harness.store.writes if name.endswith("-youtube.json")])

    def test_invalid_config_is_reported_without_fetching(self):
        harness = ReportHarness()
        harness.config_error = ValueError("invalid_youtube_config")
        code, stdout, stderr = harness.run_report()
        self.assertEqual(0, code)
        self.assert_status(stdout, "invalid_config")
        self.assertEqual([], harness.fetch_calls)
        self.assertEqual(1, len(harness.messages))
        self.assertNotIn(YOUTUBE_LEDGER, harness.store.files)

    def test_disabled_or_google_error_leaves_the_main_report_delivered(self):
        for enabled, status, reason, expected, requested in (
            (False, 200, "", "disabled", False),
            (True, 403, "quotaExceeded", "quota_exceeded", True),
            (True, 400, "keyInvalid", "key_invalid", True),
            (True, 403, "accessNotConfigured", "api_not_enabled", True),
        ):
            with self.subTest(expected=expected):
                harness = ReportHarness()
                harness.enabled = enabled
                harness.api_status = status
                harness.api_body = {"error": {"errors": [{"reason": reason}], "message": BODY_SENTINEL}}
                code, stdout, stderr = harness.run_report()
                self.assertEqual(0, code)
                self.assert_status(stdout, expected)
                self.assert_no_youtube_values(stdout + stderr)
                self.assertEqual(requested, "youtube_fetch" in harness.events)
                self.assertEqual(1, len(harness.messages))
                self.assertNotIn(YOUTUBE_LEDGER, harness.store.files)

    def test_rate_limit_or_ambiguous_response_never_retries(self):
        for status, state in ((429, "RATE_LIMITED"), (503, "UNKNOWN")):
            with self.subTest(status=status):
                harness = ReportHarness()
                harness.supplement_status = status
                code, stdout, _ = harness.run_report()
                self.assertEqual(0, code)
                self.assertIn(f"sent={state}", stdout)
                self.assertEqual(1, harness.events.count("youtube_send"))
                self.assertEqual(state, json.loads(harness.store.read(YOUTUBE_LEDGER))["delivery_state"])
                code, stdout, _ = harness.run_report("resume", report_id=REPORT_ID)
                self.assertEqual(0, code)
                self.assert_status(stdout, "already_attempted")
                self.assertEqual(1, harness.events.count("youtube_fetch"))
                self.assertEqual(1, harness.events.count("youtube_send"))

    def test_youtube_network_errors_never_change_the_main_result(self):
        for exception in (httpx.ReadTimeout, httpx.ConnectError):
            with self.subTest(exception=exception):
                harness = ReportHarness()
                harness.api_error = exception(" ".join(SENSITIVE_VALUES))
                code, stdout, stderr = harness.run_report()
                self.assertEqual(0, code)
                self.assert_status(stdout, f"network_{exception.__name__}")
                self.assert_no_youtube_values(stdout + stderr)
                self.assertNotIn(YOUTUBE_LEDGER, harness.store.files)
                self.assertEqual("SENT", json.loads(harness.store.read(MAIN_LEDGER))["parts"][0]["delivery_state"])

    def test_publication_failure_in_youtube_leaves_the_main_exit_code_unchanged(self):
        for failed_state, send_count in (("SENDING", 0), ("SENT", 1)):
            with self.subTest(failed_state=failed_state):
                harness = ReportHarness()
                harness.store.fail_publication_state = failed_state
                code, stdout, stderr = harness.run_report()
                self.assertEqual(0, code)
                self.assert_no_youtube_values(stdout + stderr)
                self.assertEqual(1, sum(line.startswith("youtube ") for line in stdout.splitlines()))
                self.assertEqual(send_count, harness.events.count("youtube_send"))
                self.assertEqual("SENT", json.loads(harness.store.read(MAIN_LEDGER))["parts"][0]["delivery_state"])
                if failed_state == "SENT":
                    self.assertEqual("SENDING", json.loads(harness.store.read(YOUTUBE_LEDGER))["delivery_state"])
                    code, stdout, _ = harness.run_report("resume", report_id=REPORT_ID)
                    self.assertEqual(0, code)
                    self.assert_status(stdout, "already_attempted")
                    self.assertEqual(1, harness.events.count("youtube_send"))

    def test_resuming_an_alert_does_not_fetch_youtube(self):
        harness = ReportHarness()
        alert_id = "alert-20261127T00"
        harness.store.files[f"reports/alerts/{alert_id}.json"] = storage.json_bytes({"parts": ["示例提醒"]})
        code, _, _ = harness.run_report("resume", report_id=alert_id)
        self.assertEqual(0, code)
        self.assertEqual([], harness.fetch_calls)
        self.assertNotIn(f"deliveries/{alert_id}-youtube.json", harness.store.files)

    def test_only_the_report_runtime_step_receives_the_secret(self):
        workflows = Path(__file__).resolve().parents[1] / ".github/workflows"
        consumers = []
        for file in workflows.glob("*.yml"):
            raw = file.read_text(encoding="utf-8")
            if "YOUTUBE_API_KEY" in raw:
                consumers.append(file.name)
                spec = yaml.load(raw, Loader=yaml.BaseLoader)
                job = spec["jobs"]["report"]
                self.assertNotIn("YOUTUBE_API_KEY", spec.get("env", {}))
                self.assertNotIn("YOUTUBE_API_KEY", job.get("env", {}))
                [runtime] = [step for step in job["steps"] if "YOUTUBE_API_KEY" in step.get("env", {})]
                self.assertEqual("python -m radar.live report", runtime["run"])
                self.assertEqual("${{ secrets.YOUTUBE_API_KEY }}", runtime["env"]["YOUTUBE_API_KEY"])
        self.assertEqual(["report.yml"], consumers)

    def test_private_git_does_not_inherit_the_youtube_key(self):
        with (patch.dict(os.environ, {"YOUTUBE_API_KEY": YOUTUBE_KEY, "GEMINI_API_KEY": GEMINI_KEY}, clear=True),
              patch.object(storage, "private_repository_size", return_value=1),
              patch.object(storage, "_run_git") as run_git):
            store = storage.PrivateGitStore.clone(Path.cwd(), "mock-private-token")
        self.assertNotIn("YOUTUBE_API_KEY", store.git_env)
        self.assertNotIn("GEMINI_API_KEY", store.git_env)
        self.assertNotIn(YOUTUBE_KEY, " ".join(run_git.call_args.args[2].values()))


if __name__ == "__main__":
    unittest.main()
