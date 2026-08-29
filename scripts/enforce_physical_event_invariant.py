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


def physical_occurrence_keys(event: dict) -> set[tuple[str, str, str, str]]:
    """Return complete real-world occurrence identities.

    A group cannot perform two different physical events at the same date/time
    and venue. Source URL, ticket vendor, title wording and sale method are not
    part of this identity; those belong to the event's metadata/offers.
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
        if day and start and venue:
            result.add((group, day, start, venue))

    if result or rows:
        return result

    day = str(event.get("eventDate") or "")[:10]
    venue = venue_key(event.get("venue"))
    start = normalize_time(event.get("startTime"))
    if day and start and venue:
        result.add((group, day, start, venue))
    return result


def _components(items: list[dict]) -> list[list[dict]]:
    remaining = [copy.deepcopy(item) for item in items]
    output: list[list[dict]] = []
    while remaining:
        component = [remaining.pop(0)]
        known = set().union(*(physical_occurrence_keys(item) for item in component))
        changed = True
        while changed:
            changed = False
            keep = []
            for item in remaining:
                keys = physical_occurrence_keys(item)
                if known.intersection(keys):
                    component.append(item)
                    known.update(keys)
                    changed = True
                else:
                    keep.append(item)
            remaining = keep
        output.append(component)
    return output


def duplicate_physical_occurrences(payload: dict) -> list[dict]:
    seen: dict[tuple[str, str, str, str], dict] = {}
    duplicates: list[dict] = []
    for event in payload.get("events", []):
        if not isinstance(event, dict) or category(event) not in SPECIAL_CATEGORIES:
            continue
        for key in physical_occurrence_keys(event):
            previous = seen.get(key)
            if previous is None:
                seen[key] = event
                continue
            duplicates.append({
                "group": event.get("group"),
                "date": key[1],
                "startTime": key[2],
                "venueKey": key[3],
                "firstId": previous.get("id"),
                "firstTitle": previous.get("displayTitle") or previous.get("eventTitle") or previous.get("title"),
                "secondId": event.get("id"),
                "secondTitle": event.get("displayTitle") or event.get("eventTitle") or event.get("title"),
            })
    return duplicates


def enforce_payload(payload: dict) -> tuple[dict, dict]:
    # First apply semantic normalization (series/title/product based). Then apply
    # the stronger physical-world invariant so title/source differences can never
    # produce two cards for one impossible simultaneous occurrence.
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

        keys = sorted(set().union(*(physical_occurrence_keys(item) for item in component)))
        categories = sorted({category(item) for item in component if category(item)})
        collisions.append({
            "sourceIds": [item.get("id") for item in component],
            "titles": [item.get("displayTitle") or item.get("eventTitle") or item.get("title") for item in component],
            "physicalOccurrences": [
                {"group": key[0], "date": key[1], "startTime": key[2], "venueKey": key[3]}
                for key in keys
            ],
            "sourceCategories": categories,
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
        description="Enforce that one group cannot have two physical special events at the same date/time/venue"
    )
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.data.read_text(encoding="utf-8"))
    enforced, report = enforce_payload(payload)
    if not args.check:
        args.data.write_text(json.dumps(enforced, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["remainingDuplicateCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
