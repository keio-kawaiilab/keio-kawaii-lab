#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from difflib import SequenceMatcher

DATA_PATH = Path("data/live-events.json")
SPECIAL_CATEGORIES = {"release-event", "large-benefit", "large-benefit-event"}


def text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


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
        value = re.sub(rf"^[【〖\[]?\s*{re.escape(group)}\s*[】〗\]]?\s*", "", value, flags=re.I)
    value = re.sub(r"^20\d{2}[./年-]\d{1,2}[./月-]\d{1,2}日?\s*", "", value)
    value = re.sub(r"\s*@.+$", "", value)
    value = value.replace("／", "/").replace("｜", "|").replace("！", "!").replace("？", "?")
    value = re.sub(r"[\s　・･·―—–_-]+", "", value)
    return value.casefold()


def venue_key(value: object) -> str:
    value = text(value).casefold()
    value = re.sub(r"^(?:東京都|神奈川県|埼玉県|千葉県|大阪府|京都府|北海道|.{2,3}県)\s*", "", value)
    return re.sub(r"[\s　・･·()（）\[\]【】_-]+", "", value)


def performance_rows(event: dict) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    schedule = event.get("schedule")
    if isinstance(schedule, list):
        for item in schedule:
            if not isinstance(item, dict):
                continue
            day = str(item.get("date") or "")[:10]
            if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", day):
                rows.append((day, venue_key(item.get("venue") or event.get("venue"))))
    if rows:
        return list(dict.fromkeys(rows))

    days = []
    if isinstance(event.get("eventDates"), list):
        days.extend(str(value)[:10] for value in event["eventDates"] if value)
    if not days and event.get("eventDate"):
        days.append(str(event["eventDate"])[:10])
    venue = venue_key(event.get("venue"))
    return list(dict.fromkeys((day, venue) for day in days if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", day)))


def urls(event: dict) -> set[str]:
    values = {str(value).strip() for value in event.get("urls") or [] if value}
    if event.get("url"):
        values.add(str(event["url"]).strip())
    return values


def title_similar(a: dict, b: dict) -> bool:
    left = normalized_title(a)
    right = normalized_title(b)
    if left == right:
        return True
    if not left or not right:
        return False
    if left in right or right in left:
        return min(len(left), len(right)) >= 8
    return SequenceMatcher(None, left, right).ratio() >= 0.86


def event_summary(event: dict) -> dict:
    return {
        "id": event.get("id"),
        "group": event.get("group"),
        "category": category(event),
        "title": event.get("displayTitle") or event.get("eventTitle") or event.get("title"),
        "eventDate": event.get("eventDate"),
        "eventEndDate": event.get("eventEndDate"),
        "eventCount": event.get("eventCount"),
        "venue": event.get("venue"),
        "startTime": event.get("startTime"),
        "gatheringTime": event.get("gatheringTime"),
        "salesStartTime": event.get("salesStartTime"),
        "ticketProvider": event.get("ticketProvider"),
        "ticketType": event.get("ticketType"),
        "applyStart": event.get("applyStart"),
        "applyEnd": event.get("applyEnd"),
        "product": event.get("product"),
        "sourceType": event.get("sourceType"),
        "sourceChannel": event.get("sourceChannel"),
        "primarySource": event.get("primarySource"),
        "urls": sorted(urls(event)),
        "performances": [list(row) for row in performance_rows(event)],
    }


def clusters(events: list[dict], related) -> list[list[dict]]:
    remaining = list(events)
    result: list[list[dict]] = []
    while remaining:
        component = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            keep = []
            for event in remaining:
                if any(related(event, current) for current in component):
                    component.append(event)
                    changed = True
                else:
                    keep.append(event)
            remaining = keep
        if len(component) > 1:
            result.append(component)
    return result


def audit(payload: dict) -> dict:
    special = [
        dict(event) for event in payload.get("events", [])
        if isinstance(event, dict) and category(event) in {"release-event", "large-benefit"}
    ]

    def same_scope(a: dict, b: dict) -> bool:
        return text(a.get("group")) == text(b.get("group")) and category(a) == category(b)

    def same_performance(a: dict, b: dict) -> bool:
        if not same_scope(a, b) or not title_similar(a, b):
            return False
        left = set(performance_rows(a))
        right = set(performance_rows(b))
        exact = left.intersection(right)
        if exact:
            return True
        # Unknown venue on one side still counts when the date is identical.
        left_days = {day for day, _ in left}
        right_days = {day for day, _ in right}
        return bool(left_days.intersection(right_days) and (any(not venue for _, venue in left) or any(not venue for _, venue in right)))

    def same_series(a: dict, b: dict) -> bool:
        if not same_scope(a, b) or not title_similar(a, b):
            return False
        if normalized_title(a) == normalized_title(b):
            return True
        return bool(urls(a).intersection(urls(b)))

    performance_clusters = clusters(special, same_performance)
    series_clusters = clusters(special, same_series)

    return {
        "updatedAt": payload.get("updatedAt"),
        "specialEventRows": len(special),
        "samePerformanceClusterCount": len(performance_clusters),
        "samePerformanceClusters": [[event_summary(event) for event in group] for group in performance_clusters],
        "splitSeriesClusterCount": len(series_clusters),
        "splitSeriesClusters": [[event_summary(event) for event in group] for group in series_clusters],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report duplicate/split release-event and large-benefit rows across all KAWAII LAB. groups")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--fail-on-duplicates", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.data.read_text(encoding="utf-8"))
    report = audit(payload)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_duplicates and report["samePerformanceClusterCount"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
