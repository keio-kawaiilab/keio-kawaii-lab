#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

DATA_PATH = Path("data/live-events.json")
GROUP_NAMES = (
    "FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR",
    "KAWAII LAB.合同", "KAWAII LAB.",
)


def normalize_text(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def source_kind(event: dict) -> str:
    source = normalize_text(event.get("sourceType")).lower()
    url = normalize_text(event.get("url")).lower()
    if source == "sukisuki" or "sukisuki-shop.com" in url:
        return "sukisuki"
    if source == "pia" or "t.pia.jp" in url:
        return "pia"
    return "official"


def is_online(event: dict) -> bool:
    text = f"{event.get('eventCategory', '')} {event.get('ticketType', '')} {event.get('title', '')}"
    return event.get("eventCategory") == "online-benefit" or bool(re.search(r"オンライン(?:特典会|サイン会)", text))


def sale_family(event: dict) -> str:
    text = normalize_text(f"{event.get('ticketType', '')} {event.get('title', '')}")
    if is_online(event):
        return "online-benefit"
    if "アップグレード" in text:
        return "upgrade"
    if re.search(
        r"(?:年会費コース|OFFICIAL FANCLUB|ファンクラブ|(?:^|\s)FC(?:\s*(?:会員|先行|限定|2次先行|2次|年会費コース))?)",
        text,
        re.I,
    ):
        return "fc"
    if re.search(r"(?:一般発売|一般販売|一般先着|一般先行)", text):
        return "general"
    if re.search(r"(?:プレリザーブ|プレイガイド|ぴあNICOS|ぴあカード|プリセール)", text, re.I):
        return "playguide"
    if "先行" in text:
        return "presale"
    if event.get("ticketType") == "現在受付なし" or event.get("applicationStatus") == "none":
        return "schedule-only"
    return "other"


def canonical_title(event: dict) -> str:
    text = normalize_text(event.get("eventTitle") or event.get("title") or "")
    text = re.sub(r"^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+", "", text)
    quoted = re.search(r"「([^」]+)」", text)
    if quoted:
        text = quoted.group(1)
    text = re.sub(r"^(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*", "", text)
    for group in GROUP_NAMES:
        text = re.sub(rf"^{re.escape(group)}\s*", "", text, flags=re.I)
    text = re.split(
        r"\s*@|開催決定|出演決定|アップグレード抽選受付|一般(?:発売|販売|先行)|"
        r"FC\s*(?:会員)?先行|ファンクラブ|OFFICIAL FANCLUB|プレリザーブ|プレイガイド|"
        r"先行受付|チケット受付|受付のお知らせ",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[!！・|｜\-–—_\[\]()（）『』「」]", "", text)
    return text.lower()


def event_days(event: dict) -> tuple[str, ...]:
    values: list[str] = []
    schedule = event.get("schedule")
    if isinstance(schedule, list):
        for item in schedule:
            if isinstance(item, dict) and item.get("date"):
                values.append(str(item["date"])[:10])
    dates = event.get("eventDates")
    if isinstance(dates, list):
        values.extend(str(value)[:10] for value in dates if value)
    if not values and event.get("eventDate"):
        values.append(str(event["eventDate"])[:10])
    return tuple(sorted(dict.fromkeys(values)))


def group_key(event: dict) -> tuple[str, tuple[str, ...]]:
    participants = tuple(sorted(str(x) for x in (event.get("participants") or []) if x))
    return normalize_text(event.get("group")), participants


def same_event_and_sale(a: dict, b: dict) -> bool:
    if group_key(a) != group_key(b):
        return False
    if sale_family(a) != sale_family(b):
        return False
    if event_days(a) != event_days(b) or not event_days(a):
        return False
    title_a, title_b = canonical_title(a), canonical_title(b)
    if not title_a or not title_b:
        return False
    return title_a == title_b or title_a in title_b or title_b in title_a


def priority(event: dict) -> int:
    source = source_kind(event)
    family = sale_family(event)
    if family == "online-benefit":
        return {"sukisuki": 500, "official": 350, "pia": 250}.get(source, 0)
    if family in {"fc", "upgrade"}:
        return {"official": 500, "pia": 100, "sukisuki": 50}.get(source, 0)
    return {"pia": 500, "official": 350, "sukisuki": 100}.get(source, 0)


def source_urls(event: dict) -> list[str]:
    values = []
    if event.get("url"):
        values.append(str(event["url"]))
    for url in event.get("urls") or []:
        if url and str(url) not in values:
            values.append(str(url))
    return values


def with_source_metadata(event: dict) -> dict:
    out = dict(event)
    source = source_kind(out)
    out["primarySource"] = source
    out["sourceCandidates"] = [source]
    return out


def merge_duplicate(items: list[dict]) -> dict:
    ranked = sorted(items, key=priority, reverse=True)
    winner = dict(ranked[0])
    all_urls: list[str] = []
    for item in ranked:
        for url in source_urls(item):
            if url not in all_urls:
                all_urls.append(url)
    if all_urls:
        winner["urls"] = all_urls
        winner["url"] = source_urls(ranked[0])[0] if source_urls(ranked[0]) else all_urls[0]
    winner["primarySource"] = source_kind(ranked[0])
    winner["sourceCandidates"] = sorted({source_kind(item) for item in ranked})
    return winner


def resolve(events: list[dict]) -> list[dict]:
    result: list[dict] = []
    used: set[int] = set()
    for index, event in enumerate(events):
        if index in used:
            continue
        bucket = [event]
        used.add(index)
        for other_index in range(index + 1, len(events)):
            if other_index in used:
                continue
            if same_event_and_sale(event, events[other_index]):
                bucket.append(events[other_index])
                used.add(other_index)
        result.append(merge_duplicate(bucket) if len(bucket) > 1 else with_source_metadata(event))
    return result


def resolve_payload(payload: dict) -> dict:
    out = dict(payload)
    events = [dict(x) for x in payload.get("events", []) if isinstance(x, dict)]
    out["events"] = resolve(events)
    out["source"] = "KAWAII LAB.各グループ公式公開情報 + チケットぴあ公開情報 + SUKISUKI公開オンライン特典会情報"
    return out


def main() -> int:
    if not DATA_PATH.exists():
        return 0
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    resolved = resolve_payload(payload)
    DATA_PATH.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Resolved source priority: {len(payload.get('events', []))} -> {len(resolved.get('events', []))} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
