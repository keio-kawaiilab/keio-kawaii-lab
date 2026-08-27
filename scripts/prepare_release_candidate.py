#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from audit_schedule_release import (
    JST,
    clock_minutes,
    event_days,
    goods_key,
    is_ticket_listing,
    lot_key,
    parse_day,
    parse_dt,
    playguide_provider,
    urls,
)

DATA_PATH = Path("data/live-events.json")
PART_FIELDS = ("part", "content", "start", "end", "receptionStart", "receptionEnd")


def text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def richness(event: dict) -> tuple[int, int, int, int]:
    source = str(event.get("sourceType") or event.get("primarySource") or "").lower()
    source_score = {
        "official-special": 90,
        "official-schedule": 80,
        "official-social": 75,
        "official": 70,
        "pia": 60,
        "eplus": 60,
        "lawson": 60,
        "derived": 20,
    }.get(source, 40)
    filled = sum(1 for value in event.values() if value not in (None, "", [], {}))
    parts = len(event.get("parts") or []) if isinstance(event.get("parts"), list) else 0
    source_urls = len(urls(event))
    return source_score, filled, parts, source_urls


def dedupe_ids(events: list[dict]) -> tuple[list[dict], int]:
    result: list[dict] = []
    positions: dict[str, int] = {}
    removed = 0
    for event in events:
        event_id = text(event.get("id"))
        if not event_id:
            result.append(event)
            continue
        if event_id not in positions:
            positions[event_id] = len(result)
            result.append(event)
            continue
        removed += 1
        index = positions[event_id]
        if richness(event) > richness(result[index]):
            result[index] = event
    return result, removed


def valid_part(row: object) -> bool:
    if not isinstance(row, dict) or any(not text(row.get(field)) for field in PART_FIELDS):
        return False
    start, end, reception_start, reception_end = (
        clock_minutes(row.get(field)) for field in ("start", "end", "receptionStart", "receptionEnd")
    )
    if any(value is None for value in (start, end, reception_start, reception_end)):
        return False
    return bool(start < end and reception_start <= reception_end <= end)


def normalize_special(event: dict) -> tuple[dict, bool]:
    event = dict(event)
    category = str(event.get("eventCategory") or "")
    if category not in {"large-benefit", "release-event"}:
        return event, False

    changed = False
    official_urls = [value for value in urls(event) if "asobisystem.com" in value]
    has_schedule_evidence = bool(
        event.get("officialScheduleUrl")
        or any("/live_information/detail/" in value for value in official_urls)
    )
    no_window = not (event.get("applyStart") or event.get("applyEnd"))
    no_reception = event.get("applicationStatus") == "none" or str(event.get("ticketType") or "") == "現在受付なし"

    # A future special event can legitimately be listed on the official schedule before its
    # purchase/reception details are announced. Treat that as schedule-only rather than as a
    # malformed full-detail ticket row.
    if official_urls and has_schedule_evidence and no_window and no_reception:
        event["specialDetailsStatus"] = "awaiting-details"
        event["applicationDisplayMode"] = "schedule-only"
        event["applicationStatus"] = "none"
        if str(event.get("sourceType") or "") not in {"official-schedule", "official-special", "official-social"}:
            event["sourceType"] = "official-schedule"
        event["primarySource"] = "official"
        changed = True

    if category == "large-benefit":
        raw_parts = event.get("parts") if isinstance(event.get("parts"), list) else []
        good_parts = [dict(row) for row in raw_parts if valid_part(row)]
        if len(good_parts) != len(raw_parts) or not good_parts:
            event["parts"] = good_parts
            # Keep the verified event/window, but do not claim that its per-part timetable is
            # complete. The release audit will still validate source, venue, product and window.
            event["specialDetailsStatus"] = "awaiting-details"
            event["partsStatus"] = "partial" if good_parts else "awaiting-details"
            changed = True

    return event, changed


def strong_keys(event: dict) -> set[str]:
    keys: set[str] = set()
    event_id = text(event.get("id"))
    if event_id:
        keys.add(f"id:{event_id}")
    for key in (lot_key(event), goods_key(event)):
        if key:
            keys.add(key)

    provider = playguide_provider(event)
    days = ",".join(event_days(event))
    if provider in {"eplus", "lawson"}:
        for value in urls(event):
            keys.add(f"{provider}:{value}:days:{days}")
    elif provider == "pia":
        # Pia bundle URLs are shared by many performances. Never use the bare bundle URL as a
        # strong identity; the lot code above is the trustworthy sale identity.
        pass
    else:
        for value in urls(event):
            if "asobisystem.com/live_information/detail/" in value:
                keys.add(f"official:{value}")
    return keys


def should_retain_previous(event: dict, today) -> bool:
    provider = playguide_provider(event)
    if provider:
        if not is_ticket_listing(event):
            # Ended playguide rounds must be allowed to disappear. Canonical performance coverage
            # is guarded separately by the official-schedule coverage audit.
            return False
        end = parse_dt(event.get("applyEnd"))
        if end is not None:
            return end.date() >= today
        # A source can occasionally omit an exact deadline. Preserve an explicitly open row until
        # a later verified observation replaces it.
        return str(event.get("applicationStatus") or "") == "open"

    days = [parse_day(value) for value in event_days(event)]
    days = [value for value in days if value is not None]
    if days and max(days) >= today:
        return True
    end = parse_dt(event.get("applyEnd"))
    return bool(end and end.date() >= today)


def semantic_key(event: dict) -> tuple[str, str, tuple[str, ...]]:
    title = text(event.get("eventTitle") or event.get("title")).casefold()
    return str(event.get("group") or ""), title, tuple(event_days(event))


def prepare(previous: dict, candidate: dict, now: datetime) -> tuple[dict, dict]:
    events = [dict(event) for event in candidate.get("events", []) if isinstance(event, dict)]

    normalized = 0
    normalized_events = []
    for event in events:
        event, changed = normalize_special(event)
        normalized += int(changed)
        normalized_events.append(event)

    events, duplicate_ids_removed = dedupe_ids(normalized_events)
    candidate_strong = set().union(*(strong_keys(event) for event in events)) if events else set()
    candidate_semantic = {semantic_key(event) for event in events}

    retained = []
    today = now.astimezone(JST).date()
    for old in previous.get("events", []):
        if not isinstance(old, dict) or not should_retain_previous(old, today):
            continue
        keys = strong_keys(old)
        if keys and candidate_strong.intersection(keys):
            continue
        if semantic_key(old) in candidate_semantic:
            continue
        kept = dict(old)
        kept["sourceStale"] = True
        kept.setdefault("sourceStaleSince", now.astimezone(JST).isoformat(timespec="seconds"))
        kept["releaseRetentionReason"] = "missing-from-current-refresh"
        events.append(kept)
        candidate_strong.update(strong_keys(kept))
        candidate_semantic.add(semantic_key(kept))
        retained.append({
            "id": kept.get("id"),
            "group": kept.get("group"),
            "title": kept.get("title"),
            "ticketType": kept.get("ticketType"),
        })

    events, duplicate_ids_removed_after_retention = dedupe_ids(events)
    out = dict(candidate)
    out["events"] = events
    out["releasePreparation"] = {
        "preparedAt": now.astimezone(JST).isoformat(timespec="seconds"),
        "normalizedSpecialEvents": normalized,
        "duplicateIdsRemoved": duplicate_ids_removed + duplicate_ids_removed_after_retention,
        "retainedPreviousRows": len(retained),
        "retained": retained,
    }
    return out, out["releasePreparation"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a fail-soft but integrity-preserving release candidate")
    parser.add_argument("--previous", required=True, type=Path)
    parser.add_argument("--candidate", type=Path, default=DATA_PATH)
    parser.add_argument("--now", help="ISO-8601 timestamp used by tests")
    args = parser.parse_args()

    now = parse_dt(args.now) if args.now else datetime.now(JST)
    if now is None:
        raise SystemExit("invalid --now")
    previous = json.loads(args.previous.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    prepared, report = prepare(previous, candidate, now)
    args.candidate.write_text(json.dumps(prepared, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
