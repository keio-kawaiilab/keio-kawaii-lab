#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DATA = Path("data/live-events.json")
SPECIAL_CATEGORIES = {"release-event", "large-benefit"}
PLACEHOLDER_VENUE_RE = re.compile(
    r"^(?:東京都\s*)?(?:都内)?(?:某所|会場未定|未定|調整中|詳細未定)$",
    re.I,
)


def text(value: object) -> str:
    return str(value or "").strip()


def is_placeholder_venue(value: object) -> bool:
    venue = text(value).replace("　", " ")
    if not venue:
        return True
    return bool(PLACEHOLDER_VENUE_RE.fullmatch(venue))


def merge_row(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key, value in extra.items():
        if out.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
            out[key] = value
    return out


def clean_schedule(rows: list[dict]) -> tuple[list[dict], int]:
    by_day: dict[str, list[dict]] = {}
    order: list[str] = []
    for raw in rows:
        if not isinstance(raw, dict) or not raw.get("date"):
            continue
        row = dict(raw)
        day = text(row.get("date"))[:10]
        row["date"] = day
        if day not in by_day:
            by_day[day] = []
            order.append(day)
        by_day[day].append(row)

    cleaned: list[dict] = []
    removed = 0
    for day in order:
        day_rows = by_day[day]
        specific = [row for row in day_rows if not is_placeholder_venue(row.get("venue"))]
        if specific:
            placeholders = [row for row in day_rows if is_placeholder_venue(row.get("venue"))]
            removed += len(placeholders)
            # Preserve useful time/detail fields from a placeholder row when the
            # now-specific official row omitted them.
            for placeholder in placeholders:
                if specific:
                    specific[0] = merge_row(specific[0], placeholder)
            day_rows = specific

        # Exact duplicate venue rows on the same day are one occurrence. Keep
        # the richest fields instead of creating another public performance.
        merged: list[dict] = []
        seen: dict[str, int] = {}
        for row in day_rows:
            venue_key = re.sub(r"[\s　]+", "", text(row.get("venue"))).casefold()
            marker = venue_key or "__placeholder__"
            if marker in seen:
                idx = seen[marker]
                merged[idx] = merge_row(merged[idx], row)
                removed += 1
            else:
                seen[marker] = len(merged)
                merged.append(row)
        cleaned.extend(merged)
    return cleaned, removed


def normalize_entity(event: dict) -> tuple[dict, int]:
    if event.get("eventCategory") not in SPECIAL_CATEGORIES:
        return event, 0
    schedule = event.get("schedule")
    if not isinstance(schedule, list):
        return event, 0

    cleaned, removed = clean_schedule(schedule)
    if not removed:
        return event, 0

    out = dict(event)
    out["schedule"] = cleaned
    dates = list(dict.fromkeys(text(row.get("date"))[:10] for row in cleaned if row.get("date")))
    venues = list(dict.fromkeys(text(row.get("venue")) for row in cleaned if text(row.get("venue"))))
    out["eventCount"] = len(cleaned)
    out["eventDates"] = dates
    if dates:
        out["eventDate"] = dates[0]
        out["eventEndDate"] = dates[-1]
    out["venues"] = venues
    if len(venues) == 1:
        out["venue"] = venues[0]
    elif venues:
        out["venue"] = f"複数会場（全{len(cleaned)}公演）"
    return out, removed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Drop obsolete same-day placeholder venues from canonical release/benefit events"
    )
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.data.read_text(encoding="utf-8"))
    events = []
    removed = 0
    for raw in payload.get("events", []):
        if not isinstance(raw, dict):
            continue
        event, count = normalize_entity(dict(raw))
        events.append(event)
        removed += count

    if args.check:
        print(json.dumps({"obsoleteSpecialOccurrences": removed}, ensure_ascii=False))
        return 1 if removed else 0

    out = dict(payload)
    out["events"] = events
    args.data.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"removedObsoleteSpecialOccurrences": removed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
