"""Print a deterministic, entirely synthetic digest through the real splitter."""

from datetime import UTC, datetime, timedelta

from radar.delivery import _message_text, _units, split_parts
from radar.report import ReportBlock, build_report
from radar.sources import load_sources


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
            "title": f"合成报道：{title}引发讨论",
            "url": f"https://example.org/synthetic/context/{rank}",
            "publisher": "示例媒体",
        }] if rank <= 3 else []
        observe("trends_my", "trends", title, rank=rank, volume=volume, related=related)
        if rank <= 5:
            observe("trends_my", "trends", title, rank=rank, at=PREVIOUS, volume="200+")
        for region in regions:
            observe(f"trends_{region.lower()}", "trends", title, geo=region, rank=rank, volume="400+")

    for source, title in (
        ("malaysiakini", "白榕社区修理站为家庭开放自行车检修日"),
        ("malay_mail", "青潮海滨放映周新增低亮无障碍银幕"),
        ("bernama", "银竹志愿者招募河岸植物清点队"),
    ):
        observe(source, "news", title)

    for source, kind, titles in (
        ("bluesky", "bluesky", ("给城市夜鸟设计一份声音地图", "可负担植物染", "低碳野餐话题")),
        ("mastodon_tags", "mastodon", ("开源修理", "跨语字幕公益", "城市麋鹿观察")),
        ("hn", "hn", ("离线地图怎样保存志愿者修订", "开源传感器模拟器", "一个低功耗日志账本")),
    ):
        for rank, title in enumerate(titles, 1):
            observe(source, kind, title, geo="GLOBAL", rank=rank)

    for rank, (title, hours) in enumerate((
        ("示例区域 A · 雷暴警告", 2),
        ("示例区域 B · 海岸大风警告", 6),
    ), 1):
        observe("weather", "weather", title, rank=rank, valid_from=OBSERVED.isoformat(),
                valid_to=(OBSERVED + timedelta(hours=hours)).isoformat())

    present = {item["source_id"] for item in rows}
    coverage = [
        {
            "source_id": source.id,
            "kind": source.kind,
            "geo": source.geo,
            "status": ("ok" if source.id in present else "disabled" if not source.enabled
                       else "error" if source.id == "mastodon_links" else "unapproved"),
            "reason": "sample_timeout" if source.id == "mastodon_links" else None,
            "observed_at": OBSERVED.isoformat() if source.id in present else None,
            "last_success_at": OBSERVED.isoformat() if source.id in present else None,
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
    notice = "合成样本 · 话题、数据和链接仅用于离线验证"
    report = synthetic_report()
    parts = split_parts([ReportBlock(notice, notice), *report.blocks], label="synthetic-digest")
    print(f"合成日报 · 共 {len(parts)} 段")
    for number, part in enumerate(parts, 1):
        plain = _message_text(part)
        print(f"\n第 {number} 段 · {len(plain)} 字符 · {_units(plain)} UTF-16 单元")
        print(plain)


if __name__ == "__main__":
    main()
