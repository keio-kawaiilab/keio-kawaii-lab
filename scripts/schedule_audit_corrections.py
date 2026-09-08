#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ohanami_two_show_correction import apply_ohanami_two_show_correction


DATA_PATH = Path("data/live-events.json")
CHRISTMAS_DAY1_AUDIT_ID = "P0-christmas-session-2026-day1-venue"
CHRISTMAS_TOKEN = "KAWAII LAB. Christmas SESSION 2026"
CHRISTMAS_DAY1 = "2026-12-12"
CHRISTMAS_DAY1_OPEN = "15:00"
CHRISTMAS_DAY1_START = "17:00"


def _text(event: dict[str, Any]) -> str:
    return " ".join(
        str(event.get(key) or "")
        for key in ("displayTitle", "eventTitle", "title")
    )


def _is_christmas(event: dict[str, Any]) -> bool:
    return CHRISTMAS_TOKEN.lower() in _text(event).lower()


def _day(value: Any) -> str:
    return str(value or "")[:10]


def _time(value: Any) -> str:
    return str(value or "").strip()


def _day1_time_compatible(open_time: Any, start_time: Any) -> bool:
    """Reject known conflicting times while allowing a missing field to be filled safely."""
    open_text = _time(open_time)
    start_text = _time(start_time)
    if open_text and open_text != CHRISTMAS_DAY1_OPEN:
        return False
    if start_text and start_text != CHRISTMAS_DAY1_START:
        return False
    return True


def _authoritative_day1_fact(events: list[dict[str, Any]]) -> tuple[str | None, str | None, list[str]]:
    candidates: list[tuple[str, str | None]] = []
    for event in events:
        if not isinstance(event, dict) or not _is_christmas(event):
            continue
        if event.get("group") != "KAWAII LAB.合同":
            continue
        if event.get("sourceType") != "official-schedule":
            continue
        if _day(event.get("eventDate")) != CHRISTMAS_DAY1:
            continue
        if not _day1_time_compatible(event.get("openTime"), event.get("startTime")):
            continue
        venue = str(event.get("venue") or "").strip()
        if not venue:
            continue
        source = str(event.get("officialScheduleUrl") or event.get("url") or "").strip() or None
        candidates.append((venue, source))

    venues = sorted({venue for venue, _ in candidates})
    if len(venues) != 1:
        return None, None, venues
    venue = venues[0]
    sources = [source for candidate_venue, source in candidates if candidate_venue == venue and source]
    return venue, (sources[0] if sources else None), venues


def _append_audit_id(event: dict[str, Any], audit_id: str) -> None:
    audit_ids = [str(value) for value in event.get("auditCorrectionIds") or [] if value]
    if audit_id not in audit_ids:
        audit_ids.append(audit_id)
    event["auditCorrectionIds"] = audit_ids


def apply_christmas_day1_venue_correction(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Fill only missing Christmas SESSION Day1 venue values from the canonical
    KAWAII LAB. official-schedule row. Conflicting non-empty venues are never
    overwritten; they are reported instead so the release can be investigated.
    """
    corrected = deepcopy(payload)
    events = [event for event in corrected.get("events") or [] if isinstance(event, dict)]
    venue, source_url, authoritative_venues = _authoritative_day1_fact(events)
    report: dict[str, Any] = {
        "auditCorrectionId": CHRISTMAS_DAY1_AUDIT_ID,
        "authoritativeVenue": venue,
        "sourceUrl": source_url,
        "authoritativeVenueCandidates": authoritative_venues,
        "matchedEvents": 0,
        "topLevelFilled": 0,
        "scheduleRowsFilled": 0,
        "conflicts": [],
    }
    if not venue:
        return corrected, report

    for event in events:
        if not _is_christmas(event):
            continue

        changed = False
        event_day = _day(event.get("eventDate"))
        if event_day == CHRISTMAS_DAY1 and _day1_time_compatible(event.get("openTime"), event.get("startTime")):
            report["matchedEvents"] += 1
            current = str(event.get("venue") or "").strip()
            if not current:
                event["venue"] = venue
                report["topLevelFilled"] += 1
                changed = True
            elif current != venue:
                report["conflicts"].append(
                    {
                        "eventId": event.get("id"),
                        "field": "venue",
                        "current": current,
                        "authoritative": venue,
                    }
                )

        schedule = event.get("schedule")
        if isinstance(schedule, list):
            for row in schedule:
                if not isinstance(row, dict) or _day(row.get("date")) != CHRISTMAS_DAY1:
                    continue
                if not _day1_time_compatible(row.get("openTime"), row.get("startTime")):
                    continue
                current = str(row.get("venue") or "").strip()
                if not current:
                    row["venue"] = venue
                    report["scheduleRowsFilled"] += 1
                    changed = True
                elif current != venue:
                    report["conflicts"].append(
                        {
                            "eventId": event.get("id"),
                            "field": "schedule[2026-12-12].venue",
                            "current": current,
                            "authoritative": venue,
                        }
                    )

        if changed:
            _append_audit_id(event, CHRISTMAS_DAY1_AUDIT_ID)
            if source_url:
                sources = [str(value) for value in event.get("performanceFactSources") or [] if value]
                if source_url not in sources:
                    sources.append(source_url)
                event["performanceFactSources"] = sources

    return corrected, report


def apply_all(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    corrected, christmas_report = apply_christmas_day1_venue_correction(payload)
    corrected, ohanami_report = apply_ohanami_two_show_correction(corrected)
    return corrected, {
        "christmasSessionDay1Venue": christmas_report,
        "sweetSteadyOhanamiTwoShows": ohanami_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply source-backed schedule audit corrections before public release.")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--check", action="store_true", help="Verify the file is already corrected without writing it.")
    parser.add_argument("--fail-on-conflict", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.data.read_text(encoding="utf-8"))
    corrected, report = apply_all(payload)
    conflicts = [
        item
        for section in report.values()
        if isinstance(section, dict)
        for item in section.get("conflicts") or []
    ]
    if args.fail_on_conflict and conflicts:
        raise SystemExit("Schedule audit correction conflict: " + json.dumps(conflicts, ensure_ascii=False))
    if args.check and corrected != payload:
        raise SystemExit("Schedule audit corrections are required before release: " + json.dumps(report, ensure_ascii=False))
    if not args.check and corrected != payload:
        args.data.write_text(json.dumps(corrected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
