"""Rank verifiable observations without filling coverage gaps."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
import json
import math
from pathlib import Path
import re
import unicodedata

from rapidfuzz import fuzz


SCORING_PATH = Path(__file__).resolve().parents[1] / "config" / "scoring.yaml"
VOLUME = re.compile(r"(?:(?:[0-9]{1,3}(?:,[0-9]{3})+)|[0-9]+)(?:\.[0-9]+)?[ ]*[kKmMbB]?\+?")
RANK_MISSING = 1000000
PUBLISHERS = {
    "malaysiakini": "malaysiakini",
    "malaysiakini_zh": "malaysiakini",
    "当今大马": "malaysiakini",
    "當今大馬": "malaysiakini",
    "malay_mail": "malay mail",
    "fmt": "free malaysia today",
    "bernama": "bernama",
}


def instant(value):
    if value is None:
        return None
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise ValueError("Observation timestamps require a UTC offset")
    return parsed.astimezone(UTC)


def trend_key(title):
    """Exact grouping after compatibility, case and whitespace normalization."""
    return " ".join(unicodedata.normalize("NFKC", title).casefold().split())


def volume_bucket(raw):
    if not raw or len(raw) > 30:
        return None
    value = unicodedata.normalize("NFKC", raw).strip()
    if not VOLUME.fullmatch(value):
        return None
    value = value.upper().removesuffix("+").strip().replace(",", "").replace(" ", "")
    scale = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(value[-1], 1)
    amount = float(value[:-1] if scale != 1 else value) * scale
    return amount if amount > 0 else None


def load_scoring(config_path=None):
    # The bundled YAML is written in its JSON subset to avoid another dependency.
    with Path(config_path or SCORING_PATH).open(encoding="utf-8") as stream:
        config = json.load(stream)
    if not config["algo_version"] or config["window_hours"] <= 0 or config["freshness_hours"] <= 0:
        raise ValueError("Invalid scoring configuration")
    return config


@dataclass(frozen=True)
class Evidence:
    row: dict
    at: datetime
    slot: datetime
    published: datetime | None
    key: str
    rank: int

    @classmethod
    def from_row(cls, row):
        return cls(
            row,
            instant(row["observed_at"]),
            instant(row["slot"]),
            instant(row.get("published_at")),
            trend_key(row["title"]),
            row.get("rank") or RANK_MISSING,
        )

    @property
    def source(self):
        return self.row["source_id"]

    @property
    def geo(self):
        return self.row["geo"]

    @property
    def url(self):
        return self.row["url"]

    @property
    def article_at(self):
        return self.published or instant(self.row.get("first_seen_at")) or self.at

    def reference(self):
        fields = ("source_id", "kind", "geo", "language", "title", "url", "rank", "volume_raw",
                  "published_at", "observed_at", "slot", "run_id", "content_id", "valid_from", "valid_to",
                  "publisher")
        return {field: self.row[field] for field in fields if field in self.row}


def row_priority(evidence):
    return evidence.at, -evidence.rank, evidence.source, evidence.url


def _comparable_title(left, right, threshold, minimum):
    if left == right:
        return True
    if min(len(left), len(right)) < minimum:
        return False
    if re.findall(r"\d+", left) != re.findall(r"\d+", right):
        return False
    return bool(fuzz.ratio(left, right, score_cutoff=threshold))


def _article_matcher(trends, news, config):
    """Index recurring headlines and URLs once, then return matching news observations."""
    by_url = defaultdict(set)
    by_title = defaultdict(set)
    articles = {}
    for item in news:
        identity = item.source, item.url
        by_url[item.url].add(identity)
        by_title[item.key].add(identity)
        # Attach media evidence to the original publication or earliest discovery.
        if identity not in articles or item.at < articles[identity].at:
            articles[identity] = item

    @cache
    def similar_titles(title):
        return tuple(
            candidate for candidate in by_title
            if _comparable_title(title, candidate, config["title_similarity"], config["minimum_title_chars"])
        )

    time_window = timedelta(hours=config["title_match_hours"])
    anchors = defaultdict(set)
    matches = defaultdict(set)
    for trend in trends:
        # Only MY searches give evidence of a Malaysia topic's local media coverage.
        if trend.geo != "MY":
            continue
        for link in trend.row.get("related") or ():
            matches[trend.key].update(by_url.get(link["url"], ()))
            if link.get("title"):
                anchors[trend.key].add((trend_key(link["title"]), trend.published or trend.at))
    for topic, headlines in anchors.items():
        for title, when in headlines:
            for candidate in similar_titles(title):
                for identity in by_title[candidate]:
                    item = articles[identity]
                    if abs(when - item.article_at) <= time_window:
                        matches[topic].add(identity)
    history = defaultdict(list)
    for item in news:
        history[item.source, item.url].append(item)
    return {topic: [item for identity in identities for item in history[identity]]
            for topic, identities in matches.items()}


def _independent_media(articles, config, *, distinguish_language=False):
    """Collapse duplicate wire headlines and group by publisher."""
    accepted = []
    evidence = sorted(articles, key=lambda item: (item.article_at, item.source, item.url))
    for item in evidence:
        if any(item.url == other.url or _comparable_title(
            item.key, other.key, config["syndication_similarity"], config["minimum_title_chars"]
        ) for other in accepted):
            continue
        accepted.append(item)
    by_source = {}
    publishers = set()
    for item in accepted:
        name = item.row.get("publisher") or PUBLISHERS.get(item.source, item.source)
        publisher = trend_key(name)
        publisher = PUBLISHERS.get(publisher, publisher)
        edition = (publisher, item.row.get("language")) if distinguish_language else publisher
        if edition in publishers or item.source in by_source:
            continue
        publishers.add(edition)
        by_source[item.source] = item
    return by_source


def _category(evidence, config):
    labels = [evidence.key]
    labels.extend(trend_key(link["title"]) for link in evidence.row.get("related") or () if link.get("title"))
    for category, terms in config["categories"].items():
        for term in terms:
            if any(ord(char) > 127 for char in term):
                if any(term in label for label in labels):
                    return category
            elif any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", label) for label in labels):
                return category
    return "其他"


def _current_rows(evidence, coverage):
    by_source = defaultdict(list)
    for item in evidence:
        by_source[item.source].append(item)
    for source_id, items in by_source.items():
        status = coverage.get(source_id, {})
        if status.get("status") != "ok":
            continue
        observed_at = instant(status.get("observed_at")) or max(item.at for item in items)
        yield from (item for item in items if item.at == observed_at)


def _first_seen(items):
    observed = min(item.at for item in items)
    earlier = [instant(item.row["first_seen_at"]) for item in items if item.row.get("first_seen_at")]
    return min([observed, *earlier])


def _growth(items, media, trend_coverage, valid_slots, config):
    """Compare measured states across actual timestamps and distinct hourly slots."""
    cohorts = defaultdict(list)
    by_geo = defaultdict(list)
    for item in items:
        cohorts[item.slot].append(item)
        by_geo[item.geo].append(item)
    signals = []
    for geo, rows in sorted(by_geo.items()):
        latest = max(rows, key=row_priority)
        previous = [item for item in rows if item.at < latest.at and item.slot != latest.slot]
        if not previous:
            continue
        baseline = max(previous, key=row_priority)
        before = volume_bucket(baseline.row.get("volume_raw"))
        after = volume_bucket(latest.row.get("volume_raw"))
        if before is not None and after is not None and after > before:
            signals.append({
                "kind": "volume", "geo": geo, "before": baseline.row["volume_raw"],
                "after": latest.row["volume_raw"], "baseline": baseline.reference(),
                "current": latest.reference(),
            })

    if len(cohorts) < 2:
        return signals

    current_slot = max(cohorts, key=lambda slot: max(item.at for item in cohorts[slot]))
    current_start = min(item.at for item in cohorts[current_slot])
    earlier = [
        slot for slot, group in cohorts.items()
        if slot != current_slot and max(item.at for item in group) < current_start
    ]
    if not earlier:
        return signals

    baseline_slot = max(earlier, key=lambda slot: max(item.at for item in cohorts[slot]))
    before = {item.geo for item in cohorts[baseline_slot]}
    after = {item.geo for item in cohorts[current_slot]}
    if before < after and (after - before) <= trend_coverage[baseline_slot]:
        signals.append({
            "kind": "geos", "before": sorted(before), "after": sorted(after),
            "baseline": [item.reference() for item in cohorts[baseline_slot]],
            "current": [item.reference() for item in cohorts[current_slot]],
        })

    before = _independent_media([item for item in media if item.slot == baseline_slot], config)
    after = _independent_media([item for item in media if item.slot == current_slot], config)
    if before and before.keys() < after.keys() and (after.keys() - before.keys()) <= valid_slots[baseline_slot]:
        signals.append({
            "kind": "media", "before": sorted(before), "after": sorted(after),
            "baseline": [item.reference() for item in before.values()],
            "current": [item.reference() for item in after.values()],
        })
    return signals


def _context(representative):
    """First Trends-linked article, present only when the source retains related metadata."""
    for link in representative.row.get("related") or ():
        if isinstance(link, dict) and link.get("title") and link.get("url"):
            return {key: link[key] for key in ("title", "url", "publisher") if link.get(key)}
    return None


def _topic_entry(representative, first_seen, config, **fields):
    entry = {
        **representative.reference(),
        "first_seen_at": first_seen.isoformat(),
        "category": _category(representative, config),
        "algo_version": config["algo_version"],
        **fields,
    }
    context = _context(representative)
    if context:
        entry["context"] = context
    return entry


def _latest(items):
    return max(items, key=row_priority)


def rank_observations(rows, coverage, now, config, historical_coverage):
    window = timedelta(hours=config["window_hours"])
    evidence = [Evidence.from_row(row) for row in rows]
    evidence = [item for item in evidence if now - window <= item.at <= now]
    trends = [
        item for item in evidence
        if item.row["kind"] == "trends" and coverage.get(item.source, {}).get("status") == "ok"
    ]
    news = [
        item for item in evidence
        if item.row["kind"] == "news" and item.geo == "MY"
        and coverage.get(item.source, {}).get("status") == "ok"
        and now - window <= item.article_at <= now
    ]
    topic_items = defaultdict(list)
    trend_coverage = defaultdict(set)
    valid_slots = defaultdict(set)
    for item in trends:
        topic_items[item.key].append(item)
        trend_coverage[item.slot].add(item.geo)
    for item in news:
        valid_slots[item.slot].add(item.source)
    for slot, statuses in historical_coverage.items():
        timestamp = instant(slot)
        for source_id, status in statuses.items():
            source = coverage.get(source_id)
            if not source or status not in {"ok", "empty"}:
                continue
            if source["kind"] == "trends":
                trend_coverage[timestamp].add(source["geo"])
            if source["kind"] == "news":
                valid_slots[timestamp].add(source_id)

    matched_news = _article_matcher(trends, news, config)
    local_rank = []
    global_rank = []
    new_rank = []
    rising_rank = []
    weights = config["my_weights"]
    local_media_covered = any(
        source["kind"] == "news" and source["geo"] == "MY" and source["status"] in {"ok", "empty"}
        for source in coverage.values()
    )
    for topic, items in topic_items.items():
        first_seen = _first_seen(items)
        latest = _latest(items)
        regions = sorted({item.geo for item in items})
        per_slot = defaultdict(set)
        for item in items:
            per_slot[item.slot].add(item.geo)
        peak_regions = max(len(geos) for geos in per_slot.values())
        global_entry = _topic_entry(latest, first_seen, config, geos=regions, peak_regions=peak_regions)
        global_rank.append(global_entry)

        local = [item for item in items if item.geo == "MY"]
        media = matched_news.get(topic, [])
        if local:
            recent = _latest(local)
            local_media = _independent_media(media, config)
            volume = volume_bucket(recent.row.get("volume_raw"))
            components = {
                "volume": weights["volume"] * math.log10(volume) if volume is not None else None,
                "local_media": weights["local_media"] * len(local_media) if local_media_covered else None,
                "recency": weights["recency"] * (1 - (now - recent.at) / window),
            }
            local_rank.append(_topic_entry(
                recent, first_seen, config,
                score=round(sum(value for value in components.values() if value is not None), 4),
                components={name: round(value, 4) if value is not None else None
                            for name, value in components.items()},
                media=[item.reference() for item in local_media.values()],
                media_covered=local_media_covered,
                geos=regions,
            ))
        if now - window <= first_seen:
            signals = _growth(items, media, trend_coverage, valid_slots, config)
            entry = {**global_entry, "growth": signals}
            (rising_rank if signals else new_rank).append(entry)

    local_rank.sort(key=lambda item: (-item["score"], -instant(item["observed_at"]).timestamp(), item["title"]))
    global_rank.sort(key=lambda item: (-len(item["geos"]), -item["peak_regions"],
                                       -instant(item["observed_at"]).timestamp(), item["title"]))
    new_rank.sort(key=lambda item: (-instant(item["first_seen_at"]).timestamp(), -len(item["geos"]), item["title"]))
    rising_rank.sort(key=lambda item: (-len(item["growth"]), -len(item["geos"]),
                                       -instant(item["observed_at"]).timestamp(), item["title"]))

    current = list(_current_rows(evidence, coverage))
    eligible_news = {(item.source, item.at, item.url) for item in news}
    news_current = [item for item in current if (item.source, item.at, item.url) in eligible_news]
    local_news = sorted(
        _independent_media(news_current, config, distinguish_language=True).values(),
        key=row_priority, reverse=True,
    )
    social = defaultdict(list)
    charts = defaultdict(list)
    for item in sorted(current, key=lambda item: (item.rank, item.source, item.key)):
        if item.row["kind"] in {"hn", "bluesky", "mastodon"}:
            social[item.source].append(_topic_entry(item, _first_seen([item]), config))
        elif item.row["kind"] == "chart":
            first = _first_seen([item])
            charts[item.source].append(_topic_entry(
                item, first, config, artist=item.row.get("artist"), genre=item.row.get("genre"),
                new_entry=now - window <= first,
            ))

    weather = []
    weather_horizon = now + timedelta(hours=config["weather_lookahead_hours"])
    for item in current:
        if item.row["kind"] != "weather":
            continue
        starts, ends = instant(item.row.get("valid_from")), instant(item.row.get("valid_to"))
        if (starts is None or starts <= weather_horizon) and ends is not None and ends > now:
            weather.append(_topic_entry(item, _first_seen([item]), config))
    associated_urls = {item.url for items in matched_news.values() for item in items}
    category_news = [_topic_entry(item, _first_seen([item]), config)
                     for item in local_news if item.url not in associated_urls]
    categories = {}
    for category in ("商品 / 消费", "AI / 科技"):
        distinct = {}
        for item in [*local_rank, *global_rank, *category_news]:
            if item["category"] == category:
                distinct.setdefault(trend_key(item["title"]), item)
        categories[category] = list(distinct.values())[:config["category_limit"]]
    return {
        "algo_version": config["algo_version"],
        "window_start": (now - window).isoformat(),
        "data_latest_observation": max((item.at for item in evidence), default=None),
        "malaysia": local_rank[:config["my_limit"]],
        "monitored_regions": global_rank[:config["global_limit"]],
        "new": new_rank[:config["new_limit"]],
        "rising": rising_rank[:config["rising_limit"]],
        "local_news": [_topic_entry(item, _first_seen([item]), config) for item in local_news[:config["local_news_limit"]]],
        "platforms": {source: items[:config["platform_limit"]] for source, items in sorted(social.items())},
        "charts": {source: items[:config.get("chart_limit", 10)] for source, items in sorted(charts.items())},
        "weather": weather[:config["weather_limit"]],
        "categories": categories,
    }
