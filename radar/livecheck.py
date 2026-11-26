"""Verify approved public feeds and the production digest in a disposable local Git repository."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, replace
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import httpx

from .delivery import _message_text
from .pipeline import (
    GOOD, MYT, SOURCE_ERROR_CODES, collect_slot, instant, partition, prepare_report, utc_now,
)
from .sources import SourceError, SourceItems, collect_source, load_sources
from .source_http import DETAIL, SourceHttp
from .storage import CODE_REPO, StorageError, _run_git, _write_files, read_json, read_observations


SUMMARY_COUNTS = ("my", "other", "fresh", "with_context", "local_news", "platforms", "weather")
PUBLIC_REASONS = SOURCE_ERROR_CODES | {"internal_error", "source_unavailable"}


class _LocalGitStore:
    """The same publish/read interface as the live store, with local commits only."""

    size_kib = 0

    def __init__(self, path):
        self.root = Path(path).resolve()
        self.git_env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TMP", "TEMP")
                        if key in os.environ}
        self.git_env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
        _run_git(["init", "--quiet", "--template="], self.root, self.git_env)

    def _path(self, key):
        path = self.root / key
        if self.root not in path.parents or path != path.resolve():
            raise StorageError("invalid_storage_key")
        return path

    def read(self, key):
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            return None

    def publish(self, files, message):
        if not files:
            return
        _write_files(self._path, files)
        _run_git(["add", "--", *files], self.root, self.git_env)
        _run_git([
            "-c", "user.name=Global Trend Radar", "-c", "user.email=radar@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-m", message,
        ], self.root, self.git_env)


def _http_status(value):
    return value if type(value) is int and 100 <= value <= 599 else None


def _public_reason(reason):
    if isinstance(reason, str) and (
        reason in PUBLIC_REASONS or re.fullmatch(r"(?:hn_item_)?http_[1-5][0-9]{2}", reason)
    ):
        return reason
    return "source_unavailable"


@dataclass
class _ProbeResult:
    rows: SourceItems
    http_status: int | None = None
    reason: str | None = None
    detail: str | None = None
    body_head: str | None = None
    body_length: int | None = None

    def replay(self):
        if self.reason is not None:
            raise SourceError(self.reason, http_status=self.http_status, skipped=self.rows.skipped)
        return self.rows


class _ProbeHttp(SourceHttp):
    """Keep the last adapter request status, including a 200 followed by a parse failure."""

    status = None
    last_body = None

    def load(self, url):
        try:
            body = super().load(url)
        except SourceError as error:
            self.status = error.http_status
            self.last_body = None
            raise
        self.status = 200
        self.last_body = body
        return body


def _body_head(body):
    """Classify how a response starts without revealing any of its text."""
    labels = []
    if body.startswith(b"\xef\xbb\xbf"):
        labels.append("bom")
        body = body[3:]
    if body[:1].isspace():
        labels.append("leading_space")
        body = body.lstrip()
    start = body[:512].lower()
    if start.startswith(b"<?xml"):
        labels.append("xml_decl")
        start = start[start.find(b"?>") + 2:].lstrip() if b"?>" in start else b""
    if start.startswith(b"<!doctype html") or start.startswith(b"<html"):
        labels.append("html")
    elif start.startswith(b"<!doctype"):
        labels.append("doctype")
    elif start.startswith(b"<rss") or start.startswith(b"<feed"):
        labels.append("feed")
    elif start.startswith(b"<!--"):
        labels.append("comment")
    elif not start:
        labels.append("empty")
    else:
        labels.append("other")
    return "+".join(labels)


def _probe_source(source):
    if source.retention != "long_term":
        return _ProbeResult(SourceItems(), reason="retention_approval_required")
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=httpx.Timeout(5.0, connect=4.0)) as client:
        transport = _ProbeHttp(client)
        try:
            rows = collect_source(source, transport)
        except SourceError as error:
            skipped = error.skipped if type(error.skipped) is int and error.skipped >= 0 else 0
            body = transport.last_body if error.code == "invalid_xml" else None
            return _ProbeResult(
                SourceItems(skipped=skipped), _http_status(error.http_status) or transport.status,
                _public_reason(error.code), getattr(error, "detail", None),
                _body_head(body) if body is not None else None, len(body) if body is not None else None,
            )
        except Exception:
            return _ProbeResult(SourceItems(), transport.status, "internal_error")
        return _ProbeResult(rows, transport.status)


def _newest_age(rows, now):
    dated = []
    for row in rows:
        try:
            value = row.get("published_at") or row.get("seen_at")
            if value:
                published = instant(value)
                if published <= now:
                    dated.append(published)
        except (AttributeError, ValueError, TypeError, OverflowError):
            continue
    return int((now - max(dated)).total_seconds() // 60) if dated else None


def _source_line(source_id, state, probe, observed_rows, now):
    if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", source_id) is None:
        raise ValueError("invalid_source_id")
    status = state["status"]
    if status not in {"ok", "empty", "error"}:
        raise ValueError("invalid_probe_status")
    age = _newest_age(observed_rows, now)
    reason = _public_reason(probe.reason) if status == "error" else "-"
    return (
        f"source={source_id} status={status} count={state['count']:d} skipped={state.get('skipped', 0):d} "
        f"http={_http_status(probe.http_status) or '-'} newest_age_min={age if age is not None else '-'} "
        f"reason={reason}"
    )


def _diagnostic_line(source_id, probe):
    if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", source_id) is None:
        raise ValueError("invalid_source_id")
    detail = probe.detail if probe.detail and DETAIL.fullmatch(probe.detail) else "-"
    head = probe.body_head if probe.body_head and re.fullmatch(r"[a-z_+]{1,64}", probe.body_head) else "-"
    length = probe.body_length if type(probe.body_length) is int else "-"
    return f"diagnostic source={source_id} detail={detail} body={head} length={length}"


def _report_line(parts, counts, degraded):
    lengths = [len(_message_text(part).encode("utf-16-le")) // 2 for part in parts]
    sizes = ",".join(str(length) for length in lengths) or "-"
    metrics = " ".join(f"{key}={counts.get(key, 0):d}" for key in SUMMARY_COUNTS)
    return f"report parts={len(lengths)} chars={sizes} {metrics} degraded={str(bool(degraded)).lower()}"


def _check_replay(store, start, first, second, eligible, archive):
    audit = read_json(store, "runs/live-check-2.json")
    failures = [source.id for source in eligible if first["sources"][source.id]["status"] == "error"]
    if (
        audit["attempted_sources"] != failures or audit["rows_added"] != 0
        or second["sha256"] != first["sha256"] or second["row_count"] != first["row_count"]
        or second["sources"] != first["sources"]
        or store.read(f"observations/{partition(start)}.jsonl.gz") != archive
    ):
        raise ValueError("non_idempotent_local_collection")


def run_checks(store, sources, emit, *, probe_gdelt=True, probe=_probe_source, clock=utc_now):
    """Probe once, replay failed results offline, and verify the production digest."""
    active = [source for source in sources if source.enabled]
    eligible = [source for source in active if source.retention == "long_term"]
    approved = {source.id for source in eligible}
    pending = {source.id: _ProbeResult(SourceItems(), reason="retention_approval_required")
               for source in active if source.id not in approved}
    probes = {}

    def fetch_once(source):
        if source.id in probes:
            raise ValueError("repeated_live_probe")
        result = probe(source)
        probes[source.id] = result
        return result.replay()

    start = clock()
    first = collect_slot(store, sources, approved, start, "live-check-1", fetch=fetch_once, clock=clock)
    archive = store.read(f"observations/{partition(start)}.jsonl.gz")
    rows = read_observations(store, partition(start), first)
    as_of = clock()
    diagnostics = []
    for source in active:
        state = first["sources"][source.id] if source.id in approved else {"status": "error", "count": 0}
        result = probes[source.id] if source.id in approved else pending[source.id]
        emit(_source_line(source.id, state, result, (row for row in rows if row["source_id"] == source.id), as_of))
        if result.reason and result.detail:
            diagnostics.append(_diagnostic_line(source.id, result))
    if probe_gdelt:
        candidate = next((source for source in sources if source.kind == "gdelt" and not source.enabled), None)
        if candidate is not None:
            result = probe(replace(candidate, enabled=True, retention="long_term"))
            status = "error" if result.reason else "ok" if result.rows else "empty"
            state = {"status": status, "count": len(result.rows), "skipped": result.rows.skipped}
            emit(_source_line(candidate.id, state, result, result.rows, clock()))
            if result.reason and result.detail:
                diagnostics.append(_diagnostic_line(candidate.id, result))
    for line in diagnostics:
        emit(line)

    second = collect_slot(
        store, sources, approved, start, "live-check-2", fetch=lambda source: probes[source.id].replay(), clock=clock,
    )
    _check_replay(store, start, first, second, eligible, archive)
    now = clock()
    day = now.astimezone(MYT).date()
    report_id = f"live-check-{day.isoformat()}"
    parts = prepare_report(store, sources, approved, now, report_id)
    report = read_json(store, f"reports/{day:%Y/%m/%d}/{report_id}.json")["ranking"]
    emit(_report_line(parts, report["rendered_counts"], report["degraded"]))
    return int(
        not active or bool(pending) or first["outcome"] != "ok"
        or any(first["sources"][source.id]["status"] not in GOOD for source in eligible)
        or report["degraded"] or len(parts) != 1
    )


def _authorized(env):
    return (
        env.get("GITHUB_ACTIONS") == "true"
        and env.get("GITHUB_REPOSITORY") == CODE_REPO
        and env.get("GITHUB_REF") == "refs/heads/main"
        and env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and env.get("GITHUB_WORKFLOW_REF") == f"{CODE_REPO}/.github/workflows/live-check.yml@refs/heads/main"
    )


def main(env=None):
    env = os.environ if env is None else env
    if not _authorized(env):
        return 1
    lines = []
    with open(os.devnull, "w", encoding="utf-8") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
        try:
            with TemporaryDirectory(prefix="radar-live-check-", dir=env.get("RUNNER_TEMP")) as directory:
                code = run_checks(
                    _LocalGitStore(directory), load_sources(), lines.append,
                    probe_gdelt=env.get("RADAR_PROBE_GDELT", "true") == "true",
                )
        except Exception:
            if lines and lines[-1].startswith("report "):
                lines.pop()
            lines.append(_report_line([], {}, True))
            code = 1
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
