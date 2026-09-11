#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

# Official CANDY TUNE ticket summary / tour schedule (verified 2026-09-11):
# https://candytune.asobisystem.com/news/detail/43700
EXPECTED_DATES = {
    "2026-08-29",
    "2026-08-30",
    "2026-09-04",
    "2026-09-09",
    "2026-09-10",
    "2026-09-19",
    "2026-10-02",
    "2026-10-04",
    "2026-10-08",
    "2026-10-09",
    "2026-10-26",
    "2026-10-27",
    "2026-10-29",
    "2026-11-10",
    "2026-11-12",
    "2026-11-17",
    "2026-11-19",
    "2026-11-24",
    "2026-11-26",
    "2026-11-30",
    "2026-12-01",
    "2026-12-08",
    "2026-12-09",
}
DATE_RE = re.compile(r"^2026-\d{2}-\d{2}")
FALLBACK_RE = re.compile(
    r"\s*window\.KL_LIVE_FALLBACK\s*=\s*(\[.*\])\s*;\s*",
    re.DOTALL,
)


def _text(event: dict) -> str:
    return " ".join(
        str(event.get(key) or "")
        for key in ("id", "_sourceId", "title", "eventTitle", "displayTitle", "url")
    )


def is_target(event: dict) -> bool:
    if str(event.get("group") or "").strip().upper() != "CANDY TUNE":
        return False
    text = _text(event).upper()
    if "CANDY-TUNE-TOUR-2026-AUTUMN" in text:
        return True
    return "JAPAN TOUR 2026" in text and ("AUTUMN" in text or "CANDY CIRCUS" in text)


def event_dates(event: dict) -> set[str]:
    found: set[str] = set()

    value = event.get("eventDate")
    if value and DATE_RE.match(str(value)):
        found.add(str(value)[:10])

    values = event.get("eventDates")
    if isinstance(values, list):
        for value in values:
            if isinstance(value, dict):
                value = value.get("date")
            if value and DATE_RE.match(str(value)):
                found.add(str(value)[:10])

    schedule = event.get("schedule")
    if isinstance(schedule, list):
        for row in schedule:
            if not isinstance(row, dict):
                continue
            value = row.get("date")
            if value and DATE_RE.match(str(value)):
                found.add(str(value)[:10])

    return found


def validate_event_list(events: object, label: str) -> None:
    if not isinstance(events, list):
        raise SystemExit(f"CANDY TUNE guard: {label} has no event list")

    targets = [event for event in events if isinstance(event, dict) and is_target(event)]
    if not targets:
        raise SystemExit(f"CANDY TUNE guard: autumn 2026 tour disappeared from {label}")

    found: set[str] = set()
    for event in targets:
        found.update(event_dates(event))

    missing = sorted(EXPECTED_DATES - found)
    if missing:
        raise SystemExit(
            f"CANDY TUNE guard: refusing publication; {label} is missing official tour dates: "
            + ", ".join(missing)
        )

    print(f"CANDY TUNE {label} integrity OK: {len(EXPECTED_DATES)}/{len(EXPECTED_DATES)} dates")


def validate_data(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        events = payload
    elif isinstance(payload, dict) and isinstance(payload.get("publicEvents"), list):
        events = payload["publicEvents"]
    elif isinstance(payload, dict):
        events = payload.get("events", [])
    else:
        events = None
    validate_event_list(events, "canonical tour")


def validate_fallback(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    match = FALLBACK_RE.fullmatch(text)
    if not match:
        raise SystemExit(
            "CANDY TUNE guard: runtime fallback is not a valid window.KL_LIVE_FALLBACK array"
        )
    try:
        events = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"CANDY TUNE guard: runtime fallback JSON is invalid: {exc}") from exc
    validate_event_list(events, "runtime fallback")


class TourCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.current_depth: int | None = None
        self.current_date: str | None = None
        self.current_text: list[str] = []
        self.cards: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if self.current_depth is not None:
            self.depth += 1
            return
        if tag == "article" and attrs_dict.get("data-group") == "CANDY TUNE":
            event_id = attrs_dict.get("data-event-id") or ""
            match = re.search(r"performance-CANDY-TUNE-(2026-\d{2}-\d{2})", event_id)
            if match:
                self.depth = 0
                self.current_depth = 0
                self.current_date = match.group(1)
                self.current_text = []

    def handle_endtag(self, tag: str) -> None:
        if self.current_depth is None:
            return
        if self.depth > 0:
            self.depth -= 1
            return
        if tag == "article":
            self.cards.append((self.current_date or "", " ".join(self.current_text)))
            self.current_depth = None
            self.current_date = None
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_depth is not None:
            value = data.strip()
            if value:
                self.current_text.append(value)


def validate_html(path: Path, from_date: str) -> None:
    parser = TourCardParser()
    parser.feed(path.read_text(encoding="utf-8"))
    found = {
        day
        for day, text in parser.cards
        if "JAPAN TOUR 2026" in text.upper() and ("AUTUMN" in text.upper() or "CANDY CIRCUS" in text.upper())
    }
    required = {day for day in EXPECTED_DATES if day >= from_date}
    missing = sorted(required - found)
    if missing:
        raise SystemExit(
            "CANDY TUNE guard: generated schedule.html lost upcoming tour cards: "
            + ", ".join(missing)
        )
    print(f"CANDY TUNE public snapshot integrity OK: {len(required)}/{len(required)} upcoming dates from {from_date}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/live-events.json")
    parser.add_argument("--html")
    parser.add_argument("--fallback")
    parser.add_argument("--from-date", default=date.today().isoformat())
    args = parser.parse_args()

    validate_data(Path(args.data))
    if args.html:
        validate_html(Path(args.html), args.from_date)
    if args.fallback:
        validate_fallback(Path(args.fallback))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
