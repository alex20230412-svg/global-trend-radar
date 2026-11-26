"""Build the private Chinese digest and its auditable ranking snapshot.

The digest is written for reading on a phone: every topic appears once, markers carry
the NEW / RISING evidence, and source health collapses into a short footer. The full
ranking (scores, baselines, media evidence) stays in the archived snapshot.
"""

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
DIGEST_VERSION = "compact-v1"
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
CATEGORY_TAGS = {
    "商品 / 消费": "消费", "AI / 科技": "科技", "娱乐": "娱乐", "体育": "体育", "公共事务": "公共",
}
INACTIVE = {"disabled", "unapproved"}
GOOD = {"ok", "empty"}
UNCOVERED = "未覆盖：马来西亚华文媒体、TikTok、Facebook、Instagram、X；平台榜只代表各自用户群。"
TITLE_LIMIT = 80
CONTEXT_LIMIT = 100
PLATFORM_TITLE_LIMIT = 60


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


class _Text:
    """Build matching Telegram HTML and visible plain text in one pass."""

    def __init__(self):
        self.html = []
        self.plain = []

    def add(self, text, *, bold=False, url=None):
        safe = escape(text, quote=False)
        if url:
            safe = f'<a href="{escape(url, quote=True)}">{safe}</a>'
        if bold:
            safe = f"<b>{safe}</b>"
        self.html.append(safe)
        self.plain.append(text)
        return self

    def block(self):
        return ReportBlock("".join(self.html), "".join(self.plain))


def _display(value, limit=200):
    text = "".join(
        char for char in str(value)
        if char == "‍" or unicodedata.category(char) not in {"Cf", "Cs", "Cc"} or char.isspace()
    )
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _time(value, *, short=False):
    if value is None:
        return "无记录"
    return instant(value).astimezone(MYT).strftime("%m-%d %H:%M" if short else "%Y-%m-%d %H:%M MYT")


def _label(source):
    kind = source["kind"]
    identifier = source["source_id"]
    if kind == "trends":
        return f"Google Trends {_display(source['geo'], 16)}"
    if kind == "mastodon":
        subtype = "链接" if "link" in identifier else "标签"
        return f"Mastodon {subtype}"
    return SOURCE_NAMES.get(identifier, KIND_NAMES.get(kind, _display(identifier, 40)))


def _url(entry):
    return clean_url(entry.get("url"), keep_fragment=True)


def _section(heading, lines):
    """One block per section: a bold heading and its lines separated by single newlines."""
    text = _Text().add(heading, bold=True)
    for line in lines:
        text.add("\n")
        text.html.append(line.html)
        text.plain.append(line.plain)
    return text.block()


def _line(text):
    return _Text().add(text).block()


def _growth_marker(entry):
    for signal in entry.get("growth") or ():
        if signal["kind"] == "volume":
            return f"🚀{_display(signal['before'], 16)}→{_display(signal['after'], 16)}"
        if signal["kind"] == "geos":
            added = sorted(set(signal["after"]) - set(signal["before"]))
            return "🚀扩散到 " + "/".join(_display(region, 8) for region in added)
        if signal["kind"] == "media":
            return f"🚀媒体 {len(signal['before'])}→{len(signal['after'])} 家"
    return None


def _topic_line(number, entry, *, volume=None, regions=None, marker=None):
    text = _Text().add(f"{number}. ")
    text.add(_display(entry["title"], TITLE_LIMIT), url=_url(entry))
    details = []
    if volume:
        details.append(_display(volume, 24))
    if marker:
        details.append(marker)
    if regions:
        details.append(regions)
    media = entry.get("media") or ()
    if media:
        details.append(f"📰{len(media)} 家本地媒体")
    tag = CATEGORY_TAGS.get(entry.get("category"))
    if tag:
        details.append(tag)
    if details:
        text.add(" · " + " · ".join(details))
    context = entry.get("context")
    if isinstance(context, dict) and context.get("title"):
        text.add("\n   ↳ ")
        text.add(_display(context["title"], CONTEXT_LIMIT), url=clean_url(context.get("url")))
        if context.get("publisher"):
            text.add(f"（{_display(context['publisher'], 40)}）")
    return text


def _regions(geos, *, exclude=None):
    others = [_display(geo, 8) for geo in geos if geo != exclude]
    return "/".join(others)


def _coverage_snapshot(coverage, now, config):
    fresh_since = now - timedelta(hours=config["freshness_hours"])
    result = {}
    for item in coverage:
        source = dict(item)
        last = instant(source.get("last_success_at"))
        observed = instant(source.get("observed_at"))
        source["last_success_at"] = last.isoformat() if last else None
        source["observed_at"] = observed.isoformat() if observed else None
        if source["status"] in GOOD:
            freshness = observed or last
            if freshness is None or not fresh_since <= freshness <= now:
                source["status"] = "stale"
        result[source["source_id"]] = source
    return result


def _footer(coverage, missed_slots):
    sources = sorted(coverage.values(), key=lambda item: (item["kind"], _label(item), item["source_id"]))
    active = [source for source in sources if source["status"] not in INACTIVE]
    normal = sum(source["status"] in GOOD for source in active)
    lines = [_line(f"来源 {normal}/{len(active)} 正常")]
    problems = []
    for source in active:
        if source["status"] in GOOD:
            continue
        status = STATUS_NAMES.get(source["status"], "状态不明")
        reason = _display(source.get("reason") or "", 32)
        detail = f"{status}：{reason}" if reason else status
        last = f"，上次成功 {_time(source['last_success_at'], short=True)}" if source["last_success_at"] else ""
        problems.append(f"{_label(source)}（{detail}{last}）")
    if problems:
        lines.append(_line("异常：" + "、".join(problems)))
    pending = sum(source["status"] == "unapproved" for source in sources)
    disabled = sum(source["status"] == "disabled" for source in sources)
    if pending or disabled:
        lines.append(_line(f"待核准 {pending} 个 · 关闭 {disabled} 个"))
    if missed_slots:
        sample = "、".join(_time(slot, short=True) for slot in missed_slots[-4:])
        lines.append(_line(f"计划采集缺口 {len(missed_slots)} 槽 · 最近 {sample}"))
    lines.append(_line(UNCOVERED))
    return _section("ℹ️ 来源状态", lines)


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
    my_degraded = my_source.get("status") not in GOOD
    degraded = my_degraded or any(source["status"] not in GOOD for source in core)
    delay = math.ceil(max(0.0, (now - target_at).total_seconds()) / 60) if target_at else None

    header = [f"数据截至 {_time(now)} · 最近观测 {_time(latest)}"]
    if delay:
        header.append(f"计划 {_time(target_at, short=True)} · 迟到 {delay} 分钟")
    if my_degraded:
        header.append("⚠️ 降级 · Google Trends MY 当前缺失，马来西亚热搜暂停显示。")
    elif my_source.get("status") == "empty":
        header.append("Google Trends MY 最新响应有效，暂无热词。")
    if degraded and not my_degraded:
        header.append("⚠️ 降级 · 部分核心来源缺失，结果可能偏向可用来源。")
    header.append(f"🚀 快速升温 · 🆕 {config['window_hours']} 小时内新出现 · 量级为 Google Trends 近似搜索量")
    blocks = [_section(f"🔥 全球热点雷达 · {_time(target_at or now)}", [_line(text) for text in header])]

    markers = {}
    for entry in ranking["new"]:
        markers[trend_key(entry["title"])] = "🆕"
    for entry in ranking["rising"]:
        markers[trend_key(entry["title"])] = _growth_marker(entry)
    shown = set()

    if not my_degraded:
        lines = []
        for number, entry in enumerate(ranking["malaysia"], 1):
            key = trend_key(entry["title"])
            shown.add(key)
            regions = _regions(entry.get("geos") or (), exclude="MY")
            lines.append(_topic_line(
                number, entry, volume=entry.get("volume_raw"), marker=markers.get(key),
                regions=f"也在 {regions}" if regions else None,
            ).block())
        if not lines and my_source.get("status") != "empty":
            lines.append(_line("本报告窗口没有合格观测。"))
        if lines:
            blocks.append(_section("🇲🇾 马来西亚热搜", lines))

    extra = []
    for entry in ranking["monitored_regions"]:
        key = trend_key(entry["title"])
        if key in shown or len(extra) >= config.get("digest_global_limit", 5):
            continue
        shown.add(key)
        extra.append(_topic_line(
            len(extra) + 1, entry, marker=markers.get(key), regions=_regions(entry["geos"]),
        ).block())
    if extra:
        blocks.append(_section("🌏 其他地区热搜", extra))

    fresh = []
    for entry in [*ranking["rising"], *ranking["new"]]:
        key = trend_key(entry["title"])
        if key in shown:
            continue
        shown.add(key)
        fresh.append(_topic_line(
            len(fresh) + 1, entry, marker=markers.get(key), regions=_regions(entry["geos"]),
        ).block())
    if fresh:
        blocks.append(_section("✨ 新冒头 / 升温", fresh))

    if ranking["local_news"]:
        news = []
        for number, entry in enumerate(ranking["local_news"], 1):
            news.append(_Text().add(f"{number}. ").add(_display(entry["title"], TITLE_LIMIT), url=_url(entry))
                        .add(f" · {_label(entry)}").block())
        blocks.append(_section("📰 马来西亚本地新闻", news))

    platforms = []
    for source in sorted(coverage.values(), key=lambda item: (item["kind"], _label(item), item["source_id"])):
        if source["kind"] not in {"bluesky", "mastodon", "hn"} or source["status"] in INACTIVE:
            continue
        items = ranking["platforms"].get(source["source_id"], [])
        text = _Text().add(f"{_label(source)}：")
        if not items:
            text.add(f"暂无 · {STATUS_NAMES.get(source['status'], '状态不明')}")
        for index, entry in enumerate(items):
            if index:
                text.add(" / ")
            text.add(_display(entry["title"], PLATFORM_TITLE_LIMIT), url=_url(entry))
        platforms.append(text.block())
    if platforms:
        blocks.append(_section("💬 社交与科技", platforms))

    weather_source = [source for source in coverage.values() if source["kind"] == "weather"]
    if weather_source and all(source["status"] not in INACTIVE for source in weather_source):
        weather_available = any(source["status"] in GOOD for source in weather_source)
        lines = []
        for entry in ranking["weather"]:
            lines.append(_Text().add("• ").add(_display(entry["title"], TITLE_LIMIT), url=_url(entry))
                         .add(f" · 至 {_time(entry['valid_to'], short=True)}").block())
        if ranking["weather"]:
            attribution = _Text().add("来源 MET Malaysia · ")
            attribution.add("CC BY 4.0", url="https://creativecommons.org/licenses/by/4.0/").add(" · 已节选")
            lines.append(attribution.block())
        else:
            lines.append(_line("最新可用响应无有效警告。" if weather_available else "气象数据缺失，无法判断警告。"))
        blocks.append(_section("⚠️ 气象警告", lines))

    blocks.append(_footer(coverage, missed))

    snapshot = {
        **ranking,
        "digest_version": DIGEST_VERSION,
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
