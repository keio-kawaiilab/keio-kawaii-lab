#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from schedule_scope import apply_event_scope

DATA_PATH = Path("data/live-events.json")
BIRTHDAY_RE = re.compile(
    r"生誕(?:祭|ライブ|イベント|公演)?|BIRTHDAY\s*(?:LIVE|EVENT|PARTY|FES|FESTIVAL)?|BD\s*(?:LIVE|EVENT)",
    re.I,
)
DATE_PREFIX_RE = re.compile(
    r"^(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*"
)


def text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def event_day(event: dict) -> str:
    if event.get("eventDate"):
        return str(event["eventDate"])[:10]
    for row in event.get("schedule") or []:
        if isinstance(row, dict) and row.get("date"):
            return str(row["date"])[:10]
    for value in event.get("eventDates") or []:
        if value:
            return str(value)[:10]
    return ""


def birthday_subject(event: dict) -> str:
    """Return the member/event subject before the birthday marker.

    The key deliberately ignores ticket-sale wording so an old schedule-only row
    and a newer FC/general-sale row for the same birthday performance can be
    recognized as one physical event.
    """
    title = text(event.get("eventTitle") or event.get("displayTitle") or event.get("title"))
    match = BIRTHDAY_RE.search(title)
    if not match:
        return ""
    prefix = DATE_PREFIX_RE.sub("", title[: match.start()])
    group = text(event.get("group"))
    if group:
        prefix = re.sub(re.escape(group), "", prefix, flags=re.I)
    prefix = re.sub(r"(?:開催決定|公演決定|記念|\bLIVE\b|\bEVENT\b)", "", prefix, flags=re.I)
    prefix = re.sub(r"[\s　!！・|｜\-–—_\[\]()（）『』「」【】]+", "", prefix)
    if prefix:
        return prefix.casefold()
    # Fallback keeps same-day birthday events distinct when a member name could
    # not be isolated from an unusual announcement title.
    fallback = re.sub(BIRTHDAY_RE, "", title)
    fallback = re.sub(r"20\d{2}", "", fallback)
    if group:
        fallback = re.sub(re.escape(group), "", fallback, flags=re.I)
    return re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠]+", "", fallback).casefold()


def birthday_key(event: dict) -> tuple[str, str, str] | None:
    subject = birthday_subject(event)
    day = event_day(event)
    group = text(event.get("group"))
    if not subject or not day or not group:
        return None
    return group.casefold(), day, subject


def schedule_only(event: dict) -> bool:
    if event.get("applyStart") or event.get("applyEnd"):
        return False
    return str(event.get("ticketType") or "") == "現在受付なし" or str(event.get("applicationStatus") or "") == "none"


def stale_schedule_shadow(event: dict) -> bool:
    return bool(
        birthday_key(event)
        and schedule_only(event)
        and (
            event.get("sourceStale") is True
            or str(event.get("releaseRetentionReason") or "") == "missing-from-current-refresh"
        )
    )


def normalize_venue(value: object) -> str:
    value = text(value).casefold()
    value = re.sub(r"^(?:北海道|東京都|京都府|大阪府|.{2,3}県)\s*", "", value)
    return re.sub(r"[\s　・･,，.。()（）\-–—_]", "", value)


def same_physical_birthday(a: dict, b: dict) -> bool:
    if birthday_key(a) != birthday_key(b) or birthday_key(a) is None:
        return False
    venue_a, venue_b = normalize_venue(a.get("venue")), normalize_venue(b.get("venue"))
    if venue_a and venue_b and venue_a != venue_b:
        return False
    start_a, start_b = text(a.get("startTime")), text(b.get("startTime"))
    if start_a and start_b and start_a != start_b:
        return False
    return True


def candidate_score(event: dict) -> tuple[int, int, int]:
    source = str(event.get("sourceType") or event.get("primarySource") or "").lower()
    source_score = {
        "official-schedule": 90,
        "official-social": 85,
        "official": 80,
        "auto": 75,
        "promoter": 70,
        "pia": 60,
        "lawson": 60,
        "eplus": 60,
        "derived": 20,
    }.get(source, 50)
    filled = sum(1 for value in event.values() if value not in (None, "", [], {}))
    has_window = int(bool(event.get("applyStart") or event.get("applyEnd")))
    return has_window, source_score, filled


def merge_shadow_metadata(target: dict, shadow: dict) -> None:
    all_urls: list[str] = []
    for event in (target, shadow):
        for value in [event.get("url"), *(event.get("urls") or [])]:
            if value and str(value) not in all_urls:
                all_urls.append(str(value))
    if all_urls:
        target["urls"] = all_urls
        if not target.get("url"):
            target["url"] = all_urls[0]
    for field in ("venue", "openTime", "startTime", "eventTitle", "displayTitle", "officialScheduleUrl"):
        if not target.get(field) and shadow.get(field):
            target[field] = shadow[field]


def dedupe_birthday_schedule_shadows(events: list[dict]) -> tuple[list[dict], int]:
    """Remove only stale schedule-only birthday rows shadowed by a richer row.

    FC/general/playguide rows are never collapsed with each other. We only drop
    the old no-reception row that survived fail-soft retention after a newer row
    for the same physical birthday performance is already present.
    """
    rows = [dict(event) for event in events]
    removed: set[int] = set()
    for index, shadow in enumerate(rows):
        if not stale_schedule_shadow(shadow):
            continue
        candidates = [
            (other_index, other)
            for other_index, other in enumerate(rows)
            if other_index != index
            and other_index not in removed
            and not schedule_only(other)
            and same_physical_birthday(shadow, other)
        ]
        if not candidates:
            continue
        target_index, target = max(candidates, key=lambda pair: candidate_score(pair[1]))
        merge_shadow_metadata(rows[target_index], shadow)
        removed.add(index)
    return [event for index, event in enumerate(rows) if index not in removed], len(removed)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply the shared hosted/external schedule classification.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    original = [event for event in payload.get("events", []) if isinstance(event, dict)]
    updated = [apply_event_scope(event) for event in original]
    updated, birthday_shadows_removed = dedupe_birthday_schedule_shadows(updated)
    missing = sum(1 for event in original if not event.get("eventScope"))
    invalid = [event.get("id") for event in updated if event.get("eventScope") not in {"kawaii-lab", "external"}]
    if invalid:
        raise SystemExit(f"Invalid eventScope values: {invalid}")
    if args.check:
        if missing:
            raise SystemExit(f"{missing} events have no eventScope")
        print(f"Event scope check passed: {len(updated)} events; {birthday_shadows_removed} stale birthday shadow(s) removed")
        return 0
    payload["events"] = updated
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Applied event scopes: {len(updated)} events ({missing} newly classified); "
        f"{birthday_shadows_removed} stale birthday shadow(s) removed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
