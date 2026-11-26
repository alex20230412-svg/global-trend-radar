"""Print a deterministic, entirely synthetic digest through the real splitter."""

from datetime import UTC, datetime, timedelta

from radar.brief import build_brief
from radar.delivery import _message_text, _units
from radar.report import build_report
from radar.sources import load_sources
from radar.youtube import YouTubeVideo, render_youtube


NOW = datetime(2026, 11, 27, 0, 37, tzinfo=UTC)
OBSERVED = NOW - timedelta(minutes=17)
PREVIOUS = OBSERVED - timedelta(hours=1)
TOPICS = (
    ("月湾 AI 课堂助教开放离线多语试用", "8K+", "SG", "JP"),
    ("星港购物节公开低耗雾灯新品与折扣", "5K+", "SG", "TH"),
    ("青原科技发布便携式无网络机器人套件", "3K+", "SG", "ID"),
    ("青潮音乐电影周开放海边放映预约", "2K+", "TH", "VN"),
    ("白榕羽毛球联赛新增家庭体验场", "1K+", "ID", "VN"),
    ("绘灯科技展推出低功耗教育芯片", "900+", "JP", "US"),
    ("滨光社区开放周末修理图书馆预约", "700+", "GB"),
    ("松岸分享节推出环保购物与再使用挑战", "650+", "AU"),
    ("雾港电影配乐公开试听", "450+", "KR"),
    ("银竹科技展公布模拟月球基地路线", "400+", "TW"),
)


def synthetic_report():
    sources = load_sources()
    rows = []

    def observe(source, kind, title, *, at=OBSERVED, geo="MY", rank=1, volume=None, **extra):
        rows.append({
            "source_id": source,
            "kind": kind,
            "title": title,
            "language": "zh",
            "geo": geo,
            "rank": rank,
            "volume_raw": volume,
            "published_at": at.isoformat(),
            "observed_at": at.isoformat(),
            "slot": at.replace(minute=0).isoformat(),
            "url": f"https://example.org/synthetic/{source}/{rank}",
            **extra,
        })

    for rank, (title, volume, *regions) in enumerate(TOPICS, 1):
        # Retained Trends article metadata only exists once the Owner approves retain_related.
        related = [{
            "title": f"合成报道：第 {rank} 个话题的相关新闻标题",
            "url": f"https://example.org/synthetic/context/{rank}",
            "publisher": "示例媒体",
        }] if rank <= 3 else []
        observe("trends_my", "trends", title, rank=rank, volume=volume, related=related)
        if rank <= 5:
            observe("trends_my", "trends", title, rank=rank, at=PREVIOUS, volume="200+")
        for region in regions:
            observe(f"trends_{region.lower()}", "trends", title, geo=region, rank=rank, volume="400+")

    for region in ("JP", "US"):
        observe(f"trends_{region.lower()}", "trends", "云桥设计周公布桌面光谱仪方案",
                geo=region, rank=11, volume="2K+")

    for source, title in (
        ("malaysiakini", "Community workshop opens a family bicycle repair day"),
        ("malaysiakini_zh", "青石社区推出华文儿童科学读书会"),
        ("malay_mail", "Seaside film week adds a low-light accessible screening"),
        ("bernama", "Volunteers recruit for a riverside plant survey"),
    ):
        observed_at = OBSERVED + timedelta(minutes=1) if source == "malaysiakini_zh" else OBSERVED
        observe(source, "news", title, at=observed_at, language="zh" if source == "malaysiakini_zh" else "en")

    for source, kind, titles in (
        ("bluesky", "bluesky", ("给城市夜鸟设计一份声音地图", "可负担植物染", "低碳野餐话题")),
        ("mastodon_tags", "mastodon", ("开源修理", "跨语字幕公益", "城市麋鹿观察")),
        ("hn", "hn", ("离线地图怎样保存志愿者修订", "开源传感器模拟器", "一个低功耗日志账本")),
    ):
        for rank, title in enumerate(titles, 1):
            observe(source, kind, title, geo="GLOBAL", rank=rank)

    for rank, (title, artist) in enumerate((
        ("示例情歌（合成）", "示例歌手甲"), ("夜市之歌（合成）", "示例乐队乙"), ("雨季练习曲（合成）", "示例歌手丙"),
    ), 1):
        observe("apple_music_my", "chart", title, rank=rank, artist=artist, genre="Pop",
                url=f"https://music.apple.com/my/album/synthetic-{rank}")
    for rank, (title, genre) in enumerate((("示例记账 App", "Finance"), ("示例外卖 App", "Food & Drink")), 1):
        observe("app_store_my", "chart", title, rank=rank, genre=genre,
                url=f"https://apps.apple.com/my/app/synthetic-{rank}")

    for rank, (title, hours) in enumerate((
        ("示例区域 A · 雷暴警告", 2),
        ("示例区域 B · 海岸大风警告", 6),
    ), 1):
        observe("weather", "weather", title, rank=rank, valid_from=OBSERVED.isoformat(),
                valid_to=(OBSERVED + timedelta(hours=hours)).isoformat())

    latest = {}
    for item in rows:
        key = item["source_id"]
        latest[key] = max(latest.get(key, ""), item["observed_at"])
    checked = {
        source.id: latest.get(source.id, OBSERVED.isoformat()) for source in sources
        if source.enabled and source.retention == "long_term" and source.id != "mastodon_links"
    }
    coverage = [
        {
            "source_id": source.id,
            "kind": source.kind,
            "geo": source.geo,
            "status": ("ok" if source.id in latest else "disabled" if not source.enabled
                       else "unapproved" if source.retention != "long_term"
                       else "error" if source.id == "mastodon_links" else "empty"),
            "reason": "sample_timeout" if source.id == "mastodon_links" else None,
            "observed_at": checked.get(source.id),
            "last_success_at": checked.get(source.id),
        }
        for source in sources
    ]
    return build_report(
        rows,
        coverage,
        now=NOW,
        target_at=NOW.replace(minute=30),
        missed_slots=[NOW.replace(minute=0) - timedelta(hours=2)],
    )


def main():
    # What the Owner receives when no AI key is available: the plain Chinese brief.
    report = synthetic_report()
    parts = build_brief(report.snapshot, NOW, "synthetic-digest").parts
    print(f"合成日报 · 共 {len(parts)} 段")
    for number, part in enumerate(parts, 1):
        plain = _message_text(part)
        print(f"\n第 {number} 段 · {len(plain)} 字符 · {_units(plain)} UTF-16 单元")
        print(plain)

    youtube = render_youtube((
        YouTubeVideo("AAAAAAAAAAA", "示例视频 A · 雨季练习曲", "示例频道甲", "10", 1_234_567),
        YouTubeVideo("BBBBBBBBBBB", "Synthetic Video B: Night Market Quest", "Example Gaming Channel", "20", 24_680),
        YouTubeVideo("CCCCCCCCCCC", '示例视频 C · "月湾故事"预告', "示例电影频道 & 朋友", "44", 985),
    ))
    youtube_plain = _message_text(youtube)
    print(f"\n合成 YouTube 消息 · 1 段 · {_units(youtube_plain)} UTF-16 单元")
    print(youtube_plain)


if __name__ == "__main__":
    main()
