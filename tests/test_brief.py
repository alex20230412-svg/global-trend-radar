"""The Owner's Chinese brief: AI path, plain fallback and the Gemini client (all offline)."""

import json
import unittest
from urllib.parse import quote

import httpx

from radar import live
from radar.brief import (
    GeminiWriter, _footer, _prompt_payload, build_brief, collect_items, sanitize,
)
from radar.delivery import _message_text
from radar.layout import entry_key, table_width
from tools.sample_report import NOW, synthetic_report


KEY = "synthetic-gemini-key-for-offline-test"


class FakeWriter:
    def __init__(self, text, status="ok", model="fake-model"):
        self.result = (text, status, model)
        self.calls = []

    def write(self, system, prompt):
        self.calls.append((system, prompt))
        return self.result


AI_TEXT = json.dumps({
    "items": [
        {"id": "m1", "label": "课堂助教", "why": "一款离线多语助教开放试用 https://evil.example/x"},
        {"id": "m2", "label": "购物节", "why": "低耗雾灯新品打折"},
        {"id": "m99", "label": "不存在的编号", "why": "凭空多出来的一行"},
        {"id": "m1", "label": "重复条目", "why": "重复内容"},
        {"id": "s1", "label": "示例情歌", "why": "抒情慢歌"},
        {"id": "s9", "label": "编造的歌", "why": "虚构"},
        {"id": "a1", "label": "示例记账", "why": "记录日常开支"},
        {"id": "n1", "label": "社区修理站", "why": "开放自行车检修日"},
        {"id": "w1", "label": "雷暴警告", "why": "风险升高"},
    ],
    "ideas": [{"text": "低耗灯具促销受关注，可留意相关零售。", "ids": ["m2"]}],
}, ensure_ascii=False)


class BriefTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = synthetic_report().snapshot

    def test_footer_names_stale_archive_and_wiki_fallback_date(self):
        text = _footer({"coverage": [
            {"source_id": "weibo_archive", "status": "stale", "reason": "archive_stale"},
            {"source_id": "wikipedia_my", "status": "ok", "data_day": "2026-11-25", "fallback": True},
            {"source_id": "chinanews_rss", "status": "error"},
        ]})
        self.assertIn("1/3 个正常", text)
        self.assertIn("微博存档已停更", text)
        self.assertIn("中新网", text)
        self.assertIn("维基百科采用 2026-11-25 的马来西亚浏览榜", text)

    def test_plain_brief_is_chinese_one_part_without_niche_platforms(self):
        brief = build_brief(self.snapshot, NOW, "daily-2026-11-27")
        self.assertEqual("plain", brief.meta["mode"])
        self.assertEqual("no_writer", brief.meta["status"])
        self.assertEqual(1, len(brief.parts))
        text = _message_text(brief.parts[0])
        for expected in ("马来西亚热搜", "全球热议", "大家在听", "示例情歌（合成） · 示例歌手甲",
                         "大家在下载", "示例记账 App · Finance", "新闻和天气", "新加坡", "8K+", "🔗",
                         "AI 摘要今天不可用", "数据来源"):
            self.assertIn(expected, text)
        self.assertIn("<pre>", brief.parts[0])
        self.assertIn("<blockquote expandable>", brief.parts[0])
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
        self.assertIn("<b>📅 11月27日（周五）热点早报</b>", html)
        # Regions the model invented are replaced by the data's own list; invented lines are dropped.
        self.assertNotIn("巴西", text)
        self.assertNotIn("不存在的编号", text)
        self.assertNotIn("凭空多出来的一行", text)
        self.assertIn("课堂助教 · 一款离线多语助教开放试用", text)
        self.assertIn("（日本、新加坡也在搜）", text)
        self.assertIn("示例情歌（合成） · 抒情慢歌", text)
        self.assertNotIn("编造的歌", text)
        self.assertNotIn("重复条目", text)
        self.assertIn('href="https://music.apple.com/my/album/synthetic-1"', html)
        self.assertIn("示例记账 App · 记录日常开支", text)
        self.assertIn("低耗灯具促销受关注", text)
        system, prompt = writer.calls[0]
        self.assertIn("不得加入条目里没有的事实", system)
        self.assertNotIn("http", prompt)
        self.assertNotIn("also_searched_in", prompt)
        self.assertNotIn("新加坡", prompt)

    def test_invalid_or_failed_model_output_falls_back_to_plain(self):
        no_items = json.dumps({"items": [{"id": "w1", "label": "雷暴", "why": "雷暴警告"}], "ideas": []})
        for writer, status in ((FakeWriter("太短"), "invalid_output"),
                               (FakeWriter(no_items), "invalid_output"),
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
            row = {"title": title, "geos": list(geos), "url": f"https://example.org/{quote(title)}",
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
        self.assertEqual(["earthquake"], others)
        self.assertEqual([("THUNDERSTORMS WARNING", "11-27 14:00")],
                         [(row["title"], row["until"]) for row in items["weather"]])
        self.assertEqual([f"m{number}" for number in range(1, 9)], [row["id"] for row in items["malaysia"]])

    def test_new_markers_follow_canonical_entries_and_report_window_input(self):
        row = {"title": "  青原科技  ", "url": "https://example.org/news"}
        snapshot = {"malaysia": [row], "charts": {"apple_music_my": [
            {"title": "合成流行曲", "artist": "合成歌手", "url": "https://example.org/music"},
        ]}}
        brief = build_brief(snapshot, NOW, "daily-2026-11-27",
                            previous_keys={entry_key("青原科技")}, token_notice="⚠️ 私库钥匙快到期")
        latest = _message_text(brief.parts[0])
        self.assertEqual(1, latest.count("🆕"))
        self.assertIn("⚠️ 私库钥匙快到期", latest)
        self.assertEqual([entry_key("青原科技"),
                          entry_key("合成流行曲", section="music", artist="合成歌手")],
                         [row["key"] for row in brief.entries])
        self.assertEqual(["malaysia", "music"], [row["section"] for row in brief.entries])
        first_week = build_brief(snapshot, NOW, "daily-2026-11-27", previous_keys=None)
        self.assertEqual(0, _message_text(first_week.parts[0]).count("🆕"))

    def test_json_discards_invented_numbers_long_labels_and_extra_item_ids(self):
        snapshot = {"malaysia": [
            {"title": "甲艺人", "url": "https://example.org/1", "context": {"title": "甲艺人获提名"}},
            {"title": "乙艺人", "url": "https://example.org/2"},
            {"title": "丙电影", "url": "https://example.org/3", "context": {"title": "丙电影已有 18 场上映"}},
        ]}
        writer = FakeWriter(json.dumps({"items": [
            {"id": "m1", "label": "甲艺人", "why": "享年六十五岁"},
            {"id": "m2", "label": "这个标签明显超过了十二个字的上限", "why": "预计 65 号发布"},
            {"id": "m3", "label": "新电影", "why": "已有 18 场"},
            {"id": "m999", "label": "虚构项目", "why": "虚构事实"},
        ], "ideas": []}, ensure_ascii=False))
        brief = build_brief(snapshot, NOW, "smoke-2026-11-27", writer)
        plain = _message_text(brief.parts[0])
        self.assertEqual("ai", brief.meta["mode"])
        self.assertIn("甲艺人获提名", plain)
        self.assertIn("乙艺人", plain)
        self.assertIn("已有 18 场", plain)
        for denied in ("六十五", "65", "十二个字的上限", "虚构项目"):
            self.assertNotIn(denied, plain)

    def test_invented_number_in_reason_keeps_a_valid_label(self):
        snapshot = {"malaysia": [{"title": "tommy thomas", "url": "https://example.org/a",
                                  "context": {"title": "Synthetic suit withdrawn worth RM1.9mil"}}],
                    "weather": [{"title": "THUNDERSTORMS WARNING", "url": "https://example.org/w",
                                 "valid_to": "2026-11-27T06:00:00+00:00"}]}
        writer = FakeWriter(json.dumps({"items": [
            {"id": "m1", "label": "前总检察长诉讼", "why": "撤回190万令吉诉讼"},
            {"id": "w1", "label": "雷暴", "why": "气象局发布雷暴预警。"},
        ], "ideas": []}, ensure_ascii=False))
        plain = _message_text(build_brief(snapshot, NOW, "smoke-2026-11-27", writer).parts[0])
        self.assertIn("前总检察长诉讼", plain)
        self.assertNotIn("190万", plain)
        self.assertIn("Synthetic suit withdrawn", plain)
        self.assertIn("气象局发布雷暴预警，到", plain)
        self.assertNotIn("。，", plain)

    def test_music_names_stay_original_apps_use_short_purpose_and_weather_in_chinese(self):
        snapshot = {
            "malaysia": [{"title": "合成话题", "url": "https://example.org/a"}],
            "charts": {
                "apple_music_my": [{"title": "Stop The Wedding!", "artist": "Synthetic Singer",
                                    "url": "https://example.org/s"}],
                "app_store_my": [{"title": "Synthetic Pay", "genre": "Finance", "url": "https://example.org/p"}],
            },
            "weather": [{"title": "CONTINUOUS RAIN WARNING (ALERT)", "url": "https://example.org/w"}],
        }
        writer = FakeWriter(json.dumps({"items": [
            {"id": "m1", "label": "合成话题", "why": "合成原因"},
            {"id": "s1", "label": "停止婚礼单曲", "why": "合成歌手的流行单曲"},
            {"id": "a1", "label": "电子钱包", "why": "提供电子钱包与付款服务的应用"},
        ], "ideas": []}, ensure_ascii=False))
        plain = _message_text(build_brief(snapshot, NOW, "smoke-2026-11-27", writer).parts[0])
        self.assertIn("Stop The Wedding! — Syn", plain)
        self.assertNotIn("停止婚礼单曲", plain)
        self.assertIn("Synthetic Pa 电子钱包", plain)
        self.assertIn("电子钱包", plain)
        self.assertIn("持续降雨警告（戒备）", plain)

    def test_labels_up_to_twelve_characters_are_kept_and_main_pages_dropped(self):
        snapshot = {"malaysia": [{"title": "hoki piala sultan azlan shah", "url": "https://example.org/h"}],
                    "wiki": [{"title": "Hoofdpagina", "url": "https://nl.wikipedia.org/wiki/Hoofdpagina",
                              "views_ceil": 172600},
                             {"title": "A. Samad Said", "url": "https://en.wikipedia.org/wiki/A._Samad_Said",
                              "views_ceil": 7400}]}
        writer = FakeWriter(json.dumps({"items": [
            {"id": "m1", "label": "大马曲棍球队晋级决赛", "why": "球队闯入决赛"},
            {"id": "k1", "label": "A. Samad Said", "why": "作家条目"},
        ], "ideas": []}, ensure_ascii=False))
        plain = _message_text(build_brief(snapshot, NOW, "smoke-2026-11-27", writer).parts[0])
        self.assertIn("大马曲棍球队晋级决赛 · 球队闯入决赛", plain)
        self.assertNotIn("hoki piala", plain)
        self.assertNotIn("Hoofdpagina", plain)
        self.assertIn("A. Samad Said", plain)

    def test_china_goes_in_its_own_message_with_popular_charts(self):
        snapshot = {
            "malaysia": [{"title": "合成话题", "url": "https://example.org/a"}],
            "china": [{"title": "合成微博话题", "url": "https://s.weibo.com/weibo?q=x", "source_label": "微博"}],
            "charts": {
                "baidu_teleplay": [{"title": "合成剧甲", "artist": "中国大陆 | 古装", "volume_raw": "95471",
                                    "url": "https://m.baidu.com/s?word=a"}],
                "baidu_movie": [{"title": "合成电影", "volume_raw": "1060000", "url": "https://m.baidu.com/s?word=b"}],
                "apple_music_cn": [{"title": "合成中文歌", "artist": "合成歌手", "url": "https://example.org/m"}],
                "app_store_cn": [{"title": "合成短剧", "genre": "Entertainment", "url": "https://example.org/p"}],
            },
        }
        writer = FakeWriter(json.dumps({"items": [
            {"id": "m1", "label": "合成话题", "why": "合成原因"},
            {"id": "c1", "label": "网民热议话题", "why": "合成讨论"},
            {"id": "p1", "label": "短剧", "why": "看短剧的应用"},
        ], "ideas": []}, ensure_ascii=False))
        brief = build_brief(snapshot, NOW, "smoke-2026-11-27", writer)
        main = "".join(_message_text(part) for part in brief.parts)
        china = "".join(_message_text(part) for part in brief.china_parts)
        self.assertNotIn("中国热议", main)
        self.assertNotIn("合成剧甲", main)
        for expected in ("🇨🇳 中国在流行", "网民热议话题（微博）", "📺 热门电视剧", "95K  合成剧甲",
                         "1.1M  合成电影", "合成中文歌 — 合成歌手", "合成短剧 · 短剧", "smoke-2026-11-27-china"):
            self.assertIn(expected, china)
        payload = json.loads(writer.calls[0][1])
        self.assertNotIn("cn_tv", payload)
        self.assertIn("cn_apps", payload)
        self.assertIn("cn_tv", {row["section"] for row in brief.entries})
        empty = build_brief({"malaysia": [{"title": "合成话题", "url": "https://example.org/a"}]}, NOW, "smoke-2026-11-27")
        self.assertEqual([], empty.china_parts)

    def test_app_names_drop_store_taglines(self):
        from radar.brief import _app_name
        self.assertEqual(("红果短剧", "好内容多品类随心看"), _app_name("红果短剧 - 好内容多品类随心看"))
        self.assertEqual(("抖音商城", "下单返积分、退货包运费"), _app_name("抖音商城-下单返积分、退货包运费"))
        self.assertEqual(("WorkBuddy", "AI 办公我帮你"), _app_name("WorkBuddy - AI 办公我帮你"))
        self.assertEqual(("Shopee", "Shop & Get Vouchers"), _app_name("Shopee: Shop & Get Vouchers"))
        self.assertEqual(("Wi-Fi Map", ""), _app_name("Wi-Fi Map"))
        snapshot = {"malaysia": [{"title": "合成话题", "url": "https://example.org/a"}],
                    "charts": {"app_store_cn": [{"title": "红果短剧 - 好内容多品类随心看",
                                                 "url": "https://example.org/p"}]}}
        china = _message_text(build_brief(snapshot, NOW, "smoke-2026-11-27").china_parts[0])
        self.assertIn("红果短剧 · 好内容多品类随心看", china)

    def test_cross_section_alias_urls_and_wiki_adult_filter(self):
        snapshot = {
            "malaysia": [{"title": "新电影", "url": "https://example.org/movie?utm_source=first"}],
            "monitored_regions": [
                {"title": "热门的电影", "url": "https://example.org/movie"},
                {"title": "新电影", "url": "https://example.org/alias"},
                {"title": "其他主题", "url": "https://example.org/other"},
            ],
            "wiki": [{"title": "成人影片", "url": "https://zh.wikipedia.org/wiki/Adult"},
                     {"title": "合成页面", "url": "https://zh.wikipedia.org/wiki/Sample", "views_ceil": 12000}],
            "china": [{"title": "合成中国话题", "source_label": "微博", "url": "https://example.org/trending"}],
        }
        brief = build_brief(snapshot, NOW, "smoke-2026-11-27")
        plain = _message_text(brief.parts[0])
        self.assertIn("12K", plain)
        self.assertNotIn("合成中国话题", plain)  # China has its own message since 2026-11-27.
        self.assertIn("合成中国话题（微博）", _message_text(brief.china_parts[0]))
        for denied in ("热门的电影", "成人影片"):
            self.assertNotIn(denied, plain)
        table = brief.parts[0].split("<pre>", 1)[1].split("</pre>", 1)[0]
        self.assertNotIn("<a", table)
        self.assertTrue(all(table_width(line) <= 28 for line in table.splitlines()))
        self.assertEqual(["malaysia", "global", "wiki", "china"], [row["section"] for row in brief.entries])

    def test_sanitize_strips_links_markdown_and_controls(self):
        self.assertEqual("标题\n\n正文 。", sanitize("## **标题**\n\n\n\n正文 https://x.example/a 。\x07"))


class GeminiWriterTests(unittest.TestCase):
    def writer(self, handler, **options):
        options.setdefault("retry_delay", 0)
        return GeminiWriter(KEY, transport=httpx.MockTransport(handler), **options)

    def test_busy_models_get_one_more_pass_after_a_wait(self):
        calls, waits = [], []

        def handler(request):
            calls.append(request.url.path)
            if len(calls) <= 2:
                return httpx.Response(503, text=KEY)
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

        writer = self.writer(handler, retry_delay=30, sleep=waits.append)
        self.assertEqual(("{}", "ok"), writer.write("s", "p")[:2])
        self.assertEqual([30], waits)
        refused = self.writer(lambda request: httpx.Response(403), retry_delay=30, sleep=waits.append)
        self.assertEqual("http_403", refused.write("s", "p")[1])
        self.assertEqual([30], waits)

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
        self.assertEqual("application/json", body["generationConfig"]["responseMimeType"])
        self.assertEqual("ARRAY", body["generationConfig"]["responseSchema"]["properties"]["items"]["type"])

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
