#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
from collections import defaultdict
from pathlib import Path

from dedupe_official_x_series import category, schedule_rows, text
from normalize_special_event_entities import (
    SPECIAL_CATEGORIES,
    make_entity,
    normalize_payload,
    venue_key,
)

DATA_PATH = Path("data/live-events.json")


def normalize_time(value: object) -> str:
    match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", text(value))
    if not match:
        return ""
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return ""
    return f"{hour:02d}:{minute:02d}"


def physical_occurrences(event: dict) -> set[tuple[str, str, str, str]]:
    """Return real-world occurrence identities, including incomplete times.

    Group/date/venue are the stable physical identity. Start time refines that
    identity when both sources know it. An empty start time is incomplete
    metadata, not evidence of a second physical event.
    """
    group = text(event.get("group")).casefold()
    if not group:
        return set()

    rows = schedule_rows(event)
    result: set[tuple[str, str, str, str]] = set()
    for row in rows:
        day = str(row.get("date") or "")[:10]
        venue = venue_key(row.get("venue") or event.get("venue"))
        start = normalize_time(row.get("startTime") or row.get("start"))
        if not start and len(rows) == 1:
            start = normalize_time(event.get("startTime"))
        if day and venue:
            result.add((group, day, start, venue))

    if result or rows:
        return result

    day = str(event.get("eventDate") or "")[:10]
    venue = venue_key(event.get("venue"))
    start = normalize_time(event.get("startTime"))
    if day and venue:
        result.add((group, day, start, venue))
    return result


def physical_occurrence_keys(event: dict) -> set[tuple[str, str, str, str]]:
    """Return complete occurrence identities for diagnostics/back-compat."""
    return {item for item in physical_occurrences(event) if item[2]}


def occurrences_match(
    left: tuple[str, str, str, str],
    right: tuple[str, str, str, str],
) -> bool:
    return (
        left[0] == right[0]
        and left[1] == right[1]
        and left[3] == right[3]
        and (left[2] == right[2] or not left[2] or not right[2])
    )


def _wildcard_match_is_unambiguous(left: dict, right: dict, base: tuple[str, str, str]) -> bool:
    group, day, venue = base
    known_times = {
        item[2]
        for event in (left, right)
        for item in physical_occurrences(event)
        if item[0] == group and item[1] == day and item[3] == venue and item[2]
    }
    return len(known_times) <= 1


def events_physically_match(left: dict, right: dict) -> bool:
    left_occurrences = physical_occurrences(left)
    right_occurrences = physical_occurrences(right)
    for a in left_occurrences:
        for b in right_occurrences:
            if not occurrences_match(a, b):
                continue
            if a[2] and b[2]:
                return True
            if category(left) != category(right):
                continue
            if _wildcard_match_is_unambiguous(left, right, (a[0], a[1], a[3])):
                return True
    return False


def _components(items: list[dict]) -> list[list[dict]]:
    remaining = [copy.deepcopy(item) for item in items]
    output: list[list[dict]] = []
    while remaining:
        component = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            keep = []
            for item in remaining:
                if any(events_physically_match(existing, item) for existing in component):
                    component.append(item)
                    changed = True
                else:
                    keep.append(item)
            remaining = keep
        output.append(component)
    return output


def _row_identity(row: dict, event: dict) -> tuple[str, str, str]:
    day = str(row.get("date") or event.get("eventDate") or "")[:10]
    venue = venue_key(row.get("venue") or event.get("venue"))
    start = normalize_time(row.get("startTime") or row.get("start"))
    return day, venue, start


def _row_richness(row: dict) -> tuple[int, int]:
    start = int(bool(normalize_time(row.get("startTime") or row.get("start"))))
    filled = sum(value not in (None, "", [], {}) for value in row.values())
    return start, filled


def _merge_schedule_row_group(rows: list[dict]) -> dict:
    base = copy.deepcopy(max(rows, key=_row_richness))
    for row in rows:
        for key, value in row.items():
            if base.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
                base[key] = copy.deepcopy(value)
    return base


def collapse_internal_schedule(event: dict) -> tuple[dict, int]:
    """Collapse duplicate rows inside one canonical event.

    For one group/date/venue, an untimed row can safely collapse into a timed
    row only when there is at most one distinct known start time. If two or more
    explicit times exist, the untimed row is ambiguous and is left untouched.
    """
    out = copy.deepcopy(event)
    raw_schedule = out.get("schedule") if isinstance(out.get("schedule"), list) else []
    rows = [copy.deepcopy(row) for row in raw_schedule if isinstance(row, dict)]
    if not rows:
        return out, 0

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    passthrough: list[dict] = []
    order: list[tuple[str, str]] = []
    for row in rows:
        day, venue, _ = _row_identity(row, out)
        if not day or not venue:
            passthrough.append(row)
            continue
        key = (day, venue)
        if key not in grouped:
            order.append(key)
        grouped[key].append(row)

    collapsed: list[dict] = []
    collapsed_count = 0
    for key in order:
        group_rows = grouped[key]
        known_times = {
            start for row in group_rows
            for _, _, start in [_row_identity(row, out)]
            if start
        }
        if len(known_times) <= 1:
            collapsed.append(_merge_schedule_row_group(group_rows))
            collapsed_count += max(0, len(group_rows) - 1)
            continue

        by_time: dict[str, list[dict]] = defaultdict(list)
        time_order: list[str] = []
        for row in group_rows:
            _, _, start = _row_identity(row, out)
            bucket = start or "__unknown__"
            if bucket not in by_time:
                time_order.append(bucket)
            by_time[bucket].append(row)
        for bucket in time_order:
            bucket_rows = by_time[bucket]
            collapsed.append(_merge_schedule_row_group(bucket_rows))
            collapsed_count += max(0, len(bucket_rows) - 1)

    collapsed.extend(passthrough)
    collapsed.sort(key=lambda row: (
        str(row.get("date") or "9999-12-31"),
        normalize_time(row.get("startTime") or row.get("start")) or "99:99",
        venue_key(row.get("venue")),
    ))
    out["schedule"] = collapsed
    out["eventCount"] = len(collapsed)

    dates = list(dict.fromkeys(str(row.get("date") or "")[:10] for row in collapsed if row.get("date")))
    if dates:
        out["eventDate"] = dates[0]
        out["eventDates"] = dates
        out["eventEndDate"] = dates[-1]

    venue_displays: dict[str, str] = {}
    for row in collapsed:
        display = text(row.get("venue"))
        key = venue_key(display)
        if key and display:
            current = venue_displays.get(key)
            if not current or len(display) > len(current):
                venue_displays[key] = display
    if venue_displays:
        venues = list(venue_displays.values())
        out["venues"] = venues
        out["venue"] = venues[0] if len(venues) == 1 else f"複数会場（全{len(collapsed)}公演）"

    if len(collapsed) == 1:
        start = normalize_time(collapsed[0].get("startTime") or collapsed[0].get("start"))
        if start:
            out["startTime"] = start
    return out, collapsed_count


def internal_schedule_duplicates(event: dict) -> list[dict]:
    rows = event.get("schedule") if isinstance(event.get("schedule"), list) else []
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        day, venue, _ = _row_identity(row, event)
        if day and venue:
            grouped[(day, venue)].append(row)

    duplicates: list[dict] = []
    for (day, venue), group_rows in grouped.items():
        known_times = {
            start for row in group_rows
            for _, _, start in [_row_identity(row, event)]
            if start
        }
        if len(known_times) <= 1 and len(group_rows) > 1:
            duplicates.append({
                "kind": "internal-schedule",
                "group": event.get("group"),
                "date": day,
                "startTime": next(iter(known_times), None),
                "venueKey": venue,
                "eventId": event.get("id"),
                "eventTitle": event.get("displayTitle") or event.get("eventTitle") or event.get("title"),
                "rowCount": len(group_rows),
                "incompleteTimeMatch": any(not _row_identity(row, event)[2] for row in group_rows),
            })
            continue

        by_time: dict[str, int] = defaultdict(int)
        for row in group_rows:
            _, _, start = _row_identity(row, event)
            if start:
                by_time[start] += 1
        for start, count in by_time.items():
            if count > 1:
                duplicates.append({
                    "kind": "internal-schedule",
                    "group": event.get("group"),
                    "date": day,
                    "startTime": start,
                    "venueKey": venue,
                    "eventId": event.get("id"),
                    "eventTitle": event.get("displayTitle") or event.get("eventTitle") or event.get("title"),
                    "rowCount": count,
                    "incompleteTimeMatch": False,
                })
    return duplicates


def duplicate_physical_occurrences(payload: dict) -> list[dict]:
    special = [
        event for event in payload.get("events", [])
        if isinstance(event, dict) and category(event) in SPECIAL_CATEGORIES
    ]
    duplicates: list[dict] = []
    for event in special:
        duplicates.extend(internal_schedule_duplicates(event))

    for index, event in enumerate(special):
        for previous in special[:index]:
            if not events_physically_match(previous, event):
                continue
            matches = []
            for left in physical_occurrences(previous):
                for right in physical_occurrences(event):
                    if occurrences_match(left, right):
                        matches.append((left, right))
            if not matches:
                continue
            left, right = matches[0]
            resolved_time = left[2] or right[2]
            duplicates.append({
                "kind": "separate-events",
                "group": event.get("group"),
                "date": left[1],
                "startTime": resolved_time or None,
                "venueKey": left[3],
                "firstId": previous.get("id"),
                "firstTitle": previous.get("displayTitle") or previous.get("eventTitle") or previous.get("title"),
                "secondId": event.get("id"),
                "secondTitle": event.get("displayTitle") or event.get("eventTitle") or event.get("title"),
                "incompleteTimeMatch": not left[2] or not right[2],
            })
    return duplicates


def enforce_payload(payload: dict) -> tuple[dict, dict]:
    normalized, semantic_report = normalize_payload(payload)
    ordinary: list[dict] = []
    special: list[dict] = []
    for raw in normalized.get("events", []):
        if not isinstance(raw, dict):
            continue
        event = copy.deepcopy(raw)
        if category(event) in SPECIAL_CATEGORIES:
            special.append(event)
        else:
            ordinary.append(event)

    components = _components(special)
    merged: list[dict] = []
    collisions: list[dict] = []
    internal_rows_collapsed = 0
    for component in components:
        if len(component) == 1:
            entity = component[0]
        else:
            occurrences = sorted(set().union(*(physical_occurrences(item) for item in component)))
            categories = sorted({category(item) for item in component if category(item)})
            collisions.append({
                "sourceIds": [item.get("id") for item in component],
                "titles": [item.get("displayTitle") or item.get("eventTitle") or item.get("title") for item in component],
                "physicalOccurrences": [
                    {"group": key[0], "date": key[1], "startTime": key[2] or None, "venueKey": key[3]}
                    for key in occurrences
                ],
                "sourceCategories": categories,
                "containsIncompleteTime": any(not key[2] for key in occurrences),
            })
            entity = make_entity(component)
            if len(categories) > 1:
                entity["sourceEventCategories"] = categories
            entity["physicalInvariantMerged"] = True

        entity, collapsed_inside = collapse_internal_schedule(entity)
        internal_rows_collapsed += collapsed_inside
        merged.append(entity)

    events = ordinary + merged
    events.sort(key=lambda event: (
        str(event.get("eventDate") or "9999-12-31"),
        str(event.get("group") or ""),
        str(event.get("eventCategory") or ""),
        str(event.get("id") or ""),
    ))

    out = dict(normalized)
    out["events"] = events
    remaining = duplicate_physical_occurrences(out)
    report = {
        "semanticNormalization": semantic_report,
        "specialEventsBeforePhysicalMerge": len(special),
        "specialEventsAfterPhysicalMerge": len(merged),
        "physicalRowsCollapsed": len(special) - len(merged),
        "internalScheduleRowsCollapsed": internal_rows_collapsed,
        "collisionCount": len(collisions),
        "collisions": collisions,
        "remainingDuplicateCount": len(remaining),
        "remainingDuplicates": remaining,
    }
    out["physicalEventInvariant"] = report
    return out, report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enforce one physical special event and one schedule row per real occurrence"
    )
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.data.read_text(encoding="utf-8"))
    if args.check:
        duplicates = duplicate_physical_occurrences(payload)
        print(json.dumps({
            "status": "ok" if not duplicates else "blocked",
            "duplicateCount": len(duplicates),
            "duplicates": duplicates,
        }, ensure_ascii=False, indent=2))
        return 1 if duplicates else 0

    enforced, report = enforce_payload(payload)
    args.data.write_text(json.dumps(enforced, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["remainingDuplicateCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
