#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


AUDIT_ID = "P0-sweet-steady-ohanami-2026-09-21-two-shows"
EVENT_TITLE = "SWEET STEADY 単独公演 お花見会"
EVENT_DAY = "2026-09-21"
VENUE = "東京都 Zepp Shinjuku(TOKYO)"
SOURCE_URL = "https://sweetsteady.asobisystem.com/news/detail/88352"
SCHEDULE_URL = "https://sweetsteady.asobisystem.com/live_information/detail/44458"
SHOWS = {
    "first": {"label": "第一回", "openTime": "13:00", "startTime": "14:00"},
    "second": {"label": "第二回", "openTime": "16:30", "startTime": "17:30"},
}
TICKET_FIELDS = (
    "ticketType",
    "applyStart",
    "applyEnd",
    "resultDate",
    "paymentEnd",
    "ticketProvider",
    "saleFamily",
    "applicationStatus",
    "deadlineSource",
    "applicationDisplayMode",
)


def _day(value: Any) -> str:
    return str(value or "")[:10]


def _time(value: Any) -> str:
    return str(value or "").strip()


def _text(event: dict[str, Any]) -> str:
    return " ".join(
        str(event.get(key) or "")
        for key in ("displayTitle", "eventTitle", "title")
    )


def _is_target(event: dict[str, Any]) -> bool:
    return (
        event.get("group") == "SWEET STEADY"
        and EVENT_TITLE.lower() in _text(event).lower()
        and _day(event.get("eventDate")) == EVENT_DAY
    )


def _venue_key(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"^(?:東京都|北海道|京都府|大阪府|.{2,3}県)\s*", "", text)
    return re.sub(r"[\s!！・|｜\-–—_\[\]()（）『』「」]", "", text)


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _append_audit_id(event: dict[str, Any]) -> None:
    audit_ids = [str(value) for value in event.get("auditCorrectionIds") or [] if value]
    if AUDIT_ID not in audit_ids:
        audit_ids.append(AUDIT_ID)
    event["auditCorrectionIds"] = audit_ids


def _append_performance_source(event: dict[str, Any], source_url: str) -> None:
    sources = [str(value) for value in event.get("performanceFactSources") or [] if value]
    if source_url not in sources:
        sources.append(source_url)
    event["performanceFactSources"] = sources


def _ticket_offer_from_row(event: dict[str, Any]) -> dict[str, Any] | None:
    ticket_type = str(event.get("ticketType") or "").strip()
    if not ticket_type or ticket_type == "現在受付なし":
        return None
    offer: dict[str, Any] = {"sourceRowId": event.get("id")}
    for field in TICKET_FIELDS:
        offer[field] = deepcopy(event.get(field))
    offer["url"] = event.get("url")
    offer["urls"] = deepcopy(event.get("urls") or [])
    offer["sourceType"] = event.get("sourceType")
    offer["primarySource"] = event.get("primarySource")
    return offer


def _offer_key(offer: dict[str, Any]) -> str:
    stable = {
        key: offer.get(key)
        for key in (
            "sourceRowId",
            *TICKET_FIELDS,
            "url",
            "sourceType",
            "primarySource",
        )
    }
    return json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str)


def _select_display_offer(offers: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not offers:
        return None

    def key(offer: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(offer.get("applyEnd") or ""),
            str(offer.get("applyStart") or ""),
            str(offer.get("sourceRowId") or ""),
        )

    return max(offers, key=key)


def _apply_selected_offer(event: dict[str, Any], offer: dict[str, Any] | None) -> None:
    if offer is None:
        event["ticketType"] = "現在受付なし"
        for field in TICKET_FIELDS:
            if field != "ticketType":
                event.pop(field, None)
        return

    for field in TICKET_FIELDS:
        value = deepcopy(offer.get(field))
        if value is None:
            event.pop(field, None)
        else:
            event[field] = value


def _set_show(event: dict[str, Any], show_key: str) -> None:
    show = SHOWS[show_key]
    event["group"] = "SWEET STEADY"
    event["title"] = EVENT_TITLE
    event["eventTitle"] = EVENT_TITLE
    event["displayTitle"] = f"{EVENT_TITLE} {show['label']}"
    event["eventDate"] = EVENT_DAY
    event["eventEndDate"] = EVENT_DAY
    event["eventDates"] = [EVENT_DAY]
    event["eventCount"] = 1
    event["venue"] = VENUE
    event["openTime"] = show["openTime"]
    event["startTime"] = show["startTime"]
    event["schedule"] = [
        {
            "date": EVENT_DAY,
            "venue": VENUE,
            "openTime": show["openTime"],
            "startTime": show["startTime"],
        }
    ]
    event["officialScheduleUrl"] = SCHEDULE_URL
    event["performanceMatchedToOfficial"] = True
    _append_audit_id(event)
    _append_performance_source(event, SOURCE_URL)
    _append_performance_source(event, SCHEDULE_URL)


def apply_ohanami_two_show_correction(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Canonicalize the 2026-09-21 Ohanami announcement into exactly two physical
    performance rows. Source/offer duplicates are folded into provenance
    metadata so the public page exposes 第一回 and 第二回 once each.
    """
    corrected = deepcopy(payload)
    raw_events = corrected.get("events") or []
    events = [event for event in raw_events if isinstance(event, dict)]
    targets = [event for event in events if _is_target(event)]
    report: dict[str, Any] = {
        "auditCorrectionId": AUDIT_ID,
        "sourceUrl": SOURCE_URL,
        "scheduleUrl": SCHEDULE_URL,
        "matchedEvents": len(targets),
        "venueMissingRows": 0,
        "sourceRowsFolded": 0,
        "secondShowCreated": False,
        "canonicalRows": 0,
        "conflicts": [],
    }
    if not targets:
        return corrected, report

    allowed_starts = {SHOWS["first"]["startTime"], SHOWS["second"]["startTime"]}
    for event in targets:
        venue = str(event.get("venue") or "").strip()
        if not venue:
            report["venueMissingRows"] += 1
        elif _venue_key(venue) != _venue_key(VENUE):
            report["conflicts"].append(
                {
                    "eventId": event.get("id"),
                    "field": "venue",
                    "current": venue,
                    "authoritative": VENUE,
                }
            )
        start = _time(event.get("startTime"))
        if start and start not in allowed_starts:
            report["conflicts"].append(
                {
                    "eventId": event.get("id"),
                    "field": "startTime",
                    "current": start,
                    "authoritative": sorted(allowed_starts),
                }
            )
    if report["conflicts"]:
        return corrected, report

    first_candidates = [
        event for event in targets
        if _time(event.get("startTime")) == SHOWS["first"]["startTime"]
    ]
    if not first_candidates:
        report["conflicts"].append(
            {
                "eventId": None,
                "field": f"performance[{EVENT_DAY} {SHOWS['first']['startTime']}]",
                "current": "missing",
                "authoritative": "first-show source row",
            }
        )
        return corrected, report

    def base_rank(event: dict[str, Any]) -> tuple[int, int, int, str]:
        return (
            0 if event.get("ohanamiCanonicalSeriesId") else 1,
            0 if str(event.get("ticketType") or "") == "現在受付なし" else 1,
            0 if event.get("officialScheduleUrl") else 1,
            str(event.get("id") or ""),
        )

    base = min(first_candidates, key=base_rank)
    base_id = str(base.get("ohanamiCanonicalSeriesId") or base.get("id") or "").strip()
    if not base_id:
        report["conflicts"].append(
            {
                "eventId": None,
                "field": "id",
                "current": None,
                "authoritative": "non-empty canonical id",
            }
        )
        return corrected, report

    merged_source_ids: list[str] = []
    for event in targets:
        merged_source_ids.extend(
            str(value) for value in event.get("auditMergedSourceRowIds") or [] if value
        )
        if not event.get("ohanamiCanonicalSeriesId") and event.get("id"):
            merged_source_ids.append(str(event["id"]))
    merged_source_ids = _unique_strings(merged_source_ids)

    offers: list[dict[str, Any]] = []
    seen_offer_keys: set[str] = set()
    for event in targets:
        previous = event.get("auditMergedTicketOffers")
        if isinstance(previous, list):
            for item in previous:
                if not isinstance(item, dict):
                    continue
                key = _offer_key(item)
                if key not in seen_offer_keys:
                    offers.append(deepcopy(item))
                    seen_offer_keys.add(key)
        if not event.get("ohanamiCanonicalSeriesId"):
            item = _ticket_offer_from_row(event)
            if item is not None:
                key = _offer_key(item)
                if key not in seen_offer_keys:
                    offers.append(item)
                    seen_offer_keys.add(key)

    selected_offer = _select_display_offer(offers)
    union_urls: list[str] = []
    for event in targets:
        union_urls.extend([event.get("url"), *(event.get("urls") or [])])
    union_urls.extend([SOURCE_URL, SCHEDULE_URL])
    union_urls = _unique_strings(union_urls)

    first = deepcopy(base)
    first["id"] = base_id
    first["ohanamiCanonicalSeriesId"] = base_id
    first["auditMergedSourceRowIds"] = merged_source_ids
    first["auditMergedTicketOffers"] = deepcopy(offers)
    first["urls"] = union_urls
    first["url"] = SOURCE_URL
    _apply_selected_offer(first, selected_offer)
    _set_show(first, "first")

    native_second = next(
        (
            event for event in targets
            if _time(event.get("startTime")) == SHOWS["second"]["startTime"]
        ),
        None,
    )
    second = deepcopy(native_second if native_second is not None else first)
    second["id"] = f"{base_id}--ohanami-second"
    second["ohanamiCanonicalSeriesId"] = base_id
    second["auditCloneOf"] = base_id
    second["auditMergedSourceRowIds"] = merged_source_ids
    second["auditMergedTicketOffers"] = deepcopy(offers)
    second["urls"] = union_urls
    second["url"] = SOURCE_URL
    _apply_selected_offer(second, selected_offer)
    _set_show(second, "second")
    report["secondShowCreated"] = native_second is None

    target_ids = {id(event) for event in targets}
    rebuilt: list[dict[str, Any]] = []
    inserted = False
    for event in events:
        if id(event) in target_ids:
            if not inserted:
                rebuilt.extend([first, second])
                inserted = True
            continue
        rebuilt.append(event)
    if not inserted:
        rebuilt.extend([first, second])

    report["sourceRowsFolded"] = max(0, len(targets) - 2)
    report["canonicalRows"] = 2
    corrected["events"] = rebuilt
    return corrected, report
