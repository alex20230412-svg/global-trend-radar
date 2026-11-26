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
import unicodedata

import httpx

from .delivery import split_parts
from .scoring import instant, trend_key
from .sources import clean_url


MYT = timezone(timedelta(hours=8), "MYT")
PROMPT_VERSION = "brief-v1"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODELS = ("gemini-flash-lite-latest", "gemini-flash-latest")
GEMINI_KEY = re.compile(r"[A-Za-z0-9_-]{20,200}")
MAX_BRIEF_CHARS = 3400
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
    "gdelt": "GDELT",
}
SYSTEM_PROMPT = """你是一位为马来西亚华人读者写早报的中文编辑。读者看不懂英文和马来文，只想知道「今天大家在关心什么」。

规则：
1. 只根据用户提供的 JSON 条目写，不得加入条目里没有的事实、数字、人名或日期。「可能的生意线索」一节除外，但那里也只能从条目推想，并且语气要保守。
2. 搜索词本身看不出意思时，用它的 headline 解释；仍然看不出就写「原因不明」，不要猜。
3. 英文、马来文一律翻成简体中文。人名、品牌、球队名可以保留原文或用常见中文译名。
4. 多场体育比赛合并成一条。
5. 每条一行，开头保留条目编号，例如 [m1]，不要写链接，不要用 Markdown（不要 ** 或 #）。
6. 严格按下面的格式和顺序输出，某一节没有条目就整节省略（天气没有就写「今天没有天气警告」）。

格式：
📅 {date} 热点早报

🇲🇾 马来西亚今天大家在搜什么
[m1] 主题：一句话说明（不超过 40 字）（其他国家也在搜时，括号写中文国名）
（最多 8 条）

🌏 其他国家在搜
[o1] 主题：一句话说明（中文国名）
（最多 4 条）

📰 马来西亚新闻
[n1] 一句话新闻（最多 3 条）

⚠️ 天气
[w1] 警告内容，到什么时候（最多 3 条）

💡 可能的生意线索（AI 推测，仅供参考）
- 一句话（最多 2 条）"""


@dataclass
class Brief:
    parts: list[str]
    meta: dict = field(default_factory=dict)


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


def collect_items(snapshot):
    """Pick the items the brief may mention, each with a stable id and an optional link."""
    items = {"malaysia": [], "other": [], "news": [], "weather": []}
    shown = set()
    for number, entry in enumerate(snapshot.get("malaysia", [])[:10], 1):
        shown.add(trend_key(entry["title"]))
        headline, publisher, _url = _context(entry)
        items["malaysia"].append({
            "id": f"m{number}", "term": _clean(entry["title"], 80), "headline": headline, "publisher": publisher,
            "also_searched_in": _countries(entry.get("geos"), exclude="MY"),
            "link": _link(entry),
        })
    rising = {trend_key(entry["title"]) for entry in snapshot.get("rising", [])}
    for entry in [*snapshot.get("monitored_regions", []), *snapshot.get("rising", []), *snapshot.get("new", [])]:
        key = trend_key(entry["title"])
        if key in shown or len(items["other"]) >= 6:
            continue
        shown.add(key)
        headline, publisher, _url = _context(entry)
        items["other"].append({
            "id": f"o{len(items['other']) + 1}", "term": _clean(entry["title"], 80), "headline": headline,
            "publisher": publisher, "countries": _countries(entry.get("geos")), "rising": key in rising,
            "link": _link(entry),
        })
    for number, entry in enumerate(snapshot.get("local_news", [])[:4], 1):
        items["news"].append({
            "id": f"n{number}", "title": _clean(entry["title"], 160),
            "publisher": PUBLISHERS.get(entry.get("source_id"), _clean(entry.get("publisher"), 40)),
            "link": clean_url(entry.get("url")),
        })
    for number, entry in enumerate(snapshot.get("weather", [])[:4], 1):
        until = instant(entry.get("valid_to"))
        items["weather"].append({
            "id": f"w{number}", "title": _clean(entry["title"], 120),
            "until": until.astimezone(MYT).strftime("%m-%d %H:%M") if until else None,
            "link": None,
        })
    return items


def _prompt_payload(items, now):
    payload = {"date": _date(now)}
    for section, rows in items.items():
        payload[section] = [{key: value for key, value in row.items() if key != "link" and value not in (None, "", [])}
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
    problems = [_source_name(source) for source in active if source.get("status") not in {"ok", "empty"}]
    line = f"ℹ️ 数据来源 {len(good)}/{len(active)} 个正常"
    if problems:
        line += "；暂时没有数据：" + "、".join(problems[:6]) + ("等" if len(problems) > 6 else "")
    return line


def _block(lines, links=None):
    """Lines become one Telegram block; [id] markers turn into a trailing 🔗 link."""
    html, plain = [], []
    for index, line in enumerate(lines):
        match = re.search(r"\[([mnow][0-9]{1,2})\]", line)
        url = (links or {}).get(match.group(1)) if match else None
        text = re.sub(r"\s*\[[mnow][0-9]{1,2}\]\s*", " ", line).strip()
        bold = index == 0
        safe = escape(text, quote=False)
        if bold:
            safe = f"<b>{safe}</b>"
        if url:
            safe += f' <a href="{escape(url, quote=True)}">🔗</a>'
            text += " 🔗"
        html.append(safe)
        plain.append(text)
    return "\n".join(html), "\n".join(plain)


def _sections(text):
    sections, current = [], []
    for line in text.splitlines():
        if line.strip():
            current.append(line.rstrip())
        elif current:
            sections.append(current)
            current = []
    if current:
        sections.append(current)
    return sections


def sanitize(text):
    """Keep the model's plain text; drop links, Markdown and control characters."""
    text = re.sub(r"https?://\S+", "", str(text or ""))
    text = text.replace("**", "").replace("__", "").replace("`", "")
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*#+\s*", "", line)
        line = "".join(char for char in line if unicodedata.category(char) not in {"Cc", "Cf", "Cs"})
        lines.append(" ".join(line.split()))
    cleaned = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def valid_brief(text):
    lines = [line for line in text.splitlines() if line.strip()]
    return 80 <= len(text) <= MAX_BRIEF_CHARS and len(lines) >= 4 and "马来西亚" in text


def _links(items):
    return {row["id"]: row["link"] for rows in items.values() for row in rows if row.get("link")}


def ai_blocks(text, items, snapshot):
    blocks = [_block(section, _links(items)) for section in _sections(text)]
    footer = _footer(snapshot) + " · 以上由 AI 根据当天标题整理，可能有误，点 🔗 看原文"
    blocks.append((escape(footer, quote=False), footer))
    return blocks


def plain_blocks(items, snapshot, now):
    blocks = [_block([f"📅 {_date(now)} 热点早报", "（AI 摘要今天不可用，以下是原文标题，点 🔗 看原文）"])]
    links = _links(items)
    lines = ["🇲🇾 马来西亚今天大家在搜什么"]
    for row in items["malaysia"]:
        also = f"（{'、'.join(row['also_searched_in'])}也在搜）" if row["also_searched_in"] else ""
        why = f" —— {row['headline']}" if row["headline"] else ""
        lines.append(f"[{row['id']}] {row['term']}{also}{why}")
    if len(lines) > 1:
        blocks.append(_block(lines, links))
    lines = ["🌏 其他国家在搜"]
    for row in items["other"][:4]:
        why = f" —— {row['headline']}" if row["headline"] else ""
        lines.append(f"[{row['id']}] {row['term']}（{'、'.join(row['countries'])}）{why}")
    if len(lines) > 1:
        blocks.append(_block(lines, links))
    lines = ["📰 马来西亚新闻"] + [f"[{row['id']}] {row['title']}（{row['publisher']}）" for row in items["news"][:3]]
    if len(lines) > 1:
        blocks.append(_block(lines, links))
    weather = [f"[{row['id']}] {row['title']}" + (f"，到 {row['until']}" if row["until"] else "")
               for row in items["weather"][:3]]
    blocks.append(_block(["⚠️ 天气", *(weather or ["今天没有天气警告"])], links))
    footer = _footer(snapshot)
    blocks.append((escape(footer, quote=False), footer))
    return blocks


def build_brief(snapshot, now, report_id, writer=None):
    """Return the Telegram parts and what produced them; never raises on model failure."""
    items = collect_items(snapshot)
    meta = {"prompt_version": PROMPT_VERSION, "mode": "plain", "status": "no_writer", "model": None}
    if writer is not None:
        text, status, model = writer.write(SYSTEM_PROMPT, _prompt_payload(items, now))
        meta.update(status=status, model=model)
        if text is not None:
            text = sanitize(text)
            if valid_brief(text):
                try:
                    parts = split_parts(ai_blocks(text, items, snapshot), label=report_id)
                    meta.update(mode="ai", status="ok", text=text)
                    return Brief(parts, meta)
                except Exception as error:  # noqa: BLE001 - any rendering problem falls back to plain text.
                    meta["status"] = f"render_{type(error).__name__}"[:48]
            else:
                meta["status"] = "invalid_output"
    return Brief(split_parts(plain_blocks(items, snapshot, now), label=report_id), meta)


class GeminiWriter:
    """Minimal Gemini generateContent client. Errors are reported as fixed status codes only."""

    def __init__(self, key, *, transport=None, models=GEMINI_MODELS, timeout=90.0):
        if not isinstance(key, str) or not GEMINI_KEY.fullmatch(key):
            raise ValueError("invalid_gemini_key")
        self._key = key
        self._transport = transport
        self._models = tuple(models)
        self._timeout = timeout

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
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192},
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
        status = "no_model"
        try:
            with self._client() as client:
                tried = []
                for model in self._models:
                    tried.append(model)
                    text, status = self._generate(client, model, system, prompt)
                    if text is not None:
                        return text, status, model
                    if status not in {"http_404", "http_400"}:
                        return None, status, model
                for model in self._discover(client):
                    if model in tried:
                        continue
                    text, status = self._generate(client, model, system, prompt)
                    if text is not None:
                        return text, status, model
                    if status not in {"http_404", "http_400"}:
                        return None, status, model
        except httpx.HTTPError as error:
            return None, f"network_{type(error).__name__}"[:48], None
        return None, status, None
