#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import dedupe_official_x_series as official_x_dedupe
from expand_special_event_entities import expand_payload
from enforce_physical_event_invariant import enforce_payload
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
SPECIAL_CATEGORIES = {"large-benefit", "release-event"}
JOINT_GROUPS = {"KAWAII LAB.合同", "KAWAII LAB."}
# Observation timestamps are refreshed when a source is checked. They prove that
# the collector ran, but they are not a change to the public event information.
# Excluding them keeps `updatedAt` truthful: it moves only when event data changes.
VOLATILE_EVENT_FIELDS = {
    "sourceObservedAt",
    "sourceStaleSince",
    "lastObservedAt",
    "lastSeenAt",
    "observedAt",
    "checkedAt",
}


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
    no_window = not (event.get("applyStart") or event.get("applyEnd"))
    no_reception = event.get("applicationStatus") == "none" or str(event.get("ticketType") or "") == "現在受付なし"

    if official_urls and no_window and no_reception:
        event["specialDetailsStatus"] = "awaiting-details"
        event["applicationDisplayMode"] = "schedule-only"
        event["applicationStatus"] = "none"
        if str(event.get("sourceType") or "") not in {"official-schedule", "official-special", "official-social"}:
            event["sourceType"] = "official-special"
        event["primarySource"] = "official"
        changed = True

    if category == "large-benefit":
        raw_parts = event.get("parts") if isinstance(event.get("parts"), list) else []
        good_parts = [dict(row) for row in raw_parts if valid_part(row)]
        if len(good_parts) != len(raw_parts) or not good_parts:
            event["parts"] = good_parts
            event["specialDetailsStatus"] = "awaiting-details"
            event["partsStatus"] = "partial" if good_parts else "awaiting-details"
            changed = True

    return event, changed


def physical_places(event: dict) -> set[tuple[str, str]]:
    """Return date/venue identities without the display group.

    A joint placeholder and its later group-specific rows necessarily have
    different group names.  Date and venue are therefore the stable identity
    used only for deciding whether a stale joint placeholder has been fully
    superseded.
    """
    rows = event.get("schedule") if isinstance(event.get("schedule"), list) else []
    places = {
        (
            str(row.get("date") or "")[:10],
            re.sub(r"[\s　]+", "", str(row.get("venue") or event.get("venue") or "")).casefold(),
        )
        for row in rows
        if isinstance(row, dict) and row.get("date")
    }
    if places:
        return {(day, venue) for day, venue in places if day and venue}
    venue = re.sub(r"[\s　]+", "", str(event.get("venue") or "")).casefold()
    return {(day, venue) for day in event_days(event) if day and venue}


def stale_joint_replaced_by_participant_rows(joint: dict, events: list[dict]) -> bool:
    """Whether a stale joint placeholder is covered by every named group.

    Large benefit events can first arrive as one schedule-only joint row.  Once
    each participating group's own sale details arrive at different times, the
    sanitizer correctly keeps those group-specific rows separate.  Retaining
    the earlier joint row as fail-soft history would then render a third black
    copy of the same event, so that stale placeholder must be retired.
    """
    if not joint.get("sourceStale") or str(joint.get("group") or "") not in JOINT_GROUPS:
        return False
    category = str(joint.get("eventCategory") or "")
    participants = {
        str(value) for value in joint.get("participants") or []
        if str(value) and str(value) not in JOINT_GROUPS
    }
    places = physical_places(joint)
    if category not in SPECIAL_CATEGORIES or len(participants) < 2 or not places:
        return False

    covered = set()
    for event in events:
        group = str(event.get("group") or "")
        if group not in participants or event.get("sourceStale"):
            continue
        if str(event.get("eventCategory") or "") != category:
            continue
        if places.intersection(physical_places(event)):
            covered.add(group)
    return covered == participants


def drop_superseded_stale_joint_specials(events: list[dict]) -> tuple[list[dict], list[str]]:
    dropped = [
        str(event.get("id") or "")
        for event in events
        if stale_joint_replaced_by_participant_rows(event, events)
    ]
    return [
        event for event in events
        if not stale_joint_replaced_by_participant_rows(event, events)
    ], dropped


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
        pass
    else:
        for value in urls(event):
            if "asobisystem.com/live_information/detail/" in value:
                keys.add(f"official:{value}")
    return keys


def future_days(event: dict, today) -> list:
    return [
        value for value in (parse_day(day) for day in event_days(event))
        if value is not None and value >= today
    ]


def should_retain_previous(event: dict, today) -> bool:
    provider = playguide_provider(event)
    if provider and is_ticket_listing(event):
        end = parse_dt(event.get("applyEnd"))
        if end is not None:
            return end.date() >= today
        return str(event.get("applicationStatus") or "") == "open"

    if future_days(event, today):
        return True
    end = parse_dt(event.get("applyEnd"))
    return bool(end and end.date() >= today)


def semantic_key(event: dict) -> tuple:
    """Fallback identity that never collapses different ticket providers/receptions."""
    group = str(event.get("group") or "")
    title = text(event.get("eventTitle") or event.get("title")).casefold()
    days = tuple(event_days(event))
    provider = playguide_provider(event)
    if provider and is_ticket_listing(event):
        return (
            "ticket",
            provider,
            group,
            title,
            text(event.get("ticketType")).casefold(),
            text(event.get("applyStart")),
            text(event.get("applyEnd")),
            days,
        )
    return (
        "performance",
        group,
        title,
        text(event.get("venue")).casefold(),
        days,
    )


def stable_public_value(value):
    """Remove per-check observation clocks before comparing public event data."""
    if isinstance(value, dict):
        return {
            key: stable_public_value(item)
            for key, item in value.items()
            if key not in VOLATILE_EVENT_FIELDS
        }
    if isinstance(value, list):
        return [stable_public_value(item) for item in value]
    return value


def stable_event_payload(rows: object) -> list[dict]:
    cleaned = [
        stable_public_value(row)
        for row in (rows if isinstance(rows, list) else [])
        if isinstance(row, dict)
    ]
    # Collector/merge ordering alone must never make the public update clock move.
    return sorted(
        cleaned,
        key=lambda row: (
            str(row.get("id") or ""),
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        ),
    )


def event_payload_changed(previous: dict, current: dict) -> bool:
    return stable_event_payload(previous.get("events")) != stable_event_payload(current.get("events"))


def prepare(previous: dict, candidate: dict, now: datetime) -> tuple[dict, dict]:
    # Preserve the actual prior public representation for the final change check.
    # Special events are expanded below for collector compatibility, then folded
    # back into canonical public entities. Comparing the expanded form to the
    # folded form would otherwise create a false update on every refresh.
    previous_public = json.loads(json.dumps(previous, ensure_ascii=False))

    # Public releases use canonical special-event entities (one real event with
    # offers[] children). Existing collectors and integrity checks still operate
    # on sale rows, so expand both sides at this compatibility boundary. This
    # keeps the old collectors stable without letting their source rows leak back
    # into the public data model.
    previous, previous_expand = expand_payload(previous)
    candidate, candidate_expand = expand_payload(candidate)
    events = [dict(event) for event in candidate.get("events", []) if isinstance(event, dict)]

    normalized = 0
    normalized_events = []
    for event in events:
        event, changed = normalize_special(event)
        normalized += int(changed)
        normalized_events.append(event)

    events, superseded_joint_rows = drop_superseded_stale_joint_specials(normalized_events)
    events, duplicate_ids_removed = dedupe_ids(events)
    candidate_strong = set().union(*(strong_keys(event) for event in events)) if events else set()
    candidate_semantic = {semantic_key(event) for event in events}

    retained = []
    today = now.astimezone(JST).date()
    for old in previous.get("events", []):
        if not isinstance(old, dict) or not should_retain_previous(old, today):
            continue
        if stale_joint_replaced_by_participant_rows(old, events):
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
            "provider": playguide_provider(kept),
            "applyEnd": kept.get("applyEnd"),
        })

    events, duplicate_ids_removed_after_retention = dedupe_ids(events)
    events, official_x_report = official_x_dedupe.collapse(events)
    out = dict(candidate)
    out["events"] = events
    out["releasePreparation"] = {
        "preparedAt": now.astimezone(JST).isoformat(timespec="seconds"),
        "normalizedSpecialEvents": normalized,
        "duplicateIdsRemoved": duplicate_ids_removed + duplicate_ids_removed_after_retention,
        "retainedPreviousRows": len(retained),
        "retained": retained,
        "expandedPreviousSpecialEntities": previous_expand.get("expandedSpecialEntities", 0),
        "expandedCandidateSpecialEntities": candidate_expand.get("expandedSpecialEntities", 0),
        "supersededStaleJointRowsRemoved": len(superseded_joint_rows),
        "supersededStaleJointRowIds": superseded_joint_rows,
        **official_x_report,
    }

    # Hard public invariant: source wording, URL and sales channel can never
    # create two special-event entities for one physically impossible duplicate.
    # Same group + same date + same start time + same venue is one real event.
    out, physical_report = enforce_payload(out)
    out["releasePreparation"]["physicalEventInvariant"] = physical_report

    checked_at = now.astimezone(JST).isoformat(timespec="seconds")
    out["checkedAt"] = checked_at
    changed = event_payload_changed(previous_public, out)
    previous_updated_at = str(previous_public.get("updatedAt") or "").strip()
    out["updatedAt"] = checked_at if changed or not previous_updated_at else previous_updated_at
    out["releasePreparation"]["eventPayloadChanged"] = changed
    out["releasePreparation"]["publicUpdatedAt"] = out["updatedAt"]
    out["releasePreparation"]["checkedAt"] = checked_at
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
