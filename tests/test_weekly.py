"""Offline weekly aggregation, routing, privacy and retry coverage."""

from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import yaml

from radar import live
from radar.delivery import TelegramClient, _message_text
from radar.storage import StorageError, json_bytes
from radar.weekly import WEEKLY_CRON, build_weekly, prepare_weekly, weekly_archive_key, weekly_key


SUNDAY = datetime(2026, 11, 29, 1, 0, tzinfo=timezone.utc)
MONDAY = date(2026, 11, 23)
WEEK = "weekly-2026-W48"


class Store:
    def __init__(self):
        self.files = {}

    def read(self, key):
        return self.files.get(key)

    def publish(self, files, _message):
        self.files.update(files)

    def seed_daily(self, day, entries, *, states=("SENT",), report_type="daily"):
        report_id = f"{report_type}-{day.isoformat()}"
        payload = {"parts": ["合成样本"] * len(states)}
        if entries is not None:
            payload["brief_entries"] = entries
        files = {
            f"reports/{day:%Y/%m/%d}/{report_id}.json": json_bytes(payload),
            f"deliveries/{report_id}.json": json_bytes({"parts": [
                {"delivery_state": state} for state in states
            ]}),
        }
        self.publish(files, "synthetic")


def entry(key, title, section="malaysia", *, url=None):
    return {"key": key, "section": section, "title": title, "url": url or f"https://example.org/{key}"}


def decoded(parts):
    return "\n".join(_message_text(part) for part in parts)


class Ideas:
    def __init__(self, value=None):
        self.prompt = None
        self.value = value

    def write(self, _system, prompt):
        self.prompt = json.loads(prompt)
        return json.dumps(self.value, ensure_ascii=False), "ok", "synthetic"


class WeeklyContentTests(unittest.TestCase):
    def test_iso_year_and_week_are_chosen_from_malaysia_date(self):
        self.assertEqual("weekly-2026-W53", weekly_key(date(2027, 1, 3)))
        self.assertEqual("weekly-2027-W01", weekly_key(date(2027, 1, 4)))

    def test_rank_uses_distinct_days_and_does_not_count_a_preview_or_unknown_send(self):
        store = Store()
        a = entry("a", "合成持续话题")
        b = entry("b", "合成稳定话题")
        chart_sections = [
            entry("music", "合成歌曲", "music"), entry("app", "合成应用", "apps"),
            entry("wiki", "合成维基条目", "wiki"), entry("china", "合成中国话题", "china"),
        ]
        for offset in range(7):
            entries = [a, *chart_sections]
            if offset <= 4:
                entries += [b, b]
            if offset == 6:
                entries += [entry("new", "合成本周新话题")]
            store.seed_daily(MONDAY + timedelta(days=offset), entries)
        store.seed_daily(MONDAY - timedelta(days=2), [a])
        store.seed_daily(MONDAY + timedelta(days=5), [entry("never", "私有未送达哨兵")],
                         states=("CONFIRMED", "UNKNOWN"))
        store.seed_daily(MONDAY + timedelta(days=3), [entry("preview", "只在预览中出现的哨兵")],
                         report_type="preview-0830")
        parts = build_weekly(store, SUNDAY.date(), WEEK)
        text = decoded(parts)
        self.assertIn("本周已送达且可统计 6/7 天 · 前一周 1/7 天", text)
        self.assertIn("前一周记录不全，新冒头榜仅按已有日报比较", text)
        self.assertIn("1. 合成持续话题 · 6 天", text)
        self.assertIn("2. 合成稳定话题 · 5 天", text)
        self.assertIn("1. 合成本周新话题 · 1 天", text)
        self.assertIn("合成歌曲 · 6 天", text)
        self.assertIn("合成应用 · 6 天", text)
        self.assertIn("合成维基条目 · 6 天", text)
        self.assertIn("合成中国话题 · 6 天", text)
        self.assertNotIn("只在预览中出现的哨兵", text)
        self.assertNotIn("私有未送达哨兵", text)
        self.assertIn("<pre>", "".join(parts))
        self.assertIn("<blockquote expandable>", "".join(parts))

    def test_legacy_rankings_are_not_counted_as_delivered_items_or_filled_in(self):
        store = Store()
        store.seed_daily(MONDAY, None)
        store.seed_daily(MONDAY + timedelta(days=1), [entry("topic", "已验证合成")], states=("CONFIRMED",))
        report = decoded(build_weekly(store, MONDAY + timedelta(days=1), WEEK))
        self.assertIn("1/2 天 · 前一周 0/7 天", report)
        self.assertIn("新冒头榜暂缺", report)
        self.assertNotIn("🆕 本周新冒出来", report)

    def test_long_link_details_remain_complete_at_message_boundaries(self):
        store = Store()
        entries = [entry(f"topic-{number}", f"合成长链接条目 {number}",
                         url=f"https://example.org/{number}/" + "&" * 1500)
                   for number in range(10)]
        store.seed_daily(MONDAY, entries)
        parts = build_weekly(store, MONDAY, WEEK)
        self.assertGreater(len(parts), 1)
        self.assertEqual(sum(part.count('<a href="') for part in parts), 10)
        for part in parts:
            self.assertEqual(part.count("<pre>"), part.count("</pre>"))
            self.assertEqual(part.count("<blockquote expandable>"), part.count("</blockquote>"))
        self.assertIn("合成长链接条目 9", decoded(parts))

    def test_ideas_see_titles_only_and_omit_unlinked_invented_and_youtube_data(self):
        store = Store()
        store.seed_daily(MONDAY, [
            entry("lead", "合成<科技> & 活动"),
            entry("video-kind", "YOUTUBE_KIND_SENTINEL", "youtube"),
            entry("video-link", "YOUTUBE_URL_SENTINEL", url="https://www.youtube.com/watch?v=AAAAAAAAAAA"),
        ])
        store.files["deliveries/daily-2026-11-23-youtube.json"] = json_bytes({"payload": "YOUTUBE_LEDGER_SENTINEL"})
        writer = Ideas({"ideas": [
            {"text": "建议先访问需求", "ids": ["w1"]},
            {"text": "编造65人参加", "ids": ["w1"]},
            {"text": "编造引用", "ids": ["not-present"]},
        ]})
        parts = build_weekly(store, MONDAY, WEEK, writer=writer, token_notice="私库钥匙 7 天后到期")
        text = decoded(parts)
        self.assertIn("合成<科技> & 活动", text)
        self.assertIn("生意线索（AI 推测，仅供参考）", text)
        self.assertIn("建议先访问需求", text)
        self.assertIn("私库钥匙 7 天后到期", text)
        self.assertNotIn("编造", text)
        self.assertNotIn("YOUTUBE_", text)
        self.assertEqual({"w1": {"title": "合成<科技> & 活动", "days": 1}}, writer.prompt)

    def test_archived_parts_do_not_change_when_daily_history_changes(self):
        store = Store()
        store.seed_daily(MONDAY, [entry("old", "先前合成话题")])
        original = prepare_weekly(store, MONDAY, WEEK)
        store.seed_daily(MONDAY, [entry("new", "较晚合成话题")])
        self.assertEqual(original, prepare_weekly(store, MONDAY, WEEK))
        self.assertIn("先前合成话题", decoded(original))
        self.assertNotIn("较晚合成话题", decoded(original))


class WeeklyRoutingTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.store.seed_daily(MONDAY, [entry("private", "绝对不能在公开日志出现的合成数据")])
        self.calls = []
        self.telegram = TelegramClient("2468:" + "Z" * 30, "1357", request=self._request)

    def _request(self, _token, method, payload):
        self.calls.append((method, payload))
        chat = {"id": 1357, "type": "private"}
        result = chat if method == "getChat" else {"chat": chat, "message_id": 4}
        return 200, {"ok": True, "result": result}

    def _report(self, *, action=None, env=None, now=SUNDAY, created=SUNDAY):
        settings = {"GITHUB_EVENT_NAME": "schedule", "RADAR_REPORT_SCHEDULE": WEEKLY_CRON,
                    "RADAR_STAGE": "c-scheduled", "RADAR_REPORT_ACTION": action}
        settings.update(env or {})
        out = io.StringIO()
        with (
            patch.object(live, "_telegram", return_value=self.telegram),
            patch.object(live, "_token_notice", return_value=None, create=True),
            patch.object(live, "_send_youtube_supplement") as youtube,
            redirect_stdout(out),
        ):
            result = live._report(self.store, (), set(), settings, "weekly-test", created, now, None)
            youtube.assert_not_called()
        self.assertNotIn("绝对不能在公开日志出现", out.getvalue())
        return result

    def test_scheduled_report_uses_weekly_ledger_for_reruns_and_manual_resume(self):
        self.assertEqual(0, self._report())
        self.assertIsNotNone(self.store.read(weekly_archive_key(WEEK)))
        self.assertIsNotNone(self.store.read(f"deliveries/{WEEK}.json"))
        self.assertEqual(["getChat", "sendMessage"], [method for method, _ in self.calls])
        self.assertEqual(0, self._report())
        self.assertEqual(0, self._report(action="resume", env={
            "GITHUB_EVENT_NAME": "workflow_dispatch", "RADAR_REPORT_ID": WEEK,
        }))
        self.assertEqual(["getChat", "sendMessage"], [method for method, _ in self.calls])

    def test_manual_weekly_preview_has_separate_number_and_can_run_in_stage_b(self):
        self.assertEqual(0, self._report(action="weekly-preview", env={
            "GITHUB_EVENT_NAME": "workflow_dispatch", "RADAR_STAGE": "b-manual",
        }))
        self.assertIsNotNone(self.store.read(weekly_archive_key("weekly-preview-0900-2026-11-29")))
        self.assertIsNone(self.store.read(weekly_archive_key(WEEK)))

    def test_formal_weekly_requires_sunday_schedule_and_stage_c(self):
        for options in (
            {"GITHUB_EVENT_NAME": "workflow_dispatch"}, {"RADAR_STAGE": "b-manual"},
            {"RADAR_REPORT_SCHEDULE": "30 0 * * *"}, {"RADAR_REPORT_SCHEDULE": "0 1 * * 1"},
        ):
            with self.subTest(options=options), self.assertRaisesRegex(StorageError, "report_operation_invalid"):
                self._report(action="weekly", env=options)
        with self.assertRaisesRegex(StorageError, "report_before_target"):
            self._report(now=SUNDAY - timedelta(minutes=1))
        self.assertEqual(1, self._report(now=SUNDAY + timedelta(days=1)))
        self.assertEqual([], self.calls)

    def test_workflow_exposes_only_weekly_preview_manually_and_keeps_stage_c_gate(self):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.load((root / ".github/workflows/report.yml").read_text(encoding="utf-8"),
                             Loader=yaml.BaseLoader)
        triggers = workflow["on"]
        self.assertIn({"cron": WEEKLY_CRON}, triggers["schedule"])
        choices = triggers["workflow_dispatch"]["inputs"]["action"]["options"]
        self.assertIn("weekly-preview", choices)
        self.assertNotIn("weekly", choices)
        job = workflow["jobs"]["report"]
        self.assertIn("github.event_name == 'schedule' && vars.RADAR_STAGE == 'c-scheduled'", job["if"])
        runtime = job["steps"][-1]
        self.assertEqual("${{ github.event.schedule }}", runtime["env"]["RADAR_REPORT_SCHEDULE"])
