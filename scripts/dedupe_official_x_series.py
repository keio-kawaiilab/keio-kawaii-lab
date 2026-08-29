#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

DATA_PATH = Path("data/live-events.json")
SPECIAL_CATEGORIES = {"release-event", "large-benefit", "large-benefit-event"}
X_STATUS_RE = re.compile(r"https://x\.com/[^/]+/status/\d+", re.I)


def text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def distinct(values):
    result = []
    seen = set()
    for value in values:
        if value in (None, "") or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def category(event: dict) -> str:
    value = str(event.get("eventCategory") or "").lower()
    if value == "large-benefit-event":
        return "large-benefit"
    if value in {"release-event", "large-benefit"}:
        return value
    title = text(event.get("displayTitle") or event.get("eventTitle") or event.get("title"))
    if "大特典会" in title:
        return "large-benefit"
    if re.search(r"リリースイベント|リリイベ|発売記念イベント", title):
        return "release-event"
    return ""


def normalized_title(event: dict) -> str:
    value = text(event.get("displayTitle") or event.get("eventTitle") or event.get("title"))
    group = text(event.get("group"))
    if group:
        value = re.sub(rf"^[【〖]?\s*{re.escape(group)}\s*[】〗]?\s*", "", value, flags=re.I)
    value = value.replace("／", "/").replace("｜", "|")
    return re.sub(r"[\s　]+", "", value).casefold()


def all_urls(event: dict) -> list[str]:
    values = [str(value) for value in event.get("urls") or [] if value]
    primary = str(event.get("url") or "").strip()
    if primary and primary not in values:
        values.insert(0, primary)
    return distinct(values)


def x_urls(event: dict) -> set[str]:
    return {value for value in all_urls(event) if X_STATUS_RE.fullmatch(value)}


def is_official_x_schedule_row(event: dict) -> bool:
    if category(event) not in {"release-event", "large-benefit"}:
        return False
    if event.get("applyStart") or event.get("applyEnd"):
        return False
    if str(event.get("sourceChannel") or "").lower() != "official-x":
        return False
    return bool(x_urls(event))


def schedule_rows(event: dict) -> list[dict]:
    raw = event.get("schedule")
    if isinstance(raw, list) and raw:
        rows = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            day = str(item.get("date") or "")[:10]
            if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", day):
                continue
            row = {"date": day, "venue": text(item.get("venue")) or None}
            if item.get("openTime"):
                row["openTime"] = item["openTime"]
            if item.get("startTime"):
                row["startTime"] = item["startTime"]
            rows.append(row)
        if rows:
            return rows

    days = []
    if isinstance(event.get("eventDates"), list):
        days.extend(str(value)[:10] for value in event["eventDates"] if value)
    if not days and event.get("eventDate"):
        days.append(str(event["eventDate"])[:10])
    return [
        {
            "date": day,
            "venue": text(event.get("venue")) or None,
            **({"openTime": event["openTime"]} if event.get("openTime") else {}),
            **({"startTime": event["startTime"]} if event.get("startTime") else {}),
        }
        for day in distinct(days)
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", day)
    ]


def merge_schedules(items: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for event in items:
        for row in schedule_rows(event):
            day = row["date"]
            venue_key = re.sub(r"\s+", "", str(row.get("venue") or "")).casefold()
            same_day = [index for index, current in enumerate(rows) if current["date"] == day]

            exact = next(
                (
                    index for index in same_day
                    if re.sub(r"\s+", "", str(rows[index].get("venue") or "")).casefold() == venue_key
                ),
                None,
            )
            if exact is not None:
                current = rows[exact]
                if not current.get("openTime") and row.get("openTime"):
                    current["openTime"] = row["openTime"]
                if not current.get("startTime") and row.get("startTime"):
                    current["startTime"] = row["startTime"]
                continue

            if not venue_key and same_day:
                continue
            unknown = next((index for index in same_day if not rows[index].get("venue")), None)
            if venue_key and unknown is not None:
                rows[unknown] = dict(row)
                continue
            rows.append(dict(row))

    rows.sort(key=lambda row: (row["date"], str(row.get("venue") or "")))
    return rows


def merge_component(items: list[dict]) -> dict:
    representative = max(
        items,
        key=lambda event: (
            len(schedule_rows(event)),
            int(str(event.get("sourceType") or "").lower() == "derived"),
            len(all_urls(event)),
            sum(value not in (None, "", [], {}) for value in event.values()),
        ),
    )
    merged = dict(representative)
    schedule = merge_schedules(items)
    dates = distinct(row["date"] for row in schedule)
    urls = distinct(value for event in items for value in all_urls(event))
    venues = distinct(row.get("venue") for row in schedule if row.get("venue"))

    if dates:
        merged["eventDate"] = dates[0]
        if len(dates) > 1:
            merged["eventEndDate"] = dates[-1]
            merged["eventDates"] = dates
        else:
            merged.pop("eventEndDate", None)
            merged.pop("eventDates", None)
    if schedule:
        merged["schedule"] = schedule
        merged["eventCount"] = len(schedule)
    if venues:
        merged["venues"] = venues
        merged["venue"] = venues[0] if len(venues) == 1 else f"複数会場（全{len(schedule)}公演）"
    if urls:
        merged["urls"] = urls
        if str(merged.get("url") or "") not in urls:
            merged["url"] = urls[0]

    # These rows are still directly sourced from official X even when several
    # dates are represented by one logical series. Calling the aggregate
    # "derived" makes the release audit treat it as an unverified special
    # event and restore the old split rows. Keep it explicitly official-social
    # and schedule-only until a purchase/participation announcement appears.
    merged["sourceType"] = "official-social"
    merged["sourceChannel"] = "official-x"
    merged["primarySource"] = "official"
    merged["sourceCandidates"] = ["official"]
    merged["specialDetailsStatus"] = "awaiting-details"
    merged["applicationDisplayMode"] = "schedule-only"
    merged["applicationStatus"] = "none"

    if any(not item.get("sourceStale") for item in items):
        merged.pop("sourceStale", None)
        merged.pop("sourceStaleSince", None)
        merged.pop("releaseRetentionReason", None)
    return merged


def connected_components(items: list[dict]) -> list[list[dict]]:
    remaining = list(items)
    components: list[list[dict]] = []
    while remaining:
        component = [remaining.pop(0)]
        known_urls = set(x_urls(component[0]))
        changed = True
        while changed:
            changed = False
            keep = []
            for event in remaining:
                event_urls = x_urls(event)
                if known_urls.intersection(event_urls):
                    component.append(event)
                    known_urls.update(event_urls)
                    changed = True
                else:
                    keep.append(event)
            remaining = keep
        components.append(component)
    return components


def collapse(events: list[dict]) -> tuple[list[dict], dict]:
    buckets: dict[tuple[str, str, str], list[dict]] = {}
    passthrough: list[dict] = []
    for event in events:
        if not is_official_x_schedule_row(event):
            passthrough.append(event)
            continue
        key = (text(event.get("group")), category(event), normalized_title(event))
        buckets.setdefault(key, []).append(event)

    merged_rows = list(passthrough)
    series_merged = 0
    rows_collapsed = 0
    for items in buckets.values():
        for component in connected_components(items):
            if len(component) == 1:
                merged_rows.extend(component)
                continue
            merged_rows.append(merge_component(component))
            series_merged += 1
            rows_collapsed += len(component) - 1

    merged_rows.sort(key=lambda event: (
        str(event.get("eventDate") or "9999-12-31"),
        str(event.get("applyEnd") or "9999"),
        str(event.get("group") or ""),
        str(event.get("id") or ""),
    ))
    return merged_rows, {
        "officialXSeriesMerged": series_merged,
        "officialXRowsCollapsed": rows_collapsed,
    }


def collapse_payload(payload: dict) -> tuple[dict, dict]:
    rows = [dict(event) for event in payload.get("events", []) if isinstance(event, dict)]
    collapsed, report = collapse(rows)
    out = dict(payload)
    out["events"] = collapsed
    return out, report


def main() -> int:
    if not DATA_PATH.exists():
        return 0
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    cleaned, report = collapse_payload(payload)
    DATA_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
