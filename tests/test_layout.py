"""Telegram table width and safe splitting of complete formatting blocks."""

import unittest

from radar.delivery import DeliveryError, _message_text, split_parts
from radar.layout import quote_block, quote_blocks, table_block, table_header, table_row, table_width


class LayoutTests(unittest.TestCase):
    def test_table_protects_columns_truncates_and_reserves_marker(self):
        rows = [
            table_row(1, "200K+", "马来西亚很长的标题超过移动端一行的宽度", marker=True),
            table_row(2, "12K", "另外一个新话题", marker=True),
        ]
        self.assertTrue(rows[0].startswith(" 1    200K+  "))
        self.assertTrue(rows[1].startswith(" 2      12K  "))
        self.assertTrue(rows[0].endswith("… 🆕"))
        self.assertTrue(all(table_width(row) <= 28 for row in rows))
        apps = table_row(1, None, "用来看演出的应用", app_name="SampleAppTitle", marker=True)
        self.assertTrue(apps.startswith(" 1  SampleAppTit "))
        self.assertLessEqual(table_width(apps), 28)
        topic = table_row(1, None, "法定假期与考试日期公布的专题", suffix="（微博）", marker=True)
        self.assertTrue(topic.endswith("（微博） 🆕"))

    def test_markup_does_not_split_atomic_blocks(self):
        table = table_block([("热搜", table_header("搜索量"), [
            table_row(index, "100K+", "合成标题还可以更长一点")
            for index in range(1, 70)
        ])])
        quote = quote_block("为什么热", [("长理由" * 22, "https://example.org/demo") for _ in range(42)])
        parts = split_parts([table, quote], label="smoke-test")
        self.assertEqual(2, len(parts))
        self.assertIn("<pre>", parts[0])
        self.assertTrue(parts[0].endswith("</pre>"))
        self.assertNotIn("<a", parts[0])
        self.assertIn("<blockquote expandable>", parts[1])
        self.assertTrue(parts[1].endswith("</blockquote>"))
        self.assertIn("<a href=", parts[1])
        for part in parts:
            self.assertTrue(_message_text(part))

    def test_pre_rejects_nested_markup(self):
        for content in ("<pre><a href=\"https://example.org\">链接</a></pre>",
                        "<pre><b>bold</b></pre>", "<blockquote>非可折叠</blockquote>",
                        "<blockquote expandable><pre>表格</pre></blockquote>"):
            with self.subTest(content=content), self.assertRaises(DeliveryError):
                _message_text(content)

    def test_detail_blocks_stay_within_raw_html_limits_for_long_links(self):
        rows = [(f"第 {index} 行", f"https://example.org/{index}/" + "a" * 1400) for index in range(30)]
        blocks = list(quote_blocks("为什么热", rows))
        self.assertGreater(len(blocks), 1)
        parts = split_parts(blocks, label="smoke-test")
        self.assertEqual(len(rows), sum(part.count("<a href=") for part in parts))
        self.assertEqual(len(blocks), sum(part.count("<blockquote expandable>") for part in parts))
