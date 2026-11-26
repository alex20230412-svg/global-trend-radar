"""Validate the new source contracts using synthetic transport and storage only."""

import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest import TestCase
from unittest.mock import patch

import httpx

from radar import pipeline, sources
from radar.livecheck import _ProbeResult, run_checks
from radar.report import build_report
from radar.source_http import HOSTS, OriginGate, SourceHttp
from radar.storage import json_bytes, read_observations


NOW = datetime(2026, 11, 26, 4, 53, tzinfo=UTC)
SOURCE = {source.id: source for source in sources.load_sources()}
WIKI = SOURCE["wikipedia_my"]
WEIBO = SOURCE["weibo_archive"]
CHINA_NEWS = SOURCE["chinanews_rss"]
CHINA_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Synthetic China feed</title>
<item><title>Mock Chinese article</title>
<link>http://www.chinanews.com.cn/synthetic?utm_source=example</link>
<description>Unneeded private-storage test sentinel</description></item>
<item><title>External item</title><link>https://example.org/no</link></item>
</channel></rss>"""


class MemoryStore:
    size_kib = 0

    def __init__(self):
        self.files = {}

    def read(self, path):
        return self.files.get(path)

    def publish(self, files, message):
        self.files.update(files)


def wiki_payload(day, articles):
    return json.dumps({
        "items": [{"year": 2026, "month": "11", "day": day, "country": "MY", "articles": articles}],
    }).encode()


def article(title, project="en.wikipedia", rank=1, views=12000):
    return {"article": title, "project": project, "rank": rank, "views_ceil": views}


class SourceAdapterTests(TestCase):
    def transport(self, handler):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return SourceHttp(
            client, resolver=lambda _: "192.0.2.10", sleep=lambda _: None,
            origins={host: OriginGate() for host in HOSTS},
        )

    def test_robots_redirect_to_www_is_followed_once_for_wikimedia(self):
        for www_robots, expected in ((404, "ok"), (200, "robots_denied")):
            requests = []

            def fake(request, www_robots=www_robots):
                requests.append((request.headers["Host"], request.url.path))
                if request.headers["Host"] == "wikimedia.org" and request.url.path == "/robots.txt":
                    return httpx.Response(302, headers={"Location": "https://www.wikimedia.org/robots.txt"})
                if request.headers["Host"] == "www.wikimedia.org":
                    return (httpx.Response(404) if www_robots == 404
                            else httpx.Response(200, stream=httpx.ByteStream(b"User-agent: *\nDisallow: /api/\n")))
                return httpx.Response(200, stream=httpx.ByteStream(b"{}"))

            http = self.transport(fake)
            with self.subTest(www_robots=www_robots):
                if expected == "ok":
                    self.assertEqual(b"{}", http.load(WIKI.url + "/2026/11/25"))
                else:
                    with self.assertRaisesRegex(sources.SourceError, "^robots_denied$"):
                        http.load(WIKI.url + "/2026/11/25")
                self.assertEqual(("wikimedia.org", "/robots.txt"), requests[0])
                self.assertEqual(("www.wikimedia.org", "/robots.txt"), requests[1])
                with self.assertRaisesRegex(sources.SourceError, "^url_blocked$"):
                    http.load("https://www.wikimedia.org/anything")

    def test_wikipedia_404_fallback_has_real_data_day_original_rank_and_views(self):
        urls = []

        def get(url):
            urls.append(url)
            if url.endswith("/25"):
                raise sources.SourceError("http_404", http_status=404)
            return wiki_payload(24, [
                article("Main_Page"), article("Talk:Example", rank=2), article("分類:範例", "zh.wikipedia", 3),
                article("Space_Odyssey%3A_Part_Two", rank=6, views=8000),
                article("合成_詞條_(節選)", "zh.wikipedia", 4, 12000),
                article("Outside", "evil-.wikipedia", 7),
            ])

        rows = sources._wikipedia(WIKI, get, NOW)
        self.assertEqual(urls, [f"{WIKI.url}/2026/11/{day}" for day in (25, 24)])
        self.assertEqual((rows.data_day, rows.fallback, rows.skipped), ("2026-11-24", True, 0))
        self.assertEqual([row["views_ceil"] for row in rows], [12000, 8000])
        self.assertEqual([row["rank"] for row in rows], [4, 6])
        self.assertEqual(rows[0]["language"], "zh")
        self.assertEqual(rows[0]["published_at"], "2026-11-24T00:00:00+00:00")
        self.assertEqual(rows[0]["url"],
                         "https://zh.wikipedia.org/wiki/%E5%90%88%E6%88%90_%E8%A9%9E%E6%A2%9D_%28%E7%AF%80%E9%81%B8%29")
        self.assertEqual(rows[1]["url"], "https://en.wikipedia.org/wiki/Space_Odyssey%3A_Part_Two")

    def test_wikipedia_first_thirty_and_no_fallback_on_temporary_failure(self):
        payload = wiki_payload(25, [article(f"Fixture_{rank}", rank=rank) for rank in range(40, 0, -1)])
        with patch.object(sources, "datetime", wraps=datetime) as date:
            date.now.return_value = NOW
            rows = sources.collect_source(WIKI, type("MemoryHttp", (), {"load": lambda _, url: payload})())
        self.assertEqual((rows.data_day, rows.fallback), ("2026-11-25", False))
        self.assertEqual([row["rank"] for row in rows], list(range(1, 31)))
        attempted = []

        def fail(url):
            attempted.append(url)
            raise sources.SourceError("http_503", http_status=503)

        with self.assertRaisesRegex(sources.SourceError, "^http_503$"):
            sources._wikipedia(WIKI, fail, NOW)
        self.assertEqual(attempted, [f"{WIKI.url}/2026/11/25"])

    def test_new_origins_pin_addresses_rate_limit_and_scope_workflow_token(self):
        requests = []
        token = "synthetic-archive-token-never-real"

        def fake(request):
            requests.append(request)
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            if request.headers["Host"] == "api.github.com":
                return httpx.Response(200, headers={"Last-Modified": format_datetime(NOW)}, stream=httpx.ByteStream(
                    b'[{"title":"Mock Weibo & topic","url":"/weibo?q=fixture+topic&tracking=omit"}]',
                ))
            return httpx.Response(503, headers={"Retry-After": "1"})

        http = self.transport(fake)
        with patch.dict("os.environ", {"RUN_METADATA_TOKEN": token}):
            rows = sources._weibo_archive(WEIBO, http, NOW)
            # top.baidu.com is allowed since PR #38 (Owner: 「你自己试看」); the rest stay blocked.
            for host in ("s.weibo.com", "www.zhihu.com", "api.bilibili.com"):
                with self.assertRaisesRegex(sources.SourceError, "^url_blocked$"):
                    http.load(f"https://{host}/synthetic")
            with self.assertRaisesRegex(sources.SourceError, "^url_blocked$"):
                http.load("https://api.github.com/repos/other/example")
            with self.assertRaisesRegex(sources.SourceError, "^http_503$"):
                http.load(CHINA_NEWS.url)
        self.assertEqual(rows[0]["url"], "https://s.weibo.com/weibo?q=fixture+topic")
        self.assertEqual(rows[0]["published_at"], NOW.isoformat())
        self.assertEqual([request.headers.get("authorization") for request in requests],
                         [None, f"Bearer {token}", None, None])
        archive = requests[1]
        self.assertEqual(archive.url.path, "/repos/justjavac/weibo-trending-hot-search/contents/raw/2026-11-26.json")
        self.assertEqual(archive.url.query, b"ref=master")
        self.assertEqual(archive.headers["accept"], "application/vnd.github.raw+json")
        self.assertEqual(archive.extensions["sni_hostname"], "api.github.com")
        self.assertIn("github.com/alex20230412-svg/global-trend-radar", archive.headers["user-agent"])

    def test_weibo_requires_verified_nonfuture_freshness_before_parsing(self):
        class Archive:
            def __init__(self, modified):
                self.last_modified = modified

            def load(self, _):
                return b"invalid json"

        for time, reason in (
            (None, "archive_freshness_unavailable"),
            (format_datetime(NOW + timedelta(minutes=6)), "archive_freshness_unavailable"),
            (format_datetime(NOW - timedelta(hours=48, seconds=1)), "archive_stale"),
            (format_datetime(NOW - timedelta(hours=48)), "invalid_json"),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(sources.SourceError, f"^{reason}$"):
                sources._weibo_archive(WEIBO, Archive(time), NOW)

    def test_china_news_canonicalizes_official_links_and_never_fetches_articles(self):
        http = self.transport(lambda request: httpx.Response(
            404 if request.url.path == "/robots.txt" else 200, stream=httpx.ByteStream(CHINA_RSS),
        ))
        row, = sources.collect_source(CHINA_NEWS, http)
        self.assertEqual(row["url"], "https://www.chinanews.com.cn/synthetic")
        self.assertEqual((row["geo"], row["rank"], row["language"]), ("CN", 1, "zh"))
        self.assertNotIn("Unneeded private-storage test sentinel", json.dumps(row))


class SourceHistoryTests(TestCase):
    def collect(self, store, source_set, fetch, execution="test-1", now=NOW):
        return pipeline.collect_slot(store, source_set, {source.id for source in source_set}, now, execution,
                                     fetch=fetch, clock=lambda: now)

    def test_durable_claim_and_existing_result_prevent_second_request_in_same_hour(self):
        store = MemoryStore()
        attempts = []

        def fetch(source):
            key = f"runs/source-claims/{pipeline.partition(NOW)}.json"
            self.assertIn(source.id, json.loads(store.read(key)))
            attempts.append(source.id)
            raise sources.SourceError("archive_stale")

        first = self.collect(store, [WEIBO], fetch)
        repeat = self.collect(store, [WEIBO], fetch, "test-2")
        self.assertEqual(attempts, [WEIBO.id])
        self.assertEqual(first["sources"], repeat["sources"])
        self.assertEqual(first["sources"][WEIBO.id]["status"], "stale")
        self.collect(store, [WEIBO], fetch, "test-3", NOW + timedelta(minutes=1))
        self.assertEqual(attempts, [WEIBO.id])

    def test_process_stopping_after_claim_does_not_repeat_request(self):
        store = MemoryStore()
        store.publish({f"runs/source-claims/{pipeline.partition(NOW)}.json": json_bytes([WEIBO.id])}, "claim")
        result = self.collect(store, [WEIBO], lambda _: self.fail("Reserved source fetched twice"))
        self.assertEqual(result["sources"][WEIBO.id]["reason"], "hourly_rate_guard")

    def test_snapshot_separates_china_and_wiki_and_preserves_day_and_views(self):
        store = MemoryStore()
        source_set = [WIKI, WEIBO, CHINA_NEWS]
        wiki = sources._wikipedia(WIKI, lambda _: wiki_payload(25, [article("Fixture_wiki")]), NOW)
        fixtures = {
            WIKI.id: wiki,
            WEIBO.id: sources.SourceItems([
                sources._observation(WEIBO, "Mock Weibo", "https://s.weibo.com/weibo?q=fixture", 1),
            ]),
            CHINA_NEWS.id: sources._news(CHINA_NEWS, CHINA_RSS),
        }
        first = self.collect(store, source_set, lambda source: fixtures[source.id])
        slot = pipeline.partition(NOW)
        rows = read_observations(store, slot, first)
        coverage = pipeline._coverage({pipeline.hour(NOW): first}, source_set, set(fixtures), NOW)
        report = build_report(rows, coverage, now=NOW)
        self.assertEqual([item["source_label"] for item in report.snapshot["china"]], ["中新网", "微博"])
        wiki_entry, = report.snapshot["wiki"]
        self.assertEqual(wiki_entry["views_ceil"], 12000)
        self.assertEqual(wiki_entry["published_at"], "2026-11-25T00:00:00+00:00")
        self.assertEqual(report.snapshot["coverage"][0]["data_day"], "2026-11-25")
        self.assertEqual(report.snapshot["malaysia"], [])
        self.assertEqual(report.snapshot["local_news"], [])
        later = NOW + timedelta(hours=1)
        second = self.collect(store, source_set, lambda source: fixtures[source.id], "test-2", later)
        later_rows = read_observations(store, pipeline.partition(later), second)
        self.assertEqual(len(later_rows), len(rows))
        self.assertNotEqual(later_rows[0]["observed_at"], rows[0]["observed_at"])
        self.assertEqual(later_rows[0]["first_seen_at"], rows[0]["first_seen_at"])

    def test_undated_archive_404_keeps_missing_state(self):
        store = MemoryStore()

        def missing(_):
            raise sources.SourceError("http_404", http_status=404)

        yesterday = self.collect(store, [WEIBO], lambda _: sources.SourceItems(), now=NOW - timedelta(hours=49))
        current = self.collect(store, [WEIBO], missing, "test-2")
        timeline = {pipeline.hour(NOW): current, pipeline.hour(NOW) - timedelta(hours=49): yesterday}
        state, = pipeline._coverage(timeline, [WEIBO], {WEIBO.id}, NOW)
        self.assertEqual((state["status"], state["reason"]), ("error", "http_404"))

    def test_missing_archive_turns_stale_after_last_verified_update_ages_out(self):
        store = MemoryStore()
        updated = NOW - timedelta(hours=49)
        self.collect(store, [WEIBO], lambda _: sources.SourceItems(archive_updated_at=updated.isoformat()),
                     now=updated)

        def missing(_):
            raise sources.SourceError("http_404", http_status=404)

        boundary = self.collect(store, [WEIBO], missing, "test-at-48h", updated + timedelta(hours=48))
        self.assertEqual(boundary["sources"][WEIBO.id]["reason"], "http_404")
        stale = self.collect(store, [WEIBO], missing, "test-after-48h", NOW)
        self.assertEqual((stale["sources"][WEIBO.id]["status"], stale["sources"][WEIBO.id]["reason"]),
                         ("stale", "archive_stale"))
        self.assertEqual(stale["row_count"], 0)

    def test_public_check_redacts_confirmed_archive_stale_and_uses_no_retry(self):
        store = MemoryStore()
        summary = []
        calls = []

        def probe(source):
            calls.append(source.id)
            return _ProbeResult(sources.SourceItems(), http_status=200, reason="archive_stale")

        result = run_checks(store, [WEIBO], summary.append, probe_gdelt=False, probe=probe, clock=lambda: NOW)
        self.assertEqual(result, 1)
        self.assertEqual(calls, [WEIBO.id])
        self.assertIn("source=weibo_archive status=stale count=0 skipped=0 http=200 newest_age_min=- reason=archive_stale",
                      summary)


class BaiduHotTests(TestCase):
    source = SOURCE["baidu_hot"]

    @staticmethod
    def board(items, *, nested=True, success=True):
        content = [{"content": items}] if nested else items
        return json.dumps({"success": success, "data": {"cards": [{"content": content}]}}).encode()

    def test_nested_and_flat_boards_skip_pinned_and_build_links(self):
        items = [
            {"isTop": True, "word": "置顶示例"},
            {"index": 1, "word": "合成话题甲", "url": "https://example.org/not-used"},
            {"index": 2, "word": "合成话题 乙&"},
        ]
        for nested in (True, False):
            with self.subTest(nested=nested):
                rows = sources._baidu_hot(self.source, self.board(items, nested=nested))
                self.assertEqual(["合成话题甲", "合成话题 乙&"], [row["title"] for row in rows])
                self.assertEqual([1, 2], [row["rank"] for row in rows])
                self.assertTrue(all(row["url"].startswith("https://m.baidu.com/s?word=") for row in rows))
                self.assertNotIn("example.org", " ".join(row["url"] for row in rows))

    def test_schema_errors_and_malformed_items(self):
        with self.assertRaises(sources.SourceError):
            sources._baidu_hot(self.source, self.board([{"index": 1, "word": "合成"}], success=False))
        with self.assertRaises(sources.SourceError):
            sources._baidu_hot(self.source, b'{"success": true, "data": {"cards": []}}')
        rows = sources._baidu_hot(self.source, self.board([
            {"index": 1, "word": "合成话题"}, {"index": 2, "word": ""}, {"index": 3, "word": "合成话题丙"},
        ]))
        self.assertEqual(1, rows.skipped)
        with self.assertRaises(sources.SourceError):
            sources._baidu_hot(self.source, self.board([{"word": ""}, {"word": None}, {"word": "合成"}]))

    def test_only_the_board_host_is_allowed(self):
        self.assertIn("top.baidu.com", HOSTS)
        self.assertEqual(("china", sources.BAIDU_HOT_URL), sources.SITE_ENDPOINTS["baidu_hot"])


class RedirectDetailTests(TestCase):
    def test_labels_never_include_the_location(self):
        from radar.source_http import DETAIL, redirect_detail
        api = httpx.URL("https://wikimedia.org/api/rest_v1/metrics/x")
        robots = httpx.URL("https://wikimedia.org/robots.txt")
        cases = (
            (api, "/other/path", "RedirectDataSame"),
            (api, "https://www.wikimedia.org/secret-path", "RedirectDataWww"),
            (robots, "https://example.org/private?token=1", "RedirectRobotsOther"),
            (api, "", "RedirectDataSame"),
        )
        for target, location, expected in cases:
            label = redirect_detail(target, location)
            self.assertEqual(expected, label)
            self.assertIsNotNone(DETAIL.fullmatch(label))
