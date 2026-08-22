#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date, datetime

import requests

import update_live_events as parser_v1


def parse_day(value: object) -> date | None:
    text = str(value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def add_one_calendar_month(day: date) -> date:
    year = day.year + (1 if day.month == 12 else 0)
    month = 1 if day.month == 12 else day.month + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def event_last_day(event: dict) -> date | None:
    return parse_day(event.get("eventEndDate")) or parse_day(event.get("eventDate"))


def should_show(event: dict, today: date) -> bool:
    """Future shows stay indefinitely; past shows remain for one calendar month."""
    last_day = event_last_day(event)
    if last_day is None:
        # Manually-added/legacy entries without a reliable show date are left alone.
        return True
    return today <= add_one_calendar_month(last_day)


def event_urls(event: dict) -> set[str]:
    result = {str(x) for x in (event.get("urls") or []) if x}
    if event.get("url"):
        result.add(str(event["url"]))
    return result


def represented_by_fresh(event: dict, fresh_by_id: dict[str, dict], fresh_urls: set[str]) -> bool:
    source_type = event.get("sourceType")
    if source_type == "auto":
        return bool(event.get("id") and event.get("id") in fresh_by_id)
    if source_type == "derived":
        urls = event_urls(event)
        return bool(urls) and urls.issubset(fresh_urls)
    return False


def build_payload(existing: dict, fresh_by_id: dict[str, dict], pending: list[dict], failures: list[dict], today: date) -> dict:
    fresh_urls = {str(e.get("url")) for e in fresh_by_id.values() if e.get("url")}

    # Freshly parsed official events: application deadline no longer controls retention.
    fresh_events = [e for e in fresh_by_id.values() if should_show(e, today)]

    # Preserve previously discovered future events even after their news article falls
    # outside the first pages scanned by the crawler. This is what makes the future
    # horizon effectively unlimited once an official announcement has been captured.
    retained: list[dict] = []
    for original in existing.get("events", []):
        if not isinstance(original, dict):
            continue
        event = dict(original)
        if not should_show(event, today):
            continue
        if represented_by_fresh(event, fresh_by_id, fresh_urls):
            continue
        retained.append(event)

    # Avoid exact-ID duplicates while keeping derived/manual records intact.
    result: list[dict] = []
    seen_ids: set[str] = set()
    for event in retained + fresh_events:
        event_id = str(event.get("id") or "")
        if event_id and event_id in seen_ids:
            continue
        if event_id:
            seen_ids.add(event_id)
        result.append(event)

    result.sort(key=lambda e: (
        str(e.get("eventDate") or "9999"),
        str(e.get("applyEnd") or "9999"),
        str(e.get("group") or ""),
    ))

    return {
        "demo": False,
        "updatedAt": datetime.now(parser_v1.JST).isoformat(timespec="seconds"),
        "source": "KAWAII LAB.各グループ公式サイトの公開INFORMATION（公演終了1か月後まで保持）",
        "events": result,
        "pendingReview": pending,
        "failures": failures,
    }


def main() -> int:
    cli = argparse.ArgumentParser(description="Update LIVE calendar with show-date retention policy.")
    cli.add_argument("--check", action="store_true")
    args = cli.parse_args()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "KeioKawaiiLabCalendarBot/1.2 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"
    })

    fresh_by_id, pending, failures, candidate_counts = parser_v1.collect(session)
    reachable_groups = sum(1 for count in candidate_counts.values() if count > 0)
    diagnostics = {
        "candidateCounts": candidate_counts,
        "parsedEvents": len(fresh_by_id),
        "pendingReview": len(pending),
        "failures": failures,
    }
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))

    if reachable_groups < 4:
        print("Fewer than four group news feeds were reachable with ticket candidates.", file=sys.stderr)
        return 2
    if not fresh_by_id:
        print("No automatically parsed events were found; existing data left untouched.", file=sys.stderr)
        return 2
    if args.check:
        print("Live source check passed; no files were modified.")
        return 0

    existing = parser_v1.read_existing()
    payload = build_payload(existing, fresh_by_id, pending, failures, datetime.now(parser_v1.JST).date())
    parser_v1.OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    parser_v1.OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(payload['events'])} events using show-date retention policy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
