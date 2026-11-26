"""Collect immutable hourly observations, compare coverage, and publish private reports."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
from html import escape

from .brief import build_brief
from .delivery import send_parts, split_parts
from .diagnostics import diagnostic
from .history import previous_brief_keys
from .report import build_report
from .scoring import trend_key
from .sources import HOURLY_SINGLE_READ_KINDS, WEIBO_ARCHIVE_MAX_AGE, SourceError, collect_source
from .storage import WARN_KIB, StorageError, archive_rows, json_bytes, read_json, read_observations


UTC = timezone.utc
MYT = timezone(timedelta(hours=8))
HOUR = timedelta(hours=1)
GOOD = {"ok", "empty"}
CORE = {"trends", "news"}
WEIBO_FRESHNESS_KEY = "health/sources/weibo_archive.json"
SOURCE_ERROR_CODES = {
    "dns_error", "private_address_blocked", "url_blocked", "host_backoff", "robots_invalid",
    "robots_denied", "robots_rate_unsupported", "response_encoding", "network_error",
    "response_too_large", "invalid_xml", "feed_schema", "trend_schema", "malformed_item",
    "invalid_json", "json_schema", "source_deadline", "hn_item_schema", "mastodon_tag_link",
    "weather_schema", "source_disabled", "retention_approval_required", "timeout", "too_many_malformed_items",
    "archive_stale", "archive_freshness_unavailable", "hourly_rate_guard", "source_config_invalid",
}


def utc_now():
    return datetime.now(UTC)


def instant(value):
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if result.tzinfo is None:
        raise ValueError("timezone_required")
    return result.astimezone(UTC)


def hour(value):
    return instant(value).replace(minute=0, second=0, microsecond=0)


def partition(value):
    return hour(value).strftime("%Y/%m/%d/%H")


def load_manifest(store, start):
    return read_json(store, f"manifests/{partition(start)}.json")


def source_policy(source, approved):
    if not source.enabled:
        return "disabled"
    if source.id not in approved or source.retention != "long_term":
        return "unapproved"
    return None


def _collect_one(source, fetch, clock):
    try:
        items = fetch(source)
    except SourceError as exc:
        reason = exc.code
        failure = diagnostic(exc, source_id=source.id)
        skipped = getattr(exc, "skipped", 0)
        if reason not in SOURCE_ERROR_CODES:
            status = failure["http_status"]
            reason = f"http_{status}" if status is not None else "source_unavailable"
        status = "stale" if reason == "archive_stale" else "error"
        return {"status": status, "reason": reason, "count": 0, "skipped": skipped, "observed_at": None}, [], failure
    observed_at = instant(clock()).isoformat()
    distinct = {}
    seen_urls = set()
    seen_titles = set()
    for item in items:
        title_key = trend_key(item["title"])
        url = item["url"]
        identity = item["content_id"]
        # Trends may share a generic source URL. Topic identity governs that feed.
        same_content = source.kind not in {"trends", "weather"} and (url in seen_urls or title_key in seen_titles)
        if identity in distinct or same_content:
            continue
        seen_urls.add(url)
        seen_titles.add(title_key)
        distinct[identity] = {**item, "source_id": source.id, "kind": source.kind, "geo": source.geo,
                              "language": item.get("language", source.language), "observed_at": observed_at}
    status = "ok" if distinct else "empty"
    state = {
        "status": status, "observed_at": observed_at, "count": len(distinct),
        "skipped": getattr(items, "skipped", 0),
    }
    if data_day := getattr(items, "data_day", None):
        state.update(data_day=data_day, fallback=items.fallback)
    if archive_updated_at := getattr(items, "archive_updated_at", None):
        state["archive_updated_at"] = archive_updated_at
    return state, list(distinct.values()), None


def _remember_first_seen(store, rows, files):
    shards = {}
    changed = set()
    for row in rows:
        if row["kind"] == "trends":
            fingerprint = hashlib.sha256(trend_key(row["title"]).encode()).hexdigest()
        else:
            value = f"{row['source_id']}:{row['content_id']}"
            fingerprint = hashlib.sha256(value.encode()).hexdigest()
        shard = fingerprint[:2]
        key = f"first-seen/{shard}.json"
        if key not in shards:
            shards[key] = read_json(store, key) or {}
        index = shards[key]
        if fingerprint not in index:
            index[fingerprint] = row["observed_at"]
            changed.add(key)
        row["first_seen_at"] = index[fingerprint]
    for key in changed:
        files[key] = json_bytes(shards[key])


def _core_outcome(sources, states, approved):
    eligible = [s for s in sources if s.kind in CORE and not source_policy(s, approved)]
    valid = any(states.get(s.id, {}).get("status") == "ok" for s in eligible)
    my_valid = any(s.kind == "trends" and s.geo == "MY" and states[s.id]["status"] == "ok"
                   for s in eligible)
    full = my_valid and all(states[s.id]["status"] in GOOD for s in eligible)
    return "ok" if full else "partial" if valid else "failed"


def collect_slot(store, sources, approved, start, execution, *, planned_at=None, timing=None,
                 fetch=collect_source, clock=utc_now):
    started = instant(clock())
    start = hour(start)
    key = partition(start)
    manifest = load_manifest(store, start)
    if manifest:
        prior_rows = read_observations(store, key, manifest)
        states = dict(manifest["sources"])
    else:
        prior_rows, states = [], {}
    pending = []
    claim_key = f"runs/source-claims/{key}.json"
    claims = set(read_json(store, claim_key) or ())
    new_claims = set()
    for source in sources:
        prior_status = states.get(source.id, {}).get("status")
        if prior_status in GOOD or (source.kind in HOURLY_SINGLE_READ_KINDS and prior_status in {"error", "stale"}):
            continue
        policy = source_policy(source, approved)
        if policy:
            states[source.id] = {"status": policy, "count": 0, "observed_at": None}
        elif source.kind in HOURLY_SINGLE_READ_KINDS and source.id in claims:
            # A prior process could have stopped after starting the request and before its commit.
            states[source.id] = {"status": "error", "reason": "hourly_rate_guard",
                                 "count": 0, "observed_at": None}
        else:
            pending.append(source)
            if source.kind in HOURLY_SINGLE_READ_KINDS:
                new_claims.add(source.id)
    if new_claims:
        store.publish({claim_key: json_bytes(sorted(claims | new_claims))}, "Reserve hourly source requests")
    rows, diagnostics, files = [], [], {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {source.id: pool.submit(_collect_one, source, fetch, clock) for source in pending}
        for source_id, future in futures.items():
            state, items, failure = future.result()
            if source_id == "weibo_archive":
                last_update = (read_json(store, WEIBO_FRESHNESS_KEY) or {}).get("updated_at")
                updated = state.get("archive_updated_at")
                if updated and (not last_update or instant(updated) > instant(last_update)):
                    files[WEIBO_FRESHNESS_KEY] = json_bytes({"updated_at": updated})
                elif (state.get("reason") == "http_404" and last_update
                      and started - instant(last_update) > WEIBO_ARCHIVE_MAX_AGE):
                    # A dated file can be absent before the first update of a day.
                    state.update(status="stale", reason="archive_stale")
            states[source_id] = state
            rows.extend(items)
            if failure is not None:
                diagnostics.append(failure)
    run_id = "collect-" + start.strftime("%Y%m%dT%H")
    for row in rows:
        row["slot"] = start.isoformat()
        row["run_id"] = run_id
    rows.sort(key=lambda row: row["observed_at"])
    _remember_first_seen(store, rows, files)
    archive = archive_rows(prior_rows + rows)
    ended = instant(clock())
    outcome = _core_outcome(sources, states, approved)
    current = {
        "schema": 1, "slot": start.isoformat(), "run_id": run_id,
        "planned_at": planned_at.isoformat() if planned_at else (manifest or {}).get("planned_at"),
        "started_at": (manifest or {}).get("started_at", started.isoformat()), "updated_at": ended.isoformat(),
        "sha256": hashlib.sha256(archive).hexdigest(), "row_count": len(prior_rows) + len(rows),
        "sources": states, "outcome": outcome,
    }
    audit = {
        "execution": execution, "operation": "collect", "slot": start.isoformat(), "run_id": run_id,
        "planned_at": current["planned_at"], "started_at": started.isoformat(), "ended_at": ended.isoformat(),
        "elapsed_seconds": (ended - started).total_seconds(), "attempted_sources": list(futures),
        "outcome": outcome, "rows_added": len(rows), "sources": states, "diagnostics": diagnostics,
    }
    if timing is not None:
        audit.update(timing)
    archive_key = f"observations/{key}.jsonl.gz"
    if manifest is None or rows:
        files[archive_key] = archive
    else:
        current["sha256"] = manifest["sha256"]
    files[f"manifests/{key}.json"] = json_bytes(current)
    files[f"runs/{execution}.json"] = json_bytes(audit)
    alerts = _alerts(store, sources, current, start, approved)
    if alerts:
        alert_id = "alert-" + start.strftime("%Y%m%dT%H")
        alerts.insert(0, f"全球热点雷达异常 · {alert_id}")
        payload = {"parts": split_parts([(escape(line), line) for line in alerts], label=alert_id)}
        alert_key = f"reports/alerts/{alert_id}.json"
        if store.read(alert_key) is None:
            files[alert_key] = json_bytes(payload)
    store.publish(files, "Record hourly radar state")
    return current


def _alerts(store, sources, current, start, approved):
    recent = [load_manifest(store, start - HOUR * n) for n in (1, 2, 3)]
    messages = []
    enabled = [s.id for s in sources if not source_policy(s, approved)]

    def failed_in(manifest, source_id):
        return manifest and manifest["sources"].get(source_id, {}).get("status") == "error"

    states = current["sources"]
    new_failure = [key for key in enabled if states[key]["status"] == "error"
                   and all(failed_in(past, key) for past in recent[:2]) and not failed_in(recent[2], key)]
    if new_failure:
        messages.append("连续三个小时槽失败 · " + "、".join(new_failure))
    if enabled and all(states[key]["status"] == "error" for key in enabled):
        if not all(failed_in(recent[0], key) for key in enabled):
            messages.append("本小时所有已批准来源均请求失败。")
    if store.size_kib >= WARN_KIB:
        last_date = recent[0]["slot"][:10] if recent[0] else None
        if last_date != start.date().isoformat():
            messages.append("私有数据仓库已达到容量预警阈值。")
    return messages


def _window(store, now, schedule_from):
    latest = hour(now)
    starts = [latest - HOUR * n for n in range(7 * 24 + 1)]
    timeline = {start: load_manifest(store, start) for start in starts}
    closed = [start for start in starts if start < latest]
    expected = [start for start in closed if schedule_from is not None and start >= hour(schedule_from)]
    schedule_results = {
        start: manifest["outcome"] if (manifest := timeline[start]) and manifest.get("planned_at") else "missed"
        for start in expected
    }
    missed = [start.isoformat() for start in expected[:24] if schedule_results[start] == "missed"]
    health = {
        "as_of": now.isoformat(), "schedule_from": schedule_from.isoformat() if schedule_from else None,
        "expected_7d": len(expected), "repo_size_kib": store.size_kib,
        "capacity_warning": store.size_kib >= WARN_KIB,
        "states_7d": {state: sum(result == state for result in schedule_results.values())
                      for state in ("ok", "partial", "failed", "missed")},
        "latest_24h_slots": [
            {"slot": start.isoformat(), "outcome": schedule_results[start]}
            for start in reversed(expected[:24])
        ],
    }
    return timeline, missed, health


def _coverage(timeline, sources, approved, now):
    latest = hour(now)
    if timeline[latest] is None and now < latest + timedelta(minutes=17):
        latest -= HOUR
    coverage = []
    for source in sources:
        policy = source_policy(source, approved)
        current = (timeline[latest] or {}).get("sources", {}).get(source.id, {})
        last_success = max(
            (result["observed_at"] for manifest in timeline.values() if manifest
             if (result := manifest["sources"].get(source.id, {})).get("status") in GOOD),
            default=None,
        )
        status = policy or current.get("status", "not_run")
        reason = current.get("reason")
        item = {
            "source_id": source.id, "kind": source.kind, "geo": source.geo,
            "status": status,
            "reason": reason,
            "observed_at": current.get("observed_at"), "last_success_at": last_success,
        }
        if "data_day" in current:
            item.update(data_day=current["data_day"], fallback=current["fallback"])
        coverage.append(item)
    return coverage


def prepare_report(store, sources, approved, now, report_id, *, target_at=None, schedule_from=None,
                   writer=None, token_notice=None):
    year, month, day = report_id.rsplit("-", 3)[-3:]
    path = f"reports/{year}/{month}/{day}/{report_id}"
    saved = read_json(store, f"{path}.json")
    if saved:
        if not set(saved["source_ids"]) <= approved:
            raise StorageError("report_source_approval_changed")
        return saved["parts"]
    now = instant(now)
    timeline, missed, health = _window(store, now, schedule_from)
    coverage = _coverage(timeline, sources, approved, now)
    eligible = {source.id for source in sources if not source_policy(source, approved)}
    rows = [
        row for start, manifest in timeline.items() if manifest and start >= hour(now - 24 * HOUR)
        for row in read_observations(store, partition(start), manifest)
        if row["source_id"] in eligible
    ]
    historical_coverage = {
        start.isoformat(): {source_id: result["status"] for source_id, result in manifest["sources"].items()
                            if source_id in eligible}
        for start, manifest in timeline.items() if manifest and start >= hour(now - 24 * HOUR)
    }
    report = build_report(rows, coverage, now=now, target_at=target_at, missed_slots=missed,
                          historical_coverage=historical_coverage)
    # The Owner reads a short Chinese brief; the detailed digest stays in the archive.
    brief = build_brief(report.snapshot, now, report_id, writer,
                        previous_keys=previous_brief_keys(store, now.astimezone(MYT).date()),
                        token_notice=token_notice)
    parts = brief.parts
    store.publish({
        f"{path}.json": json_bytes({"parts": parts, "ranking": report.snapshot, "brief": brief.meta,
                                    "brief_entries": brief.entries, "china_parts": brief.china_parts,
                                    "source_ids": sorted({row["source_id"] for row in rows})}),
        f"{path}.md": (report.markdown.rstrip() + "\n").encode(),
        f"health/{year}/{month}/{day}.json": json_bytes(health),
    }, "Archive private radar report")
    return parts


def china_parts(store, report_id):
    """The separate China message saved with a daily or preview report; [] when there is none."""
    year, month, day = report_id.rsplit("-", 3)[-3:]
    saved = read_json(store, f"reports/{year}/{month}/{day}/{report_id}.json")
    parts = saved.get("china_parts") if isinstance(saved, dict) else None
    return parts if isinstance(parts, list) and all(isinstance(part, str) for part in parts) else []


def delivery_callbacks(store):
    def load(report_id):
        return read_json(store, f"deliveries/{report_id}.json")

    def save(report_id, message_state):
        store.publish({f"deliveries/{report_id}.json": json_bytes(message_state)}, "Record radar delivery state")

    return load, save


def deliver(store, report_id, parts, telegram):
    return send_parts(report_id, parts, telegram, *delivery_callbacks(store))
