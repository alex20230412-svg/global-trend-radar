"""Build the private Chinese digest and its auditable ranking snapshot."""

from dataclasses import dataclass
from datetime import timedelta, timezone
from html import escape
import math
from typing import NamedTuple
import unicodedata
from .scoring import instant, load_scoring, rank_observations, trend_key
from .sources import clean_url


MYT = timezone(timedelta(hours=8), "MYT")
CORE_KINDS = {"trends", "news"}
SOURCE_NAMES = {
    "malaysiakini": "Malaysiakini",
    "malay_mail": "Malay Mail",
    "fmt": "Free Malaysia Today",
    "bernama": "Bernama",
}
KIND_NAMES = {
    "hn": "Hacker News", "bluesky": "Bluesky", "mastodon": "Mastodon",
    "weather": "data.gov.my 气象", "gdelt": "GDELT",
}
STATUS_NAMES = {
    "ok": "可用", "empty": "有效空结果", "error": "失败", "partial": "部分返回", "disabled": "关闭",
    "unapproved": "待核准", "not_run": "未运行", "stale": "数据过旧",
}


class ReportBlock(NamedTuple):
    html: str
    plain: str


@dataclass
class Report:
    blocks: list[ReportBlock]
    snapshot: dict

    @property
    def markdown(self):
        return "\n\n".join(block.html for block in self.blocks) + "\n"


def _display(value, limit=200):
    text = "".join(
        char for char in str(value)
        if char == "\u200d" or unicodedata.category(char) not in {"Cf", "Cs", "Cc"} or char.isspace()
    )
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _time(value, *, short=False):
    if value is None:
        return "无记录"
    return instant(value).astimezone(MYT).strftime("%m-%d %H:%M" if short else "%Y-%m-%d %H:%M MYT")


def _line(text, *, heading=False):
    safe = escape(text, quote=False)
    return ReportBlock(f"<b>{safe}</b>" if heading else safe, text)


def _label(source):
    kind = source["kind"]
    identifier = source["source_id"]
    if kind == "trends":
        return f"Google Trends {_display(source['geo'], 16)}"
    if kind == "mastodon":
        subtype = "链接" if "link" in identifier else "标签"
        return f"Mastodon {subtype}"
    return SOURCE_NAMES.get(identifier, KIND_NAMES.get(kind, _display(identifier, 40)))


def _linked_line(prefix, entry, extra):
    title = _display(entry["title"])
    language = _display(entry.get("language") or "und", 24)
    suffix = f" [{language}] · {extra}"
    safe_title = escape(title, quote=False)
    url = clean_url(entry.get("url"), keep_fragment=True)
    if url:
        safe_title = f'<a href="{escape(url, quote=True)}">{safe_title}</a>'
    return ReportBlock(
        f"{escape(prefix, quote=False)}{safe_title}{escape(suffix, quote=False)}",
        f"{prefix}{title}{suffix}",
    )


def _trend_text(entry, *, local=False):
    metadata = []
    if local:
        volume = _display(entry.get("volume_raw") or "未知", 24)
        metadata.append(f"搜索量级 {volume}")
        metadata.append(
            f"本地媒体证据 {len(entry['media'])} 家" if entry["media_covered"] else "本地媒体覆盖缺失"
        )
    else:
        regions = " / ".join(_display(region, 16) for region in entry["geos"])
        metadata.append(regions)
    metadata.extend((
        entry["category"],
        f"系统首见 {_time(entry['first_seen_at'], short=True)}",
        f"最近观测 {_time(entry['observed_at'], short=True)}",
    ))
    return " · ".join(metadata)


def _growth_text(entry):
    parts = []
    for signal in entry["growth"]:
        if signal["kind"] == "volume":
            before, after = (_display(signal[key], 24) for key in ("before", "after"))
            parts.append(f"{_display(signal['geo'], 16)} 搜索量级 {before} → {after}")
        elif signal["kind"] == "geos":
            additional = sorted(set(signal["after"]) - set(signal["before"]))
            regions = " / ".join(_display(region, 16) for region in additional)
            parts.append(f"新增观测地区 {regions}")
        else:
            parts.append(f"本地媒体证据 {len(signal['before'])} → {len(signal['after'])} 家")
    parts.append(_trend_text(entry))
    return " · ".join(parts)


def _platform_text(entry):
    rank = entry.get("rank")
    rank_label = f"平台第 {rank} · " if rank else ""
    return rank_label + f"观测 {_time(entry['observed_at'], short=True)}"


def _news_text(entry):
    published = entry.get("published_at")
    timestamp = f"发布 {_time(published, short=True)}" if published else (
        f"发布日期缺失，系统首见 {_time(entry['first_seen_at'], short=True)}"
    )
    return f"{_label(entry)} · {timestamp}"


def _weather_text(entry):
    return (f"有效期 {_time(entry.get('valid_from'), short=True)} 至 "
            f"{_time(entry['valid_to'], short=True)} · {_label(entry)}")


def _category_text(entry):
    if entry["kind"] == "news":
        return _news_text(entry)
    if "geos" in entry:
        return _trend_text(entry)
    return _trend_text(entry, local=True)


def _entries(blocks, heading, items, describe, empty):
    blocks.append(_line(heading, heading=True))
    if not items:
        blocks.append(_line(empty))
    for index, item in enumerate(items, start=1):
        blocks.append(_linked_line(f"{index}. ", item, describe(item)))


def _coverage_snapshot(coverage, now, config):
    fresh_since = now - timedelta(hours=config["freshness_hours"])
    result = {}
    for item in coverage:
        source = dict(item)
        last = instant(source.get("last_success_at"))
        observed = instant(source.get("observed_at"))
        source["last_success_at"] = last.isoformat() if last else None
        source["observed_at"] = observed.isoformat() if observed else None
        if source["status"] in {"ok", "empty"}:
            freshness = observed or last
            if freshness is None or not fresh_since <= freshness <= now:
                source["status"] = "stale"
        result[source["source_id"]] = source
    return result


def _coverage_count(coverage, kind):
    sources = [source for source in coverage.values() if source["kind"] == kind]
    usable = sum(source["status"] in {"ok", "empty"} for source in sources)
    return f"{usable}/{len(sources)}"


def _coverage_lines(blocks, coverage, missed_slots):
    blocks.append(_line("数据来源覆盖与缺失", heading=True))
    for source in sorted(coverage.values(), key=lambda item: (item["kind"], _label(item), item["source_id"])):
        status = STATUS_NAMES.get(source["status"], "状态不明")
        reason = _display(source.get("reason") or "", 48)
        last = source["last_success_at"]
        label = f"{_label(source)} · {status}"
        if reason:
            label += f" ({reason})"
        if last:
            label += f" · 上次成功 {_time(last, short=True)}"
        blocks.append(_line(label))
    if missed_slots:
        sample = "、".join(_time(slot, short=True) for slot in missed_slots[-8:])
        blocks.append(_line(f"计划采集缺口 {len(missed_slots)} 槽 · 最近缺口 {sample} MYT"))
    else:
        blocks.append(_line("报告时间窗内未记录计划采集缺口。"))
    blocks.append(_line(
        "覆盖缺口包括马来西亚华文媒体及 TikTok、Facebook、Instagram、X；平台榜仅代表各自用户群。"
    ))


def build_report(observations, coverage, *, now, target_at=None, missed_slots=(), config_path=None,
                 historical_coverage=None):
    """Render only known observations through the report's actual cutoff."""
    config = load_scoring(config_path)
    now, target_at = instant(now), instant(target_at)
    missed = sorted({instant(slot) for slot in missed_slots})
    coverage = _coverage_snapshot(coverage, now, config)
    ranking = rank_observations(observations, coverage, now, config, historical_coverage or {})
    latest = ranking.pop("data_latest_observation")
    core = [source for source in coverage.values() if source["kind"] in CORE_KINDS]
    core_success = max((instant(source["last_success_at"]) for source in core if source["last_success_at"]), default=None)
    my_source = next((source for source in core if source["geo"] == "MY" and source["kind"] == "trends"), {})
    my_degraded = my_source.get("status") not in {"ok", "empty"}
    degraded = my_degraded or any(source["status"] not in {"ok", "empty"} for source in core)
    delay = math.ceil(max(0.0, (now - target_at).total_seconds()) / 60) if target_at else None

    blocks = [_line(f"全球热点雷达 · {_time(target_at or now)}", heading=True)]
    if target_at:
        blocks.append(_line(f"计划 {_time(target_at)} · 实际生成 {_time(now)}" +
                            (f" · 迟到 {delay} 分钟" if delay else "")))
    blocks.extend((
        _line(f"数据截止 {_time(now)} · 最近观测 {_time(latest)}"),
        _line(f"核心来源最近成功 {_time(core_success)}"),
        _line("近时覆盖 · Google Trends " + _coverage_count(coverage, "trends")
              + " · 马来西亚媒体 " + _coverage_count(coverage, "news")
              + " · Bluesky " + _coverage_count(coverage, "bluesky")
              + " · Mastodon " + _coverage_count(coverage, "mastodon")
              + " · Hacker News " + _coverage_count(coverage, "hn")),
        _line("Google Trends 表示搜索飙升，各地搜索量级单独观察。条目观测时间为 MYT。"),
    ))
    if my_degraded:
        blocks.append(_line("降级 · Google Trends MY 当前缺失，马来西亚搜索榜暂停显示。"))
    elif my_source.get("status") == "empty":
        blocks.append(_line("Google Trends MY 最新响应有效，暂无热词。"))
    if degraded and not my_degraded:
        blocks.append(_line("降级 · 核心来源覆盖不完整，监测结果可能偏向可用来源。"))
    blocks.append(_line(f"搜索榜统计范围为最近 {config['window_hours']} 小时，采用当前可用来源。"))

    empty = "当前报告窗口没有合格观测。"
    _entries(blocks, f"🇲🇾 马来西亚热门 TOP {config['my_limit']}", ranking["malaysia"],
             lambda entry: _trend_text(entry, local=True), empty)
    if ranking["local_news"]:
        _entries(blocks, "马来西亚本地媒体", ranking["local_news"], _news_text, empty)
    _entries(blocks, f"🌏 监测地区热门 TOP {config['global_limit']}", ranking["monitored_regions"],
             _trend_text, empty)
    _entries(blocks, f"🆕 新出现 NEW · 最多 {config['new_limit']} 条", ranking["new"],
             _trend_text, empty)
    _entries(blocks, f"🚀 快速升温 RISING · 最多 {config['rising_limit']} 条", ranking["rising"],
             _growth_text, "缺少足够的可比较观测，或暂无量级／扩散上升证据。")

    blocks.append(_line("💬 社交与科技", heading=True))
    for source in sorted(coverage.values(), key=lambda item: (item["kind"], _label(item), item["source_id"])):
        if source["kind"] in {"bluesky", "mastodon", "hn"}:
            _entries(blocks, _label(source), ranking["platforms"].get(source["source_id"], []), _platform_text,
                     f"暂无可列条目 · {STATUS_NAMES.get(source['status'], '状态不明')}。")
    for category, items in ranking["categories"].items():
        _entries(blocks, f"{category}线索", items, _category_text, empty)

    weather_available = any(
        source["kind"] == "weather" and source["status"] in {"ok", "empty"} for source in coverage.values()
    )
    _entries(blocks, "⚠️ 气象警告", ranking["weather"], _weather_text,
             "最新可用响应无有效警告。" if weather_available else "气象数据缺失，无法判断警告。")
    if ranking["weather"]:
        blocks.append(ReportBlock(
            '来源 MET Malaysia · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> · 已节选',
            "来源 MET Malaysia · CC BY 4.0 · 已节选",
        ))
    _coverage_lines(blocks, coverage, missed)

    snapshot = {
        **ranking,
        "cutoff_at": now.isoformat(),
        "latest_observed_at": latest.isoformat() if latest else None,
        "last_core_success_at": core_success.isoformat() if core_success else None,
        "target_at": target_at.isoformat() if target_at else None,
        "delay_minutes": delay,
        "coverage": list(coverage.values()),
        "degraded": degraded,
        "missed_slots": [slot.isoformat() for slot in missed],
    }
    return Report(blocks, snapshot)
