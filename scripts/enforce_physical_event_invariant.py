#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
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
    identity when both sources know it. An empty start time is therefore a
    wildcard, not proof that an official-X shell is a separate event.
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
    """Match the same physical occurrence without inventing a second event.

    If both start times are known they must agree. If one source has no start
    time, equal group/date/venue is enough: the incomplete row is treated as a
    shell for the more detailed row. Two explicitly different times remain
    separate events.
    """
    return (
        left[0] == right[0]
        and left[1] == right[1]
        and left[3] == right[3]
        and (left[2] == right[2] or not left[2] or not right[2])
    )


def events_physically_match(left: dict, right: dict) -> bool:
    left_occurrences = physical_occurrences(left)
    right_occurrences = physical_occurrences(right)
    for a in left_occurrences:
        for b in right_occurrences:
            if not occurrences_match(a, b):
                continue
            # Exact times are physically decisive even if source category labels
            # disagree. When one time is missing, be conservative and only use
            # the wildcard merge for the same special-event category.
            if a[2] and b[2]:
                return True
            if category(left) == category(right):
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


def duplicate_physical_occurrences(payload: dict) -> list[dict]:
    special = [
        event for event in payload.get("events", [])
        if isinstance(event, dict) and category(event) in SPECIAL_CATEGORIES
    ]
    duplicates: list[dict] = []
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
    # First apply semantic normalization (series/title/product based). Then apply
    # the stronger physical-world invariant so title/source differences can never
    # produce two cards for one real occurrence. A source with missing time is a
    # shell for a same-category row at the same group/date/venue, not a new event.
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
    for component in components:
        if len(component) == 1:
            merged.append(component[0])
            continue

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
        "collisionCount": len(collisions),
        "collisions": collisions,
        "remainingDuplicateCount": len(remaining),
        "remainingDuplicates": remaining,
    }
    out["physicalEventInvariant"] = report
    return out, report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enforce one physical special event per group/date/venue/time, treating missing time as incomplete metadata"
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
