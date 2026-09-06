#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

DATA_PATH = Path("data/live-events.json")


def text(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def clock(value: object) -> str:
    match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", text(value))
    if not match:
        return ""
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return ""
    return f"{hour:02d}:{minute:02d}"


def group_key(event: dict) -> str:
    return text(event.get("group")).casefold()


def venue_key(value: object) -> str:
    value = text(value).casefold()
    value = re.sub(r"^(?:北海道|東京都|京都府|大阪府|.{2,3}県)\s*", "", value)
    return re.sub(r"[\s　!！・|｜\-–—_\[\]()（）『』「」]", "", value)


def event_rows(event: dict) -> list[tuple[dict | None, str, str, str, str]]:
    """Return (row, day, venue, open, start) occurrences.

    `row is None` means the occurrence lives on the event itself. Schedule rows
    inherit missing venue/open/start metadata from the parent exactly like the UI.
    """
    schedule = event.get("schedule") if isinstance(event.get("schedule"), list) else []
    rows: list[tuple[dict | None, str, str, str, str]] = []
    for row in schedule:
        if not isinstance(row, dict):
            continue
        day = str(row.get("date") or "")[:10]
        venue = venue_key(row.get("venue") or event.get("venue"))
        open_time = clock(row.get("openTime") or event.get("openTime"))
        start_time = clock(row.get("startTime") or row.get("start") or event.get("startTime"))
        if day and venue:
            rows.append((row, day, venue, open_time, start_time))
    if rows:
        return rows

    day = str(event.get("eventDate") or "")[:10]
    venue = venue_key(event.get("venue"))
    if day and venue:
        rows.append((None, day, venue, clock(event.get("openTime")), clock(event.get("startTime"))))
    return rows


def _set_start(event: dict, row: dict | None, corrected: str) -> None:
    if row is None:
        event["startTime"] = corrected
        return
    row["startTime"] = corrected
    schedule = event.get("schedule") if isinstance(event.get("schedule"), list) else []
    if len(schedule) == 1:
        # Keep the one-performance parent summary consistent with its row.
        parent_open = clock(event.get("openTime"))
        parent_start = clock(event.get("startTime"))
        if not parent_start or (parent_open and parent_start == parent_open):
            event["startTime"] = corrected


def reconcile_payload(payload: dict) -> tuple[dict, dict]:
    """Repair a suspicious OPEN==START row only from unambiguous peer evidence.

    A real venue can host multiple same-day performances, so this never guesses.
    For one group/date/venue, a suspicious row is rewritten only when every
    non-suspicious peer agrees on exactly one different START time. This catches
    the official SCHEDULE parser failure where the label `OPEN/START` caused the
    first value (OPEN) to be copied into START, while preserving genuine matinee /
    evening pairs.
    """
    out = copy.deepcopy(payload)
    events = [event for event in out.get("events", []) if isinstance(event, dict)]
    buckets: dict[tuple[str, str, str], list[tuple[dict, dict | None, str, str]]] = defaultdict(list)

    for event in events:
        group = group_key(event)
        if not group:
            continue
        for row, day, venue, open_time, start_time in event_rows(event):
            buckets[(group, day, venue)].append((event, row, open_time, start_time))

    fixes: list[dict] = []
    for (group, day, venue), occurrences in buckets.items():
        credible_starts = {
            start
            for _event, _row, open_time, start in occurrences
            if start and (not open_time or start != open_time)
        }
        if len(credible_starts) != 1:
            continue
        corrected = next(iter(credible_starts))
        for event, row, open_time, start in occurrences:
            if not open_time or not start or start != open_time or corrected == start:
                continue
            previous = start
            _set_start(event, row, corrected)
            fixes.append({
                "eventId": event.get("id"),
                "group": event.get("group"),
                "date": day,
                "venueKey": venue,
                "openTime": open_time,
                "previousStartTime": previous,
                "correctedStartTime": corrected,
                "sourceType": event.get("sourceType"),
                "title": event.get("eventTitle") or event.get("title"),
            })

    report = {
        "fixedCount": len(fixes),
        "fixes": fixes,
    }
    out["physicalPerformanceTimeReconciliation"] = report
    return out, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile physically impossible duplicate performance times")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.data.read_text(encoding="utf-8"))
    fixed, report = reconcile_payload(payload)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.check:
        return 1 if report["fixedCount"] else 0
    if fixed != payload:
        args.data.write_text(json.dumps(fixed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
