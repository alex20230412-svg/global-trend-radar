"""Default-branch Actions entry point. Tests use injected local stores and transports."""

from datetime import datetime, time, timedelta
import os
import re
import sys
from tempfile import TemporaryDirectory

from .delivery import DeliveryError, TelegramClient, reconcile_delivery
from .pipeline import (
    MYT, collect_slot, deliver, delivery_callbacks, hour, instant, prepare_report,
    utc_now,
)
from .sources import load_sources
from .storage import CODE_REPO, PrivateGitStore, StorageError, github_object, json_bytes, read_json


REPORT_ID = re.compile(r"(?:(?:daily|smoke)-\d{4}-\d{2}-\d{2}|alert-\d{8}T\d{2})\Z")
DELIVERED = {"SENT", "CONFIRMED"}


def authorize(env, operation):
    event = env.get("GITHUB_EVENT_NAME")
    stage = env.get("RADAR_STAGE")
    workflow = f"{CODE_REPO}/.github/workflows/{operation}.yml@refs/heads/main"
    if (
        operation not in {"collect", "report"}
        or env.get("GITHUB_ACTIONS") != "true"
        or env.get("GITHUB_REPOSITORY") != CODE_REPO
        or env.get("GITHUB_REF") != "refs/heads/main"
        or env.get("GITHUB_WORKFLOW_REF") != workflow
        or env.get("RUNNER_DEBUG") == "1"
        or event not in {"workflow_dispatch", "schedule"}
        or stage not in {"b-manual", "c-scheduled"}
        or (event == "schedule" and stage != "c-scheduled")
    ):
        raise StorageError("live_gate_closed")
    ids = [env.get("GITHUB_RUN_ID", ""), env.get("GITHUB_RUN_ATTEMPT", "")]
    if not all(re.fullmatch(r"[1-9][0-9]{0,19}", value) for value in ids):
        raise StorageError("workflow_identity_invalid")
    return f"{operation}-{ids[0]}-{ids[1]}"


def queued_at(env):
    run_id = env["GITHUB_RUN_ID"]
    token = env.get("RUN_METADATA_TOKEN")
    repo = github_object(CODE_REPO, token)
    if (repo.get("full_name") != CODE_REPO or repo.get("default_branch") != "main"
            or repo.get("visibility") != "public" or repo.get("private") is not False):
        raise StorageError("public_code_repository_required")
    info = github_object(f"{CODE_REPO}/actions/runs/{run_id}", token)
    if (
        str(info.get("id")) != run_id or info.get("head_branch") != "main"
        or info.get("head_sha") != env.get("GITHUB_SHA")
        or info.get("event") != env["GITHUB_EVENT_NAME"]
    ):
        raise StorageError("workflow_metadata_mismatch")
    return instant(info["created_at"])


def collect_plan(created_at, scheduled):
    scheduled_start = hour(created_at - timedelta(minutes=17))
    if scheduled:
        return scheduled_start, scheduled_start + timedelta(minutes=17)
    return hour(created_at), None


def _audit(store, execution, **fields):
    store.publish({f"runs/{execution}.json": json_bytes(fields)}, "Record radar run status")


def _telegram(env):
    return TelegramClient(env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", ""))


def _collection(store, sources, approved, env, execution, created, now):
    slot, planned_at = collect_plan(created, env["GITHUB_EVENT_NAME"] == "schedule")
    if slot != hour(now):
        _audit(store, execution, outcome="missed_late", slot=slot.isoformat(),
               planned_at=planned_at.isoformat() if planned_at else None, started_at=now.isoformat())
        print("collect outcome=missed_late")
        return 1
    state = collect_slot(store, sources, approved, slot, execution, planned_at=planned_at)
    alert_id = "alert-" + slot.strftime("%Y%m%dT%H")
    alert = read_json(store, f"reports/alerts/{alert_id}.json")
    if alert:
        status = deliver(store, alert_id, alert["parts"], _telegram(env))
        print(f"alert delivery={status}")
    else:
        status = "SENT"
    print(f"collect outcome={state['outcome']} observations={state['row_count']}")
    return int(state["outcome"] == "failed" or status not in DELIVERED)


def _frozen_payload(store, report_id, approved):
    if report_id.startswith("alert-"):
        path = f"reports/alerts/{report_id}.json"
    else:
        year, month, day = report_id.rsplit("-", 3)[-3:]
        path = f"reports/{year}/{month}/{day}/{report_id}.json"
    payload = read_json(store, path)
    if not payload:
        raise StorageError("private_report_missing")
    if not set(payload.get("source_ids", ())) <= approved:
        raise StorageError("report_source_approval_changed")
    return payload["parts"]


def _report(store, sources, approved, env, execution, created, now, schedule_from):
    action = env.get("RADAR_REPORT_ACTION") or "send"
    requested = env.get("RADAR_REPORT_ID", "")
    if env["GITHUB_EVENT_NAME"] == "schedule" and action != "send":
        raise StorageError("report_operation_invalid")
    if action == "send":
        day = created.astimezone(MYT).date()
        if day != now.astimezone(MYT).date():
            _audit(store, execution, outcome="missed_late", started_at=now.isoformat(), report_day=day.isoformat())
            print("report outcome=missed_late")
            return 1
        smoke = env["RADAR_STAGE"] == "b-manual"
        target = None if smoke else datetime.combine(day, time(8, 30), tzinfo=MYT)
        if target and now < target:
            raise StorageError("report_before_target")
        report_id = f"{'smoke' if smoke else 'daily'}-{day.isoformat()}"
        parts = prepare_report(store, sources, approved, now, report_id,
                               target_at=target, schedule_from=schedule_from)
    else:
        if action not in {"resume", "confirm_received", "confirm_unsent"} or not REPORT_ID.fullmatch(requested):
            raise StorageError("report_operation_invalid")
        report_id = requested
        parts = _frozen_payload(store, report_id, approved)
        if action != "resume":
            load, save = delivery_callbacks(store)
            ledger = load(report_id)
            raw_number = env.get("RADAR_PART_NO", "")
            if not ledger or not re.fullmatch(r"[1-9][0-9]{0,3}", raw_number):
                raise StorageError("delivery_part_invalid")
            number = int(raw_number)
            if number > len(ledger["parts"]):
                raise StorageError("delivery_part_invalid")
            reconcile_delivery(
                report_id, number, ledger["parts"][number - 1]["payload_hash"], load, save,
                confirmed_sent=action == "confirm_received", confirmed_unsent=action == "confirm_unsent",
            )
            _audit(store, execution, outcome=action, started_at=now.isoformat(), report_id=report_id, part=number)
            print("report outcome=reconciled")
            return 0
    status = deliver(store, report_id, parts, _telegram(env))
    _audit(store, execution, outcome=status, started_at=now.isoformat(), report_id=report_id,
           ended_at=utc_now().isoformat(), parts=len(parts))
    print(f"report delivery={status} parts={len(parts)}")
    return int(status not in DELIVERED)


def _approved_sources(sources, raw):
    approved = set(raw.split())
    available = {source.id for source in sources if source.enabled and source.retention == "long_term"}
    if not approved or not approved <= available:
        raise StorageError("source_approval_required")
    return approved


def run_live(operation, env):
    execution = authorize(env, operation)
    sources = load_sources()
    approved = _approved_sources(sources, env.get("RADAR_APPROVED_SOURCES", ""))
    starts = env.get("RADAR_SCHEDULE_FROM", "")
    if env["RADAR_STAGE"] == "c-scheduled" and not starts:
        raise StorageError("schedule_start_required")
    schedule_from = instant(starts) if starts else None
    if schedule_from and (schedule_from.minute != 17 or schedule_from.second or schedule_from.microsecond):
        raise StorageError("schedule_start_invalid")
    created = queued_at(env)
    with TemporaryDirectory(prefix="radar-private-", dir=env.get("RUNNER_TEMP")) as temp:
        store = PrivateGitStore.clone(temp, env.get("DATA_REPO_TOKEN"))
        now = utc_now()
        if schedule_from and env["GITHUB_EVENT_NAME"] == "schedule" and created < schedule_from:
            raise StorageError("schedule_not_started")
        try:
            if operation == "collect":
                return _collection(store, sources, approved, env, execution, created, now)
            return _report(store, sources, approved, env, execution, created, now, schedule_from)
        except DeliveryError as exc:
            failure_execution = f"{execution}-delivery" if operation == "collect" else execution
            _audit(store, failure_execution, outcome="delivery_error", reason=str(exc), started_at=now.isoformat())
            raise StorageError("delivery_error") from exc


def main(argv=None, env=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in {"collect", "report"}:
        print("radar outcome=invalid_command")
        return 2
    try:
        return run_live(args[0], os.environ if env is None else env)
    except StorageError as exc:
        print(f"radar outcome={exc}")
    except Exception:
        # Public Actions logs must never include request URLs, exception bodies, or private content.
        print("radar outcome=operation_failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
