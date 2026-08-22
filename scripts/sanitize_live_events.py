#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

DATA_PATH = Path("data/live-events.json")
TITLE_PREFIX_RE = re.compile(r"^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+")
TITLE_DATE_RE = re.compile(r"(?:(?:20\d{2})年\s*)?\d{1,2}月\s*\d{1,2}日(?:\s*[（(][^）)]*[）)])?")
GROUP_ORDER = {
    "FRUITS ZIPPER": 0,
    "CANDY TUNE": 1,
    "SWEET STEADY": 2,
    "CUTIE STREET": 3,
    "MORE STAR": 4,
}


def clean_title(value: str) -> str:
    return TITLE_PREFIX_RE.sub("", str(value or "")).strip()


def title_merge_key(value: str) -> str:
    title = clean_title(value)
    title = TITLE_DATE_RE.sub("", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip(" -–—｜|　")


def stable_id(*parts: object) -> str:
    raw = "\x1f".join(str(x or "") for x in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def distinct(values):
    result = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def parse_day(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def base_cleanup(payload: dict) -> list[dict]:
    events = []
    seen = set()
    for original in payload.get("events", []):
        if not isinstance(original, dict):
            continue
        event = dict(original)
        event["title"] = clean_title(event.get("title", ""))

        event_date = str(event.get("eventDate") or "")[:10]
        result_date = str(event.get("resultDate") or "")[:10]
        # 当落発表日時を公演日時と誤認したデータは表示しない。
        if event_date and result_date and event_date == result_date:
            continue

        key = (
            event.get("group"), event.get("url"), event_date,
            event.get("ticketType"), event.get("applyStart"),
        )
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    return events


def merge_joint_events(events: list[dict]) -> list[dict]:
    """同一公演を複数グループの公式記事が告知している場合、1件にまとめる。"""
    buckets: dict[tuple, list[dict]] = {}
    for event in events:
        key = (
            title_merge_key(event.get("title", "")),
            str(event.get("eventDate") or "")[:10],
            event.get("ticketType"),
            event.get("applyStart"),
            event.get("applyEnd"),
            event.get("resultDate"),
            event.get("paymentEnd"),
            re.sub(r"\s+", "", str(event.get("venue") or "")),
        )
        buckets.setdefault(key, []).append(event)

    merged: list[dict] = []
    for key, items in buckets.items():
        groups = distinct(item.get("group") for item in items if item.get("group") in GROUP_ORDER)
        if len(groups) < 2:
            merged.extend(items)
            continue

        groups.sort(key=lambda g: GROUP_ORDER.get(g, 99))
        first = dict(items[0])
        urls = distinct(
            url
            for item in items
            for url in (item.get("urls") or ([item.get("url")] if item.get("url") else []))
        )
        first["id"] = stable_id("joint", *key, *groups)
        first["group"] = "KAWAII LAB.合同"
        first["participants"] = groups
        first["urls"] = urls
        first["url"] = urls[0] if urls else None
        first["sourceType"] = "derived"
        published = [x.get("sourcePublishedAt") for x in items if x.get("sourcePublishedAt")]
        if published:
            first["sourcePublishedAt"] = max(published)
        merged.append(first)
    return merged


def merge_consecutive_days(events: list[dict]) -> list[dict]:
    """同会場・同受付条件で連日開催される公演は、日付範囲1件にまとめる。"""
    buckets: dict[tuple, list[dict]] = {}
    for event in events:
        participants = tuple(event.get("participants") or [])
        key = (
            event.get("group"),
            participants,
            title_merge_key(event.get("title", "")),
            event.get("ticketType"),
            event.get("applyStart"),
            event.get("applyEnd"),
            event.get("resultDate"),
            event.get("paymentEnd"),
            re.sub(r"\s+", "", str(event.get("venue") or "")),
        )
        buckets.setdefault(key, []).append(event)

    result: list[dict] = []
    for key, items in buckets.items():
        dated = [(parse_day(item.get("eventDate")), item) for item in items]
        dated = [(d, item) for d, item in dated if d]
        undated = [item for item in items if not parse_day(item.get("eventDate"))]
        dated.sort(key=lambda pair: pair[0])

        run: list[tuple] = []

        def flush():
            nonlocal run
            if not run:
                return
            if len(run) == 1:
                result.append(run[0][1])
                run = []
                return

            merged = dict(run[0][1])
            dates = [pair[0] for pair in run]
            all_urls = distinct(
                url
                for _, item in run
                for url in (item.get("urls") or ([item.get("url")] if item.get("url") else []))
            )
            merged["eventDate"] = dates[0].isoformat()
            merged["eventEndDate"] = dates[-1].isoformat()
            merged["eventDates"] = [d.isoformat() for d in dates]
            merged["urls"] = all_urls
            merged["url"] = all_urls[0] if all_urls else merged.get("url")
            merged["id"] = stable_id("range", *key, dates[0], dates[-1])
            merged["sourceType"] = "derived"
            result.append(merged)
            run = []

        for day, item in dated:
            if not run:
                run = [(day, item)]
                continue
            if day == run[-1][0] + timedelta(days=1):
                run.append((day, item))
            else:
                flush()
                run = [(day, item)]
        flush()
        result.extend(undated)

    return result


def sanitize_payload(payload: dict) -> dict:
    cleaned = dict(payload)
    events = base_cleanup(payload)
    events = merge_joint_events(events)
    events = merge_consecutive_days(events)
    events.sort(key=lambda e: (
        str(e.get("applyEnd") or "9999"),
        str(e.get("eventDate") or "9999"),
        str(e.get("group") or ""),
    ))
    cleaned["events"] = events
    return cleaned


def main() -> int:
    if not DATA_PATH.exists():
        return 0
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    cleaned = sanitize_payload(payload)
    DATA_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Sanitized live calendar data: {len(payload.get('events', []))} -> {len(cleaned.get('events', []))} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
