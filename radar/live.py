"""Default-branch Actions entry point. Tests use injected local stores and transports."""

from datetime import datetime, time, timedelta
import os
import re
import sys
from tempfile import TemporaryDirectory

from .binding import bind_chat, bound_chat_id, confirm_bind
from .brief import GeminiWriter, UnavailableWriter
from .delivery import DeliveryError, TelegramClient, reconcile_delivery, send_parts
from .diagnostics import diagnostic
from .expiry import token_expiry_notice
from .pipeline import (
    MYT, collect_slot, deliver, delivery_callbacks, hour, instant, prepare_report,
    utc_now,
)
from .sources import load_sources
from .storage import CODE_REPO, PrivateGitStore, PublicationError, StorageError, github_object, json_bytes, read_json
from .weekly import WEEKLY_CRON, WEEKLY_REPORT_ID, prepare_weekly, weekly_archive_key, weekly_key
from .youtube import fetch_youtube, load_youtube_config, render_youtube


REPORT_ID = re.compile(r"(?:(?:daily|smoke|preview-\d{4})-\d{4}-\d{2}-\d{2}|alert-\d{8}T\d{2})\Z")
DELIVERED = {"SENT", "CONFIRMED"}
BINDING_ACTIONS = {"bind_chat", "confirm_bind"}
PUBLIC_ERRORS = {
    "live_gate_closed", "workflow_identity_invalid", "public_code_repository_required",
    "workflow_metadata_mismatch", "private_report_missing", "report_source_approval_changed",
    "report_operation_invalid", "report_before_target", "delivery_part_invalid",
    "telegram_binding_required", "binding_owner_required", "source_approval_required",
    "schedule_start_required", "schedule_start_invalid", "schedule_not_started",
    "github_credential_missing", "github_access_rejected", "github_metadata_oversize",
    "github_metadata_unavailable", "github_invalid_metadata", "private_repository_required",
    "repository_size_unknown", "repository_capacity_stop", "git_operation_unconfirmed",
    "git_operation_failed", "git_publication_failed", "invalid_storage_key", "storage_symlink_rejected",
    "observation_checksum_mismatch", "observation_archive_invalid", "observation_count_mismatch",
    "invalid_telegram_token", "binding_bot_changed", "binding_private_start_required",
    "binding_ambiguous_start", "binding_updates_unavailable", "binding_updates_incomplete",
    "binding_not_requested", "binding_confirmation_expired", "binding_ack_unconfirmed", "binding_state_invalid",
}


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


SCHEDULE_START_KEY = "health/schedule-start.json"


def _schedule_start(store, env, operation, created):
    """RADAR_SCHEDULE_FROM wins; otherwise the first scheduled collection records its own plan."""
    starts = env.get("RADAR_SCHEDULE_FROM", "")
    if starts:
        value = instant(starts)
    else:
        saved = read_json(store, SCHEDULE_START_KEY)
        value = instant(saved["schedule_from"]) if isinstance(saved, dict) and saved.get("schedule_from") else None
        if (value is None and env.get("RADAR_STAGE") == "c-scheduled" and operation == "collect"
                and env.get("GITHUB_EVENT_NAME") == "schedule"):
            value = collect_plan(created, True)[1]
            store.publish({SCHEDULE_START_KEY: json_bytes({
                "schedule_from": value.isoformat(), "recorded_at": utc_now().isoformat(),
            })}, "Record schedule start")
    if value and (value.minute != 17 or value.second or value.microsecond):
        raise StorageError("schedule_start_invalid")
    return value


def _audit(store, execution, **fields):
    store.publish({f"runs/{execution}.json": json_bytes(fields)}, "Record radar run status")


def _writer(env):
    key = env.get("GEMINI_API_KEY", "")
    if not key.strip():
        return UnavailableWriter("no_key")
    try:
        return GeminiWriter(key)
    except ValueError:
        return UnavailableWriter("invalid_key_format")


def _telegram(env, store):
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = bound_chat_id(store, token)
    if chat_id is None:
        raise StorageError("telegram_binding_required")
    return TelegramClient(token, chat_id)


def _collection(store, sources, approved, env, execution, created, now):
    planned_slot, planned_at = collect_plan(created, env["GITHUB_EVENT_NAME"] == "schedule")
    slot = hour(now)
    late = slot > planned_slot
    timing = {
        "created_at": created.isoformat(),
        "planned_slot": planned_slot.isoformat() if planned_at else None,
        "planned_at": planned_at.isoformat() if planned_at else None,
        "late_to_next_slot": late,
        "delay_seconds": int((now - (planned_at or created)).total_seconds()),
    }
    # A delayed trigger may collect current data, but it cannot claim the missed slot or
    # stand in for this hour's own scheduled trigger when computing schedule coverage.
    due = planned_at if slot == planned_slot else None
    state = collect_slot(store, sources, approved, slot, execution, planned_at=due, timing=timing)
    alert_id = "alert-" + slot.strftime("%Y%m%dT%H")
    alert = read_json(store, f"reports/alerts/{alert_id}.json")
    if alert:
        status = deliver(store, alert_id, alert["parts"], _telegram(env, store))
        print(f"alert delivery={status}")
    else:
        status = "SENT"
    print(f"collect outcome={state['outcome']} observations={state['row_count']}")
    return int(state["outcome"] == "failed" or status not in DELIVERED)


def _frozen_payload(store, report_id, approved):
    if report_id.startswith("alert-"):
        path = f"reports/alerts/{report_id}.json"
    elif WEEKLY_REPORT_ID.fullmatch(report_id):
        path = weekly_archive_key(report_id)
    else:
        year, month, day = report_id.rsplit("-", 3)[-3:]
        path = f"reports/{year}/{month}/{day}/{report_id}.json"
    payload = read_json(store, path)
    if not payload:
        raise StorageError("private_report_missing")
    if not set(payload.get("source_ids", ())) <= approved:
        raise StorageError("report_source_approval_changed")
    return payload["parts"]


def _send_youtube_supplement(store, execution, report_id, main_status, telegram, raw_key):
    """Isolate the one-shot supplement from the saved brief and its delivery result."""
    code, items, sent = "invalid_payload", 0, "NOT_SENT"
    audit_safe = True
    delivery_id = report_id + "-youtube"
    ledger_key = f"deliveries/{delivery_id}.json"

    def save_attempt(_report_id, ledger):
        part = ledger["parts"][0]
        store.publish({ledger_key: json_bytes({
            "payload_hash": part["payload_hash"], "delivery_state": part["delivery_state"],
        })}, "Record YouTube delivery state")

    try:
        # While disabled the supplement is a no-op: no ledger read and no audit write.
        try:
            config = load_youtube_config()
        except ValueError:
            config, code = None, "invalid_config"
        if config is None:
            pass
        elif not config.enabled:
            code = "disabled"
        elif main_status not in DELIVERED:
            code = "main_not_sent"
        elif store.read(ledger_key) is not None:
            code = "already_attempted"
        else:
            result = fetch_youtube(config, raw_key)
            code, items = result.status, len(result.videos)
            if code == "ok" and items:
                message = render_youtube(result.videos)
                sent = "UNKNOWN"
                # The shared writer lock serializes the existence check and this publish-before-send.
                sent = send_parts(delivery_id, [message], telegram, lambda _: None, save_attempt,
                                  retry_rate_limit=False, silent=True)
    except PublicationError:
        # A failed push can leave local commits ahead of the remote. Do not publish again.
        audit_safe = False
    except Exception:
        # Provider data and delivery exceptions are never copied to logs or the audit.
        pass
    print(f"youtube status={code} items={items} sent={sent}")
    if audit_safe and code != "disabled":
        try:
            _audit(store, f"{execution}-youtube", status=code, items=items, sent=sent)
        except Exception:
            pass


def _token_notice(env, now):
    status, notice = token_expiry_notice(env.get("DATA_REPO_TOKEN", ""), now)
    if status != "no_token":
        print(f"token_expiry status={status}")
    return notice


def _report(store, sources, approved, env, execution, created, now, schedule_from):
    action = env.get("RADAR_REPORT_ACTION")
    event = env["GITHUB_EVENT_NAME"]
    requested = env.get("RADAR_REPORT_ID", "")
    if event == "schedule":
        cron = env.get("RADAR_REPORT_SCHEDULE") or "30 0 * * *"
        scheduled_action = "weekly" if cron == WEEKLY_CRON else "send"
        if cron not in {"30 0 * * *", WEEKLY_CRON} or (action and action != scheduled_action):
            raise StorageError("report_operation_invalid")
        action = scheduled_action
    elif action == "weekly" or (action == "weekly-preview" and event != "workflow_dispatch"):
        raise StorageError("report_operation_invalid")
    action = action or "send"
    notice = _token_notice(env, now) if action in {"send", "preview", "resume"} else None
    if action in {"weekly", "weekly-preview"}:
        local = now.astimezone(MYT)
        day = local.date()
        if action == "weekly":
            if env["RADAR_STAGE"] != "c-scheduled":
                raise StorageError("report_operation_invalid")
            scheduled_day = created.astimezone(MYT).date()
            if scheduled_day.weekday() != 6 or day != scheduled_day:
                _audit(store, execution, outcome="missed_late", started_at=now.isoformat(),
                       report_day=scheduled_day.isoformat())
                print("report outcome=missed_late")
                return 1
            if local.time() < time(9):
                raise StorageError("report_before_target")
        report_id = weekly_key(day) if action == "weekly" else f"weekly-preview-{local:%H%M}-{day.isoformat()}"
        parts = prepare_weekly(store, day, report_id, writer=_writer(env), token_notice=_token_notice(env, now))
    elif action == "preview":
        # A fresh, separately numbered brief for the Owner to check the format at any time.
        local = now.astimezone(MYT)
        report_id = f"preview-{local:%H%M}-{local.date().isoformat()}"
        parts = prepare_report(store, sources, approved, now, report_id, schedule_from=schedule_from,
                               writer=_writer(env), token_notice=notice)
    elif action == "send":
        day = created.astimezone(MYT).date()
        if day != now.astimezone(MYT).date():
            _audit(store, execution, outcome="missed_late", started_at=now.isoformat(), report_day=day.isoformat())
            print("report outcome=missed_late")
            print("youtube status=main_not_sent items=0 sent=NOT_SENT")
            return 1
        smoke = env["RADAR_STAGE"] == "b-manual"
        target = None if smoke else datetime.combine(day, time(8, 30), tzinfo=MYT)
        if target and now < target:
            raise StorageError("report_before_target")
        report_id = f"{'smoke' if smoke else 'daily'}-{day.isoformat()}"
        parts = prepare_report(store, sources, approved, now, report_id,
                               target_at=target, schedule_from=schedule_from, writer=_writer(env), token_notice=notice)
    else:
        if action not in {"resume", "confirm_received", "confirm_unsent"} or not (
            REPORT_ID.fullmatch(requested) or WEEKLY_REPORT_ID.fullmatch(requested)
        ):
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
    telegram = _telegram(env, store)
    status = deliver(store, report_id, parts, telegram)
    _audit(store, execution, outcome=status, started_at=now.isoformat(), report_id=report_id,
           ended_at=utc_now().isoformat(), parts=len(parts))
    print(f"report delivery={status} parts={len(parts)}")
    if not report_id.startswith(("alert-", "weekly-")):
        _send_youtube_supplement(store, execution, report_id, status, telegram, env.get("YOUTUBE_API_KEY", ""))
    return int(status not in DELIVERED)


def _approved_sources(sources, raw=""):
    available = {source.id for source in sources if source.enabled and source.retention == "long_term"}
    approved = set(raw.split()) or available
    if not approved or not approved <= available:
        raise StorageError("source_approval_required")
    return approved


def run_live(operation, env):
    execution = authorize(env, operation)
    action = env.get("RADAR_REPORT_ACTION") if operation == "report" else None
    binding = action in BINDING_ACTIONS
    if binding:
        owner = CODE_REPO.split("/", 1)[0]
        actor = env.get("GITHUB_ACTOR")
        if (env["GITHUB_EVENT_NAME"] != "workflow_dispatch" or actor != owner
                or env.get("GITHUB_TRIGGERING_ACTOR", actor) != owner):
            raise StorageError("binding_owner_required")
    else:
        sources = load_sources()
        approved = _approved_sources(sources, env.get("RADAR_APPROVED_SOURCES", ""))
    created = queued_at(env)
    with TemporaryDirectory(prefix="radar-private-", dir=env.get("RUNNER_TEMP")) as temp:
        store = PrivateGitStore.clone(temp, env.get("DATA_REPO_TOKEN"))
        now = utc_now()
        schedule_from = None if binding else _schedule_start(store, env, operation, created)
        try:
            if schedule_from and env["GITHUB_EVENT_NAME"] == "schedule" and created < schedule_from:
                raise StorageError("schedule_not_started")
            if binding:
                token = env.get("TELEGRAM_BOT_TOKEN", "")
                status = bind_chat(store, token) if action == "bind_chat" else confirm_bind(
                    store, token, requested_at=created.timestamp(),
                )
                _audit(store, execution, operation=action, outcome=status, started_at=now.isoformat())
                print(f"binding outcome={status}")
                return int(status not in {"ACK_SENT", "BOUND", "ALREADY_BOUND"})
            if operation == "collect":
                return _collection(store, sources, approved, env, execution, created, now)
            return _report(store, sources, approved, env, execution, created, now, schedule_from)
        except PublicationError:
            raise
        except Exception as exc:
            try:
                audit = read_json(store, f"runs/{execution}.json") or {
                    "operation": operation, "outcome": "operation_failed", "started_at": now.isoformat(),
                }
                audit["failure_diagnostic"] = diagnostic(exc)
                _audit(store, execution, **audit)
            except (StorageError, OSError, ValueError):
                # No fallback printing if private storage is unavailable.
                pass
            raise


def main(argv=None, env=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in {"collect", "report"}:
        print("radar outcome=invalid_command")
        return 2
    try:
        return run_live(args[0], os.environ if env is None else env)
    except (StorageError, DeliveryError) as exc:
        outcome = str(exc)
        print(f"radar outcome={outcome if outcome in PUBLIC_ERRORS else 'operation_failed'}")
    except Exception:
        # Public Actions logs must never include request URLs, exception bodies, or private content.
        print("radar outcome=operation_failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
