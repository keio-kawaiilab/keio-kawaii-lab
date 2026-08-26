#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime

import requests

import update_live_events as parser_v1
import update_live_events_v2 as updater


def is_current_application(event: dict, now: datetime) -> bool:
    end = updater.parse_day(event.get("applyEnd"))
    show = updater.event_last_day(event)
    if not end or end < now.date():
        return False
    if show and show < now.date():
        return False
    return True


def normalize_offer(event: dict, existing: dict, now: datetime) -> dict:
    offer = dict(event)
    group = str(offer.get("group") or "")
    event_date = str(offer.get("eventDate") or "")[:10]

    # Use the already verified performance title/venue when the FC article describes
    # an existing show. This guarantees that the offer merges into the same card.
    same_day = [
        item for item in existing.get("events", [])
        if isinstance(item, dict)
        and item.get("group") == group
        and str(item.get("eventDate") or "")[:10] == event_date
    ]
    if len(same_day) == 1:
        base = same_day[0]
        stable_title = base.get("eventTitle") or base.get("title")
        if stable_title:
            offer["eventTitle"] = stable_title
        if base.get("venue"):
            offer["venue"] = base.get("venue")
        if base.get("openTime"):
            offer["openTime"] = base.get("openTime")
        if base.get("startTime"):
            offer["startTime"] = base.get("startTime")

    start_moment = parser_v1._iso_datetime(str(offer.get("applyStart"))) if offer.get("applyStart") else None
    end_moment = parser_v1._iso_datetime(str(offer.get("applyEnd"))) if offer.get("applyEnd") else None
    naive_now = now.replace(tzinfo=None)
    is_open = bool(start_moment and end_moment and start_moment <= naive_now <= end_moment)

    offer.update({
        "ticketType": "KAWAII LAB. FC先行",
        "ticketProvider": "official",
        "sourceType": "auto",
        "sourceChannel": "kawaii-lab-fc",
        "primarySource": "official",
        "sourceCandidates": ["official"],
        "eventScope": "kawaii-lab",
        "applicationStatus": "open" if is_open else "upcoming",
        "applicationWindowVerified": True,
        "deadlineVerified": True,
        "applicationDisplayMode": "band",
        "applicationWindowSource": offer.get("url"),
        "deadlineSource": offer.get("url"),
    })
    return offer


def main() -> int:
    existing = parser_v1.read_existing()
    session = requests.Session()
    session.headers.update({
        "User-Agent": "KeioKawaiiLabCalendarBot/1.5 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"
    })

    discovered, pending, failures, candidate_count = updater.collect_central_fc(session, existing)
    now = datetime.now(parser_v1.JST)
    current = [normalize_offer(event, existing, now) for event in discovered.values() if is_current_application(event, now)]

    by_id = {
        str(event.get("id")): dict(event)
        for event in existing.get("events", [])
        if isinstance(event, dict) and event.get("id")
    }
    for offer in current:
        by_id[str(offer["id"])] = offer

    payload = dict(existing)
    payload["updatedAt"] = now.isoformat(timespec="seconds")
    payload["events"] = sorted(
        by_id.values(),
        key=lambda event: (
            str(event.get("eventDate") or "9999"),
            str(event.get("applyEnd") or "9999"),
            str(event.get("group") or ""),
        ),
    )
    payload["pendingReview"] = existing.get("pendingReview", [])
    payload["failures"] = existing.get("failures", [])

    parser_v1.OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "centralCandidates": candidate_count,
        "centralParsed": len(discovered),
        "currentOffersMerged": len(current),
        "pending": len(pending),
        "failures": failures,
        "offers": [
            {
                "group": event.get("group"),
                "eventTitle": event.get("eventTitle") or event.get("title"),
                "eventDate": event.get("eventDate"),
                "applyStart": event.get("applyStart"),
                "applyEnd": event.get("applyEnd"),
                "url": event.get("url"),
            }
            for event in current
        ],
    }, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
