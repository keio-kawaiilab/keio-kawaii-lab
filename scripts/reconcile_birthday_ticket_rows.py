#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

DATA_PATH = Path("data/live-events.json")
BIRTHDAY_RE = re.compile(r"生誕(?:祭|ライブ|イベント|公演)?|BIRTHDAY\s*(?:LIVE|EVENT|PARTY|FES|FESTIVAL)?|BD\s*(?:LIVE|EVENT)", re.I)
OFFICIAL_HOSTS = {
    "kawaiilab.asobisystem.com",
    "fruitszipper.asobisystem.com",
    "candytune.asobisystem.com",
    "sweetsteady.asobisystem.com",
    "cutiestreet.asobisystem.com",
    "morestar.asobisystem.com",
}
TICKET_FIELDS = (
    "ticketType",
    "ticketProvider",
    "applicationStatus",
    "applyStart",
    "applyEnd",
    "resultDate",
    "paymentEnd",
    "applicationDisplayMode",
    "applicationWindowVerified",
    "deadlineVerified",
    "applicationWindowSource",
    "deadlineSource",
    "specialDetailsStatus",
    "sourcePublishedAt",
    "discoverySourceUrl",
)
SOURCE_FIELDS = (
    "sourceType",
    "sourceChannel",
    "primarySource",
    "sourceCandidates",
)


def title(event: dict) -> str:
    return str(event.get("eventTitle") or event.get("title") or "")


def birthday_key(event: dict) -> tuple[str, str] | None:
    if not BIRTHDAY_RE.search(title(event)):
        return None
    group = str(event.get("group") or "")
    day = str(event.get("eventDate") or "")[:10]
    if not group or not day:
        return None
    return group, day


def has_application(event: dict) -> bool:
    ticket_type = str(event.get("ticketType") or "")
    return bool(
        (ticket_type and ticket_type != "現在受付なし")
        or event.get("applyStart")
        or event.get("applyEnd")
    )


def official_url(value: object) -> bool:
    if not value:
        return False
    try:
        return (urlparse(str(value)).hostname or "").lower() in OFFICIAL_HOSTS
    except Exception:
        return False


def is_verified_official_ticket(event: dict) -> bool:
    if not has_application(event):
        return False
    if str(event.get("primarySource") or "").lower() != "official":
        return False
    values = [event.get("url"), event.get("applicationWindowSource"), event.get("deadlineSource")]
    values.extend(event.get("urls") or [])
    return any(official_url(value) for value in values)


def ticket_signature(event: dict) -> tuple[str, str, str]:
    return (
        str(event.get("ticketType") or ""),
        str(event.get("applyStart") or ""),
        str(event.get("applyEnd") or ""),
    )


def unique_urls(*values: object) -> list[str]:
    result: list[str] = []
    for value in values:
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            candidate = str(candidate or "")
            if candidate and candidate not in result:
                result.append(candidate)
    return result


def official_primary_url(event: dict) -> str | None:
    for value in (
        event.get("applicationWindowSource"),
        event.get("deadlineSource"),
        event.get("url"),
        *(event.get("urls") or []),
    ):
        if official_url(value):
            return str(value)
    return None


def richness(event: dict) -> tuple[int, int, int]:
    return (
        int(bool(event.get("applyStart"))) + int(bool(event.get("applyEnd"))),
        int(bool(event.get("applicationWindowVerified"))) + int(bool(event.get("deadlineVerified"))),
        int(official_url(event.get("url"))),
    )


def reconcile(payload: dict) -> tuple[dict, dict]:
    events = [dict(event) for event in payload.get("events", []) if isinstance(event, dict)]
    by_key: dict[tuple[str, str], list[int]] = {}
    for index, event in enumerate(events):
        key = birthday_key(event)
        if key:
            by_key.setdefault(key, []).append(index)

    removed: set[int] = set()
    reconciled = []

    for key, indexes in by_key.items():
        verified = [index for index in indexes if is_verified_official_ticket(events[index])]
        placeholders = [index for index in indexes if not has_application(events[index])]
        if not verified or not placeholders:
            continue

        verified.sort(key=lambda index: richness(events[index]), reverse=True)
        source_index = verified[0]
        source = events[source_index]
        target_index = placeholders[0]
        target = dict(events[target_index])

        # Preserve the long-lived event id/date identity, but make the actual
        # official ticket announcement the displayed source and copy verified
        # application fields onto that row.
        for field in ("title", "eventTitle", "displayTitle", *TICKET_FIELDS, *SOURCE_FIELDS):
            value = source.get(field)
            if value is not None:
                target[field] = value

        for field in ("venue", "openTime", "startTime", "eventCategory", "eventScope"):
            if source.get(field) and not target.get(field):
                target[field] = source[field]

        primary = official_primary_url(source)
        urls = unique_urls(primary, source.get("url"), source.get("urls"), target.get("url"), target.get("urls"))
        if primary:
            target["url"] = primary
        if urls:
            target["urls"] = urls

        target["primarySource"] = "official"
        target["sourceCandidates"] = list(dict.fromkeys(["official", *(target.get("sourceCandidates") or [])]))
        events[target_index] = target

        # The selected rich row has now been folded into the stable placeholder.
        removed.add(source_index)

        # Remove extra schedule-only shadows for the same physical birthday.
        for index in placeholders[1:]:
            removed.add(index)

        # Preserve genuinely different verified ticket rounds.
        seen_signatures = {ticket_signature(target)}
        for index in verified[1:]:
            signature = ticket_signature(events[index])
            if signature in seen_signatures:
                removed.add(index)
            else:
                seen_signatures.add(signature)

        reconciled.append({
            "group": key[0],
            "eventDate": key[1],
            "eventId": target.get("id"),
            "ticketType": target.get("ticketType"),
            "applyStart": target.get("applyStart"),
            "applyEnd": target.get("applyEnd"),
            "url": target.get("url"),
        })

    result = [event for index, event in enumerate(events) if index not in removed]
    result.sort(key=lambda event: (
        str(event.get("eventDate") or "9999-12-31")[:10],
        str(event.get("group") or ""),
        str(event.get("applyEnd") or "9999"),
        str(event.get("title") or ""),
    ))
    out = dict(payload)
    out["events"] = result
    report = {
        "reconciledBirthdays": len(reconciled),
        "removedShadowRows": len(removed),
        "rows": reconciled,
    }
    return out, report


def main() -> int:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    merged, report = reconcile(payload)
    DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
