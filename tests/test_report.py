"""Synthetic observations exercise the report without querying live sources."""

from datetime import UTC, datetime, timedelta
import json
import unittest

from radar.report import build_report, trend_key
from radar.scoring import volume_bucket


NOW = datetime(2026, 11, 26, 0, 37, tzinfo=UTC)
OLDER = NOW - timedelta(hours=1)
FIRST = NOW - timedelta(hours=2)


def observed(title, *, geo="MY", time=NOW, source=None, kind="trends", volume="200+",
             language="en", url=None, rank=1, related=(), published_at=None, **fields):
    source = source or f"trends_{geo.lower()}"
    slot = time.replace(minute=0, second=0, microsecond=0)
    return {
        "source_id": source, "kind": kind, "geo": geo, "language": language, "title": title,
        "url": url or f"https://{source}.example/observed", "rank": rank, "volume_raw": volume,
        "published_at": published_at, "related": list(related), "content_id": f"{source}:{title}",
        "observed_at": time.isoformat(), "slot": slot.isoformat(), "run_id": slot.isoformat(), **fields,
    }


def source_status(source="trends_my", *, kind="trends", geo="MY", status="ok", time=NOW):
    return {
        "source_id": source, "kind": kind, "geo": geo, "status": status,
        "observed_at": time.isoformat() if status in {"ok", "empty"} else None,
        "last_success_at": time.isoformat() if time else None,
    }


def report(rows, coverage=None, **kwargs):
    if coverage is None:
        by_source = {"trends_my": source_status()}
        for item in rows:
            by_source.setdefault(item["source_id"], source_status(
                item["source_id"], kind=item["kind"], geo=item["geo"],
            ))
        coverage = list(by_source.values())
    return build_report(rows, coverage, now=NOW, **kwargs)


class RankingTests(unittest.TestCase):
    def test_normalized_topic_keeps_meaningful_punctuation(self):
        self.assertEqual(trend_key("  ＡＩ  Tool Launch "), "ai tool launch")
        self.assertNotEqual(trend_key("C++"), trend_key("C"))

    def test_global_uses_distinct_regions_and_preserves_local_volume(self):
        result = report([
            observed("AI shopping assistant", volume="100+"),
            observed(" AI   Shopping Assistant ", geo="SG", volume="2M+"),
            observed("Football final", volume="50K+"),
            observed("Football final", time=OLDER, volume="50K+"),
        ]).snapshot
        self.assertEqual(["MY", "SG"], result["monitored_regions"][0]["geos"])
        self.assertEqual(2, result["monitored_regions"][0]["peak_regions"])
        self.assertEqual("50K+", result["malaysia"][0]["volume_raw"])
        self.assertEqual("100+", result["malaysia"][1]["volume_raw"])
        self.assertEqual("phase-a-v1", result["malaysia"][1]["algo_version"])
        self.assertEqual("AI / 科技", result["malaysia"][1]["category"])

    def test_secondary_media_association_title_and_syndication(self):
        linked_title = "Local retailers offer discounts on a new shopping festival"
        bernama_link = "https://bernama.example/original?edition=my"
        result = report([
            observed("New shopping festival", related=[{"url": bernama_link, "title": linked_title}]),
            observed(linked_title, source="bernama", kind="news", url=bernama_link),
            observed(linked_title + "!", source="fmt", kind="news", url="https://fmt.example/reprint"),
            observed(linked_title + " today", source="malay_mail", kind="news",
                     url="https://malaymail.example/coverage"),
            observed(linked_title + " today", source="malaysiakini", kind="news",
                     time=NOW - timedelta(hours=13), url="https://mkini.example/old"),
        ]).snapshot
        self.assertEqual("商品 / 消费", result["malaysia"][0]["category"])
        self.assertEqual({"bernama", "malay_mail"}, {row["source_id"] for row in result["malaysia"][0]["media"]})
        self.assertEqual(1, len(result["categories"]["商品 / 消费"]))

    def test_known_wire_publisher_is_not_counted_twice(self):
        urls = ["https://bernama.example/original", "https://fmt.example/republished"]
        result = report([
            observed("AI classroom device", related=[{"url": url} for url in urls]),
            observed("AI device launched", source="bernama", kind="news", url=urls[0]),
            observed("New gadget hits shop shelves", source="fmt", kind="news", url=urls[1], publisher="BERNAMA"),
        ]).snapshot
        self.assertEqual(1, len(result["malaysia"][0]["media"]))

    def test_undated_bernama_story_uses_retained_first_discovery(self):
        url = "https://bernama.example/still-in-feed"
        result = report([
            observed("Local bookshop", related=[{"url": url}]),
            observed("Older report without publication date", source="bernama", kind="news", url=url,
                     first_seen_at=(NOW - timedelta(days=3)).isoformat()),
        ]).snapshot
        self.assertEqual([], result["malaysia"][0]["media"])
        self.assertEqual([], result["local_news"])

    def test_volume_rising_requires_distinct_actual_observations(self):
        sample = [
            observed("New phone", time=OLDER, volume="100+"),
            observed("New phone", volume="200+"),
            observed("First single", volume="300+"),
            observed("Missing baseline", time=OLDER, volume=None),
            observed("Missing baseline", volume="200+"),
            observed("Same hour", time=NOW - timedelta(minutes=5), volume="100+"),
            observed("Same hour", volume="200+"),
        ]
        result = report(sample).snapshot
        self.assertEqual(["New phone"], [item["title"] for item in result["rising"]])
        self.assertEqual("100+", result["rising"][0]["growth"][0]["before"])
        self.assertEqual({"First single", "Missing baseline", "Same hour"}, {item["title"] for item in result["new"]})

    def test_geo_expansion_requires_baseline_for_the_added_region(self):
        rising = [
            observed("New phone", time=OLDER),
            observed("New phone"),
            observed("New phone", geo="SG"),
        ]
        self.assertEqual([], report(rising).snapshot["rising"])
        rising.append(observed("Another observed topic", geo="SG", time=OLDER))
        signal = report(rising).snapshot["rising"][0]["growth"][0]
        self.assertEqual("geos", signal["kind"])
        self.assertEqual(["MY"], signal["before"])
        self.assertEqual(["MY", "SG"], signal["after"])

    def test_valid_empty_source_is_coverage_for_growth(self):
        result = report([
            observed("New phone", time=OLDER),
            observed("New phone"),
            observed("New phone", geo="SG"),
        ], historical_coverage={OLDER.replace(minute=0).isoformat(): {"trends_sg": "empty"}}).snapshot
        self.assertEqual("geos", result["rising"][0]["growth"][0]["kind"])

    def test_independent_local_media_expansion_uses_observed_baseline(self):
        refs = [
            {"url": "https://bernama.example/story"},
            {"url": "https://fmt.example/story"},
        ]
        result = report([
            observed("New phone", time=OLDER, related=refs),
            observed("New phone", related=refs),
            observed("A manufacturer unveiled new mobile devices", source="bernama", kind="news",
                     url=refs[0]["url"], time=OLDER),
            observed("A manufacturer unveiled new mobile devices", source="bernama", kind="news",
                     url=refs[0]["url"]),
            observed("Buyers queue to place pre-orders", source="fmt", kind="news", url=refs[1]["url"]),
        ], historical_coverage={OLDER.replace(minute=0).isoformat(): {"fmt": "empty"}}).snapshot
        self.assertEqual("media", result["rising"][0]["growth"][0]["kind"])
        self.assertEqual(["bernama", "fmt"], result["rising"][0]["growth"][0]["after"])

    def test_retained_first_seen_and_future_rows_do_not_create_false_new_entries(self):
        past = NOW - timedelta(days=4)
        result = report([
            observed("Old topic", first_seen_at=past.isoformat()),
            observed("Too old", time=past),
            observed("Future", time=NOW + timedelta(seconds=1)),
        ]).snapshot
        self.assertEqual(["Old topic"], [item["title"] for item in result["malaysia"]])
        self.assertEqual([], result["new"])
        self.assertEqual([], result["rising"])

    def test_volume_parser_rejects_invalid_and_reads_logged_buckets(self):
        self.assertEqual(200_000, volume_bucket("200,000+"))
        self.assertEqual(1_500, volume_bucket("1.5K+"))
        for bad in (None, "unknown", "1,2+", "0", "-100+", "9e200", "2K junk"):
            self.assertIsNone(volume_bucket(bad))


class ReportTests(unittest.TestCase):
    def test_trend_background_is_escaped_and_only_in_display_projection(self):
        result = report([observed("New shopping festival")])
        baseline_snapshot = json.dumps(result.snapshot)
        baseline_markdown = result.markdown
        baseline_blocks = list(result.blocks)
        self.assertEqual(baseline_blocks, result.display_blocks())

        display = result.display_blocks({
            " NEW   shopping festival ": ("Early plans & <sale>", "Synthetic <Daily>"),
            "Unranked topic": ("Unlisted headline", "Synthetic Daily"),
        })
        rendered = "\n".join(block.html for block in display)
        self.assertEqual(1, rendered.count("Early plans &amp; &lt;sale&gt;"))
        self.assertIn("Synthetic &lt;Daily&gt;", rendered)
        self.assertIn("仅当次展示", rendered)
        self.assertNotIn("Unlisted headline", rendered)
        self.assertEqual(baseline_snapshot, json.dumps(result.snapshot))
        self.assertEqual(baseline_markdown, result.markdown)
        self.assertEqual(baseline_blocks, result.blocks)
        self.assertNotIn("Early plans", result.markdown)

    def test_render_links_and_escape_external_text_for_telegram(self):
        result = report([observed(
            '新商品 & <b>引号"</b> 👩‍💻', language="zh",
            url="https://retailer.example/page?x=1&y=2",
        )])
        self.assertIn("&amp; &lt;b&gt;引号\"&lt;/b&gt; 👩‍💻", result.markdown)
        self.assertIn('href="https://retailer.example/page?x=1&amp;y=2"', result.markdown)
        self.assertIn('[zh]', result.markdown)
        self.assertIn('新商品 & <b>引号"</b> 👩‍💻', "\n".join(block.plain for block in result.blocks))
        self.assertNotIn("javascript:", report([observed("Fake URL", url="javascript:alert(1)")]).markdown)
        json.dumps(result.snapshot)

    def test_freshness_missed_slots_and_local_time_are_explicit(self):
        result = report(
            [observed("Earlier topic", time=OLDER)],
            [source_status(status="error", time=OLDER), source_status("trends_sg", geo="SG", time=FIRST)],
            target_at=NOW.replace(minute=30),
            missed_slots=[FIRST],
        )
        self.assertIn("2026-11-26 08:30 MYT", result.markdown)
        self.assertIn("迟到 7 分钟", result.markdown)
        self.assertIn("最近观测 2026-11-26 07:37 MYT", result.markdown)
        self.assertIn("降级 · Google Trends MY 当前缺失", result.markdown)
        self.assertIn("计划采集缺口 1 槽", result.markdown)
        self.assertTrue(result.snapshot["degraded"])
        self.assertNotIn("Earlier topic", result.markdown)

    def test_valid_empty_trend_snapshot_does_not_reuse_stale_rankings(self):
        result = report(
            [observed("Prior search", time=OLDER)],
            [source_status(status="empty")],
        )
        self.assertIn("Google Trends MY 最新响应有效，暂无热词", result.markdown)
        self.assertNotIn("Prior search", result.markdown)
        self.assertEqual([], result.snapshot["malaysia"])

    def test_missing_local_media_is_distinct_from_observed_zero(self):
        row = observed("New phone")
        missing = report([row], [source_status(), source_status("bernama", kind="news", status="error")])
        empty = report([row], [source_status(), source_status("bernama", kind="news", status="empty")])
        self.assertIn("本地媒体覆盖缺失", missing.markdown)
        self.assertIsNone(missing.snapshot["malaysia"][0]["components"]["local_media"])
        self.assertIn("本地媒体证据 0 家", empty.markdown)
        self.assertEqual(0, empty.snapshot["malaysia"][0]["components"]["local_media"])

    def test_platform_uses_latest_covered_snapshot_and_weather_validity(self):
        hn = {"source": "hn", "kind": "hn", "geo": "GLOBAL"}
        weather = {"source": "weather", "kind": "weather", "geo": "MY", "language": "ms"}
        result = report([
            observed("Old HN article", time=OLDER, **hn),
            observed("New HN article", **hn),
            observed("Active warning", url="https://weather.example/active", **weather,
                     valid_from=OLDER.isoformat(), valid_to=(NOW + timedelta(hours=1)).isoformat()),
            observed("Expired warning", url="https://weather.example/expired", **weather,
                     valid_from=FIRST.isoformat(), valid_to=OLDER.isoformat()),
        ], [
            source_status("hn", kind="hn", geo="GLOBAL"),
            source_status("weather", kind="weather"),
        ])
        self.assertEqual([], result.snapshot["malaysia"])
        self.assertEqual("New HN article", result.snapshot["platforms"]["hn"][0]["title"])
        self.assertEqual(["Active warning"], [item["title"] for item in result.snapshot["weather"]])
        self.assertNotIn("Old HN article", result.markdown)
        self.assertNotIn("Expired warning", result.markdown)
        self.assertIn("CC BY 4.0", result.markdown)

    def test_stale_platform_or_empty_weather_never_reuses_old_items(self):
        result = report([
            observed("Old HN article", source="hn", kind="hn", geo="GLOBAL", time=OLDER),
            observed("Warning", source="weather", kind="weather", time=OLDER,
                     valid_from=FIRST.isoformat(), valid_to=(NOW + timedelta(hours=1)).isoformat()),
        ], [
            source_status("hn", kind="hn", geo="GLOBAL", status="ok", time=NOW - timedelta(hours=4)),
            source_status("weather", kind="weather", status="empty"),
        ])
        self.assertEqual({}, result.snapshot["platforms"])
        self.assertEqual([], result.snapshot["weather"])
        self.assertIn("Hacker News · 数据过旧", result.markdown)
        self.assertIn("最新可用响应无有效警告", result.markdown)
