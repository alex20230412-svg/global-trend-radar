"""Synthetic, offline tests for the official Malaysia YouTube chart adapter."""

from contextlib import redirect_stderr, redirect_stdout
from html import escape
from io import StringIO
import re
import unittest

import httpx

from radar.delivery import TELEGRAM_LIMIT, _message_text, _units
from radar.youtube import (
    MAX_RESPONSE_BYTES, YouTubeConfig, YouTubeVideo, fetch_youtube, load_youtube_config,
    render_youtube,
)


MOCK_KEY = "synthetic" + "-youtube-key-for-tests-only"


class SyntheticStream(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.reads = 0

    def __iter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk


def fixture_video(number=1, *, title=None, channel="示例频道", category="10", views="1234567"):
    return {
        "id": f"{number:011d}",
        "snippet": {
            "title": f"示例视频 {number}" if title is None else title,
            "channelTitle": channel,
            "categoryId": category,
        },
        "statistics": {"viewCount": views},
        "url": "https://ignored.example.invalid/link",
    }


class YouTubeTests(unittest.TestCase):
    def fetch(self, result, *, config=YouTubeConfig(enabled=True), key=MOCK_KEY):
        with httpx.Client(transport=httpx.MockTransport(lambda _: result)) as client:
            return fetch_youtube(config, key, client=client)

    def test_request_only_uses_official_endpoint_and_header_with_trimmed_key(self):
        def respond(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.scheme, "https")
            self.assertEqual(request.url.host, "www.googleapis.com")
            self.assertEqual(request.url.path, "/youtube/v3/videos")
            self.assertEqual(dict(request.url.params), {
                "part": "snippet,statistics", "chart": "mostPopular", "regionCode": "MY",
                "maxResults": "25", "fields": "items(id,snippet(title,channelTitle,categoryId),statistics(viewCount))",
            })
            self.assertEqual(request.headers["x-goog-api-key"], MOCK_KEY)
            self.assertNotIn(MOCK_KEY, str(request.url))
            self.assertEqual(request.extensions["timeout"]["connect"], 8)
            self.assertEqual(request.extensions["timeout"]["read"], 15)
            return httpx.Response(200, json={"items": [fixture_video()]})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            result = fetch_youtube(YouTubeConfig(enabled=True), f"\t {MOCK_KEY} \n", client=client)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.videos[0].video_id, "00000000001")
        markup = render_youtube(result.videos)
        self.assertIn('href="https://www.youtube.com/watch?v=00000000001"', markup)
        self.assertNotIn("ignored.example.invalid", markup)

    def test_missing_invalid_and_disabled_keys_skip_transport(self):
        def unreachable(_):
            self.fail("No request should be made for an invalid or disabled client")

        with httpx.Client(transport=httpx.MockTransport(unreachable)) as client:
            shipped = load_youtube_config()
            self.assertEqual(("MY", 25, 5), (shipped.region, shipped.max_results, shipped.per_category))
            disabled = YouTubeConfig(enabled=False)
            self.assertEqual(fetch_youtube(disabled, MOCK_KEY, client=client).status, "disabled")
            enabled = YouTubeConfig(enabled=True)
            for key in ("", "   ", None):
                self.assertEqual(fetch_youtube(enabled, key, client=client).status, "no_key")
            for key in ("short", "X" * 513, MOCK_KEY + " x", MOCK_KEY + "\r\nX: x", "中文" * 20, 87654):
                self.assertEqual(fetch_youtube(enabled, key, client=client).status, "invalid_key_format")

    def test_group_caps_keeps_api_order_and_formats_view_counts(self):
        items = [
            fixture_video(1, category="20", views="5"),
            fixture_video(2, category="10"),
            fixture_video(3, category="10", views="100000000"),
            fixture_video(4, category="10"),
            fixture_video(5, category="1"),
            fixture_video(6, category="30"),
            fixture_video(7, category="44"),
            fixture_video(8, category="99", views=None),
        ]
        result = self.fetch(httpx.Response(200, json={"items": items}),
                            config=YouTubeConfig(enabled=True, per_category=2))
        self.assertEqual([int(video.video_id) for video in result.videos], [1, 2, 3, 5, 6, 8])
        plain = _message_text(render_youtube(result.videos))
        self.assertIn("🎵 音乐\n1. 示例视频 2 — 示例频道 · 观看 123万", plain)
        self.assertIn("\n2. 示例视频 3 — 示例频道 · 观看 1亿", plain)
        self.assertIn("🎮 游戏\n1. 示例视频 1 — 示例频道 · 观看 5", plain)
        self.assertIn("🎬 电影与预告片\n1. 示例视频 5", plain)
        self.assertIn("\n2. 示例视频 6", plain)
        self.assertIn("▶️ 其他\n1. 示例视频 8 — 示例频道 🔗", plain)
        self.assertNotIn("示例视频 4", plain)
        self.assertNotIn("示例视频 7", plain)

    def test_drops_malformed_entries_until_strict_majority(self):
        bad_id = fixture_video()
        bad_id["id"] = "not a video"
        no_channel = fixture_video(2)
        del no_channel["snippet"]["channelTitle"]
        wrong_type = fixture_video(3, title=["示例视频 类型错误"])
        bad_category = fixture_video(4, category=42)
        good = [fixture_video(number) for number in (5, 6, 7, 8)]
        half_bad = {"items": [bad_id, no_channel, wrong_type, bad_category, *good]}
        result = self.fetch(httpx.Response(200, json=half_bad))
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.videos), 4)
        half_bad["items"].append(None)
        result = self.fetch(httpx.Response(200, json=half_bad))
        self.assertEqual(result.status, "invalid_payload")
        self.assertEqual(result.videos, ())

    def test_invalid_top_level_and_json_do_not_produce_message_content(self):
        bodies = (b"not JSON", b"[]", b"null", b"{}", b"{\"items\": {}}")
        for content in bodies:
            result = self.fetch(httpx.Response(200, content=content))
            self.assertEqual(result.status, "invalid_payload")
            self.assertEqual(result.videos, ())
        empty = self.fetch(httpx.Response(200, json={"items": []}))
        self.assertEqual((empty.status, empty.videos), ("ok", ()))

    def test_text_preserves_original_script_escapes_controls_and_limits_fields(self):
        title = '<b>"原文"</b> & \x00' + "🎞" * 125
        channel = "'原频道' & \x07" + "字" * 125
        parsed = self.fetch(httpx.Response(200, json={"items": [fixture_video(title=title, channel=channel)]}))
        video, = parsed.videos
        for cleaned in (video.title, video.channel_title):
            self.assertEqual(len(cleaned), 100)
        self.assertNotIn("\x00", video.title)
        self.assertNotIn("\x07", video.channel_title)
        html = render_youtube(parsed.videos)
        self.assertIn(escape(video.title), html)
        self.assertIn(escape(video.channel_title), html)
        self.assertIn(video.title, _message_text(html))
        self.assertIn(video.channel_title, _message_text(html))

    def test_does_not_follow_redirects_even_with_a_redirecting_client(self):
        reached = []

        def respond(request):
            reached.append(request.url.host)
            return httpx.Response(302, headers={"location": "https://untrusted.example.invalid/other"})

        with httpx.Client(follow_redirects=True, transport=httpx.MockTransport(respond)) as client:
            result = fetch_youtube(YouTubeConfig(enabled=True), MOCK_KEY, client=client)
        self.assertEqual(reached, ["www.googleapis.com"])
        self.assertEqual(result.status, "http_302")

    def test_rejects_oversized_declared_or_streamed_and_unexpected_compression(self):
        declared = SyntheticStream([b"{}"])
        result = self.fetch(httpx.Response(
            200, headers={"content-length": str(MAX_RESPONSE_BYTES + 1)}, stream=declared,
        ))
        self.assertEqual(result.status, "invalid_payload")
        self.assertEqual(declared.reads, 0)
        streamed = SyntheticStream([b"x" * MAX_RESPONSE_BYTES, b"x", b"{}"])
        self.assertEqual(self.fetch(httpx.Response(200, stream=streamed)).status, "invalid_payload")
        self.assertEqual(streamed.reads, 2)
        compressed = SyntheticStream([b"fake encoding"])
        self.assertEqual(self.fetch(httpx.Response(
            200, headers={"content-encoding": "gzip"}, stream=compressed,
        )).status, "invalid_payload")
        self.assertEqual(compressed.reads, 0)

    def test_google_errors_map_only_known_reasons(self):
        cases = (
            (403, "errors", "quotaExceeded", "quota_exceeded"),
            (403, "errors", "dailyLimitExceeded", "quota_exceeded"),
            (400, "errors", "keyInvalid", "key_invalid"),
            (400, "details", "API_KEY_INVALID", "key_invalid"),
            (403, "errors", "accessNotConfigured", "api_not_enabled"),
            (403, "details", "SERVICE_DISABLED", "api_not_enabled"),
            (403, "errors", "forbidden", "http_403"),
            (418, "errors", "raw private sentinels", "http_418"),
        )
        for status, section, reason, expected in cases:
            body = {"error": {"message": MOCK_KEY, section: [{"reason": reason}]}}
            result = self.fetch(httpx.Response(status, json=body))
            self.assertEqual(result.status, expected)
            self.assertEqual(result.videos, ())
        self.assertEqual(self.fetch(httpx.Response(502, content=b"private text")).status, "http_502")

    def test_network_failure_does_not_print_key_or_exception_body(self):
        class PrivateProviderText(httpx.ConnectError):
            pass

        stdout, stderr = StringIO(), StringIO()
        for exception, expected in (
            (httpx.ConnectError, "network_ConnectError"),
            (httpx.ReadTimeout, "network_ReadTimeout"),
            (PrivateProviderText, "network_HTTPError"),
        ):
            def respond(request):
                raise exception(f"private provider text {MOCK_KEY}", request=request)

            with (httpx.Client(transport=httpx.MockTransport(respond)) as client,
                  redirect_stdout(stdout), redirect_stderr(stderr)):
                result = fetch_youtube(YouTubeConfig(enabled=True), MOCK_KEY, client=client)
            self.assertEqual(result.status, expected)
        self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("", ""))

    def test_long_messages_stay_one_part_and_reserve_all_policy_links(self):
        videos = tuple(
            YouTubeVideo(f"{index:011d}", "🧪" * 100, "👨" * 100, category, 1234)
            for index, category in enumerate(("10", "20", "44", "99") * 5)
        )
        markup = render_youtube(videos)
        plain = _message_text(markup)
        self.assertLessEqual(_units(plain), TELEGRAM_LIMIT)
        self.assertTrue(markup.startswith("<b>▶️ 大家在看"))
        for group in ("🎵 音乐", "🎮 游戏", "🎬 电影与预告片", "▶️ 其他"):
            self.assertIn(group, plain)
        hrefs = re.findall(r'href="([^"]+)"', markup)
        self.assertEqual(hrefs[-2:], ["https://www.youtube.com/t/terms", "https://policies.google.com/privacy"])
        self.assertTrue(all(re.fullmatch(r"https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}", url)
                            for url in hrefs[:-2]))
        self.assertNotIn("ignored.example.invalid", markup)
        self.assertIn("数据来自 YouTube（YouTube API Services）", plain)
        self.assertLess(len(hrefs) - 2, len(videos))


if __name__ == "__main__":
    unittest.main()
