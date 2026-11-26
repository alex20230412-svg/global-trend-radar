"""Fetch one Malaysia YouTube chart and format its ephemeral Telegram message."""

from contextlib import nullcontext
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import zip_longest
import json
from pathlib import Path
import re
import unicodedata

import httpx
import yaml

from .delivery import DeliveryError, _message_text
from .layout import quote_block, table_block, table_header, table_row


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "youtube.yaml"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
WATCH_URL = "https://www.youtube.com/watch?v="
TERMS_URL = "https://www.youtube.com/t/terms"
PRIVACY_URL = "https://policies.google.com/privacy"
MAX_RESPONSE_BYTES = 1024 * 1024
TIMEOUT = httpx.Timeout(15.0, connect=8.0)
KEY = re.compile(r"[\x21-\x7e]{20,512}")
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
DECIMAL = re.compile(r"[0-9]{1,20}")
CATEGORY_IDS = {
    "10": "🎵 音乐",
    "20": "🎮 游戏",
    "1": "🎬 电影与预告片",
    "30": "🎬 电影与预告片",
    "44": "🎬 电影与预告片",
}
OTHER_CATEGORY = "▶️ 其他"
GROUPS = tuple(dict.fromkeys(CATEGORY_IDS.values())) + (OTHER_CATEGORY,)
ERROR_REASONS = {
    "quotaExceeded": "quota_exceeded",
    "dailyLimitExceeded": "quota_exceeded",
    "keyInvalid": "key_invalid",
    "API_KEY_INVALID": "key_invalid",
    "accessNotConfigured": "api_not_enabled",
    "SERVICE_DISABLED": "api_not_enabled",
}
NETWORK_ERRORS = {
    httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout,
    httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.CloseError,
    httpx.RemoteProtocolError, httpx.LocalProtocolError, httpx.ProxyError,
}
HEADER = "<b>▶️ 大家在看：马来西亚 YouTube 热门</b>\n（YouTube 热门榜数据来自音乐、电影和游戏）"
FOOTER = (
    "数据来自 YouTube（YouTube API Services），标题为原文。"
    f'<a href="{TERMS_URL}">YouTube 服务条款🔗</a> · '
    f'<a href="{PRIVACY_URL}">Google 隐私权政策🔗</a>'
)


@dataclass(frozen=True)
class YouTubeConfig:
    enabled: bool = False
    region: str = "MY"
    max_results: int = 25
    per_category: int = 5

    def __post_init__(self):
        if (
            type(self.enabled) is not bool or self.region != "MY"
            or type(self.max_results) is not int or not 1 <= self.max_results <= 25
            or type(self.per_category) is not int or not 1 <= self.per_category <= 25
        ):
            raise ValueError("invalid_youtube_config")


@dataclass(frozen=True)
class YouTubeVideo:
    video_id: str
    title: str
    channel_title: str
    category_id: str
    view_count: int | None = None

    @property
    def group(self):
        return CATEGORY_IDS.get(self.category_id, OTHER_CATEGORY)


@dataclass(frozen=True)
class YouTubeResult:
    status: str
    videos: tuple[YouTubeVideo, ...] = field(default=(), repr=False)


def load_youtube_config(path=None):
    try:
        raw = yaml.safe_load(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or set(raw) != {"enabled", "region", "max_results", "per_category"}:
            raise ValueError
        return YouTubeConfig(**raw)
    except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError):
        raise ValueError("invalid_youtube_config") from None


def _original_text(value):
    if not isinstance(value, str):
        return ""
    return "".join(
        char for char in value
        if unicodedata.category(char) not in {"Cc", "Cf", "Cs", "Zl", "Zp"} or char in "\u200c\u200d"
    ).strip()[:100]


def _parse_video(raw):
    if not isinstance(raw, dict):
        return None
    video_id, snippet = raw.get("id"), raw.get("snippet")
    if not isinstance(video_id, str) or VIDEO_ID.fullmatch(video_id) is None or not isinstance(snippet, dict):
        return None
    title = _original_text(snippet.get("title"))
    channel = _original_text(snippet.get("channelTitle"))
    category_id = snippet.get("categoryId")
    if not title or not channel or not isinstance(category_id, str) or not category_id.strip():
        return None
    stats = raw.get("statistics", {})
    if not isinstance(stats, dict):
        return None
    views = stats.get("viewCount")
    if views is not None and (not isinstance(views, str) or DECIMAL.fullmatch(views) is None):
        return None
    return YouTubeVideo(video_id, title, channel, category_id, int(views) if views is not None else None)


def _parse_chart(payload, config):
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return YouTubeResult("invalid_payload")
    raw_items = payload["items"]
    bad = 0
    totals = dict.fromkeys(GROUPS, 0)
    selected = []
    for raw in raw_items:
        video = _parse_video(raw)
        if video is None:
            bad += 1
        elif len(selected) < config.max_results and totals[video.group] < config.per_category:
            selected.append(video)
            totals[video.group] += 1
    if bad * 2 > len(raw_items):
        return YouTubeResult("invalid_payload")
    return YouTubeResult("ok", tuple(selected))


def _error_status(status, payload):
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        for key in ("errors", "details"):
            details = error.get(key)
            if not isinstance(details, list):
                continue
            for detail in details:
                reason = detail.get("reason") if isinstance(detail, dict) else None
                if isinstance(reason, str) and reason in ERROR_REASONS:
                    return ERROR_REASONS[reason]
    # The generic Google 'forbidden' reason retains its HTTP status.
    return f"http_{status}"


def _read_json(response):
    if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
        raise ValueError("invalid_payload")
    length = response.headers.get("content-length")
    if length is not None and (DECIMAL.fullmatch(length) is None or int(length) > MAX_RESPONSE_BYTES):
        raise ValueError("invalid_payload")
    raw = bytearray()
    for chunk in response.iter_bytes():
        if len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
            raise ValueError("invalid_payload")
        raw.extend(chunk)
    return json.loads(raw)


def fetch_youtube(config, raw_key, *, client=None):
    if not config.enabled:
        return YouTubeResult("disabled")
    if raw_key is not None and not isinstance(raw_key, str):
        return YouTubeResult("invalid_key_format")
    key = (raw_key or "").strip()
    if not key:
        return YouTubeResult("no_key")
    if KEY.fullmatch(key) is None:
        return YouTubeResult("invalid_key_format")

    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": config.region,
        "maxResults": config.max_results,
        "fields": "items(id,snippet(title,channelTitle,categoryId),statistics(viewCount))",
    }
    headers = {"x-goog-api-key": key, "Accept": "application/json", "Accept-Encoding": "identity"}
    http = nullcontext(client) if client is not None else httpx.Client(trust_env=False)
    try:
        with http as transport:
            with transport.stream(
                "GET", VIDEOS_URL, headers=headers, params=params, timeout=TIMEOUT, follow_redirects=False,
            ) as response:
                status = response.status_code
                if 300 <= status < 400:
                    return YouTubeResult(f"http_{status}")
                try:
                    payload = _read_json(response)
                except (json.JSONDecodeError, UnicodeError):
                    return YouTubeResult("invalid_payload" if status == 200 else f"http_{status}")
                if status != 200:
                    return YouTubeResult(_error_status(status, payload))
                return _parse_chart(payload, config)
    except (ValueError, RecursionError):
        return YouTubeResult("invalid_payload")
    except httpx.HTTPError as error:
        kind = type(error)
        name = kind.__name__ if kind in NETWORK_ERRORS else "HTTPError"
        return YouTubeResult(f"network_{name}")


def _views(count):
    if count >= 10_000:
        return f"{Decimal(count // 1000) / 10:.1f}万"
    return f"{count:,}"


def _message(groups):
    sections = [HEADER]
    tables, details = [], []
    for group, videos in groups.items():
        if not videos:
            continue
        rows = []
        for number, video in enumerate(videos, 1):
            views = _views(video.view_count) if video.view_count is not None else "—"
            rows.append(table_row(number, views, video.channel_title, metric_width=10))
            details.append((f"{group} {number}. {video.title}", WATCH_URL + video.video_id))
        tables.append((group, table_header("观看", "频道", metric_width=10), rows))
    if tables:
        sections.append(table_block(tables)[0])
        sections.append(quote_block(
            "完整标题和链接（点开看）", details, row_units=None, preserve_spaces=True,
        )[0])
    sections.append(FOOTER)
    return "\n\n".join(sections)


def render_youtube(videos):
    """Keep complete entries and reserve space for the policy links in a single message."""
    by_group = {group: [] for group in GROUPS}
    selected = {group: [] for group in GROUPS}
    for video in videos:
        by_group[video.group].append(video)

    # Allocate the first entries of each group before filling later entries.
    full_groups = set()
    for batch in zip_longest(*by_group.values()):
        for group, video in zip(GROUPS, batch, strict=True):
            if video is None or group in full_groups:
                continue
            selected[group].append(video)
            try:
                _message_text(_message(selected))
            except DeliveryError:
                selected[group].pop()
                # The following entries in this group must not overtake this one.
                full_groups.add(group)
    return _message(selected)
