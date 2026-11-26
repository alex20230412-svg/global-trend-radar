"""Turn the day's ranking snapshot into a short Chinese brief for the Owner's Telegram.

The detailed digest stays in the private archive. What the Owner reads is either an AI
summary written only from the day's items (titles, Trends context headlines, weather) or,
when no key is set or the model fails, a plain Chinese layout of the original titles.
"""

from dataclasses import dataclass, field
from datetime import timedelta, timezone
from html import escape
import json
import re
import time
import unicodedata

import httpx

from .delivery import split_parts
from .layout import entry_key, quote_blocks, table_block, table_header, table_row, table_width
from .scoring import instant, trend_key
from .sources import clean_url


MYT = timezone(timedelta(hours=8), "MYT")
PROMPT_VERSION = "brief-v5.2"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
# Flash follows the format and the no-invention rule better than Flash-Lite (first live run).
GEMINI_MODELS = ("gemini-flash-latest", "gemini-flash-lite-latest")
# Visible ASCII only (no spaces or line breaks that could reach a header); Google key formats vary.
GEMINI_KEY = re.compile(r"[\x21-\x7e]{20,512}")
MAX_BRIEF_CHARS = 18000
COUNTRIES = {
    "MY": "马来西亚", "SG": "新加坡", "ID": "印尼", "TH": "泰国", "PH": "菲律宾", "VN": "越南",
    "US": "美国", "GB": "英国", "IN": "印度", "JP": "日本", "KR": "韩国", "TW": "台湾", "HK": "香港",
    "AU": "澳洲", "GLOBAL": "全球",
}
PUBLISHERS = {
    "malaysiakini": "当今大马", "malaysiakini_zh": "当今大马", "malay_mail": "Malay Mail",
    "fmt": "Free Malaysia Today", "bernama": "马新社 Bernama",
}
SOURCE_NAMES = {
    "malaysiakini": "当今大马（英文）", "malaysiakini_zh": "当今大马（中文）", "malay_mail": "Malay Mail",
    "fmt": "Free Malaysia Today", "bernama": "马新社", "hn": "Hacker News", "bluesky": "Bluesky",
    "mastodon_tags": "Mastodon 标签", "mastodon_links": "Mastodon 链接", "weather": "大马气象局",
    "gdelt": "GDELT", "apple_music_my": "Apple Music 榜", "app_store_my": "App Store 榜",
    "wikipedia_my": "马来西亚维基百科", "weibo_archive": "微博存档", "chinanews_rss": "中新网", "baidu_hot": "百度热搜",
}
SYSTEM_PROMPT = """你为马来西亚华人编辑中文热点早报。只返回 JSON 对象 items 和 ideas。
items 的每行包含原样 id、label、why。label 是最多 8 个中文字的主题，why 是一句简体中文原因。
优先保留马来西亚热搜，依照输入顺序。中国热议从候选选至多 8 条，维基从前 30 条选至多 5 条，排除色情或成人内容。
热搜话题的 label 用中文概括事件。维基条目、歌曲、人名、剧名和 App 名保留原文，不要音译或硬译。
App 的 label 写 2 到 5 个字的用途（例如 网购、电子钱包、直播带货），why 用一句话说明用途。不要重复同一人物、事件或作品。
只能依据输入的标题和上下文，不得加入条目里没有的事实。禁止编造数字、年龄、日期、人名。不知道原因就写「原因不明」。
不用写栏目、地区名单、搜索量、排名、链接或 Markdown，程序会补上。
ideas 最多 3 条，每条写成一个可以尝试的生意或服务：卖什么、做什么、给谁，并说明依据。不能只复述新闻或天气。
每条包含 text 和支持该推测的已有 ids。用保守语气，推测须有材料支持。"""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "items": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {name: {"type": "STRING"} for name in ("id", "label", "why")},
            "required": ["id", "label", "why"],
        }},
        "ideas": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"text": {"type": "STRING"}, "ids": {
                "type": "ARRAY", "items": {"type": "STRING"},
            }},
            "required": ["text", "ids"],
        }},
    },
    "required": ["items", "ideas"],
}


@dataclass
class Brief:
    parts: list[str]
    meta: dict = field(default_factory=dict)
    entries: list[dict] = field(default_factory=list)


def _clean(value, limit=200):
    text = "".join(
        char for char in str(value or "")
        if unicodedata.category(char) not in {"Cf", "Cs", "Cc"} or char == "\n"
    )
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _countries(geos, exclude=None):
    return [COUNTRIES.get(geo, geo) for geo in geos or () if geo != exclude]


def _context(entry):
    context = entry.get("context") if isinstance(entry.get("context"), dict) else {}
    return _clean(context.get("title"), 160), _clean(context.get("publisher"), 40), clean_url(context.get("url"))


def _link(entry):
    _title, _publisher, url = _context(entry)
    return url or clean_url(entry.get("url"))


def _date(now):
    local = instant(now).astimezone(MYT)
    return f"{local.month}月{local.day}日"


SPORTS = re.compile(r"\bvs?\.?\b|\bnba\b|\bnfl\b|\bepl\b|\bfc\b", re.IGNORECASE)
ADULT = re.compile(r"色情|成人视频|成人影片|性愛影片|性爱影片|\bporn(?:ography)?\b|\bhentai\b", re.IGNORECASE)
NUMBERS = re.compile(
    r"[0-9]+(?:[.,][0-9]+)*|"
    r"[〇零一二三四五六七八九十百千万两亿]+(?=\s*(?:岁|年|月|日|号|元|人|名|级|分钟|小时))"
)
LIMITS = {
    "malaysia": 8, "other": 4, "china": 8, "wiki": 5, "music": 5, "apps": 5,
    "news": 3, "weather": 3,
}
HEADINGS = {
    "malaysia": "🔥 马来西亚热搜",
    "other": "🌏 全球热议",
    "china": "🇨🇳 中国热议",
    "wiki": "🔍 大家在查（维基）",
    "music": "🎵 大家在听",
    "apps": "📱 大家在下载",
}
ARCHIVE_SECTIONS = {"other": "global"}
SHORT_LABELS = {"中新网": "中新"}
HIDDEN_KEYS = {"link", "original_url", "also_searched_in", "countries", "volume", "views", "key"}


WEATHER_ZH = (
    ("THUNDERSTORM", "雷暴警告"), ("CONTINUOUS RAIN", "持续降雨警告"), ("STRONG WIND", "强风和大浪警告"),
    ("TROPICAL", "热带气旋警告"), ("TSUNAMI", "海啸警告"), ("EARTHQUAKE", "地震消息"), ("HEAT", "热浪警告"),
)
WEATHER_LEVELS = (
    ("SEVERE", "严重"), ("DANGER", "危险"), ("ALERT", "戒备"),
    ("FIRST CATEGORY", "第一类"), ("SECOND CATEGORY", "第二类"), ("THIRD CATEGORY", "第三类"),
)


def _weather_zh(title):
    """Chinese name for a MET Malaysia warning when the AI gave none; unknown titles stay as they are."""
    upper = str(title).upper()
    for word, name in WEATHER_ZH:
        if word in upper:
            level = next((zh for key, zh in WEATHER_LEVELS if key in upper), "")
            return f"{name}（{level}）" if level else name
    return title


def _is_sport(entry):
    return entry.get("category") == "体育" or SPORTS.search(str(entry.get("title", ""))) is not None


def _fingerprints(row):
    title = trend_key(row.get("term") or row.get("title") or "")
    headline = trend_key(row.get("headline") or "")
    return ({("title", name) for name in (title, headline) if name}
            | {("url", url) for url in (row.get("original_url"), row.get("link")) if url})


def _select_unique(rows, limit, seen):
    selected = []
    for row in rows:
        keys = _fingerprints(row)
        if not keys or seen & keys:
            continue
        selected.append(row)
        seen.update(keys)
        if len(selected) == limit:
            break
    return selected


def _numbered(rows, prefix):
    return [dict(row, id=f"{prefix}{number}") for number, row in enumerate(rows, 1)]


def _topics(entries, region_key, exclude=None):
    rows, sports = [], []
    for entry in entries:
        title = _clean(entry.get("title"), 100)
        if not title:
            continue
        headline, publisher, _url = _context(entry)
        row = {
            "term": title, "headline": headline, "publisher": publisher,
            region_key: _countries(entry.get("geos"), exclude=exclude), "link": _link(entry),
            "original_url": clean_url(entry.get("url")),
            "volume": _clean(entry.get("volume_raw"), 12) if exclude == "MY" else "",
            "key": entry_key(entry.get("title"), _link(entry)),
        }
        (sports if _is_sport(entry) else rows).append(row)
    if sports:
        regions = list(dict.fromkeys(country for row in sports for country in row[region_key]))
        sport = {
            "term": "体育赛事", "headline": "；".join(row["term"] for row in sports[:4]),
            "publisher": "", region_key: regions[:6], "volume": "", "link": sports[0]["link"],
            "key": entry_key("体育赛事"),
        }
        limit = LIMITS["malaysia"] if exclude == "MY" else LIMITS["other"]
        rows.insert(min(len(rows), limit - 1), sport)
    return rows


def _candidate(entry):
    title = _clean(entry.get("title"), 120)
    url = clean_url(entry.get("url"))
    headline, publisher, _ = _context(entry)
    views = str(entry.get("views_ceil", ""))
    return {
        "title": title, "link": url, "headline": headline, "publisher": publisher,
        "source_label": _clean(entry.get("source_label") or entry.get("source_id"), 12),
        "views": int(views) if re.fullmatch(r"[0-9]{1,18}", views) else None,
        "key": entry_key(entry.get("title"), url),
    }


def collect_items(snapshot):
    """Prepare ranked, de-duplicated input with code-owned identifiers."""
    seen = set()
    items = {
        "malaysia": _numbered(_select_unique(
            _topics(snapshot.get("malaysia", []), "also_searched_in", exclude="MY"),
            LIMITS["malaysia"], seen,
        ), "m"),
    }
    other = [*snapshot.get("monitored_regions", []), *snapshot.get("rising", []), *snapshot.get("new", [])]
    items["other"] = _numbered(_select_unique(_topics(other, "countries"), LIMITS["other"], seen), "o")
    for section, prefix in (("china", "c"), ("wiki", "k")):
        candidates = (_candidate(row) for row in snapshot.get(section, []))
        candidates = (row for row in candidates if row["title"] and row["link"]
                      and not (section == "wiki" and ADULT.search(row["title"])))
        items[section] = _numbered(_select_unique(candidates, 30, set(seen)), prefix)
    charts = snapshot.get("charts", {})
    for section, source_id, prefix in (("music", "apple_music_my", "s"), ("apps", "app_store_my", "a")):
        maker = "artist" if section == "music" else "developer"
        entries = ({
            "title": _clean(entry.get("title"), 100), maker: _clean(entry.get("artist"), 60),
            "genre": _clean(entry.get("genre"), 30), "link": clean_url(entry.get("url")),
            "key": entry_key(entry.get("title"), entry.get("url"), section=section, artist=entry.get("artist")),
        } for entry in charts.get(source_id, []))
        items[section] = _numbered(_select_unique(
            (row for row in entries if row["title"]), LIMITS[section], seen,
        ), prefix)
    news = ({
        "title": _clean(entry.get("title"), 160),
        "publisher": PUBLISHERS.get(entry.get("source_id"), _clean(entry.get("publisher"), 40)),
        "link": clean_url(entry.get("url")),
    } for entry in snapshot.get("local_news", []))
    items["news"] = _numbered(_select_unique((row for row in news if row["title"]), LIMITS["news"], seen), "n")
    latest = {}
    for entry in snapshot.get("weather", []):
        title = _clean(entry.get("title"), 120)
        until = instant(entry.get("valid_to"))
        if title and (title not in latest or (until and (latest[title][0] is None or until > latest[title][0]))):
            latest[title] = (until, clean_url(entry.get("url")))
    items["weather"] = _numbered([{
        "title": title, "until": until.astimezone(MYT).strftime("%m-%d %H:%M") if until else None, "link": url,
    } for title, (until, url) in list(latest.items())[:LIMITS["weather"]]], "w")
    return items


def _prompt_payload(items, now):
    payload = {"date": _date(now)}
    for section, rows in items.items():
        payload[section] = [{key: value for key, value in row.items()
                             if key not in HIDDEN_KEYS and value not in (None, "", [])}
                            for row in rows]
    return json.dumps(payload, ensure_ascii=False)


def _source_name(source):
    if source.get("kind") == "trends":
        return f"Google 趋势（{COUNTRIES.get(source.get('geo'), source.get('geo'))}）"
    return SOURCE_NAMES.get(source.get("source_id"), _clean(source.get("source_id"), 40))


def _footer(snapshot):
    coverage = snapshot.get("coverage", [])
    active = [source for source in coverage if source.get("status") not in {"disabled", "unapproved"}]
    good = [source for source in active if source.get("status") in {"ok", "empty"}]
    problems = []
    for source in active:
        if source.get("status") in {"ok", "empty"}:
            continue
        if "weibo" in source.get("source_id", "") and (
            source.get("status") == "stale" or source.get("reason") in {"stale", "archive_stale"}
        ):
            problems.append("微博存档已停更")
        else:
            problems.append(_source_name(source))
    line = f"ℹ️ 数据来源 {len(good)}/{len(active)} 个正常"
    if problems:
        line += "；暂时没有数据：" + "、".join(problems[:6]) + ("等" if len(problems) > 6 else "")
    for source in good:
        day = source.get("data_day")
        if (source.get("source_id") == "wikipedia_my" and source.get("fallback")
                and isinstance(day, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)):
            line += f"\n维基百科采用 {day} 的马来西亚浏览榜"
            break
    return line


def sanitize(text):
    """Keep model text without model-supplied links, Markdown or controls."""
    text = re.sub(r"https?://\S+", "", str(text or ""))
    text = text.replace("**", "").replace("__", "").replace(chr(96), "")
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*#+\s*", "", line)
        line = "".join(char for char in line if unicodedata.category(char) not in {"Cc", "Cf", "Cs"})
        lines.append(" ".join(line.split()))
    cleaned = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def numbers(text):
    return set(NUMBERS.findall(unicodedata.normalize("NFKC", text)))


def _reference(row):
    return " ".join(str(row.get(name) or "") for name in (
        "term", "title", "headline", "publisher", "artist", "developer", "genre",
    ))


def _model_json(text, items):
    if not isinstance(text, str) or len(text) > MAX_BRIEF_CHARS:
        raise ValueError("invalid_output")
    raw = json.loads(text)
    if (not isinstance(raw, dict) or not isinstance(raw.get("items"), list)
            or not isinstance(raw.get("ideas"), list)):
        raise ValueError("invalid_output")
    by_id = {row["id"]: row for rows in items.values() for row in rows}
    annotations = {}
    for proposed in raw["items"]:
        if not isinstance(proposed, dict):
            continue
        key, label, why = (proposed.get(name) for name in ("id", "label", "why"))
        if not isinstance(key, str) or key not in by_id or key in annotations:
            continue
        if not isinstance(label, str) or not isinstance(why, str):
            continue
        label, why = _clean(sanitize(label)), _clean(sanitize(why), MAX_BRIEF_CHARS)
        reference = numbers(_reference(by_id[key]))
        # Check the label and the reason separately: an invented number in one drops only that part,
        # and the source title or headline is shown in its place.
        label_ok = bool(label) and table_width(label) <= 16 and not numbers(label) - reference
        why_ok = bool(why) and not numbers(why) - reference
        annotations[key] = (label if label_ok else "", _clean(why, 42) if why_ok else "")
    if not any(annotations.get(row["id"], ("", ""))[0] for row in items["malaysia"]):
        raise ValueError("no_malaysia_items")
    return annotations, raw["ideas"]


def _ideas(proposals, rows):
    usable = {row["id"]: row for row in rows}
    lines = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        text, ids = proposal.get("text"), proposal.get("ids")
        if (not isinstance(text, str) or not isinstance(ids, list) or not ids
                or any(not isinstance(key, str) or key not in usable for key in ids)):
            continue
        text = _clean(sanitize(text), 80)
        references = " ".join(_reference(usable[key]) for key in ids)
        if text and text not in lines and numbers(text) <= numbers(references):
            lines.append(text)
        if len(lines) == 3:
            break
    return lines


def _section_rows(items, annotations):
    seen = set()
    for section in HEADINGS:
        rows = items[section]
        if annotations is not None and section in {"china", "wiki"}:
            rows = [row for row in rows if row["id"] in annotations]
        yield section, _select_unique(rows, LIMITS[section], seen)


def _heading(now):
    local = instant(now).astimezone(MYT)
    weekday = "一二三四五六日"[local.weekday()]
    return f"📅 {_date(now)}（周{weekday}）热点早报"


def _table_view(section, row):
    if section == "malaysia":
        volume = row.get("volume", "")
        return volume if re.fullmatch(r"[0-9,.]+[KkMmBb]?\+?", volume) else "-"
    if section == "wiki":
        views = row["views"]
        return "-" if views is None else f"{views // 1000}K" if views >= 1000 else str(views)
    return None


def _format_brief(items, snapshot, now, previous_keys, token_notice, annotations=None, ideas=()):
    heading = _heading(now)
    opening = heading if annotations is not None else heading + "\n（AI 摘要今天不可用，点开看原文）"
    blocks = [(f"<b>{escape(heading)}</b>" + escape(opening[len(heading):]), opening)]
    tables, details, history, shown = [], [], [], []
    labels_seen = set()
    for section, rows in _section_rows(items, annotations):
        if not rows:
            continue
        metric_width = (max(6, *(table_width(_table_view(section, row)) for row in rows))
                        if section == "malaysia" else 7)
        section_header = (table_header("搜索量", metric_width=metric_width) if section == "malaysia" else
                          table_header("浏览", "条目") if section == "wiki" else
                          table_header(title="用途", app=True) if section == "apps" else table_header())
        table = []
        for number, row in enumerate(rows, 1):
            title = row.get("term") or row["title"]
            label, why = (annotations or {}).get(row["id"], ("", ""))
            if label and trend_key(label) in labels_seen:
                label = ""
            labels_seen.add(trend_key(label or title))
            shown_title = label or title
            if section == "apps":
                shown_title = label or why or row.get("genre") or row.get("developer") or "用途不明"
            elif section == "music":
                # Song names stay original in the table; the AI's note goes in the details.
                shown_title = f"{title} — {row['artist']}" if row.get("artist") else title
            table.append(table_row(
                number, _table_view(section, row), shown_title, metric_width=metric_width,
                marker=previous_keys is not None and row["key"] not in previous_keys,
                app_name=title if section == "apps" else None,
                suffix=f"（{SHORT_LABELS.get(row['source_label'], row['source_label'])}）" if section == "china" else "",
            ))
            explanation = why or row.get("headline") or row.get("artist") or row.get("genre") or ""
            regions = row.get("also_searched_in") or row.get("countries") or ()
            details.append((
                f"{HEADINGS[section].split()[0]} {number}. {title if section in {'music', 'apps'} else label or title}"
                + (f" · {explanation}" if explanation else "")
                + (f"（{'、'.join(regions)}{'也在搜' if section == 'malaysia' else ''}）" if regions else ""),
                row["link"],
            ))
            history.append({
                "key": row["key"], "section": ARCHIVE_SECTIONS.get(section, section),
                "title": title, "url": row["link"], "metric": row.get("views") if section == "wiki" else row.get("volume"),
                "source": row.get("source_label"), "artist": row.get("artist"),
            })
        tables.append((HEADINGS[section], section_header, table))
        shown.extend(rows)
    if tables:
        blocks.append(table_block(tables))
    blocks.extend(quote_blocks("为什么热（点开看）", details))

    news = []
    used = {key for row in shown for key in _fingerprints(row)}
    final_news = _select_unique(items["news"], LIMITS["news"], used)
    for row in final_news + items["weather"]:
        label, why = (annotations or {}).get(row["id"], ("", ""))
        suffix = f"，到 {row['until']}" if row.get("until") else ""
        if row.get("publisher"):
            suffix += f"（{row['publisher']}）"
        text = why or label or (_weather_zh(row["title"]) if row["id"].startswith("w") else row["title"])
        news.append(((text.rstrip("。.") if suffix else text) + suffix, row.get("link")))
    if not items["weather"]:
        weather_unavailable = any(source.get("kind") == "weather" and source.get("status") not in {"ok", "empty"}
                                  for source in snapshot.get("coverage", []))
        news.append(("天气数据暂不可用" if weather_unavailable else "今天没有天气警告", None))
    blocks.extend(quote_blocks("新闻和天气（点开看）", news))
    shown.extend(final_news + items["weather"])
    tips = _ideas(ideas, shown)
    if tips:
        name = "💡 可能的生意线索（AI 推测，仅供参考）"
        body = "\n".join(f"• {tip}" for tip in tips)
        blocks.append((f"<b>{escape(name)}</b>\n{escape(body)}", f"{name}\n{body}"))

    footer = _footer(snapshot)
    if annotations is not None:
        footer += "\n以上由 AI 根据当天标题整理，可能有误，点 🔗 看原文"
    if token_notice:
        footer += f"\n{token_notice}"
    blocks.append((escape(footer, quote=False), footer))
    return blocks, history


def build_brief(snapshot, now, report_id, writer=None, *, previous_keys=None, token_notice=None):
    """Build a Telegram brief from source rows and optional validated annotations."""
    items = collect_items(snapshot)
    meta = {"prompt_version": PROMPT_VERSION, "mode": "plain", "status": "no_writer", "model": None}
    if writer is not None:
        try:
            text, status, model = writer.write(SYSTEM_PROMPT, _prompt_payload(items, now))
            meta.update(status=status, model=model)
            if text is not None:
                annotations, ideas = _model_json(text, items)
                blocks, entries = _format_brief(
                    items, snapshot, now, previous_keys, token_notice, annotations, ideas,
                )
                parts = split_parts(blocks, label=report_id)
                meta.update(mode="ai", status="ok")
                return Brief(parts, meta, entries)
        except Exception:
            meta["status"] = "invalid_output"
    blocks, entries = _format_brief(items, snapshot, now, previous_keys, token_notice)
    return Brief(split_parts(blocks, label=report_id), meta, entries)


TRANSIENT = {"http_429", "http_500", "http_502", "http_503", "http_504"}


class UnavailableWriter:
    """Stands in for the model when no usable key is configured, so the archive says why."""

    def __init__(self, reason):
        self.reason = reason

    def write(self, system, prompt):
        return None, self.reason, None


class GeminiWriter:
    """Minimal Gemini generateContent client. Errors are reported as fixed status codes only."""

    def __init__(self, key, *, transport=None, models=GEMINI_MODELS, timeout=90.0,
                 retry_delay=30.0, sleep=time.sleep):
        key = key.strip() if isinstance(key, str) else key
        if not isinstance(key, str) or not GEMINI_KEY.fullmatch(key):
            raise ValueError("invalid_gemini_key")
        self._key = key
        self._transport = transport
        self._models = tuple(models)
        self._timeout = timeout
        self._retry_delay = retry_delay
        self._sleep = sleep

    def _client(self):
        return httpx.Client(transport=self._transport, timeout=httpx.Timeout(self._timeout, connect=10.0),
                            trust_env=False, follow_redirects=False)

    def _headers(self):
        return {"x-goog-api-key": self._key, "Content-Type": "application/json"}

    def _discover(self, client):
        try:
            response = client.get(f"{GEMINI_BASE}/models", params={"pageSize": 200}, headers=self._headers())
            if response.status_code != 200:
                return []
            models = response.json().get("models", [])
        except (httpx.HTTPError, ValueError, AttributeError):
            return []
        names = []
        for model in models if isinstance(models, list) else []:
            if not isinstance(model, dict) or "generateContent" not in (model.get("supportedGenerationMethods") or []):
                continue
            name = str(model.get("name", "")).removeprefix("models/")
            if not re.fullmatch(r"gemini-[a-z0-9.-]{1,60}", name) or "flash" not in name:
                continue
            if any(word in name for word in ("tts", "live", "image", "audio", "embedding", "transcribe",
                                              "robotics", "omni", "exp")):
                continue
            names.append(name)
        stable = [name for name in names if "preview" not in name]
        ordered = sorted(stable or names, key=lambda name: ("lite" not in name, [-ord(c) for c in name]))
        return ordered[:3]

    def _generate(self, client, model, system, prompt):
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2, "maxOutputTokens": 8192,
                "responseMimeType": "application/json", "responseSchema": RESPONSE_SCHEMA,
            },
        }
        response = client.post(f"{GEMINI_BASE}/models/{model}:generateContent", json=body, headers=self._headers())
        if response.status_code != 200:
            return None, f"http_{response.status_code}"
        try:
            candidates = response.json().get("candidates") or []
            parts = candidates[0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts if isinstance(part, dict) and not part.get("thought"))
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            return None, "invalid_response"
        return (text, "ok") if text.strip() else (None, "empty_output")

    def write(self, system, prompt):
        """One more pass after a short wait when every model was busy (a live preview saw 503)."""
        text, status, model = self._write_once(system, prompt)
        if text is None and self._retry_delay and (status in TRANSIENT or status.startswith("network_")):
            self._sleep(self._retry_delay)
            text, status, model = self._write_once(system, prompt)
        return text, status, model

    def _write_once(self, system, prompt):
        """Try each model in turn; a timeout or error on one falls through to the next."""
        status, last, tried, missing = "no_model", None, [], False
        try:
            with self._client() as client:
                queue = list(self._models)
                while queue:
                    model = queue.pop(0)
                    if model in tried:
                        continue
                    tried.append(model)
                    try:
                        text, status = self._generate(client, model, system, prompt)
                    except httpx.HTTPError as error:
                        text, status = None, f"network_{type(error).__name__}"[:48]
                    last = model
                    if text is not None:
                        return text, status, model
                    if status in {"http_401", "http_403"}:
                        return None, status, model  # the key itself is refused; other models will be too
                    missing = missing or status in {"http_404", "http_400"}
                    if not queue and missing:
                        missing = False
                        queue = [name for name in self._discover(client) if name not in tried]
        except httpx.HTTPError as error:
            return None, f"network_{type(error).__name__}"[:48], last
        return None, status, last
