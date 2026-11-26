"""Offline checks for the approved Malaysian Chinese-edition RSS."""

import unittest
from unittest.mock import Mock

from radar.source_http import HOSTS
from radar.sources import collect_source, load_sources


class ChineseSourceTests(unittest.TestCase):
    def test_malaysiakini_zh_uses_the_official_news_feed_and_only_metadata(self):
        source = next(source for source in load_sources() if source.id == "malaysiakini_zh")
        self.assertEqual(("news", "MY", "zh", True, "long_term"),
                         (source.kind, source.geo, source.language, source.enabled, source.retention))
        self.assertIn("www.malaysiakini.com", HOSTS)
        http = Mock()
        http.load.return_value = """
            <rss version="2.0"><channel><title>合成订阅</title><language>en-US</language><item>
                <title>合成新闻</title>
                <link>https://example.org/news?utm_source=feed</link>
                <description>正文哨兵</description>
                <author>作者哨兵</author>
                <pubDate>Thu, 26 Nov 2026 02:00:00 GMT</pubDate>
                <source url="https://example.org/feed">合成媒体</source>
            </item></channel></rss>
        """.encode()

        [row] = collect_source(source, http)

        http.load.assert_called_once_with("https://www.malaysiakini.com/zh/rss/news.rss")
        self.assertEqual(
            ("malaysiakini_zh", "MY", "zh", "合成新闻", "https://example.org/news",
             "2026-11-26T02:00:00+00:00", "合成媒体"),
            (row["source_id"], row["geo"], row["language"], row["title"], row["url"], row["published_at"],
             row["publisher"]),
        )
        self.assertNotIn("哨兵", repr(row))
