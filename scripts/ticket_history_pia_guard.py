#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

import update_pia_events as pia

DATA_PATH = Path("data/live-events.json")
JST = timezone(timedelta(hours=9))


def stable_id(*parts: object) -> str:
    raw = "\x1f".join(str(value or "") for value in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def guarded_status(context: str) -> str | None:
    original = pia.availability_status_original(context) if hasattr(pia, "availability_status_original") else None
    if original:
        return original
    if "予定枚数終了" in context:
        return "sold_out"
    if any(hint in context for hint in pia.ENDED_HINTS):
        return "ended"
    return None


def _original_status(context: str) -> str | None:
    if any(hint in context for hint in pia.ACTIVE_HINTS):
        return "open"
    if any(hint in context for hint in pia.UPCOMING_HINTS):
        return "upcoming"
    return None


def history_key(event: dict) -> tuple[str, str, str, str]:
    group = str(event.get("group") or "")
    day = str(event.get("eventDate") or "")[:10]
    kind = str(event.get("ticketType") or "")
    provider = str(event.get("ticketProvider") or event.get("primarySource") or "pia")
    return group, day, kind, provider


def normalize_guard_row(event: dict) -> dict:
    row = dict(event)
    row["id"] = stable_id(
        "pia-history-guard",
        row.get("group"),
        row.get("eventDate"),
        row.get("ticketType"),
        row.get("applyStart"),
        row.get("applyEnd"),
        row.get("url"),
    )
    row["sourceType"] = "ticket-history-guard"
    row["sourceChannel"] = "pia-ended-sale"
    row["primarySource"] = "pia"
    row["ticketProvider"] = "pia"
    row["sourceCandidates"] = ["pia"]
    row["historyPreserved"] = True
    if row.get("applyStart"):
        row["applicationWindowVerified"] = True
        row["applicationWindowSource"] = row.get("url")
    if row.get("applyEnd"):
        row["deadlineVerified"] = True
        row["deadlineSource"] = row.get("url")
    if row.get("applyStart") and row.get("applyEnd"):
        row["applicationDisplayMode"] = "band"
    else:
        row["applicationDisplayMode"] = "offers"
    return row


def discover_pages(session: requests.Session, group: str) -> tuple[list[tuple[str, str]], list[str]]:
    failures: list[str] = []
    pages = list(pia.SEEDED_EVENT_PAGES.get(group, []))
    artist_url = pia.ARTIST_URLS[group]
    try:
        pages = pia.discover_event_pages(session, group, artist_url)
    except Exception as exc:
        failures.append(f"{group} artist page: {type(exc).__name__}: {exc}")
    seen = set()
    result = []
    for url, fallback in pages:
        url = pia.canonical_url(url)
        if not url or url in seen:
            continue
        seen.add(url)
        result.append((url, fallback or group))
    return result[:40], failures


def collect_ended_sales(
    payload: dict,
    session: requests.Session,
    today: date,
) -> tuple[list[dict], list[str]]:
    existing = [x for x in payload.get("events", []) if isinstance(x, dict)]
    ended: list[dict] = []
    failures: list[str] = []

    original = pia.availability_status
    pia.availability_status_original = _original_status
    pia.availability_status = guarded_status
    try:
        for group in pia.ARTIST_URLS:
            pages, page_failures = discover_pages(session, group)
            failures.extend(page_failures)
            for event_url, fallback in pages:
                try:
                    parsed = pia.parse_event_page(
                        session,
                        group,
                        event_url,
                        fallback,
                        existing,
                        today,
                    )
                except Exception as exc:
                    failures.append(f"{group} {event_url}: {type(exc).__name__}: {exc}")
                    continue
                for event in parsed:
                    if event.get("applicationStatus") not in {"ended", "sold_out"}:
                        continue
                    if not event.get("applyStart") and not event.get("applyEnd"):
                        # We know a sale existed, but the archive intentionally does
                        # not publish a period without at least one directly observed
                        # boundary. Keep it out rather than inventing a date.
                        continue
                    ended.append(normalize_guard_row(event))
    finally:
        pia.availability_status = original
        if hasattr(pia, "availability_status_original"):
            delattr(pia, "availability_status_original")

    return ended, failures


def merge(payload: dict, rows: list[dict]) -> tuple[int, int]:
    events = [dict(x) for x in payload.get("events", []) if isinstance(x, dict)]
    index = {history_key(event): i for i, event in enumerate(events)}
    added = 0
    enriched = 0
    for row in rows:
        key = history_key(row)
        if key not in index:
            events.append(row)
            index[key] = len(events) - 1
            added += 1
            continue
        current = events[index[key]]
        changed = False
        for field in (
            "applyStart", "applyEnd", "applicationStatus", "applicationWindowVerified",
            "deadlineVerified", "applicationWindowSource", "deadlineSource", "historyPreserved",
        ):
            if current.get(field) in (None, "", False) and row.get(field) not in (None, "", False):
                current[field] = row[field]
                changed = True
        urls = list(dict.fromkeys([*(current.get("urls") or []), *(row.get("urls") or [])]))
        if urls != (current.get("urls") or []):
            current["urls"] = urls
            changed = True
        if changed:
            enriched += 1
    payload["events"] = events
    return added, enriched


def run(check: bool = False, today: date | None = None) -> dict:
    today = today or datetime.now(JST).date()
    original_payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    payload = json.loads(json.dumps(original_payload, ensure_ascii=False))
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; keio-kawaii-lab-pia-history-guard/1.0; +https://github.com/keio-kawaiilab/keio-kawaii-lab)",
        "Accept-Language": "ja,en;q=0.8",
    })
    try:
        rows, failures = collect_ended_sales(payload, session, today)
    finally:
        session.close()

    added, enriched = merge(payload, rows)
    changed = payload != original_payload
    if changed and not check:
        payload["updatedAt"] = datetime.now(JST).isoformat(timespec="seconds")
        DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "checkedAt": datetime.now(JST).isoformat(timespec="seconds"),
        "endedPiaRowsObserved": len(rows),
        "endedPiaRowsAdded": added,
        "endedPiaRowsEnriched": enriched,
        "changed": changed,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preserve ended and sold-out Ticket Pia sales as ticket history evidence.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(check=args.check), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
