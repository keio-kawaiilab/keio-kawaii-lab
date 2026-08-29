#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

from dedupe_official_x_series import all_urls, category, merge_schedules, schedule_rows, text

DATA_PATH = Path("data/live-events.json")
SPECIAL_CATEGORIES = {"release-event", "large-benefit"}
SALE_FIELDS = (
    "ticketProvider", "ticketType", "applyStart", "applyEnd", "resultDate", "paymentEnd",
    "applicationStatus", "applicationWindowVerified", "purchaseMethod", "ticketIssueMethod",
    "ticketName", "product", "salesStartTime", "gatheringTime",
)
LIST_FIELDS = ("participants", "ticketBenefits", "numberedCallTimes", "parts", "sourceCandidates")
SALES_PROVIDERS = {"sukisuki", "hmv", "tower", "rakuten", "kawaii-store", "pia", "lawson", "eplus"}


def compact(value: object) -> str:
    return re.sub(r"[\s　・･·|｜!！?？\-–—_()（）\[\]【】『』「」]+", "", text(value)).casefold()


def normalized_series_title(event: dict) -> str:
    value = text(event.get("displayTitle") or event.get("eventTitle") or event.get("title"))
    group = text(event.get("group"))
    if group:
        value = re.sub(rf"^[【〖\[]?\s*{re.escape(group)}\s*[】〗\]]?\s*", "", value, flags=re.I)
    value = re.sub(r"^(?:20\d{2}[./年-])?\d{1,2}[./月-]\d{1,2}日?(?:\([^)]*\)|（[^）]*）)?\s*", "", value)
    value = re.sub(r"(?:@|＠).+$", "", value)
    value = re.sub(r"のファンクラブ限定部.*$", "", value)
    return compact(value)


def normalized_product(event: dict) -> str:
    value = compact(event.get("product"))
    value = re.sub(r"(?:通常盤|初回盤|税込|税抜|円|¥|\\)[0-9,.]*", "", value)
    return value


def venue_key(value: object) -> str:
    value = text(value).casefold()
    value = re.sub(r"^(?:北海道|東京都|京都府|大阪府|.{2,3}県)\s*", "", value)
    return compact(value)


def occurrence_keys(event: dict) -> set[tuple[str, str]]:
    return {(str(row.get("date") or "")[:10], venue_key(row.get("venue"))) for row in schedule_rows(event)}


def provider(event: dict) -> str:
    raw = text(event.get("ticketProvider") or event.get("primarySource") or event.get("sourceType")).lower()
    joined = " ".join(all_urls(event)).lower()
    if "sukisuki-shop.com" in joined:
        return "sukisuki"
    if "hmv.co.jp" in joined:
        return "hmv"
    if "tower.jp" in joined:
        return "tower"
    if "rakuten" in joined or "r10.to" in joined:
        return "rakuten"
    if "kawaiilab.goods-order.com" in joined:
        return "kawaii-store"
    if "t.pia.jp" in joined:
        return "pia"
    if "l-tike.com" in joined:
        return "lawson"
    if "eplus.jp" in joined:
        return "eplus"
    return raw if raw in SALES_PROVIDERS else "official"


def is_offer_row(event: dict) -> bool:
    if text(event.get("ticketType")) == "現在受付なし" or str(event.get("applicationStatus") or "").lower() == "none":
        return False
    p = provider(event)
    return bool(
        event.get("applyStart")
        or event.get("applyEnd")
        or event.get("ticketProvider")
        or p in SALES_PROVIDERS
    )


def official_source_urls(event: dict) -> list[str]:
    values = []
    for value in all_urls(event):
        if "asobisystem.com" in value or re.search(r"https://x\.com/[^/]+/status/\d+", value, re.I):
            if value not in values:
                values.append(value)
    return values


def offer_from_event(event: dict) -> dict:
    values = all_urls(event)
    p = provider(event)
    preferred = next((u for u in values if (
        (p == "sukisuki" and "sukisuki-shop.com" in u)
        or (p == "hmv" and "hmv.co.jp" in u)
        or (p == "tower" and "tower.jp" in u)
        or (p == "rakuten" and ("rakuten" in u or "r10.to" in u))
        or (p == "kawaii-store" and "kawaiilab.goods-order.com" in u)
        or (p == "pia" and "t.pia.jp" in u)
        or (p == "lawson" and "l-tike.com" in u)
        or (p == "eplus" and "eplus.jp" in u)
    )), values[0] if values else "")
    offer = {
        "sourceRowId": event.get("id"),
        "provider": p,
        "url": preferred,
        "urls": values,
    }
    for field in SALE_FIELDS:
        if event.get(field) not in (None, "", [], {}):
            offer[field] = copy.deepcopy(event[field])
    offer["ticketProvider"] = p
    return offer


def offer_key(offer: dict) -> tuple:
    return (
        text(offer.get("provider") or offer.get("ticketProvider")).lower(),
        compact(offer.get("ticketType")),
        text(offer.get("applyStart")),
        text(offer.get("applyEnd")),
        text(offer.get("url")),
    )


def compatible_release(a: dict, b: dict) -> bool:
    if text(a.get("group")) != text(b.get("group")) or category(a) != category(b):
        return False
    if normalized_series_title(a) != normalized_series_title(b):
        return False
    pa, pb = normalized_product(a), normalized_product(b)
    if pa and pb and pa != pb:
        return False
    return True


def compatible_benefit(a: dict, b: dict) -> bool:
    if text(a.get("group")) != text(b.get("group")) or category(a) != category(b):
        return False
    if normalized_series_title(a) != normalized_series_title(b):
        return False
    left, right = occurrence_keys(a), occurrence_keys(b)
    if left.intersection(right):
        return True
    left_days = {day for day, _ in left}
    right_days = {day for day, _ in right}
    if not left_days.intersection(right_days):
        return False
    return any(not venue for _, venue in left) or any(not venue for _, venue in right)


def components(items: list[dict], related) -> list[list[dict]]:
    remaining = list(items)
    output: list[list[dict]] = []
    while remaining:
        component = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            keep = []
            for item in remaining:
                if any(related(item, current) for current in component):
                    component.append(item)
                    changed = True
                else:
                    keep.append(item)
            remaining = keep
        output.append(component)
    return output


def richness(event: dict) -> tuple[int, int, int, int]:
    official = len(official_source_urls(event))
    filled = sum(value not in (None, "", [], {}) for value in event.values())
    details = sum(len(event.get(field) or []) for field in LIST_FIELDS if isinstance(event.get(field), list))
    return official, details, filled, len(all_urls(event))


def distinct_dicts(values: Iterable[object]) -> list:
    output = []
    seen = set()
    for value in values:
        if value in (None, "", [], {}):
            continue
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if marker in seen:
            continue
        seen.add(marker)
        output.append(copy.deepcopy(value))
    return output


def merge_list_fields(entity: dict, items: list[dict]) -> None:
    for field in LIST_FIELDS:
        merged = distinct_dicts(value for item in items for value in (item.get(field) or []) if isinstance(item.get(field), list))
        if merged:
            entity[field] = merged


def canonical_key(items: list[dict], schedule: list[dict]) -> str:
    first = items[0]
    group = text(first.get("group"))
    cat = category(first)
    title = normalized_series_title(first)
    product = next((normalized_product(item) for item in items if normalized_product(item)), "")
    if cat == "release-event":
        return "|".join((group, cat, title, product))
    occurrence = schedule[0] if schedule else {}
    return "|".join((group, cat, title, str(occurrence.get("date") or ""), venue_key(occurrence.get("venue"))))


def make_entity(items: list[dict]) -> dict:
    representative = max(items, key=richness)
    entity = copy.deepcopy(representative)
    schedule = merge_schedules(items)
    dates = list(dict.fromkeys(row["date"] for row in schedule if row.get("date")))
    venues = list(dict.fromkeys(text(row.get("venue")) for row in schedule if text(row.get("venue"))))
    key = canonical_key(items, schedule)
    canonical_id = "special-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    offers = []
    seen_offers = set()
    for item in items:
        existing = item.get("offers") if isinstance(item.get("offers"), list) else []
        source_offers = [dict(value) for value in existing if isinstance(value, dict)]
        if is_offer_row(item):
            source_offers.append(offer_from_event(item))
        for offer in source_offers:
            marker = offer_key(offer)
            if marker in seen_offers:
                continue
            seen_offers.add(marker)
            offers.append(offer)

    source_urls = []
    for item in items:
        for value in all_urls(item):
            if value not in source_urls:
                source_urls.append(value)
    source_row_ids = list(dict.fromkeys(str(item.get("id")) for item in items if item.get("id")))

    entity["id"] = canonical_id
    entity["entityType"] = "special-event"
    entity["specialEventEntityVersion"] = 1
    entity["sourceRowIds"] = source_row_ids
    entity["offers"] = offers
    entity["eventCategory"] = category(representative)
    entity["schedule"] = schedule
    entity["eventCount"] = len(schedule)
    if dates:
        entity["eventDate"] = dates[0]
        entity["eventDates"] = dates
        entity["eventEndDate"] = dates[-1]
    if venues:
        entity["venues"] = venues
        entity["venue"] = venues[0] if len(venues) == 1 else f"複数会場（全{len(schedule)}公演）"
    entity["urls"] = source_urls
    official = next((u for u in source_urls if "asobisystem.com" in u), None) or next(
        (u for u in source_urls if re.search(r"https://x\.com/[^/]+/status/\d+", u, re.I)), None
    )
    if official:
        entity["url"] = official
    elif source_urls:
        entity["url"] = source_urls[0]

    merge_list_fields(entity, items)

    # Sale/lot rows are children of the event entity. The parent stays a neutral
    # schedule record so one real-world event can never become multiple cards.
    for field in ("ticketProvider", "applyStart", "applyEnd", "resultDate", "paymentEnd", "applicationWindowVerified"):
        entity.pop(field, None)
    entity["ticketType"] = "現在受付なし"
    entity["applicationStatus"] = "none"
    entity["applicationDisplayMode"] = "offers" if offers else "schedule-only"
    if not offers:
        entity.setdefault("specialDetailsStatus", "awaiting-details")

    if any(str(item.get("sourceType") or "").startswith("official") for item in items):
        if any(str(item.get("sourceType") or "") == "official-special" for item in items):
            entity["sourceType"] = "official-special"
        elif any(str(item.get("sourceType") or "") == "official-social" for item in items):
            entity["sourceType"] = "official-social"
        entity["primarySource"] = "official"
    if any(not item.get("sourceStale") for item in items):
        for field in ("sourceStale", "sourceStaleSince", "releaseRetentionReason"):
            entity.pop(field, None)
    return entity


def normalize_events(events: list[dict]) -> tuple[list[dict], dict]:
    ordinary = []
    releases = []
    benefits = []
    already_canonical = 0
    for raw in events:
        event = copy.deepcopy(raw)
        cat = category(event)
        if cat not in SPECIAL_CATEGORIES:
            ordinary.append(event)
        elif cat == "release-event":
            releases.append(event)
            already_canonical += int(event.get("entityType") == "special-event")
        else:
            benefits.append(event)
            already_canonical += int(event.get("entityType") == "special-event")

    release_components = components(releases, compatible_release)
    benefit_components = components(benefits, compatible_benefit)
    entities = [make_entity(component) for component in release_components + benefit_components]
    result = ordinary + entities
    result.sort(key=lambda event: (
        str(event.get("eventDate") or "9999-12-31"),
        str(event.get("group") or ""),
        str(event.get("eventCategory") or ""),
        str(event.get("id") or ""),
    ))
    source_special_rows = len(releases) + len(benefits)
    return result, {
        "sourceSpecialRows": source_special_rows,
        "canonicalSpecialEvents": len(entities),
        "rowsCollapsed": max(0, source_special_rows - len(entities)),
        "releaseEventEntities": len(release_components),
        "largeBenefitEntities": len(benefit_components),
        "alreadyCanonicalRows": already_canonical,
    }


def normalize_payload(payload: dict) -> tuple[dict, dict]:
    rows = [dict(event) for event in payload.get("events", []) if isinstance(event, dict)]
    normalized, report = normalize_events(rows)
    out = dict(payload)
    out["events"] = normalized
    out["specialEventNormalization"] = report
    return out, report


def validate(payload: dict) -> list[str]:
    errors = []
    seen_ids = set()
    for event in payload.get("events", []):
        if not isinstance(event, dict):
            continue
        event_id = text(event.get("id"))
        if event_id and event_id in seen_ids:
            errors.append(f"duplicate event id after normalization: {event_id}")
        seen_ids.add(event_id)
        if category(event) not in SPECIAL_CATEGORIES:
            continue
        if event.get("entityType") != "special-event" or event.get("specialEventEntityVersion") != 1:
            errors.append(f"special row is not canonical: {event_id or event.get('title')}")
        seen_offers = set()
        for offer in event.get("offers") or []:
            if not isinstance(offer, dict):
                errors.append(f"invalid offer child: {event_id}")
                continue
            marker = offer_key(offer)
            if marker in seen_offers:
                errors.append(f"duplicate offer child: {event_id} {marker}")
            seen_offers.add(marker)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize release events and large benefit events into one event entity with child sale offers")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = json.loads(args.data.read_text(encoding="utf-8"))
    normalized, report = normalize_payload(payload)
    errors = validate(normalized)
    if args.check:
        print(json.dumps({**report, "errors": errors}, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    args.data.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**report, "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
