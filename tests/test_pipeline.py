"""Synthetic end-to-end hourly state, storage conflicts and live gate tests."""

from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from functools import partial
from io import StringIO
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import yaml

from radar import live, pipeline, storage
from radar.sources import Source, SourceError, load_sources


BASE = datetime(2026, 1, 1, 0, 20, tzinfo=timezone.utc)


class MemoryStore:
    size_kib = 5

    def __init__(self):
        self.files = {}

    def read(self, key):
        return self.files.get(key)

    def publish(self, files, message):
        self.files.update(files)


def item(title="Synthetic gadget", volume="200+"):
    return {"title": title, "url": "https://example.org/synthetic", "content_id": title,
            "volume_raw": volume, "rank": 1, "published_at": None, "related": []}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.my = Source("trends_my", "trends", "MY", "und", "https://example.org", True, "long_term")
        self.sg = Source("trends_sg", "trends", "SG", "und", "https://example.org", True, "long_term")
        self.pending = Source("test_pending", "news", "MY", "en", "https://example.org")
        self.sources = [self.my, self.sg, self.pending]
        self.approved = {s.id for s in self.sources}

    def collect(self, now, execution, fetch, planned_at=None):
        return pipeline.collect_slot(self.store, self.sources, self.approved, now, execution, fetch=fetch,
                                     clock=lambda: now, planned_at=planned_at)

    def test_retry_repairs_only_failed_source_and_repetition_preserves_history(self):
        attempts = Counter()

        def fetch(source):
            attempts[source.id] += 1
            if source == self.sg and attempts[source.id] == 1:
                raise SourceError("timeout")
            return [item(), item()]

        first = self.collect(BASE, "collect-1-1", fetch)
        self.assertEqual(first["row_count"], 1)
        retry = self.collect(BASE + timedelta(minutes=5), "collect-1-2", fetch)
        self.assertEqual(retry["row_count"], 2)
        repeated = self.collect(BASE + timedelta(minutes=6), "collect-1-3", fetch)
        self.assertEqual(repeated["sha256"], retry["sha256"])
        self.assertEqual(attempts, {self.my.id: 1, self.sg.id: 2})
        later = self.collect(BASE + timedelta(hours=1), "collect-2-1", fetch)
        first_rows = storage.read_observations(self.store, pipeline.partition(BASE), retry)
        later_rows = storage.read_observations(self.store, pipeline.partition(BASE + timedelta(hours=1)), later)
        self.assertEqual(len(later_rows), 2)
        self.assertEqual(first_rows[0]["first_seen_at"], later_rows[0]["first_seen_at"])
        self.assertNotEqual(first_rows[0]["observed_at"], later_rows[0]["observed_at"])
        self.assertNotEqual(first_rows[0]["run_id"], later_rows[0]["run_id"])
        self.assertEqual([row["observed_at"] for row in first_rows],
                         [BASE.isoformat(), (BASE + timedelta(minutes=5)).isoformat()])

    def test_empty_result_is_a_completed_source(self):
        result = self.collect(BASE, "collect-1-1", lambda _: [])
        self.assertEqual(result["sources"][self.my.id]["status"], "empty")
        repeat = self.collect(BASE, "collect-1-2", lambda _: self.fail("valid empty was queried again"))
        self.assertEqual(repeat["row_count"], 0)

    def test_consecutive_errors_and_coverage_never_fill_a_missing_slot(self):
        def fetch(source):
            if source == self.sg:
                raise SourceError("timeout")
            return [item()]

        for offset in [0, 2, 3, 4]:
            now = BASE + timedelta(hours=offset)
            self.collect(now, f"collect-{offset + 1}-1", fetch, planned_at=now.replace(minute=17))
        self.assertEqual([key for key in self.store.files if key.startswith("reports/alerts/")],
                         ["reports/alerts/alert-20260101T04.json"])
        now = BASE + timedelta(hours=5)
        parts = pipeline.prepare_report(self.store, self.sources, self.approved, now, "smoke-2026-01-01",
                                        schedule_from=BASE)
        self.assertTrue(parts)
        self.assertEqual(parts, pipeline.prepare_report(
            self.store, self.sources, self.approved, now + timedelta(minutes=5), "smoke-2026-01-01",
        ))
        health = storage.read_json(self.store, "health/2026/01/01.json")
        self.assertEqual(health["states_7d"], {"ok": 0, "partial": 4, "failed": 0, "missed": 1})
        self.assertNotIn("manifests/2026/01/01/01.json", self.store.files)

    def test_manual_result_does_not_count_as_scheduled_success(self):
        self.collect(BASE, "collect-1-1", lambda _: [item()])
        now = BASE + timedelta(hours=1)
        _, missed, health = pipeline._window(self.store, now, BASE.replace(minute=17))
        self.assertEqual(missed, [pipeline.hour(BASE).isoformat()])
        self.assertEqual(health["states_7d"], {"ok": 0, "partial": 0, "failed": 0, "missed": 1})

    def test_late_scheduled_collection_uses_current_hour_and_preserves_plan(self):
        created = BASE.replace(hour=10, minute=17)
        now = BASE.replace(hour=11, minute=5)
        collect = partial(pipeline.collect_slot, fetch=lambda _: [item()], clock=lambda: now)
        with patch.object(live, "collect_slot", side_effect=collect), redirect_stdout(StringIO()):
            result = live._collection(
                self.store, [self.my], {self.my.id}, {"GITHUB_EVENT_NAME": "schedule"}, "collect-7-1", created, now,
            )
        self.assertEqual(result, 0)
        self.assertIsNone(pipeline.load_manifest(self.store, created))
        actual = pipeline.load_manifest(self.store, now)
        self.assertEqual(actual["row_count"], 1)
        self.assertIsNone(actual["planned_at"])
        audit = storage.read_json(self.store, "runs/collect-7-1.json")
        self.assertEqual(audit["planned_at"], created.isoformat())
        self.assertEqual(audit["planned_slot"], pipeline.hour(created).isoformat())
        self.assertEqual(audit["slot"], pipeline.hour(now).isoformat())
        self.assertEqual(audit["delay_seconds"], 48 * 60)
        self.assertTrue(audit["late_to_next_slot"])
        rows = storage.read_observations(self.store, pipeline.partition(now), actual)
        self.assertEqual(rows[0]["observed_at"], now.isoformat())

    def test_source_failure_has_safe_http_and_source_diagnostic(self):
        def fetch(source):
            if source == self.sg:
                raise SourceError("http_private_response", http_status=429)
            return [item()]

        self.collect(BASE, "collect-8-1", fetch)
        audit = storage.read_json(self.store, "runs/collect-8-1.json")
        [diagnostic] = audit["diagnostics"]
        self.assertEqual(diagnostic["source_id"], self.sg.id)
        self.assertEqual(diagnostic["http_status"], 429)
        self.assertEqual(diagnostic["module"], "radar.pipeline")
        self.assertNotIn(b"private_response", self.store.read("runs/collect-8-1.json"))

    def test_bad_checksum_does_not_overwrite_existing_hour(self):
        self.collect(BASE, "collect-1-1", lambda _: [item()])
        self.store.files["observations/2026/01/01/00.jsonl.gz"] = b"corrupted"
        with self.assertRaisesRegex(storage.StorageError, "observation_checksum_mismatch"):
            self.collect(BASE, "collect-1-2", lambda _: [])
        self.assertNotIn("runs/collect-1-2.json", self.store.files)


class IsolationTests(unittest.TestCase):
    def test_default_branch_and_event_gate(self):
        env = {"GITHUB_REPOSITORY": storage.CODE_REPO, "GITHUB_REF": "refs/heads/main",
               "GITHUB_WORKFLOW_REF": f"{storage.CODE_REPO}/.github/workflows/collect.yml@refs/heads/main",
               "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_ACTIONS": "true", "RADAR_STAGE": "b-manual",
               "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
        self.assertEqual(live.authorize(env, "collect"), "collect-123-1")
        for changed in ({"GITHUB_REF": "refs/heads/other"}, {"RADAR_STAGE": ""}, {"RUNNER_DEBUG": "1"},
                        {"GITHUB_EVENT_NAME": "schedule"}, {"GITHUB_REPOSITORY": storage.DATA_REPO},
                        {"GITHUB_EVENT_NAME": "pull_request_target"}):
            with self.subTest(changed=changed), self.assertRaisesRegex(storage.StorageError, "live_gate_closed"):
                live.authorize({**env, **changed}, "collect")

    def test_workflow_queues_and_schedules_are_gated_by_stage_c(self):
        root = Path(__file__).resolve().parents[1] / ".github/workflows"
        for name, cron in (("collect", "17 * * * *"), ("report", "30 0 * * *"),
                           ("offline", None)):
            with self.subTest(workflow=name):
                workflow = (root / f"{name}.yml").read_text(encoding="utf-8")
                spec = yaml.load(workflow, Loader=yaml.BaseLoader)
                self.assertEqual(set(spec["on"]), {"workflow_dispatch", "schedule"} if cron else
                                 {"workflow_dispatch", "pull_request"})
                job = next(iter(spec["jobs"].values()))
                self.assertEqual(job["runs-on"], "ubuntu-24.04")
                self.assertEqual(job["timeout-minutes"], "8")
                self.assertEqual(job["steps"][0]["with"]["persist-credentials"], "false")
                for step in job["steps"][:2]:
                    self.assertRegex(step["uses"], r"^actions/[-a-z]+@[0-9a-f]{40}$")
                if cron:
                    self.assertEqual(spec["on"]["schedule"], [{"cron": cron}])
                    self.assertIn("github.event_name == 'schedule' && vars.RADAR_STAGE == 'c-scheduled'", job["if"])
                    self.assertEqual(job["concurrency"], {"group": "radar-private-writer",
                                                          "queue": "max", "cancel-in-progress": "false"})
                    self.assertIn("refs/heads/main", job["if"])
                    self.assertEqual(job["environment"], "radar-live")
                    self.assertNotIn("secrets.TELEGRAM_CHAT_ID", workflow)
                else:
                    self.assertNotIn("secrets.", workflow)
                    self.assertNotIn("radar.live", workflow)
                    self.assertNotIn("environment", job)
                    self.assertEqual(spec["permissions"], {"contents": "read"})

    def test_keepalive_only_reenables_workflows_without_secrets(self):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/keepalive.yml"
        workflow = path.read_text(encoding="utf-8")
        spec = yaml.load(workflow, Loader=yaml.BaseLoader)
        self.assertEqual({"schedule", "workflow_dispatch"}, set(spec["on"]))
        self.assertEqual({"actions": "write"}, spec["permissions"])
        job = spec["jobs"]["keepalive"]
        self.assertIn("vars.RADAR_STAGE == 'c-scheduled'", job["if"])
        self.assertNotIn("secrets.", workflow)
        self.assertTrue(all("uses" not in step for step in job["steps"]))  # no checkout or third-party action
        self.assertNotIn("environment", job)
        for name in ("collect.yml", "report.yml", "keepalive.yml"):
            self.assertIn(name, workflow)

    def test_first_scheduled_collection_records_the_schedule_start(self):
        store = MemoryStore()
        env = {"RADAR_STAGE": "c-scheduled", "GITHUB_EVENT_NAME": "schedule"}
        created = datetime(2026, 11, 26, 5, 24, tzinfo=timezone.utc)
        self.assertIsNone(live._schedule_start(store, {**env, "GITHUB_EVENT_NAME": "workflow_dispatch"},
                                               "collect", created))
        self.assertIsNone(live._schedule_start(store, env, "report", created))
        self.assertEqual({}, store.files)
        start = live._schedule_start(store, env, "collect", created)
        self.assertEqual(datetime(2026, 11, 26, 5, 17, tzinfo=timezone.utc), start)
        later = created + timedelta(hours=3)
        self.assertEqual(start, live._schedule_start(store, env, "collect", later))
        self.assertEqual(start, live._schedule_start(store, {**env, "GITHUB_EVENT_NAME": "workflow_dispatch"},
                                                     "report", later))
        self.assertEqual(datetime(2026, 1, 1, 0, 17, tzinfo=timezone.utc), live._schedule_start(
            store, {**env, "RADAR_SCHEDULE_FROM": "2026-01-01T00:17:00+00:00"}, "collect", later))
        with self.assertRaisesRegex(storage.StorageError, "^schedule_start_invalid$"):
            live._schedule_start(MemoryStore(), {**env, "RADAR_SCHEDULE_FROM": "2026-01-01T00:20:00+00:00"},
                                 "collect", later)

    def test_unapproved_sources_fail_closed(self):
        sources = load_sources()
        expected = {source.id for source in sources if source.enabled}
        self.assertIn("trends_my", expected)
        self.assertEqual(live._approved_sources(sources), expected)
        self.assertEqual(live._approved_sources(sources, "weather"), {"weather"})
        self.assertEqual(live._approved_sources(sources, "trends_my"), {"trends_my"})
        for candidate in ("weather other_source", "gdelt"):
            with self.subTest(candidate=candidate), self.assertRaises(storage.StorageError):
                live._approved_sources(sources, candidate)

    def test_public_logs_omit_network_exception_details(self):
        output = StringIO()
        with patch.object(live, "run_live", side_effect=ValueError("PRIVATE EXCEPTION BODY")), redirect_stdout(output):
            self.assertEqual(live.main(["report"], {}), 1)
        self.assertEqual(output.getvalue(), "radar outcome=operation_failed\n")

    @staticmethod
    def report_env():
        return {
            "GITHUB_REPOSITORY": storage.CODE_REPO, "GITHUB_REF": "refs/heads/main",
            "GITHUB_WORKFLOW_REF": f"{storage.CODE_REPO}/.github/workflows/report.yml@refs/heads/main",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_ACTIONS": "true", "RADAR_STAGE": "b-manual",
            "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_ACTOR": "alex20230412-svg", "GITHUB_TRIGGERING_ACTOR": "alex20230412-svg",
        }

    def test_unexpected_failure_stdout_and_private_audit_only_allow_safe_fields(self):
        store, output = MemoryStore(), StringIO()
        sensitive = ["123456789:" + "A" * 35, "https://example.test/private?q=probe", "PRIVATE RESPONSE BODY"]
        failure = RuntimeError(" ".join(sensitive))
        failure.http_status = 503
        with (patch.object(live, "queued_at", return_value=BASE),
              patch.object(storage.PrivateGitStore, "clone", return_value=store),
              patch.object(live, "_report", side_effect=failure), redirect_stdout(output)):
            self.assertEqual(live.main(["report"], self.report_env()), 1)
        self.assertEqual(output.getvalue(), "radar outcome=operation_failed\n")
        key = "runs/report-123-1.json"
        audit = storage.read_json(store, key)
        self.assertEqual(audit["outcome"], "operation_failed")
        diagnostic = audit["failure_diagnostic"]
        self.assertEqual(diagnostic["exception_class"], "RuntimeError")
        self.assertEqual(diagnostic["module"], "radar.live")
        self.assertGreater(diagnostic["line"], 0)
        self.assertIsNone(diagnostic["source_id"])
        self.assertEqual(diagnostic["http_status"], 503)
        for text in sensitive:
            self.assertNotIn(text.encode(), store.read(key))
            self.assertNotIn(text, output.getvalue())

    def test_binding_is_owner_only_and_independent_from_source_approval(self):
        env = {**self.report_env(), "RADAR_REPORT_ACTION": "confirm_bind"}
        with patch.object(live, "queued_at") as metadata:
            with self.assertRaisesRegex(storage.StorageError, "binding_owner_required"):
                live.run_live("report", {**env, "GITHUB_TRIGGERING_ACTOR": "other-user"})
            metadata.assert_not_called()
        store = MemoryStore()
        with (patch.object(live, "queued_at", return_value=BASE),
              patch.object(storage.PrivateGitStore, "clone", return_value=store),
              patch.object(live, "load_sources", side_effect=AssertionError("binding read source policy")),
              patch.object(live, "confirm_bind", return_value="BOUND") as confirm,
              redirect_stdout(StringIO())):
            self.assertEqual(live.run_live("report", env), 0)
        confirm.assert_called_once_with(store, "", requested_at=BASE.timestamp())

    def test_repository_must_be_exact_private_main(self):
        repo = {"full_name": storage.DATA_REPO, "private": True, "visibility": "private",
                "default_branch": "main", "size": 50}
        self.assertEqual(storage.private_repository_size("mock", lambda *_: repo), 50)
        for change in ({"private": False}, {"visibility": "public"}, {"full_name": storage.CODE_REPO},
                       {"default_branch": "other"}, {"size": storage.STOP_KIB}):
            with self.subTest(change=change), self.assertRaises(storage.StorageError):
                storage.private_repository_size("mock", lambda *_: {**repo, **change})

    def test_schedule_slot_uses_enqueued_timestamp_instead_of_runner_start(self):
        scheduled, due_at = live.collect_plan(BASE, True)
        self.assertEqual(scheduled, pipeline.hour(BASE))
        self.assertEqual(due_at.minute, 17)
        next_hour = BASE + timedelta(hours=1)
        self.assertEqual(live.collect_plan(next_hour.replace(minute=2), True), (scheduled, due_at))
        self.assertEqual(live.collect_plan(next_hour.replace(minute=2), False), (pipeline.hour(next_hour), None))

    def test_live_metadata_checks_public_runner_repo_and_exact_run(self):
        repo = {"full_name": storage.CODE_REPO, "default_branch": "main", "private": False,
                "visibility": "public"}
        env = {"GITHUB_RUN_ID": "7", "GITHUB_SHA": "synthetic-sha", "GITHUB_EVENT_NAME": "schedule"}
        run = {"id": 7, "head_sha": env["GITHUB_SHA"], "head_branch": "main", "event": "schedule",
               "created_at": BASE.isoformat()}
        with patch.object(live, "github_object", side_effect=[repo, run]):
            self.assertEqual(live.queued_at(env), BASE)
        with patch.object(live, "github_object", return_value={**repo, "visibility": "private"}):
            with self.assertRaisesRegex(storage.StorageError, "public_code_repository_required"):
                live.queued_at(env)
        with patch.object(live, "github_object", side_effect=[repo, {**run, "id": 8}]):
            with self.assertRaisesRegex(storage.StorageError, "workflow_metadata_mismatch"):
                live.queued_at(env)

    def test_competing_git_writer_cannot_overwrite_remote(self):
        def git(*args):
            return subprocess.run(["git", *args], check=True, capture_output=True).stdout

        with TemporaryDirectory(dir=Path.cwd()) as temp:
            root = Path(temp).resolve()
            remote = root / "remote"
            seed = root / "seed"
            git("init", "--bare", "--initial-branch=main", str(remote))
            git("clone", str(remote), str(seed))
            git("-C", str(seed), "-c", "user.name=Mock", "-c", "user.email=mock@example.test",
                "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "Seed")
            git("-C", str(seed), "push", "origin", "main")
            roots = [root / "first", root / "second"]
            for path in roots:
                git("clone", "--no-hardlinks", str(remote), str(path))
            first, competing = (storage.PrivateGitStore(path, dict(os.environ), 0, "mock") for path in roots)
            key = "health/synthetic.json"
            with patch.object(storage, "DATA_URL", str(remote)), patch.object(storage, "private_repository_size"):
                first.publish({key: b"first"}, "first local writer")
                with self.assertRaises(storage.StorageError):
                    competing.publish({key: b"competing"}, "competing local writer")
            self.assertEqual(git("--git-dir", str(remote), "show", f"main:{key}"), b"first")


if __name__ == "__main__":
    unittest.main()
