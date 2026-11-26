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

**🔥 马来西亚现在最热门的话题**
[m1] 课堂 AI 助教：一款离线多语助教开放试用（也在中国、巴西、德国搜寻） https://evil.example/x
1. [m2] 购物节：低耗雾灯新品打折
[m99] 不存在的编号
凭空多出来的一行

🎵 大家在听（马来西亚 Apple Music 热门歌曲）
[s1] 示例情歌 - 示例歌手甲：抒情慢歌
[s9] 编造的歌

📱 大家在下载（马来西亚 App Store 热门免费 App）
[a1] 示例记账 App：记录日常开支

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
        for expected in ("马来西亚现在最热门的话题", "全球正在热议", "大家在听", "示例情歌（合成） - 示例歌手甲",
                         "大家在下载", "示例记账 App（Finance）", "马来西亚新闻", "天气", "新加坡", "搜索 ", "🔗",
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
        # Regions the model invented are replaced by the data's own list; invented lines are dropped.
        self.assertNotIn("巴西", text)
        self.assertNotIn("不存在的编号", text)
        self.assertNotIn("凭空多出来的一行", text)
        items = collect_items(self.snapshot)
        first = items["malaysia"][0]
        expected = f" · 搜索 {first['volume']}（{'、'.join(first['also_searched_in'])}也在搜）"
        self.assertIn("课堂 AI 助教：一款离线多语助教开放试用" + expected, text)
        self.assertIn("示例情歌 - 示例歌手甲：抒情慢歌", text)
        self.assertNotIn("编造的歌", text)
        self.assertIn('href="https://music.apple.com/my/album/synthetic-1"', html)
        self.assertIn("示例记账 App：记录日常开支", text)
        system, prompt = writer.calls[0]
        self.assertIn("不得加入条目里没有的事实", system)
        self.assertNotIn("http", prompt)
        self.assertNotIn("also_searched_in", prompt)
        self.assertNotIn("新加坡", prompt)

    def test_invalid_or_failed_model_output_falls_back_to_plain(self):
        no_items = ("📅 11月27日 热点早报\n\n🇲🇾 马来西亚今天大家在搜什么\n"
                    + "这里没有任何条目编号，只是一段模型自己写的话，内容足够长。\n" * 4)
        for writer, status in ((FakeWriter("太短"), "invalid_output"),
                               (FakeWriter(no_items), "render_ValueError"),
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
        self.assertIn("新加坡", items["malaysia"][0]["also_searched_in"])
        self.assertNotIn("also_searched_in", payload["malaysia"][0])  # regions are added by code only
        self.assertNotIn("http", json.dumps(payload, ensure_ascii=False))
        self.assertLessEqual(len(items["malaysia"]), 8)
        self.assertLessEqual(len(items["other"]), 4)

    def test_sports_merge_repeats_drop_and_caps_apply_before_the_model(self):
        def entry(title, geos=("MY",), headline=None, category="其他"):
            row = {"title": title, "geos": list(geos), "url": f"https://example.org/{len(title)}",
                   "category": category}
            if headline:
                row["context"] = {"title": headline, "url": f"https://example.org/c/{len(title)}"}
            return row

        snapshot = {
            "malaysia": [
                entry("warriors vs kings", ("MY", "SG")), entry("duran duran", headline="Andy Taylor 1961–2026"),
                entry("thunder vs timberwolves", ("MY", "GB")), entry("lrt"), entry("tariff"),
                *[entry(f"topic {number}") for number in range(10)],
            ],
            "monitored_regions": [
                entry("andy taylor duran duran", ("MY", "PH"), headline="Andy Taylor 1961–2026"),
                entry("lamelo ball", ("AU",), category="体育"), entry("earthquake", ("AU",)),
            ],
            "weather": [
                {"title": "THUNDERSTORMS WARNING", "valid_to": "2026-11-27T04:00:00+00:00"},
                {"title": "THUNDERSTORMS WARNING", "valid_to": "2026-11-27T06:00:00+00:00"},
            ],
        }
        items = collect_items(snapshot)
        terms = [row["term"] for row in items["malaysia"]]
        self.assertEqual(8, len(terms))
        self.assertEqual(1, terms.count("体育赛事"))
        sport = next(row for row in items["malaysia"] if row["term"] == "体育赛事")
        self.assertEqual("warriors vs kings；thunder vs timberwolves", sport["headline"])
        self.assertEqual(["新加坡", "英国"], sport["also_searched_in"])
        others = [row["term"] for row in items["other"]]
        self.assertNotIn("andy taylor duran duran", others)  # same headline as a Malaysian topic
        self.assertEqual(["earthquake", "体育赛事"], others)
        self.assertEqual([("THUNDERSTORMS WARNING", "11-27 14:00")],
                         [(row["title"], row["until"]) for row in items["weather"]])
        self.assertEqual([f"m{number}" for number in range(1, 9)], [row["id"] for row in items["malaysia"]])

    def test_sanitize_strips_links_markdown_and_controls(self):
        self.assertEqual("标题\n\n正文 。", sanitize("## **标题**\n\n\n\n正文 https://x.example/a 。\x07"))


class GeminiWriterTests(unittest.TestCase):
    def writer(self, handler, **options):
        return GeminiWriter(KEY, transport=httpx.MockTransport(handler), **options)

    def test_key_goes_in_header_and_unknown_model_tries_the_next_alias(self):
        seen = []

        def handler(request):
            seen.append(request)
            if "/models/gemini-flash-latest:" in request.url.path:
                return httpx.Response(404, json={"error": {"message": KEY}})
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": "思考过程", "thought": True}, {"text": "中文早报"},
            ]}}]})

        text, status, model = self.writer(handler).write("系统", "条目")
        self.assertEqual(("中文早报", "ok", "gemini-flash-lite-latest"), (text, status, model))
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
        self.assertEqual((None, "network_ConnectTimeout", "gemini-flash-lite-latest"), (text, status, model))

    def test_a_slow_first_model_falls_through_to_the_next(self):
        def handler(request):
            if "/models/gemini-flash-latest:" in request.url.path:
                raise httpx.ReadTimeout("slow")
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "好"}]}}]})

        self.assertEqual(("好", "ok", "gemini-flash-lite-latest"), self.writer(handler).write("s", "p"))

    def test_a_refused_key_stops_at_the_first_model(self):
        calls = []

        def handler(request):
            calls.append(request.url.path)
            return httpx.Response(403)

        self.assertEqual((None, "http_403", "gemini-flash-latest"), self.writer(handler).write("s", "p"))
        self.assertEqual(1, len(calls))

    def test_invalid_key_is_rejected_and_live_falls_back_to_plain_with_a_reason(self):
        with self.assertRaises(ValueError):
            GeminiWriter("not a key")
        self.assertEqual("invalid_key_format", live._writer({"GEMINI_API_KEY": "not a key"}).reason)
        self.assertEqual("no_key", live._writer({}).reason)
        self.assertEqual("no_key", live._writer({"GEMINI_API_KEY": " \n"}).reason)
        self.assertIsInstance(live._writer({"GEMINI_API_KEY": KEY}), GeminiWriter)
        # A pasted trailing newline or space is harmless.
        self.assertIsInstance(live._writer({"GEMINI_API_KEY": f" {KEY}\n"}), GeminiWriter)
        snapshot = synthetic_report().snapshot
        brief = build_brief(snapshot, NOW, "daily-2026-11-27", live._writer({"GEMINI_API_KEY": "not a key"}))
        self.assertEqual(("plain", "invalid_key_format"), (brief.meta["mode"], brief.meta["status"]))

    def test_stripped_key_is_sent_without_whitespace(self):
        seen = []

        def handler(request):
            seen.append(request.headers["x-goog-api-key"])
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "好"}]}}]})

        GeminiWriter(f"  {KEY}\n", transport=httpx.MockTransport(handler)).write("s", "p")
        self.assertEqual([KEY], seen)

    def test_preview_report_ids_are_accepted_for_recovery(self):
        self.assertTrue(live.REPORT_ID.fullmatch("preview-0915-2026-11-26"))
        self.assertFalse(live.REPORT_ID.fullmatch("preview-2026-11-26"))


if __name__ == "__main__":
    unittest.main()
