#!/usr/bin/env python3
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from schedule_scope import HOSTED, infer_event_scope


SPECIAL_CATEGORIES = {"release-event", "large-benefit"}
ONLINE_RE = re.compile(r"オンライン(?:特典会|サイン会)", re.I)
TICKET_FIELDS = (
    "ticketType",
    "ticketProvider",
    "saleFamily",
    "applyStart",
    "applyEnd",
    "resultDate",
    "paymentEnd",
    "applicationStatus",
    "applicationWindowVerified",
    "deadlineVerified",
    "applicationDisplayMode",
    "applicationWindowSource",
    "deadlineSource",
    "sourceType",
    "sourceChannel",
    "primarySource",
    "sourcePublishedAt",
    "sourceObservedAt",
)
TOP_LEVEL_TICKET_FIELDS = {
    "ticketType",
    "ticketProvider",
    "saleFamily",
    "applyStart",
    "applyEnd",
    "resultDate",
    "paymentEnd",
    "applicationStatus",
    "applicationWindowVerified",
    "deadlineVerified",
    "applicationDisplayMode",
    "applicationWindowSource",
    "deadlineSource",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _day(value: Any) -> str:
    return str(value or "")[:10]


def _time(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _venue_key(value: Any) -> str:
    text = _text(value).casefold()
    text = re.sub(r"^(?:北海道|東京都|京都府|大阪府|.{2,3}県)\s*", "", text)
    return re.sub(r"[\s　!！・･|｜\-–—_\[\]()（）『』「」,，.。]", "", text)


def _title_key(event: dict[str, Any]) -> str:
    text = _text(event.get("eventTitle") or event.get("displayTitle") or event.get("title")).casefold()
    text = re.sub(r"^(?:20\d{2}[.\/-]\d{1,2}[.\/-]\d{1,2}|20\d{2}年\d{1,2}月\d{1,2}日)\s*", "", text)
    return re.sub(r"[\s　!！・|｜\-–—_\[\]()（）『』「」]", "", text)


def _tour_key(event: dict[str, Any]) -> str:
    value = _text(event.get("officialTourUrl"))
    if not value:
        return ""
    return re.sub(r"[?#].*$", "", value).rstrip("/").casefold()


def _is_online(event: dict[str, Any]) -> bool:
    return event.get("eventCategory") == "online-benefit" or bool(
        ONLINE_RE.search(_text(event.get("displayTitle") or event.get("eventTitle") or event.get("title")))
    )


def _is_regular_hosted(event: dict[str, Any]) -> bool:
    if event.get("eventCategory") in SPECIAL_CATEGORIES:
        return False
    if event.get("entityType") == "special-event":
        return False
    if _is_online(event):
        return False
    return infer_event_scope(event) == HOSTED


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def _event_urls(event: dict[str, Any]) -> list[str]:
    return _unique_strings([event.get("url"), *(event.get("urls") or [])])


def _occurrences(event: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    schedule = event.get("schedule")
    if isinstance(schedule, list):
        for item in schedule:
            if not isinstance(item, dict) or not _day(item.get("date")):
                continue
            rows.append(
                {
                    "date": _day(item.get("date")),
                    "venue": _text(item.get("venue") or event.get("venue")),
                    "openTime": _time(item.get("openTime") or event.get("openTime")),
                    "startTime": _time(item.get("startTime") or event.get("startTime")),
                }
            )
    if rows:
        return rows

    dates = event.get("eventDates")
    if isinstance(dates, list):
        for value in dates:
            day = _day(value)
            if day:
                rows.append(
                    {
                        "date": day,
                        "venue": _text(event.get("venue")),
                        "openTime": _time(event.get("openTime")),
                        "startTime": _time(event.get("startTime")),
                    }
                )
    if rows:
        return rows

    day = _day(event.get("eventDate"))
    if day:
        rows.append(
            {
                "date": day,
                "venue": _text(event.get("venue")),
                "openTime": _time(event.get("openTime")),
                "startTime": _time(event.get("startTime")),
            }
        )
    return rows


def _time_match_keys(event: dict[str, Any], occurrence: dict[str, Any]) -> list[str]:
    group = _text(event.get("group"))
    day = _day(occurrence.get("date"))
    venue = _venue_key(occurrence.get("venue") or event.get("venue"))
    base = "|".join((group, day, venue))
    result = [base]
    tour = _tour_key(event)
    if tour:
        result.append(base + "|tour:" + tour)
    title = _title_key(event)
    if title:
        result.append(base + "|title:" + title)
    return result


def _reconcile_occurrence_times(records: list[dict[str, Any]]) -> None:
    starts: dict[str, set[str]] = {}
    opens: dict[str, set[str]] = {}
    for record in records:
        event = record["event"]
        occurrence = record["occurrence"]
        start = _time(occurrence.get("startTime") or event.get("startTime"))
        opened = _time(occurrence.get("openTime") or event.get("openTime"))
        for key in _time_match_keys(event, occurrence):
            if start:
                starts.setdefault(key, set()).add(start)
            if opened:
                opens.setdefault(key, set()).add(opened)

    for record in records:
        event = record["event"]
        occurrence = record["occurrence"]
        keys = _time_match_keys(event, occurrence)
        start_values = sorted({value for key in keys for value in starts.get(key, set())})
        open_values = sorted({value for key in keys for value in opens.get(key, set())})
        current_start = _time(occurrence.get("startTime") or event.get("startTime"))
        current_open = _time(occurrence.get("openTime") or event.get("openTime"))
        if not current_start and len(start_values) == 1:
            occurrence["startTime"] = start_values[0]
            current_start = start_values[0]
        elif current_start and current_open and current_start == current_open:
            credible = [value for value in start_values if value != current_open]
            if len(credible) == 1:
                occurrence["startTime"] = credible[0]
        if not current_open and len(open_values) == 1:
            occurrence["openTime"] = open_values[0]


def _performance_key(event: dict[str, Any], occurrence: dict[str, Any]) -> str:
    group = _text(event.get("group"))
    day = _day(occurrence.get("date"))
    start = _time(occurrence.get("startTime") or event.get("startTime"))
    if day and start:
        return "|".join((group, day, "time", start))
    return "|".join(
        (
            group,
            day,
            "fallback",
            _venue_key(occurrence.get("venue") or event.get("venue")),
            _title_key(event),
        )
    )


def _provider_id(event: dict[str, Any]) -> str:
    for value in (event.get("ticketProvider"), event.get("primarySource"), event.get("sourceType")):
        token = _text(value).casefold()
        if token in {"pia", "lawson", "eplus", "official", "resale", "sukisuki", "kawaii-store", "rakuten", "hmv", "tower"}:
            return token
    for url in _event_urls(event):
        host = urlparse(url).netloc.casefold()
        if "pia.jp" in host:
            return "pia"
        if "l-tike.com" in host:
            return "lawson"
        if "eplus.jp" in host:
            return "eplus"
        if "sukisuki" in host:
            return "sukisuki"
    return "official"


def _is_offer(event: dict[str, Any]) -> bool:
    ticket_type = _text(event.get("ticketType"))
    if not ticket_type or ticket_type == "現在受付なし":
        return False
    return bool(_event_urls(event))


def _offer_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    if not _is_offer(event):
        return None
    offer: dict[str, Any] = {
        "sourceRowId": event.get("id"),
        "provider": _provider_id(event),
        "url": event.get("url"),
        "urls": _event_urls(event),
    }
    for field in TICKET_FIELDS:
        value = deepcopy(event.get(field))
        if value is not None:
            offer[field] = value
    return offer


def _offer_key(offer: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        _text(offer.get(field))
        for field in ("provider", "ticketType", "applyStart", "applyEnd", "resultDate", "paymentEnd", "url")
    )


def _base_score(event: dict[str, Any]) -> tuple[int, int, int, int, str]:
    source_type = _text(event.get("sourceType")).casefold()
    primary = _text(event.get("primarySource")).casefold()
    official = 1 if primary == "official" else 0
    schedule_source = 1 if source_type == "official-schedule" else 0
    no_offer = 1 if not _is_offer(event) else 0
    schedule_size = len(event.get("schedule") or []) if isinstance(event.get("schedule"), list) else 0
    return schedule_source, official, no_offer, schedule_size, _text(event.get("id"))


def _preferred_base(records: list[dict[str, Any]]) -> dict[str, Any]:
    return max((record["event"] for record in records), key=_base_score)


def _canonical_entity(key: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    base = deepcopy(_preferred_base(records))
    occurrence = max(
        (record["occurrence"] for record in records),
        key=lambda item: (
            int(bool(_text(item.get("venue")))),
            int(bool(_time(item.get("startTime")))),
            int(bool(_time(item.get("openTime")))),
        ),
    )
    day = _day(occurrence.get("date"))
    venue = _text(occurrence.get("venue") or base.get("venue"))
    opened = _time(occurrence.get("openTime") or base.get("openTime"))
    start = _time(occurrence.get("startTime") or base.get("startTime"))

    source_ids = _unique_strings(
        [
            *(value for record in records for value in (record["event"].get("sourceRowIds") or [])),
            *(record["event"].get("id") for record in records),
        ]
    )
    all_urls = _unique_strings(
        [value for record in records for value in _event_urls(record["event"])]
    )
    official_urls = [
        value
        for record in records
        if _text(record["event"].get("primarySource")).casefold() == "official"
        for value in _event_urls(record["event"])
    ]

    offers: list[dict[str, Any]] = []
    seen_offers: set[tuple[str, ...]] = set()
    for record in records:
        event = record["event"]
        existing = event.get("offers")
        if isinstance(existing, list):
            for raw_offer in existing:
                if not isinstance(raw_offer, dict):
                    continue
                offer = deepcopy(raw_offer)
                marker = _offer_key(offer)
                if marker not in seen_offers:
                    offers.append(offer)
                    seen_offers.add(marker)
        offer = _offer_from_event(event)
        if offer is not None:
            marker = _offer_key(offer)
            if marker not in seen_offers:
                offers.append(offer)
                seen_offers.add(marker)

    for field in TOP_LEVEL_TICKET_FIELDS:
        base.pop(field, None)
    base["id"] = "performance-" + re.sub(r"[^0-9A-Za-z]+", "-", key).strip("-")[:120]
    base["entityType"] = "performance"
    base["performanceEntityVersion"] = 1
    base["performanceKey"] = key
    base["sourceRowIds"] = source_ids
    base["offers"] = offers
    base["eventDate"] = day
    base["eventEndDate"] = day
    base["eventDates"] = [day] if day else []
    base["eventCount"] = 1
    base["venue"] = venue or None
    if opened:
        base["openTime"] = opened
    else:
        base.pop("openTime", None)
    if start:
        base["startTime"] = start
    else:
        base.pop("startTime", None)
    base["schedule"] = [
        {
            "date": day,
            "venue": venue or None,
            **({"openTime": opened} if opened else {}),
            **({"startTime": start} if start else {}),
        }
    ] if day else []
    base["ticketType"] = "複数受付" if len(offers) > 1 else (_text(offers[0].get("ticketType")) if offers else "現在受付なし")
    base["applicationDisplayMode"] = "offers" if offers else "schedule-only"
    base["applicationStatus"] = "offers" if offers else "none"
    if all_urls:
        base["urls"] = all_urls
        base["url"] = (official_urls[0] if official_urls else all_urls[0])
    if official_urls:
        base["primarySource"] = "official"
    return base


def build_public_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build one hosted live-performance entity per physical performance.

    Acquisition rows remain untouched in ``events``. The returned public model
    folds FC/playguide/etc. rows into ``offers`` while retaining every source row
    id and URL as provenance. Special events, online events, and external
    appearances remain on their existing dedicated paths.
    """
    raw = [deepcopy(event) for event in events if isinstance(event, dict)]
    records: list[dict[str, Any]] = []
    passthrough: list[dict[str, Any]] = []
    for index, event in enumerate(raw):
        if not _is_regular_hosted(event):
            passthrough.append(event)
            continue
        occurrences = _occurrences(event)
        if not occurrences:
            passthrough.append(event)
            continue
        for occurrence_index, occurrence in enumerate(occurrences):
            records.append(
                {
                    "event": event,
                    "occurrence": occurrence,
                    "eventIndex": index,
                    "occurrenceIndex": occurrence_index,
                }
            )

    _reconcile_occurrence_times(records)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        key = _performance_key(record["event"], record["occurrence"])
        grouped.setdefault(key, []).append(record)

    canonical = [_canonical_entity(key, grouped[key]) for key in sorted(grouped)]
    public_events = passthrough + canonical

    source_occurrence_count = len(records)
    merged_source_occurrences = max(0, source_occurrence_count - len(canonical))
    report = {
        "rawEventCount": len(raw),
        "passthroughEventCount": len(passthrough),
        "performanceEntityCount": len(canonical),
        "sourceOccurrenceCount": source_occurrence_count,
        "mergedSourceOccurrences": merged_source_occurrences,
        "offerCount": sum(len(event.get("offers") or []) for event in canonical),
    }
    return public_events, report


def performance_entities(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public, _ = build_public_events(events)
    return [event for event in public if event.get("entityType") == "performance"]
