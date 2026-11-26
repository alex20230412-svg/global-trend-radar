"""Render an entirely synthetic weekly preview, without GitHub or a model."""

from datetime import date, timedelta
import json

from radar.delivery import _message_text, _units
from radar.storage import json_bytes
from radar.weekly import build_weekly, weekly_key


END = date(2026, 11, 29)


class _SampleStore:
    def __init__(self):
        self.files = {}

    def read(self, key):
        return self.files.get(key)

    def daily(self, day, entries):
        report_id = f"daily-{day.isoformat()}"
        path = f"reports/{day:%Y/%m/%d}/{report_id}.json"
        self.files[path] = json_bytes({"brief_entries": entries, "parts": ["合成日报"]})
        self.files[f"deliveries/{report_id}.json"] = json_bytes({"parts": [{"delivery_state": "SENT"}]})


class _SampleIdeas:
    def write(self, _system, prompt):
        entries = list(json.loads(prompt))
        texts = (
            "可先向社区活动参与者了解报名难点，再考虑小规模试点",
            "可调查中文科学读物的需求，再决定是否策划体验活动",
            "可测试读者是否需要易读的周末话题导览",
        )
        ideas = [{"text": text, "ids": [key]} for key, text in zip(entries[:3], texts, strict=True)]
        return json.dumps({"items": [], "ideas": ideas}, ensure_ascii=False), "ok", "synthetic"


def _entry(section, key, title):
    return {"key": key, "section": section, "title": title, "url": f"https://example.org/weekly/{key}"}


def synthetic_weekly():
    store = _SampleStore()
    monday = END - timedelta(days=6)
    recurring = _entry("malaysia", "community", "星湾社区开放文化体验活动")
    store.daily(monday - timedelta(days=2), [recurring])
    for offset in range(7):
        entries = [recurring, _entry("music", "music", "雨林节奏 · 合成歌手"),
                   _entry("apps", "app", "Cloud Compass · 合成地图"),
                   _entry("wiki", "wiki", "合成海鸟观察记录"),
                   _entry("china", "china", "合成长江夜游主题")]
        if offset >= 2:
            entries.append(_entry("malaysia", "science", "中文儿童科学读书会"))
        if offset >= 4:
            entries.append(_entry("global", "design", "云桥设计周公布桌面光谱仪方案"))
        if offset == 6:
            entries.append(_entry("malaysia", "weekend", "周末街角修理工作坊"))
        store.daily(monday + timedelta(days=offset), entries)
    return build_weekly(store, END, weekly_key(END), writer=_SampleIdeas())


def print_sample_weekly():
    parts = synthetic_weekly()
    print(f"合成周报 · 共 {len(parts)} 段")
    for number, markup in enumerate(parts, 1):
        plain = _message_text(markup)
        print(f"\n第 {number} 段 · {_units(plain)} UTF-16 单元")
        print(plain)


if __name__ == "__main__":
    print_sample_weekly()
