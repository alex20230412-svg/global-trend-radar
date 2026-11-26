from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
import yaml

from radar import livecheck
from radar.pipeline import partition
from radar.source_http import OriginGate, SourceError
from radar.sources import SourceItems, load_sources
from radar.storage import CODE_REPO, read_json


NOW = datetime(2031, 2, 3, 1, 17, tzinfo=UTC)
TITLE = "SENTINEL_TOPIC_PRIVATE_INPUT"
URL = "https://example.invalid/SENTINEL_PRIVATE_URL"
BODY = "SENTINEL_UPSTREAM_BODY"
ERROR = "SENTINEL_PRIVATE_EXCEPTION"
ENV = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_REPOSITORY": CODE_REPO,
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_WORKFLOW_REF": f"{CODE_REPO}/.github/workflows/live-check.yml@refs/heads/main",
}
SOURCE_LINE = (
    r"source=[a-z0-9_]+ status=(?:ok|empty|error) count=[0-9]+ skipped=[0-9]+ "
    r"http=(?:[1-5][0-9]{2}|-) newest_age_min=(?:[0-9]+|-) reason=[a-z0-9_-]+"
)
REPORT_LINE = (
    r"report parts=[0-9]+ chars=(?:[0-9]+(?:,[0-9]+)*|-) my=[0-9]+ other=[0-9]+ fresh=[0-9]+ "
    r"with_context=[0-9]+ local_news=[0-9]+ platforms=[0-9]+ weather=[0-9]+ degraded=(?:true|false)"
)


class LiveCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources = {source.id: source for source in load_sources()}
        cls.trends = replace(sources["trends_my"], enabled=True, retention="long_term", retain_related=True)
        cls.news = replace(sources["bernama"], enabled=True, retention="long_term")
        cls.weather = replace(sources["weather"], enabled=True, retention="long_term")
        cls.gdelt = sources["gdelt"]

    def _mock_http(self, handler):
        client = httpx.Client
        source_http = livecheck._ProbeHttp
        origins = {"trends.google.com": OriginGate(), "www.bernama.com": OriginGate(),
                   "api.data.gov.my": OriginGate()}
        self.enterContext(patch.object(
            livecheck.httpx, "Client",
            side_effect=lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
        ))
        self.enterContext(patch.object(
            livecheck, "_ProbeHttp",
            side_effect=lambda http: source_http(
                http, origins=origins, resolver=lambda _host: "192.0.2.7", sleep=lambda _delay: None,
            ),
        ))

    def test_only_the_manual_default_branch_of_this_repo_is_authorized(self):
        stdout = StringIO()
        with redirect_stdout(stdout), patch.object(livecheck, "load_sources") as load:
            for key, unsafe in {
                "GITHUB_ACTIONS": "",
                "GITHUB_REPOSITORY": "other/global-trend-radar",
                "GITHUB_REF": "refs/heads/feature",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_WORKFLOW_REF": f"{CODE_REPO}/.github/workflows/collect.yml@refs/heads/main",
            }.items():
                with self.subTest(key=key):
                    self.assertEqual(livecheck.main({**ENV, key: unsafe}), 1)
            load.assert_not_called()
        self.assertEqual("", stdout.getvalue())

    def test_workflow_has_only_a_manual_default_branch_gate_and_read_permission(self):
        path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "live-check.yml"
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        self.assertEqual({"workflow_dispatch"}, set(workflow["on"]))
        self.assertEqual({"contents": "read"}, workflow["permissions"])
        self.assertEqual("radar-live-check", workflow["concurrency"]["group"])
        job = workflow["jobs"]["check"]
        self.assertIn("github.ref == 'refs/heads/main'", job["if"])
        self.assertIn(CODE_REPO, job["if"])
        self.assertNotIn("environment", job)
        self.assertLessEqual(int(job["timeout-minutes"]), 10)
        self.assertEqual("false", job["steps"][0]["with"]["persist-credentials"])
        for step in job["steps"]:
            if "uses" in step:
                self.assertRegex(step["uses"], r"@[0-9a-f]{40}$")
        script = path.read_text(encoding="utf-8")
        self.assertNotIn("secrets.", script)
        self.assertNotIn("RADAR_STAGE", script)
        self.assertIn("python -m radar.livecheck", script)

    def test_probe_once_through_source_http_and_offline_retry_of_failed_source(self):
        requests = []
        rss = f'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss">
  <channel><title>Fixture</title><item><title>{TITLE}</title>
    <pubDate>Mon, 03 Feb 2031 00:55:00 GMT</pubDate><ht:approx_traffic>200+</ht:approx_traffic>
    <ht:news_item><ht:news_item_title>{BODY}</ht:news_item_title><ht:news_item_url>{URL}</ht:news_item_url>
    <ht:news_item_source>Example</ht:news_item_source></ht:news_item>
  </item></channel>
</rss>'''.encode()

        def handler(request):
            host = request.headers["Host"]
            requests.append((host, request.url.path))
            if request.url.path == "/robots.txt":
                return httpx.Response(200, stream=httpx.ByteStream(b"User-agent: *\nAllow: /\n"))
            if host == "trends.google.com":
                return httpx.Response(200, stream=httpx.ByteStream(rss))
            if host == "api.data.gov.my":
                return httpx.Response(200, stream=httpx.ByteStream(b"[]"))
            return httpx.Response(403, stream=httpx.ByteStream(BODY.encode()))

        self._mock_http(handler)
        with TemporaryDirectory() as directory:
            store = livecheck._LocalGitStore(directory)
            lines = []
            code = livecheck.run_checks(
                store, [self.trends, self.news, self.weather], lines.append,
                probe_gdelt=False, clock=lambda: NOW,
            )
            first = read_json(store, "runs/live-check-1.json")
            second = read_json(store, "runs/live-check-2.json")
            self.assertEqual(["trends_my", "bernama", "weather"], first["attempted_sources"])
            self.assertEqual(["bernama"], second["attempted_sources"])
            self.assertEqual(1, first["rows_added"])
            self.assertEqual(0, second["rows_added"])
            self.assertTrue(store.read(f"observations/{partition(NOW)}.jsonl.gz"))
            local_git = subprocess.run(
                ["git", "log", "--format=%s"], cwd=directory, env=store.git_env, capture_output=True, check=True,
            )
            self.assertEqual(
                [b"Archive private radar report", b"Record hourly radar state", b"Record hourly radar state"],
                local_git.stdout.splitlines(),
            )
            self.assertEqual(b"", subprocess.run(
                ["git", "remote"], cwd=directory, env=store.git_env, capture_output=True, check=True,
            ).stdout)
        self.assertEqual(1, code)
        self.assertCountEqual(
            [("trends.google.com", "/robots.txt"), ("trends.google.com", "/trending/rss"),
             ("www.bernama.com", "/robots.txt"), ("www.bernama.com", "/en/rssfeed.php"),
             ("api.data.gov.my", "/robots.txt"), ("api.data.gov.my", "/weather/warning/")],
            requests,
        )
        self.assertEqual(
            "source=trends_my status=ok count=1 skipped=0 http=200 newest_age_min=22 reason=-", lines[0],
        )
        self.assertEqual(
            "source=bernama status=error count=0 skipped=0 http=403 newest_age_min=- reason=http_403", lines[1],
        )
        self.assertEqual(
            "source=weather status=empty count=0 skipped=0 http=200 newest_age_min=- reason=-", lines[2],
        )
        self.assertRegex(lines[3], REPORT_LINE)
        self.assertIn("my=1 other=0 fresh=1 with_context=1", lines[3])
        self.assertIn("weather=0 degraded=true", lines[3])
        for sentinel in (TITLE, URL, BODY):
            self.assertNotIn(sentinel, "\n".join(lines))

    def test_main_suppresses_titles_urls_provider_body_and_noisy_exceptions(self):
        def noisy_source(_source, _transport):
            print(f"{TITLE} {URL} {BODY}")
            import sys
            print(ERROR, file=sys.stderr)
            raise SourceError(ERROR)

        with patch.object(livecheck, "load_sources", return_value=[self.trends]), patch.object(
            livecheck, "collect_source", side_effect=noisy_source,
        ):
            stdout, stderr = StringIO(), StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(1, livecheck.main(ENV))
        self.assertEqual("", stderr.getvalue())
        source, report = stdout.getvalue().splitlines()
        self.assertRegex(source, SOURCE_LINE)
        self.assertRegex(report, REPORT_LINE)
        self.assertIn("reason=source_unavailable", source)
        for sentinel in (TITLE, URL, BODY, ERROR):
            self.assertNotIn(sentinel, stdout.getvalue())

    def test_report_failure_is_one_bounded_degraded_line(self):
        def failed_check(_store, _sources, emit, **_options):
            emit("report parts=1 chars=2 my=1 other=0 fresh=0 with_context=0 local_news=0 platforms=0 "
                 "weather=0 degraded=false")
            raise RuntimeError(f"{ERROR} {URL}")

        with patch.object(livecheck, "run_checks", side_effect=failed_check):
            stdout, stderr = StringIO(), StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(1, livecheck.main(ENV))
        self.assertEqual("", stderr.getvalue())
        self.assertEqual(
            "report parts=0 chars=- my=0 other=0 fresh=0 with_context=0 local_news=0 platforms=0 "
            "weather=0 degraded=true\n", stdout.getvalue(),
        )

    def test_optional_gdelt_error_does_not_enter_local_collection_or_fail_the_digest(self):
        seen = []

        def probe(source):
            seen.append((source.id, source.enabled, source.retention))
            if source.kind == "gdelt":
                return livecheck._ProbeResult(SourceItems(), 503, "http_503")
            return livecheck._ProbeResult(SourceItems([{
                "title": TITLE, "url": URL, "content_id": "fixture-id",
                "volume_raw": "200+", "published_at": (NOW - timedelta(minutes=5)).isoformat(),
            }]), 200)

        with TemporaryDirectory() as directory:
            store = livecheck._LocalGitStore(directory)
            lines = []
            self.assertEqual(0, livecheck.run_checks(
                store, [self.trends, self.gdelt], lines.append, probe=probe, clock=lambda: NOW,
            ))
            audit = read_json(store, "runs/live-check-2.json")
            self.assertEqual("disabled", audit["sources"]["gdelt"]["status"])
            self.assertEqual([], audit["attempted_sources"])
        self.assertEqual([("trends_my", True, "long_term"), ("gdelt", True, "long_term")], seen)
        self.assertIn("source=gdelt status=error", lines[1])
        self.assertIn("report parts=1", lines[2])
        self.assertIn("degraded=false", lines[2])

    def test_replay_rejects_retrying_a_successful_source_even_if_rows_are_unchanged(self):
        manifest = {"sources": {"trends_my": {"status": "ok"}}, "sha256": "fixture", "row_count": 1}
        audit = {"attempted_sources": ["trends_my"], "rows_added": 0}
        with patch.object(livecheck, "read_json", return_value=audit), self.assertRaisesRegex(
            ValueError, "^non_idempotent_local_collection$",
        ):
            livecheck._check_replay(None, NOW, manifest, manifest, [self.trends], b"same archive")

    def test_freshness_uses_available_published_or_gdelt_index_time(self):
        self.assertEqual(8, livecheck._newest_age([
            {"published_at": "broken"}, {"published_at": (NOW + timedelta(hours=1)).isoformat()},
            {"seen_at": (NOW - timedelta(minutes=8, seconds=42)).isoformat()},
            {"published_at": (NOW - timedelta(days=1)).isoformat()},
        ], NOW))
        self.assertIsNone(livecheck._newest_age([{"published_at": None}], NOW))


if __name__ == "__main__":
    unittest.main()
