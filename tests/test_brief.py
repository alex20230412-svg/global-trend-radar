"""The Owner's Chinese brief: AI path, plain fallback and the Gemini client (all offline)."""

import json
import unittest

import httpx

from radar import live
from radar.brief import (
    GeminiWriter, _prompt_payload, build_brief, collect_items, sanitize,
)
from radar.delivery import _message_text
from tools.sample_report import NOW, synthetic_report


KEY = "AIzaSyFAKE_offline_test_key_000000000000"


class FakeWriter:
    def __init__(self, text, status="ok", model="fake-model"):
        self.result = (text, status, model)
        self.calls = []

    def write(self, system, prompt):
        self.calls.append((system, prompt))
        return self.result


AI_TEXT = """## 📅 11月27日 热点早报

**🇲🇾 马来西亚今天大家在搜什么**
[m1] 课堂 AI 助教：一款离线多语助教开放试用（日本、新加坡也在搜） https://evil.example/x
1. [m2] 购物节：低耗雾灯新品打折（新加坡、泰国也在搜）
[m99] 不存在的编号

📰 马来西亚新闻
[n1] 社区修理站开放自行车检修日

⚠️ 天气
[w1] 示例区域 A 雷暴警告，到 11-27 10:20

💡 可能的生意线索（AI 推测，仅供参考）
- 低耗灯具促销受关注，可留意相关零售。"""


class BriefTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = synthetic_report().snapshot

    def test_plain_brief_is_chinese_one_part_without_niche_platforms(self):
        brief = build_brief(self.snapshot, NOW, "daily-2026-11-27")
        self.assertEqual("plain", brief.meta["mode"])
        self.assertEqual("no_writer", brief.meta["status"])
        self.assertEqual(1, len(brief.parts))
        text = _message_text(brief.parts[0])
        for expected in ("马来西亚今天大家在搜什么", "其他国家在搜", "马来西亚新闻", "天气", "新加坡", "🔗",
                         "AI 摘要今天不可用", "数据来源"):
            self.assertIn(expected, text)
        for unexpected in ("Hacker News", "Mastodon 标签", "Bluesky", "也在 SG", "📰1 家"):
            self.assertNotIn(unexpected, text)
        # The one failing synthetic source is named in plain Chinese in the footer.
        self.assertIn("暂时没有数据：Mastodon 链接", text)

    def test_ai_brief_is_sanitized_and_markers_become_source_links(self):
        writer = FakeWriter(AI_TEXT)
        brief = build_brief(self.snapshot, NOW, "daily-2026-11-27", writer)
        self.assertEqual(("ai", "ok", "fake-model"), (brief.meta["mode"], brief.meta["status"], brief.meta["model"]))
        self.assertEqual(1, len(brief.parts))
        html = brief.parts[0]
        text = _message_text(html)
        self.assertNotIn("evil.example", html)
        self.assertNotIn("**", text)
        self.assertNotIn("##", text)
        self.assertNotIn("[m", text)
        self.assertIn('href="https://example.org/synthetic/context/1"', html)
        self.assertIn('href="https://example.org/synthetic/context/2"', html)
        self.assertIn("以上由 AI 根据当天标题整理", text)
        self.assertIn("<b>📅 11月27日 热点早报</b>", html)
        system, prompt = writer.calls[0]
        self.assertIn("不得加入条目里没有的事实", system)
        self.assertNotIn("http", prompt)

    def test_invalid_or_failed_model_output_falls_back_to_plain(self):
        for writer, status in ((FakeWriter("太短"), "invalid_output"),
                               (FakeWriter(None, "http_429", "gemini-flash-lite-latest"), "http_429"),
                               (FakeWriter("没有提到国名的长文本。" * 20), "invalid_output")):
            with self.subTest(status=status):
                brief = build_brief(self.snapshot, NOW, "daily-2026-11-27", writer)
                self.assertEqual(("plain", status), (brief.meta["mode"], brief.meta["status"]))
                self.assertIn("AI 摘要今天不可用", _message_text(brief.parts[0]))

    def test_prompt_payload_lists_ids_without_links(self):
        items = collect_items(self.snapshot)
        payload = json.loads(_prompt_payload(items, NOW))
        self.assertEqual("11月27日", payload["date"])
        self.assertEqual("m1", payload["malaysia"][0]["id"])
        self.assertIn("新加坡", payload["malaysia"][0]["also_searched_in"])
        self.assertNotIn("http", json.dumps(payload, ensure_ascii=False))
        self.assertEqual(10, len(items["malaysia"]))

    def test_sanitize_strips_links_markdown_and_controls(self):
        self.assertEqual("标题\n\n正文 。", sanitize("## **标题**\n\n\n\n正文 https://x.example/a 。\x07"))


class GeminiWriterTests(unittest.TestCase):
    def writer(self, handler, **options):
        return GeminiWriter(KEY, transport=httpx.MockTransport(handler), **options)

    def test_key_goes_in_header_and_unknown_model_tries_the_next_alias(self):
        seen = []

        def handler(request):
            seen.append(request)
            if "gemini-flash-lite-latest" in request.url.path:
                return httpx.Response(404, json={"error": {"message": KEY}})
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": "思考过程", "thought": True}, {"text": "中文早报"},
            ]}}]})

        text, status, model = self.writer(handler).write("系统", "条目")
        self.assertEqual(("中文早报", "ok", "gemini-flash-latest"), (text, status, model))
        for request in seen:
            self.assertEqual(KEY, request.headers["x-goog-api-key"])
            self.assertNotIn(KEY, str(request.url))
        body = json.loads(seen[-1].content)
        self.assertEqual("系统", body["systemInstruction"]["parts"][0]["text"])
        self.assertEqual("条目", body["contents"][0]["parts"][0]["text"])

    def test_discovery_prefers_a_stable_flash_lite_text_model(self):
        posted = []

        def handler(request):
            if request.method == "GET":
                return httpx.Response(200, json={"models": [
                    {"name": "models/gemini-9.9-flash-tts", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-9.2-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-9.1-flash-lite", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-9.3-flash-lite-preview", "supportedGenerationMethods": ["generateContent"]},
                ]})
            posted.append(request.url.path)
            if "gemini-9.1-flash-lite" in request.url.path:
                return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "好"}]}}]})
            return httpx.Response(404)

        text, status, model = self.writer(handler).write("s", "p")
        self.assertEqual(("好", "ok", "gemini-9.1-flash-lite"), (text, status, model))
        self.assertTrue(posted[-1].endswith("/models/gemini-9.1-flash-lite:generateContent"))

    def test_rate_limit_and_network_errors_are_codes_only(self):
        text, status, model = self.writer(lambda request: httpx.Response(429, text=KEY)).write("s", "p")
        self.assertEqual((None, "http_429", "gemini-flash-lite-latest"), (text, status, model))

        def broken(request):
            raise httpx.ConnectTimeout(KEY)

        text, status, model = self.writer(broken).write("s", "p")
        self.assertEqual((None, "network_ConnectTimeout", None), (text, status, model))

    def test_invalid_key_is_rejected_and_live_falls_back_to_plain(self):
        with self.assertRaises(ValueError):
            GeminiWriter("not a key")
        self.assertIsNone(live._writer({"GEMINI_API_KEY": "not a key"}))
        self.assertIsNone(live._writer({}))
        self.assertIsInstance(live._writer({"GEMINI_API_KEY": KEY}), GeminiWriter)

    def test_preview_report_ids_are_accepted_for_recovery(self):
        self.assertTrue(live.REPORT_ID.fullmatch("preview-0915-2026-11-26"))
        self.assertFalse(live.REPORT_ID.fullmatch("preview-2026-11-26"))


if __name__ == "__main__":
    unittest.main()
