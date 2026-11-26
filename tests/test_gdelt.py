"""GDELT DOC adapters exercised with synthesized responses and an injected clock."""

import json
import unittest
from dataclasses import replace

import httpx

from radar.source_http import GDELT_HOST, OriginGate, SourceError, SourceHttp
from radar.sources import collect_source, load_sources


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


def article(path="synthetic", **fields):
    return {
        "url": f"https://example.org/{path}?utm_source=tracking",
        "seendate": "20261126T020000Z",
        "title": "Synthetic article · 气象",
        "sourcecountry": "Malaysia",
        "language": "Malay",
        "domain": "discard.example",
        "url_mobile": "https://example.org/discard",
        "socialimage": "https://example.org/discard.png",
        "description": "Synthetic discarded article text",
        **fields,
    }


class GdeltTests(unittest.TestCase):
    def setUp(self):
        self.configured = next(source for source in load_sources() if source.id == "gdelt")
        self.candidate = replace(self.configured, enabled=True, retention="long_term")
        self.clock = Clock()
        self.requests = []

    def transport(self, replies, robots=b"User-agent: *\nAllow: /api/v2/doc/doc\n"):
        replies = iter(replies)

        def handle(request):
            self.requests.append((request, self.clock()))
            if request.url.path == "/robots.txt":
                return httpx.Response(200, stream=httpx.ByteStream(robots))
            reply = next(replies)
            if isinstance(reply, httpx.Response):
                return reply
            return httpx.Response(200, stream=httpx.ByteStream(json.dumps(reply).encode()))

        client = httpx.Client(transport=httpx.MockTransport(handle), trust_env=False)
        self.addCleanup(client.close)
        return SourceHttp(
            client, resolver=lambda _host: "8.8.8.8", sleep=self.clock.sleep, clock=self.clock,
            origins={GDELT_HOST: OriginGate()},
        )

    def test_candidate_remains_disabled_by_default(self):
        self.assertFalse(self.configured.enabled)
        self.assertEqual(self.configured.retention, "pending")
        with self.assertRaisesRegex(SourceError, "^source_disabled$"):
            collect_source(self.configured, self.transport([]))
        self.assertEqual(self.requests, [])

    def test_fixed_queries_clean_metadata_dedupe_and_host_pacing(self):
        candidate = article()
        world = article("worldwide", sourcecountry="United States", language="English")
        rows = collect_source(self.candidate, self.transport([
            {"articles": [candidate]}, {"articles": [candidate, world]},
        ]))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows.skipped, 0)
        self.assertEqual(
            rows[0],
            {"title": "Synthetic article · 气象", "url": "https://example.org/synthetic",
             "language": "Malay", "source_country": "Malaysia", "seen_at": "2026-11-26T02:00:00+00:00",
             "kind": "gdelt", "source_id": "gdelt", "geo": "GLOBAL", "rank": None, "volume_raw": None,
             "published_at": None, "related": [], "content_id": rows[0]["content_id"]},
        )
        self.assertEqual(rows[1]["source_country"], "United States")
        self.assertEqual(rows[1]["language"], "English")
        self.assertEqual([time for _, time in self.requests], [100.0, 105.0, 110.0])
        self.assertEqual([request.url.path for request, _ in self.requests],
                         ["/robots.txt", "/api/v2/doc/doc", "/api/v2/doc/doc"])
        for request, _ in self.requests:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.headers["host"], GDELT_HOST)
            # GDELT routinely needs longer than the 5 s default read timeout.
            self.assertEqual(request.extensions["timeout"]["read"], 20.0)
            self.assertEqual(request.extensions["timeout"]["connect"], 4.0)
        my_params = self.requests[1][0].url.params
        world_params = self.requests[2][0].url.params
        self.assertIn("Malaysia", my_params["query"])
        self.assertIn("international", world_params["query"])
        for params in (my_params, world_params):
            self.assertEqual({key: params[key] for key in params if key != "query"},
                             {"mode": "ArtList", "format": "json", "timespan": "1h",
                              "sort": "HybridRel", "maxrecords": "20"})

    def test_empty_response_is_valid_and_malformed_entries_are_counted(self):
        rows = collect_source(self.candidate, self.transport([
            {"articles": []}, {"articles": [article(), article("bad-date", seendate="unknown")]},
        ]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.skipped, 1)

    def test_robots_wait_longer_than_minimum_takes_precedence(self):
        rows = collect_source(self.candidate, self.transport(
            [{"articles": []}, {"articles": []}],
            b"User-agent: *\nAllow: /api/v2/doc/doc\nCrawl-delay: 7\n",
        ))
        self.assertEqual(rows, [])
        self.assertEqual([time for _, time in self.requests], [100.0, 107.0, 114.0])

    def test_robots_denial_stops_before_feed_requests(self):
        http = self.transport([], b"User-agent: *\nDisallow: /api/\n")
        with self.assertRaisesRegex(SourceError, "^robots_denied$"):
            collect_source(self.candidate, http)
        self.assertEqual(len(self.requests), 1)

    def test_second_request_error_is_not_masked_by_first_results(self):
        http = self.transport([{"articles": [article()]}, httpx.Response(429)])
        with self.assertRaisesRegex(SourceError, "^http_429$") as failure:
            collect_source(self.candidate, http)
        self.assertEqual(failure.exception.http_status, 429)
        self.assertEqual(len(self.requests), 3)

    def test_invalid_envelope_stops_before_second_query(self):
        http = self.transport([{"not_articles": []}])
        with self.assertRaisesRegex(SourceError, "^json_schema$"):
            collect_source(self.candidate, http)
        self.assertEqual(len(self.requests), 2)


if __name__ == "__main__":
    unittest.main()
