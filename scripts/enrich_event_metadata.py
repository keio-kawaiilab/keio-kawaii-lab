#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

DATA_PATH = Path("data/live-events.json")

# 公開された公式情報で確定しているものだけを補完する。
# 自動パーサが後続記事から会場を拾えなかった場合でも、既知の公式情報を失わないための安全網。
KNOWN_EVENT_METADATA = [
    {
        "group": "CANDY TUNE",
        "eventDate": "2026-10-01",
        "titleContains": "小川奈々子 生誕祭 2026",
        "sourceUrl": "https://candytune.asobisystem.com/news/detail/86518",
        "venue": "SGCホール有明",
    },
]


def source_urls(event: dict) -> set[str]:
    urls = set()
    if event.get("url"):
        urls.add(str(event["url"]))
    for url in event.get("urls") or []:
        if url:
            urls.add(str(url))
    return urls


def matches(event: dict, rule: dict) -> bool:
    if event.get("group") != rule["group"]:
        return False
    if str(event.get("eventDate") or "")[:10] != rule["eventDate"]:
        return False
    if rule["titleContains"] not in str(event.get("title") or ""):
        return False
    # 公式記事URLが保持されていれば最も確実。派生データでURL順が変わっても urls を見る。
    urls = source_urls(event)
    return rule["sourceUrl"] in urls or not urls


def enrich_payload(payload: dict) -> tuple[dict, int]:
    changed = 0
    for event in payload.get("events", []):
        if not isinstance(event, dict):
            continue
        for rule in KNOWN_EVENT_METADATA:
            if not matches(event, rule):
                continue
            if not event.get("venue"):
                event["venue"] = rule["venue"]
                changed += 1
            schedule = event.get("schedule")
            if isinstance(schedule, list):
                for item in schedule:
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("date") or "")[:10] == rule["eventDate"] and not item.get("venue"):
                        item["venue"] = rule["venue"]
            venues = event.get("venues")
            if isinstance(venues, list) and rule["venue"] not in venues:
                event["venues"] = [*venues, rule["venue"]]
            break
    return payload, changed


def main() -> int:
    if not DATA_PATH.exists():
        return 0
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    payload, changed = enrich_payload(payload)
    if changed:
        DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Enriched official event metadata: {changed} event(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
