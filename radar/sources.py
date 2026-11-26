"""Configured RSS and JSON adapters for hourly trend observations."""

import json
import re
import time
import unicodedata
from calendar import timegm
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit
from xml.etree.ElementTree import ParseError

import feedparser
import httpx
import yaml
from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException

from .source_http import CONNECT_TIMEOUT, GDELT_HOST, SourceError, SourceHttp


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "sources.yaml"
KINDS = {"trends", "news", "hn", "bluesky", "mastodon", "weather", "gdelt"}
GEOS = {"MY", "SG", "ID", "TH", "PH", "VN", "US", "GB", "IN", "JP", "KR", "TW", "HK", "AU"}
TREND_URL = "https://trends.google.com/trending/rss?geo="
WEATHER_LINK = "https://www.met.gov.my/en/"
GDELT_URL = f"https://{GDELT_HOST}/api/v2/doc/doc"
GDELT_MAX_ARTICLES = 20
GDELT_QUERIES = (
    '(Malaysia OR "Kuala Lumpur" OR Putrajaya)',
    '(world OR international OR global OR economy OR technology OR climate)',
)
SITE_ENDPOINTS = {
    "malaysiakini": ("news", "https://www.malaysiakini.com/en/rss/news.rss"),
    "malaysiakini_zh": ("news", "https://www.malaysiakini.com/zh/rss/news.rss"),
    "malay_mail": ("news", "https://www.malaymail.com/feed/rss/malaysia"),
    "fmt": ("news", "https://cms.freemalaysiatoday.com/feed"),
    "bernama": ("news", "https://www.bernama.com/en/rssfeed.php"),
    "hn": ("hn", "https://hacker-news.firebaseio.com/v0/topstories.json"),
    "bluesky": ("bluesky", "https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics?limit=10"),
    "mastodon_tags": ("mastodon", "https://mastodon.social/api/v1/trends/tags?limit=10"),
    "mastodon_links": ("mastodon", "https://mastodon.social/api/v1/trends/links?limit=10"),
    "weather": ("weather", "https://api.data.gov.my/weather/warning/?limit=50&sort=-warning_issue__issued"),
    "gdelt": ("gdelt", GDELT_URL),
}
TRACKERS = {"fbclid", "gclid", "dclid", "msclkid", "igshid", "mc_cid", "mc_eid", "mkt_tok"}
SENSITIVE_QUERY = {"token", "access_token", "api_key", "key", "password", "email", "sig", "signature"}
HT_NAMESPACES = {
    "https://trends.google.com/trending/rss",
    "https://trends.google.com/trends/trendingsearches/daily",
}


@dataclass(frozen=True)
class Source:
    id: str
    kind: str
    geo: str
    language: str
    url: str
    enabled: bool = True
    retention: str = "pending"
    retain_related: bool = False


class SourceItems(list):
    """Usable observations plus the number of malformed input items."""

    def __init__(self, rows=(), *, skipped=0):
        super().__init__(rows)
        self.skipped = skipped


class MalformedItem(SourceError):
    """One item failed validation without invalidating the source envelope."""


def load_sources(path=None):
    try:
        document = yaml.safe_load(Path(path or DEFAULT_CONFIG).read_text(encoding="utf-8"))
        if not isinstance(document, dict) or set(document) != {"sources"}:
            raise ValueError
        rows = document["sources"]
        if not isinstance(rows, list) or not rows:
            raise ValueError
        sources = [Source(**row) for row in rows]
        if len({source.id for source in sources}) != len(sources):
            raise ValueError
        for source in sources:
            _validate_source(source)
    except (TypeError, ValueError, OSError, UnicodeError, yaml.YAMLError):
        raise SourceError("source_config_invalid") from None
    return sources


def _validate_source(source):
    if (
        source.kind not in KINDS
        or source.geo not in GEOS | {"GLOBAL"}
        or not isinstance(source.language, str)
        or re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", source.language) is None
        or type(source.enabled) is not bool
        or source.retention not in {"pending", "long_term"}
        or type(source.retain_related) is not bool
        or (source.retain_related and (
            source.kind != "trends" or source.retention != "long_term"
        ))
    ):
        raise ValueError
    if source.kind == "trends":
        valid = (
            source.geo in GEOS and source.id == f"trends_{source.geo.lower()}"
            and source.url == TREND_URL + source.geo
        )
    else:
        valid = SITE_ENDPOINTS.get(source.id) == (source.kind, source.url)
    if not valid:
        raise ValueError


def clean_url(value, *, keep_fragment=False):
    """Canonicalize display URLs only. The HTTP client only uses configured URLs."""
    if not isinstance(value, str) or len(value) > 1600 or any(
        char.isspace() or ord(char) < 32 or char in """<>"'\\""" for char in value
    ):
        return None
    try:
        url = urlsplit(value)
        if (
            url.scheme.lower() not in {"http", "https"} or not url.hostname or url.username
            or url.password or "@" in url.netloc or url.port is not None
        ):
            return None
        host = url.hostname.lower().rstrip(".")
        if len(host) > 253 or "." not in host or host.endswith((".local", ".localhost", ".internal")):
            return None
        if re.fullmatch(r"[a-z0-9.-]+", host) is None:
            return None
        try:
            ip_address(host)
        except ValueError:
            if re.fullmatch(r"(?:0x[0-9a-f]+|\d+)(?:\.(?:0x[0-9a-f]+|\d+))*", host):
                return None
        else:
            # These are links for people, so also reject public literal IPs.
            return None
        params = parse_qsl(url.query, keep_blank_values=True, max_num_fields=60)
        params = [
            (key, val) for key, val in params
            if key.lower() not in TRACKERS | SENSITIVE_QUERY
            and not key.lower().startswith(("utm_", "x-amz-", "x-goog-"))
        ]
        fragment = url.fragment if keep_fragment else ""
        quote_query = quote if host == "trends.google.com" and url.path == "/trends/explore" else quote_plus
        return urlunsplit((
            url.scheme.lower(), host, url.path or "/", urlencode(params, quote_via=quote_query), fragment,
        ))
    except (UnicodeError, ValueError):
        return None


def _title(value, limit=240):
    if not isinstance(value, str):
        return ""
    value = "".join(
        char for char in value
        if unicodedata.category(char) not in {"Cc", "Cs"} or char.isspace()
    )
    value = "".join(
        char for char in value
        if not any(lo <= ord(char) <= hi for lo, hi in ((0x202A, 0x202E), (0x2066, 0x2069)))
    )
    return " ".join(value.split())[:limit]


def _iso(value, default_tz=None):
    if not isinstance(value, str):
        return None
    try:
        date = datetime.fromisoformat(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None
    if date is None:
        return None
    if date.tzinfo is None:
        if default_tz is None:
            return None
        date = date.replace(tzinfo=default_tz)
    try:
        return date.astimezone(UTC).isoformat(timespec="seconds")
    except (OverflowError, ValueError):
        return None


def _observation(
    source, title, url, rank=None, *, volume_raw=None, published_at=None,
    related=None, identity=None, language=None,
):
    title = _title(title)
    url = clean_url(url, keep_fragment=source.kind == "trends")
    if not title or not url:
        raise MalformedItem("malformed_item")
    content_id = sha256((identity or url).encode("utf-8")).hexdigest()
    return {
        "source_id": source.id,
        "kind": source.kind,
        "geo": source.geo,
        "language": language or source.language,
        "title": title,
        "url": url,
        "rank": rank,
        "volume_raw": volume_raw,
        "published_at": published_at,
        "related": related or [],
        "content_id": content_id,
    }


def _xml(body):
    try:
        return fromstring(body, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ParseError, DefusedXmlException, ValueError) as error:
        detail = type(error).__name__
        position = getattr(error, "position", None)
        if isinstance(position, tuple) and len(position) == 2 and all(type(value) is int for value in position):
            detail += f":{position[0]}:{position[1]}"
        raise SourceError("invalid_xml", detail=detail) from None


def _ht_field(node, name):
    for child in node:
        namespace, _, local = child.tag[1:].partition("}") if child.tag.startswith("{") else ("", "", child.tag)
        if namespace in HT_NAMESPACES and local in {name, f"ht_{name}"}:
            return child
    return None


def _ht_text(node, name):
    element = _ht_field(node, name)
    return element.text if element is not None else None


def _item_rows(items, parse_item):
    rows = []
    skipped = 0
    last_error = None
    for rank, item in enumerate(items, 1):
        try:
            row = parse_item(rank, item)
        except MalformedItem as exc:
            skipped += 1
            last_error = exc
            continue
        if row is not None:
            rows.append(row)
    if skipped * 2 > len(items):
        raise SourceError("too_many_malformed_items", skipped=skipped) from last_error
    return SourceItems(rows, skipped=skipped)


def _trends(source, body):
    channel = _xml(body).find("channel")
    if channel is None or not channel.findtext("title"):
        raise SourceError("feed_schema")
    return _item_rows(channel.findall("item")[:100], lambda rank, item: _trend_item(source, rank, item))


def _trend_item(source, rank, item):
    title = _title(item.findtext("title"))
    volume = _title(_ht_text(item, "approx_traffic"), 32)
    published = _iso(item.findtext("pubDate"))
    if not volume or not published:
        raise MalformedItem("trend_schema")
    related = []
    if source.retain_related:
        for child in item:
            if not any(child.tag == f"{{{ns}}}news_item" for ns in HT_NAMESPACES):
                continue
            url = clean_url(_ht_text(child, "news_item_url"))
            if not url:
                continue
            related.append({
                "title": _title(_ht_text(child, "news_item_title")),
                "url": url,
                "publisher": _title(_ht_text(child, "news_item_source"), 100),
            })
            if len(related) == 3:
                break
    query = urlencode({"geo": source.geo, "q": title}, quote_via=quote)
    return _observation(
        source, title, f"https://trends.google.com/trends/explore?{query}", rank, volume_raw=volume,
        published_at=published, related=related,
        identity=unicodedata.normalize("NFKC", title).casefold(),
    )


def _news(source, body):
    # Only hand already-validated bytes to feedparser. Passing it a URL would
    # give the library its own uncontrolled network path.
    _xml(body)
    feed = feedparser.parse(body)
    if not feed.version or not feed.feed.get("title") or feed.bozo:
        raise SourceError("feed_schema")

    def parse_item(_rank, entry):
        date = entry.get("published_parsed") or entry.get("updated_parsed")
        published_at = datetime.fromtimestamp(timegm(date), UTC).isoformat() if date else None
        language = entry.get("language") or feed.feed.get("language")
        if not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
            language = source.language
        elif source.language != "und" and language.split("-")[0].lower() != source.language.split("-")[0].lower():
            # Some editions reuse a template that declares the wrong language (the Chinese
            # Malaysiakini feed says en-US). A feed may refine, but not contradict, the config.
            language = source.language
        # Preserve a factual syndication label when the feed exposes a source;
        # descriptions, author details and full text are never stored.
        title = entry.get("title")
        if source.id == "bernama" and isinstance(title, str):
            title = _bernama_title(title)
        row = _observation(
            source, title, entry.get("link"),
            published_at=published_at, language=language,
        )
        publisher = entry.get("source")
        if isinstance(publisher, dict) and _title(publisher.get("title"), 100):
            row["publisher"] = _title(publisher["title"], 100)
        return row

    return _item_rows(feed.entries[:100], parse_item)


def _bernama_title(title):
    # The English feed has historically labeled some UTF-8 bytes as Latin-1.
    # Only attempt repair when obvious mojibake is present and the entire title
    # decodes cleanly as UTF-8.
    if not re.search(r"[\x80-\x9f]|[ÂÃâ][\u0080-\u00bf€‚ƒ„…†‡]", title):
        return title
    for encoding in ("latin-1", "cp1252"):
        try:
            return title.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
    return title


def _list(value):
    if not isinstance(value, list):
        raise SourceError("json_schema")
    return value


def _object(value):
    if not isinstance(value, dict):
        raise SourceError("json_schema")
    return value


def _item_object(value):
    if not isinstance(value, dict):
        raise MalformedItem("json_item_schema")
    return value


def _json(body):
    try:
        return json.loads(body)
    except (ValueError, UnicodeError, RecursionError):
        raise SourceError("invalid_json") from None


def _hn(source, body, get):
    deadline = time.monotonic() + 100
    seen = set()

    def parse_item(rank, item_id):
        if type(item_id) is not int or not 0 < item_id <= 999_999_999_999:
            raise MalformedItem("hn_item_schema")
        if item_id in seen:
            return None
        seen.add(item_id)
        if time.monotonic() > deadline:
            raise SourceError("source_deadline")
        try:
            raw = get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")
        except SourceError as error:
            # An unsuccessful request is retriable for the source, even if the story
            # metadata for other items was valid.
            raise SourceError(f"hn_item_{error.code}", error.retry_after, http_status=error.http_status) from error
        try:
            item = _item_object(_json(raw))
        except SourceError as error:
            raise MalformedItem("hn_item_schema") from error
        if item.get("deleted") or item.get("dead") or item.get("type") == "job":
            return None
        if item.get("id") != item_id or item.get("type") != "story":
            raise MalformedItem("hn_item_schema")
        story_url = clean_url(item.get("url")) or f"https://news.ycombinator.com/item?id={item_id}"
        item_time = item.get("time")
        published_at = (
            datetime.fromtimestamp(item_time, UTC).isoformat()
            if type(item_time) is int and 0 <= item_time < 4_102_444_800 else None
        )
        score = item.get("score")
        return _observation(
            source, item.get("title"), story_url, rank,
            volume_raw=str(score) if type(score) is int and 0 <= score < 1_000_000_000 else None,
            published_at=published_at, identity=str(item_id),
        )

    return _item_rows(_list(_json(body))[:30], parse_item)


def _bluesky(source, body):
    payload = _object(_json(body))

    def parse_item(rank, raw):
        item = _item_object(raw)
        title = _title(item.get("displayName") or item.get("topic"))
        url = item.get("link")
        if isinstance(url, str) and url.startswith(("/search?", "/profile/")):
            url = f"https://bsky.app{url}"
        url = clean_url(url)
        if not url or urlsplit(url).hostname != "bsky.app":
            url = f"https://bsky.app/search?{urlencode({'q': title})}"
        return _observation(source, title, url, rank, identity=title.casefold())

    return _item_rows(_list(payload.get("topics"))[:10], parse_item)


def _mastodon(source, body):
    tags = source.id == "mastodon_tags"

    def parse_item(rank, raw):
        item = _item_object(raw)
        title = _title(item.get("name" if tags else "title"))
        url = item.get("url")
        if tags and title:
            title = "#" + title.lstrip("#")
            if clean_url(url) is None or urlsplit(url).hostname != "mastodon.social":
                raise MalformedItem("mastodon_tag_link")
        # Daily server counts may reset across midnight. Preserve the source's
        # rank here and avoid presenting a day's counts as an hourly metric.
        return _observation(source, title, url, rank)

    return _item_rows(_list(_json(body))[:10], parse_item)


def _weather(source, body):
    malaysia = timezone(timedelta(hours=8))

    def parse_item(_rank, raw):
        item = _item_object(raw)
        issue = _item_object(item.get("warning_issue"))
        english = _title(item.get("heading_en") or issue.get("title_en"))
        title = english or _title(item.get("heading_bm") or issue.get("title_bm"))
        issued = _iso(issue.get("issued"), malaysia)
        start = _iso(item.get("valid_from"), malaysia)
        end = _iso(item.get("valid_to"), malaysia)
        if not issued or not start or not end or end < start:
            raise MalformedItem("weather_schema")
        if datetime.fromisoformat(end) <= datetime.now(UTC):
            return None
        return _observation(
            source, title, WEATHER_LINK, published_at=issued,
            identity=f"{title}|{issued}|{start}|{end}", language="en" if english else "ms",
        ) | {"valid_from": start, "valid_to": end, "publisher": "MET Malaysia (CC BY 4.0)"}

    return _item_rows(_list(_json(body))[:50], parse_item)


def _gdelt(source, get):
    def parse_article(_rank, raw):
        article = _item_object(raw)
        # seendate belongs to the index. Leave publisher time unset.
        seen_at = _iso(article.get("seendate"))
        if not seen_at:
            raise MalformedItem("gdelt_seen_date")
        return _observation(
            source, article.get("title"), article.get("url"),
            language=_title(article.get("language"), 48),
        ) | {"seen_at": seen_at, "source_country": _title(article.get("sourcecountry"), 64) or None}

    batches = []
    for query in GDELT_QUERIES:
        params = urlencode({
            "query": query, "mode": "ArtList", "format": "json", "timespan": "1h",
            "sort": "HybridRel", "maxrecords": GDELT_MAX_ARTICLES,
        })
        payload = _object(_json(get(f"{source.url}?{params}")))
        batches.append(_item_rows(_list(payload.get("articles"))[:GDELT_MAX_ARTICLES], parse_article))
    return SourceItems(
        (row for batch in batches for row in batch), skipped=sum(batch.skipped for batch in batches),
    )


def collect_source(source, http=None):
    """Collect one configured source. Caller adds the UTC observation time and run ID."""
    _validate_source(source)
    if not source.enabled:
        raise SourceError("source_disabled")
    if http is None:
        if source.retention != "long_term":
            raise SourceError("retention_approval_required")
        with httpx.Client(
            trust_env=False, timeout=httpx.Timeout(5.0, connect=CONNECT_TIMEOUT), follow_redirects=False,
        ) as client:
            return collect_source(source, SourceHttp(client))
    if source.kind == "gdelt":
        rows = _gdelt(source, http.load)
    else:
        body = http.load(source.url)
        if source.kind == "hn":
            rows = _hn(source, body, http.load)
        else:
            parser = {
                "trends": _trends,
                "news": _news,
                "bluesky": _bluesky,
                "mastodon": _mastodon,
                "weather": _weather,
            }[source.kind]
            rows = parser(source, body)
    unique = {}
    for row in rows:
        unique.setdefault(row["content_id"], row)
    return SourceItems(unique.values(), skipped=rows.skipped)
