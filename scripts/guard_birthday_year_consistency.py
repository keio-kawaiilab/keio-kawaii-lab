#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

DATA_PATH = Path("data/live-events.json")
BIRTHDAY_RE = re.compile(
    r"生誕(?:祭|ライブ|イベント|公演)?|BIRTHDAY\s*(?:LIVE|EVENT|PARTY|FES|FESTIVAL)?|BD\s*(?:LIVE|EVENT)",
    re.I,
)
YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def event_title(event: dict) -> str:
    return str(event.get("eventTitle") or event.get("displayTitle") or event.get("title") or "")


def explicit_title_years(event: dict) -> set[int]:
    return {int(value) for value in YEAR_RE.findall(event_title(event))}


def parse_day(value: object) -> date | None:
    raw = str(value or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def event_days(event: dict) -> list[date]:
    values: list[object] = []
    if event.get("eventDate"):
        values.append(event.get("eventDate"))
    if isinstance(event.get("eventDates"), list):
        values.extend(event.get("eventDates") or [])
    if isinstance(event.get("schedule"), list):
        values.extend(
            row.get("date")
            for row in event.get("schedule") or []
            if isinstance(row, dict) and row.get("date")
        )
    parsed = [day for day in (parse_day(value) for value in values) if day is not None]
    return list(dict.fromkeys(parsed))


def birthday_year_problem(event: dict) -> str | None:
    title = event_title(event)
    if not BIRTHDAY_RE.search(title):
        return None

    days = event_days(event)
    title_years = explicit_title_years(event)

    # A year written into a birthday-event name identifies that physical event.
    # It must agree with the actual performance date. Name similarity can never
    # override this rule (e.g. "生誕祭2025" on a 2026 performance date).
    if title_years and days:
        performance_years = {day.year for day in days}
        if title_years.isdisjoint(performance_years):
            return "explicit-title-year-does-not-match-performance-year"

    # A ticket window cannot begin after the physical event has already ended.
    # This catches a stale 2025 birthday row being enriched with a 2026 FC sale
    # even when its old 2025 eventDate was preserved.
    if days:
        last_day = max(days)
        for field in ("applyStart", "applyEnd"):
            application_day = parse_day(event.get(field))
            if application_day and application_day > last_day:
                return f"{field}-is-after-performance-date"

    return None


def filter_payload(payload: dict) -> tuple[dict, dict]:
    kept: list[dict] = []
    removed: list[dict] = []

    for raw in payload.get("events", []):
        if not isinstance(raw, dict):
            continue
        event = dict(raw)
        reason = birthday_year_problem(event)
        if reason:
            removed.append({
                "id": event.get("id"),
                "group": event.get("group"),
                "title": event_title(event),
                "eventDate": event.get("eventDate"),
                "applyStart": event.get("applyStart"),
                "applyEnd": event.get("applyEnd"),
                "reason": reason,
            })
            continue
        kept.append(event)

    out = dict(payload)
    out["events"] = kept
    report = {
        "removedCount": len(removed),
        "removed": removed,
    }
    return out, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Reject impossible cross-year birthday-event rows")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.data.read_text(encoding="utf-8"))
    cleaned, report = filter_payload(payload)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.check:
        return 1 if report["removedCount"] else 0

    if cleaned != payload:
        args.data.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
