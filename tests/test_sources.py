"""Synthetic provider schemas only. No captured payloads or live requests."""

import json
import socket
import unittest
from dataclasses import replace
from unittest.mock import patch

import httpx

from radar.source_http import HOSTS, MAX_BODY, OriginGate, SourceHttp, public_address
from radar.sources import SourceError, clean_url, collect_source, load_sources


GOOGLE_RSS = b"""
<rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss">
  <channel>
    <title>Synthetic Trends fixture</title>
    <item>
      <title>Mock AI device &amp; accessories</title>
      <link>https://trends.google.com/trending?geo=MY&amp;utm_source=mock#fictional</link>
      <pubDate>Thu, 26 Nov 2026 07:00:00 +0800</pubDate>
      <ht:approx_traffic>200+</ht:approx_traffic>
      <ht:news_item>
        <ht:news_item_title>Mock tech publisher</ht:news_item_title>
        <ht:news_item_url>https://example.org/article?utm_source=fixture</ht:news_item_url>
        <ht:news_item_source>Mock press</ht:news_item_source>
        <ht:news_item_snippet>Discard this mock body.</ht:news_item_snippet>
      </ht:news_item>
      <ht:news_item>
        <ht:news_item_title>Mock article two</ht:news_item_title>
        <ht:news_item_url>https://example.org/two</ht:news_item_url>
        <ht:news_item_source>Mock press two</ht:news_item_source>
      </ht:news_item>
    </item>
    <item>
      <title>MOCK AI device &amp; Accessories</title>
      <link>https://trends.google.com/trending?geo=MY#mocksecond</link>
      <pubDate>Thu, 26 Nov 2026 07:00:00 +0800</pubDate>
      <ht:approx_traffic>200+</ht:approx_traffic>
    </item>
    <item>
      <title>Another synthetic search</title>
      <link>https://trends.google.com/trending?geo=MY</link>
      <pubDate>Thu, 26 Nov 2026 07:00:00 +0800</pubDate>
      <ht:approx_traffic>500+</ht:approx_traffic>
    </item>
  </channel>
</rss>
"""
NEWS_RSS = b"""
<rss version="2.0">
 <channel>
   <title>Mock Malaysia News</title>
   <language>en-MY</language>
   <link>https://example.org/</link>
   <description>Fixture, not a real news feed.</description>
   <item>
     <title>Mock Malaysia tech item</title>
     <link>https://example.org/news?page=7&amp;utm_source=fixture#jump</link>
     <guid>https://example.org/news?page=7</guid>
     <pubDate>Thu, 26 Nov 2026 07:00:00 +0800</pubDate>
     <description>Never persist this mock description.</description>
     <source url="https://example.com/mock-rss">Synthetic Agency</source>
   </item>
 </channel>
</rss>
"""


class FixtureHttp:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []

    def load(self, url):
        self.urls.append(url)
        raw = self.responses[url]
        if isinstance(raw, Exception):
            raise raw
        return raw if isinstance(raw, bytes) else json.dumps(raw).encode()


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {item.id: item for item in load_sources()}

    def collect(self, key, raw, *, extra=None, source=None):
        source = source or self.sources[key]
        return collect_source(source, FixtureHttp({source.url: raw, **(extra or {})}))

    def test_config_full_approved_scope_but_no_unreviewed_retention(self):
        self.assertEqual(sum(source.kind == "trends" for source in self.sources.values()), 14)
        self.assertEqual(sum(source.kind == "news" for source in self.sources.values()), 4)
        self.assertEqual({x.id for x in self.sources.values() if x.retention == "long_term"}, {"weather"})
        self.assertFalse(self.sources["gdelt"].enabled)

    def test_google_trends_namespace_rank_raw_volume_and_in_slot_dedup(self):
        source = replace(self.sources["trends_my"], retention="long_term", retain_related=True)
        first, second = self.collect(source.id, GOOGLE_RSS, source=source)
        self.assertEqual((first["rank"], second["rank"]), (1, 3))
        self.assertEqual(first["title"], "Mock AI device & accessories")
        self.assertEqual(first["volume_raw"], "200+")
        self.assertEqual(first["published_at"], "2026-11-25T23:00:00+00:00")
        self.assertTrue(first["url"].endswith("#fictional"))
        self.assertEqual([item["publisher"] for item in first["related"]], ["Mock press", "Mock press two"])
        self.assertEqual(first["related"][0]["url"], "https://example.org/article")
        self.assertNotIn("Discard this mock body", json.dumps(first))
        self.assertNotEqual(first["content_id"], second["content_id"])

    def test_google_article_metadata_stays_off_without_field_approval(self):
        result = self.collect("trends_my", GOOGLE_RSS)
        self.assertEqual(result[0]["related"], [])

    def test_trend_missing_historical_field_is_failure_not_zero(self):
        feed = GOOGLE_RSS.replace(b"<ht:approx_traffic>200+</ht:approx_traffic>", b"")
        with self.assertRaisesRegex(SourceError, "^trend_schema$"):
            self.collect("trends_my", feed)

    def test_news_all_four_ids_with_missing_bernama_pubdate(self):
        for key in ("malaysiakini", "malay_mail", "fmt", "bernama"):
            with self.subTest(key=key):
                feed = NEWS_RSS if key != "bernama" else NEWS_RSS.replace(
                    b"<pubDate>Thu, 26 Nov 2026 07:00:00 +0800</pubDate>", b""
                )
                item, = self.collect(key, feed)
                self.assertEqual(item["source_id"], key)
                self.assertEqual(item["url"], "https://example.org/news?page=7")
                self.assertEqual(item["language"], "en-MY")
                self.assertEqual(item["publisher"], "Synthetic Agency")
                self.assertEqual(
                    item["published_at"], None if key == "bernama" else "2026-11-25T23:00:00+00:00"
                )
                self.assertNotIn("mock description", json.dumps(item))

    def test_invalid_xml_and_dtd_are_rejected(self):
        for body in (
            b"<rss><channel>",
            b"<!DOCTYPE rss SYSTEM 'https://example.org/no-network'><rss/>",
        ):
            with self.subTest(body=body), self.assertRaisesRegex(SourceError, "^invalid_xml$"):
                self.collect("trends_my", body)

    def test_bernama_mislabeled_encoding_fix_is_limited_to_mojibake(self):
        fixture = b'<?xml version="1.0" encoding="ISO-8859-1"?>' + NEWS_RSS.lstrip()
        fixture = fixture.replace(b"Mock Malaysia tech item", "Mock item – synthetic".encode())
        row, = self.collect("bernama", fixture)
        self.assertEqual(row["title"], "Mock item – synthetic")
        genuine = fixture.replace("Mock item – synthetic".encode(), b"Caf\xe9 example")
        row, = self.collect("bernama", genuine)
        self.assertEqual(row["title"], "Café example")

    def test_hacker_news_preserves_rank_and_ignores_author_text_and_job(self):
        stem = "https://hacker-news.firebaseio.com/v0/item/"
        first, second = self.collect("hn", [1, 2, 3], extra={
            stem + "1.json": {
                "id": 1, "type": "story", "title": "Mock Ask HN story", "time": 1_795_641_600,
                "by": "fictional test user", "text": "discarded mock body", "score": 9,
            },
            stem + "2.json": {"id": 2, "type": "job"},
            stem + "3.json": {
                "id": 3, "type": "story", "title": "Mock other story", "url": "https://example.org/article",
            },
        })
        self.assertEqual(first["url"], "https://news.ycombinator.com/item?id=1")
        self.assertEqual(first["volume_raw"], "9")
        self.assertEqual(second["rank"], 3)
        self.assertNotIn("discarded mock body", json.dumps(first))
        self.assertNotIn("fictional test user", json.dumps(first))

    def test_hacker_news_item_failure_does_not_persist_partial_as_success(self):
        stem = "https://hacker-news.firebaseio.com/v0/item/"
        with self.assertRaisesRegex(SourceError, "^hn_item_http_429$"):
            self.collect("hn", [1, 2], extra={
                stem + "1.json": {"id": 1, "type": "story", "title": "Mock story"},
                stem + "2.json": SourceError("http_429", 15),
            })

    def test_hacker_news_top_30_bounds(self):
        source = self.sources["hn"]
        stem = "https://hacker-news.firebaseio.com/v0/item/"
        http = FixtureHttp({
            source.url: list(range(1, 33)),
            **{f"{stem}{i}.json": {"id": i, "type": "story", "title": f"Mock story {i}"} for i in range(1, 31)},
        })
        self.assertEqual(len(collect_source(source, http)), 30)
        self.assertEqual(len(http.urls), 31)

    def test_bluesky_explicit_topic_and_relative_url_only(self):
        first, second = self.collect("bluesky", {
            "topics": [
                {"topic": "mock AI", "displayName": "Mock AI", "link": "/search?q=mock+AI"},
                {"topic": "Mock Shopping", "link": "https://example.org/third-party"},
            ],
            "suggested": [{"topic": "Personalized suggestion ignored"}],
        })
        self.assertEqual(first["url"], "https://bsky.app/search?q=mock+AI")
        self.assertEqual(second["url"], "https://bsky.app/search?q=Mock+Shopping")

    def test_mastodon_separate_platform_feeds_and_preview_body_removed(self):
        tag, = self.collect("mastodon_tags", [
            {"name": "mocktag", "url": "https://mastodon.social/tags/mocktag", "history": []},
        ])
        link, = self.collect("mastodon_links", [
            {"title": "Mock Link", "url": "https://example.org/story", "html": "<script />"},
        ])
        self.assertEqual(tag["title"], "#mocktag")
        self.assertEqual(link["kind"], "mastodon")
        self.assertNotIn("<script", json.dumps(link))

    def test_weather_warning_validity_timezone_attribution_and_no_body(self):
        current = {
            "warning_issue": {"issued": "2090-09-01T16:00:00", "title_bm": "Mock warning"},
            "valid_from": "2090-09-01T16:00:00", "valid_to": "2090-09-02T16:00:00",
            "text_bm": "Discard mock weather body",
        }
        expired = {
            "warning_issue": {"issued": "2000-09-01T16:00:00", "title_en": "Expired mock warning"},
            "valid_from": "2000-09-01T16:00:00", "valid_to": "2000-09-02T16:00:00",
        }
        row, = self.collect("weather", [current, expired])
        self.assertEqual(row["published_at"], "2090-09-01T08:00:00+00:00")
        self.assertEqual(row["valid_to"], "2090-09-02T08:00:00+00:00")
        self.assertEqual(row["language"], "ms")
        self.assertIn("CC BY 4.0", row["publisher"])
        self.assertNotIn("Discard mock weather body", json.dumps(row))
        self.assertEqual(self.collect("weather", []), [])

    def test_gdelt_is_disabled_without_request(self):
        http = FixtureHttp({})
        with self.assertRaisesRegex(SourceError, "^source_disabled$"):
            collect_source(self.sources["gdelt"], http)
        self.assertEqual(http.urls, [])

    def test_pending_source_does_not_open_default_network_client(self):
        with patch("radar.sources.httpx.Client") as client:
            with self.assertRaisesRegex(SourceError, "^retention_approval_required$"):
                collect_source(self.sources["trends_my"])
            client.assert_not_called()

    def test_canonical_urls_reject_auth_private_literals_and_scripts(self):
        for url in (
            "file:///etc/hostname", "javascript:mock", "https://account@example.org/mock",
            "https://127.0.0.1/mock", "https://0x7f.0x0.0x1/mock", "https://example.local/mock",
            "https://example.org/\nmock",
        ):
            self.assertIsNone(clean_url(url), repr(url))
        self.assertEqual(
            clean_url("https://EXAMPLE.org/a?utm_campaign=mock&id=7&access_token=mock#top"),
            "https://example.org/a?id=7",
        )


class BytesStream(httpx.SyncByteStream):
    def __init__(self, body):
        self.body = body

    def __iter__(self):
        yield self.body


class HttpTests(unittest.TestCase):
    url = "https://trends.google.com/trending/rss?geo=MY"

    def http(self, handler, sleeps=None):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return SourceHttp(
            client, resolver=lambda _: "192.0.2.10",
            sleep=(sleeps if sleeps is not None else []).append,
            origins={name: OriginGate() for name in HOSTS},
        )

    def test_robots_wildcards_and_pinned_origin(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, stream=BytesStream(b"User-agent: *\nDisallow: /trending/*\n"))

        with self.assertRaisesRegex(SourceError, "^robots_denied$"):
            self.http(handler).load(self.url)
        request, = requests
        self.assertEqual(request.url.host, "192.0.2.10")
        self.assertEqual(request.headers["Host"], "trends.google.com")
        self.assertEqual(request.extensions["sni_hostname"], "trends.google.com")
        self.assertIn("GlobalTrendRadar", request.headers["User-Agent"])

    def test_retry_after_and_never_follow_redirects(self):
        requests = []
        sleeps = []

        def handler(request):
            requests.append(request.url.path)
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            if len(requests) == 2:
                return httpx.Response(429, headers={"Retry-After": "3"})
            return httpx.Response(302, headers={"Location": "https://127.0.0.1/private"})

        with self.assertRaisesRegex(SourceError, "^http_302$"):
            self.http(handler, sleeps).load(self.url)
        self.assertEqual(requests, ["/robots.txt", "/trending/rss", "/trending/rss"])
        self.assertIn(3, sleeps)

    def test_long_provider_backoff_stops_same_host_without_followup(self):
        requests = []

        def handler(request):
            requests.append(request.url.path)
            return httpx.Response(404 if request.url.path == "/robots.txt" else 429,
                                  headers={"Retry-After": "600"})

        http = self.http(handler)
        with self.assertRaisesRegex(SourceError, "^http_429$"):
            http.load(self.url)
        with self.assertRaisesRegex(SourceError, "^host_backoff$"):
            http.load(self.url.replace("MY", "SG"))
        self.assertEqual(requests, ["/robots.txt", "/trending/rss"])

    def test_oversized_and_compressed_responses_are_rejected(self):
        for headers, content, reason in (
            ({}, b"X" * (MAX_BODY + 1), "response_too_large"),
            ({"Content-Encoding": "gzip"}, b"mock encoded data", "response_encoding"),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(SourceError, f"^{reason}$"):
                def handler(request):
                    if request.url.path == "/robots.txt":
                        return httpx.Response(404)
                    return httpx.Response(200, headers=headers, stream=BytesStream(content))
                self.http(handler).load(self.url)

    def test_dns_non_public_resolution_is_rejected_even_among_public_answers(self):
        addresses = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443)),
        ]
        with patch("radar.source_http.socket.getaddrinfo", return_value=addresses):
            with self.assertRaisesRegex(SourceError, "^private_address_blocked$"):
                public_address("trends.google.com")


if __name__ == "__main__":
    unittest.main()
