"""Read delivered daily briefs without treating previews or ranking candidates as appearances."""

from datetime import timedelta
from html.parser import HTMLParser

from .layout import entry_key
from .sources import clean_url
from .storage import read_json


BRIEF_SECTIONS = {"malaysia", "global", "china", "wiki", "music", "apps"}


def _daily_payload(store, day):
    report_id = f"daily-{day.isoformat()}"
    try:
        ledger = read_json(store, f"deliveries/{report_id}.json")
        parts = ledger.get("parts") if isinstance(ledger, dict) else None
        if not parts or not isinstance(parts, list) or any(
            not isinstance(row, dict) or row.get("delivery_state") not in {"SENT", "CONFIRMED"}
            for row in parts
        ):
            return None
        payload = read_json(store, f"reports/{day:%Y/%m/%d}/{report_id}.json")
    except (ValueError, TypeError):
        return None
    messages = payload.get("parts") if isinstance(payload, dict) else None
    if not isinstance(messages, list) or len(messages) != len(parts):
        return None
    return payload


def _entries(payload):
    entries = payload.get("brief_entries")
    if not isinstance(entries, list):
        return None
    return [
        entry for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("key"), str) and entry["key"]
        and isinstance(entry.get("section"), str) and entry["section"] in BRIEF_SECTIONS
        and isinstance(entry.get("title"), str) and entry["title"]
    ]


def read_daily_entries(store, day):
    """Return exact displayed entries from a completed v5 daily delivery, or None if unavailable."""
    payload = _daily_payload(store, day)
    return _entries(payload) if payload else None


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            url = clean_url(dict(attrs).get("href"))
            if url:
                self.urls.add(url)


def _legacy_keys(payload):
    """Old briefs can prove only appearances with an original link in the sent payload."""
    parser = _Links()
    for part in payload["parts"]:
        if isinstance(part, str):
            parser.feed(part)
    ranking = payload.get("ranking")
    if not isinstance(ranking, dict):
        return set()
    charts = ranking.get("charts")
    charts = charts if isinstance(charts, dict) else {}
    sets = (
        ("malaysia", ranking.get("malaysia", [])),
        ("global", [*ranking.get("monitored_regions", []), *ranking.get("rising", []), *ranking.get("new", [])]),
        ("music", charts.get("apple_music_my", [])),
        ("apps", charts.get("app_store_my", [])),
    )
    keys = set()
    for section, rows in sets:
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = clean_url(row.get("url"))
            context = row.get("context")
            headline = clean_url(context.get("url")) if isinstance(context, dict) else None
            if url in parser.urls or headline in parser.urls:
                keys.add(entry_key(row.get("title"), url, section=section, artist=row.get("artist")))
    return keys


def previous_brief_keys(store, day):
    keys = set()
    for offset in range(1, 8):
        payload = _daily_payload(store, day - timedelta(days=offset))
        if payload is None:
            continue
        entries = _entries(payload)
        if entries is None:
            keys.update(_legacy_keys(payload))
        else:
            keys.update(entry["key"] for entry in entries)
    return keys
