#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from typing import Any


AUDIT_ID = "P0-sweet-steady-sweet-step-2026-09"
SWEET_STEP_TITLE = "SWEET STEP"
DATE_FIELDS = (
    "salesStartTime",
    "gatheringTime",
    "startTime",
    "openTime",
    "purchaseMethod",
    "ticketName",
    "ticketIssueMethod",
    "numberedCallTimes",
    "parts",
    "ticketBenefits",
)

COMMON_PURCHASE_METHOD = "KAWAII LAB. STOREアプリで商品購入整理券を取得し、会場で対象商品を購入"
COMMON_TICKET_NAME = "商品購入整理券"
COMMON_TICKET_ISSUE_METHOD = "KAWAII LAB. STOREアプリ（1人1回・先着順）"
COMMON_BENEFITS = [
    "＜整理番号付き優先エリア入場券＞…対象商品ご購入のお客様に先着で1枚お渡し(1会計おひとり様1枚まで)",
    "＜お見送り会参加券＞…通常盤1枚ご購入につき1枚お渡し",
]


def _schedule_by_date(event: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in event.get("schedule") or []:
        if not isinstance(row, dict):
            continue
        day = str(row.get("date") or "")[:10]
        if day:
            out[day] = deepcopy(row)
    return out


def _is_target(event: dict[str, Any]) -> bool:
    if event.get("group") != "SWEET STEADY":
        return False
    if event.get("eventCategory") != "release-event":
        return False
    title = " ".join(
        str(event.get(key) or "")
        for key in ("displayTitle", "eventTitle", "title")
    )
    if SWEET_STEP_TITLE not in title:
        return False
    dates = set(_schedule_by_date(event))
    return {"2026-09-05", "2026-09-07", "2026-09-14"}.issubset(dates)


def _number_calls_0905() -> list[dict[str, str]]:
    return [
        {"numbers": "1〜200番", "time": "10:00"},
        {"numbers": "201番〜400番", "time": "10:20"},
        {"numbers": "401番〜600番", "time": "10:40"},
        {"numbers": "601番〜800番", "time": "11:00"},
        {"numbers": "801番〜1000番", "time": "11:20"},
        {"numbers": "1,001番〜", "time": "11:40"},
    ]


def _number_calls_0907() -> list[dict[str, str]]:
    return [
        {"numbers": "1〜200番", "time": "11:50"},
        {"numbers": "201番〜400番", "time": "12:10"},
        {"numbers": "401番〜600番", "time": "12:30"},
        {"numbers": "601番〜800番", "time": "12:50"},
        {"numbers": "801番〜1000番", "time": "13:10"},
        {"numbers": "1,001番〜", "time": "13:30"},
    ]


def _verified_detail(
    *,
    venue: str | None,
    sales: str,
    gathering: str,
    start: str,
    calls: list[dict[str, str]],
    source_url: str,
) -> dict[str, Any]:
    return {
        "venue": venue,
        "salesStartTime": sales,
        "gatheringTime": gathering,
        "startTime": start,
        "purchaseMethod": COMMON_PURCHASE_METHOD,
        "ticketName": COMMON_TICKET_NAME,
        "ticketIssueMethod": COMMON_TICKET_ISSUE_METHOD,
        "numberedCallTimes": calls,
        "ticketBenefits": deepcopy(COMMON_BENEFITS),
        "specialDetailsStatus": "verified",
        "sourceUrl": source_url,
    }


def apply_known_occurrence_corrections(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply audited, source-backed per-date corrections without splitting the canonical series."""
    corrected = deepcopy(payload)
    report = {"auditCorrectionId": AUDIT_ID, "matched": 0, "changed": 0}

    for event in corrected.get("events") or []:
        if not isinstance(event, dict) or not _is_target(event):
            continue
        report["matched"] += 1
        before = deepcopy(event)
        schedule = _schedule_by_date(event)

        for field in DATE_FIELDS:
            event.pop(field, None)

        event["displayByOccurrence"] = True
        event["occurrenceDetails"] = {
            "2026-09-05": _verified_detail(
                venue=schedule["2026-09-05"].get("venue"),
                sales="10:10",
                gathering="13:20",
                start="14:00",
                calls=_number_calls_0905(),
                source_url="https://sweetsteady.asobisystem.com/news/detail/88315",
            ),
            "2026-09-07": _verified_detail(
                venue=schedule["2026-09-07"].get("venue"),
                sales="12:00",
                gathering="16:00",
                start="16:30",
                calls=_number_calls_0907(),
                source_url="https://sweetsteady.asobisystem.com/news/detail/89031",
            ),
            "2026-09-14": {
                "venue": schedule["2026-09-14"].get("venue"),
                "specialDetailsStatus": "awaiting-details",
                "sourceUrl": "https://sweetsteady.asobisystem.com/live_information/detail/44456",
            },
        }

        audit_ids = [str(x) for x in event.get("auditCorrectionIds") or [] if x]
        if AUDIT_ID not in audit_ids:
            audit_ids.append(AUDIT_ID)
        event["auditCorrectionIds"] = audit_ids

        if event != before:
            report["changed"] += 1

    return corrected, report


def expand_occurrence_views(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand only explicitly marked canonical events into date-scoped display rows."""
    out: list[dict[str, Any]] = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        details = event.get("occurrenceDetails")
        schedule = event.get("schedule")
        if event.get("displayByOccurrence") is not True or not isinstance(details, dict) or not isinstance(schedule, list):
            out.append(deepcopy(event))
            continue

        for index, row in enumerate(schedule):
            if not isinstance(row, dict):
                continue
            day = str(row.get("date") or "")[:10]
            if not day:
                continue
            occurrence = details.get(day)
            if not isinstance(occurrence, dict):
                occurrence = {}

            view = deepcopy(event)
            parent_id = str(event.get("id") or "special-event")
            view["id"] = f"{parent_id}--{day}" + (f"-{index}" if index else "")
            view["seriesId"] = parent_id
            view["eventDate"] = day
            view["eventDates"] = [day]
            view["eventEndDate"] = day
            view["eventCount"] = 1
            view["schedule"] = [deepcopy(row)]
            if row.get("venue"):
                view["venue"] = row["venue"]
            if row.get("openTime"):
                view["openTime"] = row["openTime"]
            if row.get("startTime"):
                view["startTime"] = row["startTime"]

            for key, value in occurrence.items():
                if key == "sourceUrl":
                    continue
                if value is None:
                    view.pop(key, None)
                else:
                    view[key] = deepcopy(value)

            source_url = occurrence.get("sourceUrl")
            if source_url:
                view["url"] = source_url
                urls: list[str] = []
                for value in [source_url, *(view.get("urls") or [])]:
                    if value and value not in urls:
                        urls.append(value)
                view["urls"] = urls

            view.pop("occurrenceDetails", None)
            view.pop("displayByOccurrence", None)
            out.append(view)

    return out
