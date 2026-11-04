"""Collapse duplicate parses of the verified 2026-11-06 joint free live."""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable


ARTICLE = "https://kawaiilab.asobisystem.com/news/detail/93695"
DAY = "2026-11-06"
TITLE = "KAWAII LAB. ファンクラブ限定フリーライブ"
VENUE = "東京都 東京ガーデンシアター"
PARTICIPANTS = ["CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR"]


def _urls(event: dict) -> list[str]:
    values = [event.get("url"), *(event.get("urls") or [])]
    return list(dict.fromkeys(str(value) for value in values if value))


def _matches(event: dict) -> bool:
    title = str(event.get("eventTitle") or event.get("title") or "")
    return (
        str(event.get("eventDate") or "")[:10] == DAY
        and "ファンクラブ限定フリーライブ" in title
        and "東京ガーデンシアター" in str(event.get("venue") or "")
        and ARTICLE in _urls(event)
    )


def collapse(events: Iterable[dict]) -> tuple[list[dict], dict]:
    """Keep one canonical row for duplicate parses of the same NEWS article.

    Different group SCHEDULE URLs are retained as provenance rows.  Only the
    identical central article is collapsed, so distinct receptions or shows
    are never combined by a loose title/date heuristic.
    """
    rows = [deepcopy(event) for event in events if isinstance(event, dict)]
    matches = [event for event in rows if _matches(event)]
    report = {"verifiedFreeLiveRowsCollapsed": 0, "verifiedFreeLiveIds": []}
    if not matches:
        return rows, report

    target = max(
        matches,
        key=lambda event: (
            str(event.get("startTime") or "") == "18:00",
            len(event.get("offers") or []),
            str(event.get("group") or "") == "KAWAII LAB.合同",
        ),
    )
    source_row_ids = list(dict.fromkeys(
        str(value)
        for event in matches
        for value in (event.get("sourceRowIds") or [event.get("id")])
        if value
    ))
    all_urls = list(dict.fromkeys(url for event in matches for url in _urls(event)))
    fact_sources = list(dict.fromkeys(
        str(value)
        for event in matches
        for value in (event.get("performanceFactSources") or [])
        if value
    ))
    richest_offers = max(
        (event.get("offers") or [] for event in matches),
        key=len,
        default=[],
    )
    target.update({
        "group": "KAWAII LAB.合同",
        "participants": list(PARTICIPANTS),
        "title": TITLE,
        "eventTitle": TITLE,
        "eventDate": DAY,
        "eventEndDate": DAY,
        "eventDates": [DAY],
        "eventCount": 1,
        "venue": VENUE,
        "openTime": "16:30",
        "startTime": "18:00",
        "schedule": [{
            "date": DAY,
            "venue": VENUE,
            "openTime": "16:30",
            "startTime": "18:00",
        }],
        "url": ARTICLE,
        "urls": all_urls,
        "sourceRowIds": source_row_ids,
        "performanceFactSources": fact_sources,
        "eventScope": "kawaii-lab",
    })
    if richest_offers:
        target["offers"] = deepcopy(richest_offers)
        target["applicationDisplayMode"] = "offers"

    first_index = min(rows.index(event) for event in matches)
    removed_ids = [str(event.get("id") or "") for event in matches if event is not target]
    match_objects = {id(event) for event in matches}
    rows = [event for event in rows if id(event) not in match_objects]
    rows.insert(first_index, target)
    report["verifiedFreeLiveRowsCollapsed"] = len(removed_ids)
    report["verifiedFreeLiveIds"] = removed_ids
    return rows, report

