"""Build a weekly recap from the entries actually delivered in daily briefs."""

from collections import defaultdict
from datetime import timedelta
from html import escape
import json
import re
import unicodedata
from urllib.parse import urlsplit

from .delivery import split_parts
from .history import read_daily_entries
from .layout import quote_blocks, table_block, table_header, table_row
from .sources import clean_url
from .storage import json_bytes, read_json


WEEKLY_CRON = "0 1 * * 0"
WEEKLY_REPORT_ID = re.compile(r"weekly-(?:\d{4}-W\d{2}|preview-\d{4}-\d{4}-\d{2}-\d{2})\Z")
TOPICS = {"malaysia", "global", "china", "wiki"}
SECTIONS = TOPICS | {"music", "apps"}
CHARTS = (
    ("🔥 本周持续最热", "malaysia", 10),
    ("🎵 本周常上榜的歌曲", "music", 5),
    ("📱 本周常上榜的 App", "apps", 5),
    ("🔍 本周常查的维基条目", "wiki", 5),
    ("🇨🇳 本周中国热议", "china", 5),
)
IDEAS_SYSTEM = """你是马来西亚中文周报编辑。根据收到的条目提出三到五个可验证的生意假设。
只根据给定条目推想，使用保守措辞。不得添加不存在的数字、地点、人名和事件。
每条用 ids 标注一个或多个给定的条目编号，text 用一句不超过 65 字的简体中文。
输入不足时可以少写。只输出 JSON：{"items":[],"ideas":[{"text":"...","ids":["w1"]}]}。"""


def weekly_key(day):
    iso = day.isocalendar()
    return f"weekly-{iso.year:04d}-W{iso.week:02d}"


def weekly_archive_key(report_id):
    return f"reports/weekly/{report_id}.json"


def _text(value, limit):
    if not isinstance(value, str):
        return ""
    clean = " ".join("".join(char for char in value if unicodedata.category(char) not in {"Cc", "Cf", "Cs"}).split())
    return clean if len(clean) <= limit else clean[:limit - 1] + "…"


def _supported_entry(entry):
    section = entry.get("section") if isinstance(entry, dict) else None
    if not isinstance(section, str) or section not in SECTIONS:
        return None
    key = entry.get("key")
    title = _text(entry.get("title"), 140)
    url = clean_url(entry.get("url"))
    host = urlsplit(url).hostname if url else ""
    # Weekly consumes daily data only. Keep YouTube links out even if a non-YouTube feed included one.
    if not isinstance(key, str) or not key or not title or any(
        host == domain or host.endswith("." + domain)
        for domain in ("youtube.com", "youtu.be", "youtube-nocookie.com")
    ):
        return None
    return {"key": key, "section": section, "title": title, "url": url}


def _occurrences(days):
    """Take at most one occurrence per category and key on a date."""
    by_section = defaultdict(lambda: defaultdict(list))
    topics = defaultdict(list)
    for day, entries in days.items():
        seen = set()
        seen_topics = set()
        section_rank = defaultdict(int)
        for raw in entries:
            entry = _supported_entry(raw)
            if entry is None:
                continue
            section, key = entry["section"], entry["key"]
            if (section, key) in seen:
                continue
            seen.add((section, key))
            section_rank[section] += 1
            occurrence = (day, section_rank[section], entry)
            by_section[section][key].append(occurrence)
            if section in TOPICS and key not in seen_topics:
                seen_topics.add(key)
                topics[key].append(occurrence)
    return by_section, topics


def _ordered(occurrences, limit):
    return sorted(occurrences.values(), key=lambda items: (
        -len(items), sum(rank for _, rank, _ in items), items[-1][2]["key"],
    ))[:limit]


def _window(store, first, count):
    days = {}
    for offset in range(count):
        day = first + timedelta(days=offset)
        entries = read_daily_entries(store, day)
        if entries is not None:
            days[day] = entries
    return days


def _ideas(rows, writer):
    if writer is None or not rows:
        return []
    prompt_items = {
        f"w{i}": {"title": hits[-1][2]["title"], "days": len(hits)}
        for i, hits in enumerate(rows, 1)
    }
    try:
        text, _, _ = writer.write(IDEAS_SYSTEM, json.dumps(prompt_items, ensure_ascii=False))
        payload = json.loads(text)
    except (ValueError, TypeError, RuntimeError):
        return []
    ideas = payload.get("ideas") if isinstance(payload, dict) else None
    if not isinstance(ideas, list):
        return []
    output = []
    seen = set()
    for entry in ideas:
        if not isinstance(entry, dict):
            continue
        text = _text(entry.get("text"), 65)
        ids = entry.get("ids")
        if (not text or text in seen or not isinstance(ids, list) or not ids
                or any(not isinstance(key, str) or key not in prompt_items for key in ids)):
            continue
        numbers = set(re.findall(r"\d+", text))
        original = " ".join(prompt_items[key]["title"] for key in ids)
        if not numbers <= set(re.findall(r"\d+", original)):
            continue
        seen.add(text)
        output.append(text)
        if len(output) == 5:
            break
    return output


def build_weekly(store, day, report_id, *, writer=None, token_notice=None):
    """Render this ISO week's delivered reports through the chosen MYT date."""
    first = day - timedelta(days=day.weekday())
    expected = day.weekday() + 1
    current = _window(store, first, expected)
    previous = _window(store, first - timedelta(days=7), 7)
    sections, topics = _occurrences(current)
    _, older_topics = _occurrences(previous)
    recent = sorted(
        (hits for key, hits in topics.items() if key not in older_topics),
        key=lambda hits: (-hits[0][0].toordinal(), -len(hits), hits[0][1], hits[0][2]["key"]),
    )[:5] if previous else []

    title = f"📅 {first:%m月%d日}–{day:%m月%d日} 热点周报"
    coverage = f"本周已送达且可统计 {len(current)}/{expected} 天 · 前一周 {len(previous)}/7 天"
    blocks = [(f"<b>{escape(title)}</b>\n{escape(coverage)}", f"{title}\n{coverage}")]
    tables, details = [], []
    chart_rows = [(heading, _ordered(sections[section], limit)) for heading, section, limit in CHARTS]
    chart_rows.insert(1, ("🆕 本周新冒出来", recent))
    for heading, hits_list in chart_rows:
        if not hits_list:
            continue
        rows = []
        links = []
        for rank, hits in enumerate(hits_list, 1):
            entry = hits[-1][2]
            rows.append(table_row(rank, f"{len(hits)}天", entry["title"], metric_width=3))
            links.append((f"{rank}. {entry['title']} · {len(hits)} 天", entry["url"]))
        tables.append((heading, table_header("天", "条目", metric_width=3), rows))
        details.extend(quote_blocks(f"{heading}（点开看）", links))
    if tables:
        blocks.append(table_block(tables))
        blocks.extend(details)
    else:
        text = "本周暂无可统计的早报。"
        blocks.append((text, text))
    if current and not previous:
        text = "前一周没有可比较的早报，新冒头榜暂缺。"
        blocks.append((text, text))
    elif recent and len(previous) < 7:
        text = "前一周记录不全，新冒头榜仅按已有日报比较。"
        blocks.append((text, text))

    ideas_input = _ordered(topics, 10)
    seen = {hits[-1][2]["key"] for hits in ideas_input}
    for section in ("music", "apps"):
        for hits in _ordered(sections[section], 4):
            key = hits[-1][2]["key"]
            if key not in seen:
                seen.add(key)
                ideas_input.append(hits)
    ideas = _ideas(ideas_input, writer)
    if ideas:
        title = "💡 可能的生意线索（AI 推测，仅供参考）"
        rows = "\n".join(f"• {idea}" for idea in ideas)
        blocks.append((f"<b>{escape(title)}</b>\n{escape(rows)}", f"{title}\n{rows}"))
    footer = "天数按纳入统计的日报计算，点 🔗 看原文。"
    if token_notice:
        footer += "\n" + token_notice
    blocks.append((escape(footer), footer))
    return split_parts(blocks, label=report_id)


def prepare_weekly(store, day, report_id, *, writer=None, token_notice=None):
    """Freeze the exact text before delivery and reuse it after a retry."""
    key = weekly_archive_key(report_id)
    previous = read_json(store, key)
    if previous is not None:
        return previous["parts"]
    parts = build_weekly(store, day, report_id, writer=writer, token_notice=token_notice)
    store.publish({key: json_bytes({"parts": parts})}, "Freeze weekly report")
    return parts
