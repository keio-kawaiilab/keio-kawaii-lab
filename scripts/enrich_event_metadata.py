#!/usr/bin/env python3
from __future__ import annotations

import json
import re
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

# ツアー全体の「公式情報」は、個別公演ページやニュース記事ではなく
# 公式特設ページを正とする。プレイガイドの申込ページは別用途なので上書きしない。
KNOWN_TOUR_FEATURES = [
    {
        "group": "FRUITS ZIPPER",
        "pattern": re.compile(r"JAPAN\s*TOUR\s*2026.*AUTUMN", re.I),
        "url": "https://fruitszipper.asobisystem.com/feature/2026tour_autumn",
    },
    {
        "group": "CANDY TUNE",
        "pattern": re.compile(r"JAPAN\s*TOUR\s*2026.*AUTUMN", re.I),
        "url": "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026",
    },
    {
        "group": "SWEET STEADY",
        "pattern": re.compile(r"(?:JAPAN\s*(?:HALL\s*)?TOUR\s*2026|JAPAN\s*TOUR\s*2026.*WINTER)", re.I),
        "url": "https://sweetsteady.asobisystem.com/feature/sweetsteady_japanhalltour2026",
    },
    {
        "group": "CUTIE STREET",
        "pattern": re.compile(r"(?:ARENA\s*TOUR\s*2026|AUTUMN\s*TOUR)", re.I),
        "url": "https://cutiestreet.asobisystem.com/feature/autumntour",
    },
]
PLAYGUIDE_SOURCES = {"pia", "lawson", "eplus"}
PLAYGUIDE_HOST_HINTS = ("t.pia.jp", "l-tike.com", "eplus.jp")


def source_urls(event: dict) -> set[str]:
    urls = set()
    if event.get("url"):
        urls.add(str(event["url"]))
    for url in event.get("urls") or []:
        if url:
            urls.add(str(url))
    return urls


def ordered_source_urls(event: dict) -> list[str]:
    values: list[str] = []
    for value in [event.get("url"), *(event.get("urls") or [])]:
        if value and str(value) not in values:
            values.append(str(value))
    return values


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


def is_playguide_event(event: dict) -> bool:
    source = str(event.get("ticketProvider") or event.get("sourceType") or event.get("primarySource") or "").lower()
    if source in PLAYGUIDE_SOURCES:
        return True
    primary_url = str(event.get("url") or "").lower()
    return any(host in primary_url for host in PLAYGUIDE_HOST_HINTS)


def tour_feature_url(event: dict) -> str | None:
    title = str(event.get("eventTitle") or event.get("displayTitle") or event.get("title") or "")
    group = str(event.get("group") or "")
    for rule in KNOWN_TOUR_FEATURES:
        if group == rule["group"] and rule["pattern"].search(title):
            return str(rule["url"])
    return None


def normalize_tour_link(event: dict) -> bool:
    feature = tour_feature_url(event)
    if not feature or is_playguide_event(event):
        return False

    previous = ordered_source_urls(event)
    urls = [feature, *[value for value in previous if value != feature]]
    changed = (
        event.get("url") != feature
        or event.get("officialTourUrl") != feature
        or list(event.get("urls") or []) != urls
    )
    event["url"] = feature
    event["officialTourUrl"] = feature
    event["urls"] = urls
    return changed


def enrich_payload(payload: dict) -> tuple[dict, int]:
    changed = 0
    for event in payload.get("events", []):
        if not isinstance(event, dict):
            continue

        event_changed = normalize_tour_link(event)

        for rule in KNOWN_EVENT_METADATA:
            if not matches(event, rule):
                continue
            if not event.get("venue"):
                event["venue"] = rule["venue"]
                event_changed = True
            schedule = event.get("schedule")
            if isinstance(schedule, list):
                for item in schedule:
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("date") or "")[:10] == rule["eventDate"] and not item.get("venue"):
                        item["venue"] = rule["venue"]
                        event_changed = True
            venues = event.get("venues")
            if isinstance(venues, list) and rule["venue"] not in venues:
                event["venues"] = [*venues, rule["venue"]]
                event_changed = True
            break

        if event_changed:
            changed += 1
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
