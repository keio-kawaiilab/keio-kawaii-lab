#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import install_performance_public_view as _view
from performance_entities import TOP_LEVEL_TICKET_FIELDS, _offer_from_event
from schedule_scope import HOSTED, infer_event_scope


DATA = Path("data/live-events.json")
PAGE = Path("schedule.html")

KAWACOLLE_FAMILY = "kawacolle-tgc"
LIVE_OR_TREAT_FAMILY = "fm-osaka-live-or-treat-2026"

KAWACOLLE_RE = re.compile(r"(?:KAWAII\s*LAB\.?\s*)?COLLECTION\s+produced\s+by\s+TGC", re.I)
LIVE_OR_TREAT_RE = re.compile(r"FM(?:大阪|\s*OSAKA).*Live\s*or\s*Treat\s*2026", re.I)
ANNOUNCEMENT_RE = re.compile(r"開催決定|出演決定|受付開始|抽選受付|お知らせ", re.I)

FAMILY_PROVENANCE = {
    KAWACOLLE_FAMILY: {
        "correctionId": "P2-external-kawacolle-tgc",
        "sourceUrl": "https://tgc.girlswalker.com/kawacolle/",
        "organizer": "KAWAII LAB. COLLECTION実行委員会",
    },
    LIVE_OR_TREAT_FAMILY: {
        "correctionId": "P2-external-fm-osaka-live-or-treat-2026",
        "sourceUrl": "https://morestar.asobisystem.com/news/detail/89194",
        "organizer": "FM大阪",
    },
}

PARTICIPANT_ORDER = [
    "FRUITS ZIPPER",
    "CANDY TUNE",
    "SWEET STEADY",
    "CUTIE STREET",
    "MORE STAR",
    "KAWAII LAB. SOUTH",
]


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _title_text(event: dict[str, Any]) -> str:
    return " ".join(
        _text(event.get(field))
        for field in ("eventTitle", "displayTitle", "title")
        if _text(event.get(field))
    )


def _family(event: dict[str, Any]) -> str:
    text = _title_text(event)
    if KAWACOLLE_RE.search(text):
        return KAWACOLLE_FAMILY
    if LIVE_OR_TREAT_RE.search(text):
        return LIVE_OR_TREAT_FAMILY
    return ""


def _day(event: dict[str, Any]) -> str:
    if event.get("eventDate"):
        return str(event.get("eventDate"))[:10]
    for row in event.get("schedule") or []:
        if isinstance(row, dict) and row.get("date"):
            return str(row.get("date"))[:10]
    for value in event.get("eventDates") or []:
        if value:
            return str(value)[:10]
    return ""


def _venue_key(value: Any) -> str:
    text = _text(value).casefold()
    text = re.sub(r"^(?:北海道|東京都|京都府|大阪府|.{2,3}県)\s*", "", text)
    return re.sub(r"[\s　!！・･|｜\-–—_\[\]()（）『』「」,，.。〒]", "", text)


def _event_urls(event: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for value in [event.get("url"), *(event.get("urls") or [])]:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def _merge_unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def _candidate_titles(rows: list[dict[str, Any]], family: str) -> list[str]:
    candidates: list[str] = []
    matcher = KAWACOLLE_RE if family == KAWACOLLE_FAMILY else LIVE_OR_TREAT_RE
    for row in rows:
        for field in ("eventTitle", "displayTitle", "title"):
            value = _text(row.get(field))
            if value and matcher.search(value) and value not in candidates:
                candidates.append(value)
    return candidates


def _canonical_title(rows: list[dict[str, Any]], family: str) -> str:
    candidates = _candidate_titles(rows, family)
    if not candidates:
        return _text(rows[0].get("eventTitle") or rows[0].get("displayTitle") or rows[0].get("title"))

    def score(value: str) -> tuple[int, int, int]:
        full_name = 0
        if family == KAWACOLLE_FAMILY and re.search(r"KAWAII\s*LAB\.?\s*COLLECTION", value, re.I):
            full_name = 1
        if family == LIVE_OR_TREAT_FAMILY and re.search(r"FM(?:大阪|\s*OSAKA)", value, re.I):
            full_name = 1
        clean = int(not ANNOUNCEMENT_RE.search(value) and not re.match(r"^20\d{2}[.年/-]", value))
        return full_name, clean, -len(value)

    return max(candidates, key=score)


def _offer_marker(offer: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        _text(offer.get(field)).casefold() if field == "provider" else _text(offer.get(field))
        for field in ("provider", "ticketType", "applyStart", "applyEnd", "resultDate", "paymentEnd")
    )


def _prefer_offer_url(current: str, candidate: str, family: str) -> str:
    if not current:
        return candidate
    if not candidate:
        return current
    if family == KAWACOLLE_FAMILY:
        current_central = "kawaiilab.asobisystem.com" in current
        candidate_central = "kawaiilab.asobisystem.com" in candidate
        if candidate_central and not current_central:
            return candidate
    return current


def _merged_offers(rows: list[dict[str, Any]], family: str) -> list[dict[str, Any]]:
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    order: list[tuple[str, ...]] = []
    for row in rows:
        offers = [deepcopy(item) for item in row.get("offers") or [] if isinstance(item, dict)]
        if not offers:
            generated = _offer_from_event(row)
            if generated is not None:
                offers.append(generated)
        for offer in offers:
            marker = _offer_marker(offer)
            if marker not in merged:
                merged[marker] = offer
                order.append(marker)
                continue
            target = merged[marker]
            urls = _merge_unique(
                [target.get("url"), *(target.get("urls") or []), offer.get("url"), *(offer.get("urls") or [])]
            )
            if urls:
                target["urls"] = urls
            chosen = _prefer_offer_url(_text(target.get("url")), _text(offer.get("url")), family)
            if chosen:
                target["url"] = chosen
    return [merged[marker] for marker in order]


def _participants(rows: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for row in rows:
        for value in row.get("participants") or []:
            text = _text(value)
            if text and text not in values:
                values.append(text)
        group = _text(row.get("group"))
        if group and group not in {"KAWAII LAB.合同", "KAWAII LAB."} and group not in values:
            values.append(group)
    ordered = [group for group in PARTICIPANT_ORDER if group in values]
    ordered.extend(sorted(group for group in values if group not in ordered))
    return ordered


def _best_base(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def score(row: dict[str, Any]) -> tuple[int, int, int, int]:
        title = _text(row.get("eventTitle") or row.get("displayTitle") or row.get("title"))
        return (
            int(bool(_text(row.get("venue")))),
            int(bool(_text(row.get("startTime")))),
            len(row.get("offers") or []),
            int(not ANNOUNCEMENT_RE.search(title)),
        )

    return deepcopy(max(rows, key=score))


def _merge_family_rows(rows: list[dict[str, Any]], family: str) -> dict[str, Any]:
    base = _best_base(rows)
    provenance = FAMILY_PROVENANCE[family]
    title = _canonical_title(rows, family)
    participants = _participants(rows)
    offers = _merged_offers(rows, family)
    day = _day(base) or next((_day(row) for row in rows if _day(row)), "")
    start = _text(base.get("startTime")) or next((_text(row.get("startTime")) for row in rows if _text(row.get("startTime"))), "")
    opened = _text(base.get("openTime")) or next((_text(row.get("openTime")) for row in rows if _text(row.get("openTime"))), "")
    venue = _text(base.get("venue")) or next((_text(row.get("venue")) for row in rows if _text(row.get("venue"))), "")

    source_ids = _merge_unique(
        [
            value
            for row in rows
            for value in (row.get("sourceRowIds") or ([row.get("id")] if row.get("id") else []))
        ]
    )
    public_ids = _merge_unique([row.get("id") for row in rows])
    urls = _merge_unique([value for row in rows for value in _event_urls(row)])

    for field in TOP_LEVEL_TICKET_FIELDS:
        base.pop(field, None)

    base["eventScope"] = "external"
    base["eventScopeCorrectionId"] = provenance["correctionId"]
    base["eventScopeSource"] = "verified-organizer"
    base["eventScopeSourceUrl"] = provenance["sourceUrl"]
    base["organizer"] = provenance["organizer"]
    base["externalEventFamily"] = family
    base["entityType"] = "performance"
    base["performanceEntityVersion"] = 1
    base["eventDate"] = day or None
    base["eventEndDate"] = day or None
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
    if day:
        base["schedule"] = [{
            "date": day,
            "venue": venue or None,
            **({"openTime": opened} if opened else {}),
            **({"startTime": start} if start else {}),
        }]
    base["offers"] = offers
    base["ticketType"] = "複数受付" if len(offers) > 1 else (_text(offers[0].get("ticketType")) if offers else "現在受付なし")
    base["applicationDisplayMode"] = "offers" if offers else "schedule-only"
    base["applicationStatus"] = "offers" if offers else "none"
    base["sourceRowIds"] = source_ids
    base["mergedPublicEventIds"] = public_ids
    if urls:
        base["urls"] = urls
        preferred = next((url for url in urls if family == KAWACOLLE_FAMILY and "kawaiilab.asobisystem.com" in url), "")
        if not preferred and family == LIVE_OR_TREAT_FAMILY:
            preferred = next((url for url in urls if "morestar.asobisystem.com" in url), "")
        base["url"] = preferred or urls[0]

    if title:
        base["title"] = title
        base["eventTitle"] = title
        base["displayTitle"] = title

    if family == KAWACOLLE_FAMILY:
        base["group"] = "KAWAII LAB.合同"
        base["participants"] = participants
    elif participants:
        base["participants"] = participants

    key = "|".join(("external", family, day, start, _venue_key(venue)))
    base["performanceKey"] = key
    base["id"] = "performance-" + re.sub(r"[^0-9A-Za-z]+", "-", key).strip("-")[:120]
    return base


def _mark_raw_external(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    result: list[dict[str, Any]] = []
    changed = 0
    for event in events:
        row = deepcopy(event)
        family = _family(row)
        if family:
            provenance = FAMILY_PROVENANCE[family]
            if row.get("eventScope") != "external":
                changed += 1
            row["eventScope"] = "external"
            row["eventScopeCorrectionId"] = provenance["correctionId"]
            row["eventScopeSource"] = "verified-organizer"
            row["eventScopeSourceUrl"] = provenance["sourceUrl"]
            row["organizer"] = provenance["organizer"]
        result.append(row)
    return result, changed


def normalize_public_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows = [deepcopy(event) for event in events if isinstance(event, dict)]
    buckets: dict[tuple[str, str], list[int]] = {}
    for index, row in enumerate(rows):
        family = _family(row)
        if not family:
            continue
        buckets.setdefault((family, _day(row)), []).append(index)

    replacements: dict[int, dict[str, Any]] = {}
    removed: set[int] = set()
    collapsed = 0
    corrected = 0
    for (family, _), indices in buckets.items():
        family_rows = [rows[index] for index in indices]
        merged = _merge_family_rows(family_rows, family)
        replacements[indices[0]] = merged
        removed.update(indices[1:])
        collapsed += max(0, len(indices) - 1)
        corrected += 1

    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if index in removed:
            continue
        normalized.append(replacements.get(index, row))
    return normalized, {"familiesCorrected": corrected, "publicRowsCollapsed": collapsed}


def _replace_snapshot(page: str, events: list[dict[str, Any]]) -> str:
    snapshot_match = re.search(
        r'<script id="snapshot-data" type="application/json">([\s\S]*?)</script>',
        page,
    )
    if not snapshot_match:
        raise RuntimeError("schedule snapshot-data is missing")
    snapshot = json.loads(snapshot_match.group(1))
    normalized, _ = normalize_public_events(snapshot.get("events") or [])
    snapshot["events"] = normalized
    encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return page[: snapshot_match.start(1)] + encoded + page[snapshot_match.end(1) :]


def _replace_static_cards(page: str) -> str:
    snapshot_match = re.search(
        r'<script id="snapshot-data" type="application/json">([\s\S]*?)</script>',
        page,
    )
    if not snapshot_match:
        raise RuntimeError("schedule snapshot-data is missing after external normalization")
    snapshot = json.loads(snapshot_match.group(1))
    default_visible = [
        event
        for event in snapshot.get("events") or []
        if isinstance(event, dict) and infer_event_scope(event) == HOSTED
    ]
    cards = "\n".join(_view._build_public_card(event) for event in default_visible)
    page, count = re.subn(
        r'(<div class="cards" id="cards">).*?(</div>\s*<script id="snapshot-data")',
        lambda match: match.group(1) + "\n" + cards + "\n" + match.group(2),
        page,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("could not rebuild default cards after external event normalization")
    page = re.sub(
        r'<div class="summary" id="summary">.*?</div>',
        f'<div class="summary" id="summary">{len(default_visible)}公演を掲載中（KAWAII LAB.主催のみ）</div>',
        page,
        count=1,
        flags=re.S,
    )
    return page


def _validate_known_public_events(events: list[dict[str, Any]]) -> None:
    kawacolle = [
        event for event in events
        if _family(event) == KAWACOLLE_FAMILY and _day(event) == "2026-10-12"
    ]
    if kawacolle:
        if len(kawacolle) != 1:
            raise RuntimeError(f"Kawacolle 2026-10-12 must be one public event, got {len(kawacolle)}")
        if kawacolle[0].get("eventScope") != "external":
            raise RuntimeError("Kawacolle 2026-10-12 is not external in the public model")

    live_or_treat = [
        event for event in events
        if _family(event) == LIVE_OR_TREAT_FAMILY and _day(event) == "2026-10-17"
    ]
    if live_or_treat:
        if len(live_or_treat) != 1:
            raise RuntimeError(f"Live or Treat 2026-10-17 must be one public event, got {len(live_or_treat)}")
        if live_or_treat[0].get("eventScope") != "external":
            raise RuntimeError("Live or Treat 2026-10-17 is not external in the public model")


def main() -> int:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    raw_events, raw_changed = _mark_raw_external(
        [event for event in payload.get("events") or [] if isinstance(event, dict)]
    )
    public_events, report = normalize_public_events(
        [event for event in payload.get("publicEvents") or [] if isinstance(event, dict)]
    )
    _validate_known_public_events(public_events)

    payload["events"] = raw_events
    payload["publicEvents"] = public_events
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    page = PAGE.read_text(encoding="utf-8")
    page = _replace_snapshot(page, public_events)
    page = _replace_static_cards(page)
    PAGE.write_text(page, encoding="utf-8")

    print(json.dumps({"externalRawScopesCorrected": raw_changed, **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
