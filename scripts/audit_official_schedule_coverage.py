#!/usr/bin/env python3
"""Fail closed unless every official future LIVE/EVENT listing is represented."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from enforce_physical_event_invariant import enforce_payload
from reconcile_official_schedule_index import reconcile
from schedule_scope import VALID_SCOPES, special_event_category
from update_official_schedule import GROUPS, event_days, participants


def audit(data: dict, index: dict, previous_index: dict | None = None) -> list[str]:
    errors = []
    events = [event for event in data.get("events", []) if isinstance(event, dict)]
    by_id = {str(event.get("id") or ""): event for event in events if event.get("id")}
    entries = [entry for entry in index.get("entries", []) if isinstance(entry, dict)]
    if not entries:
        errors.append("official schedule index is empty")
    groups = index.get("groups") or {}
    for group in GROUPS:
        if group not in groups or int((groups.get(group) or {}).get("count") or 0) <= 0:
            errors.append(f"official schedule source is missing or empty: {group}")
    for entry in entries:
        represented = str(entry.get("representedBy") or "")
        event = by_id.get(represented)
        label = f"{entry.get('group')} / {entry.get('date')} / {entry.get('title')}"
        if not event:
            errors.append(f"official row has no represented event: {label}")
            continue
        if str(entry.get("date") or "") not in event_days(event):
            errors.append(f"represented event has the wrong date: {label}")
        if str(entry.get("group") or "") not in participants(event):
            errors.append(f"represented event has the wrong participant: {label}")
        if event.get("eventScope") != entry.get("eventScope"):
            errors.append(f"represented event has a different scope: {label}")
        sources = [str(event.get("url") or ""), *(str(value) for value in event.get("urls") or [])]
        if str(entry.get("url") or "") not in sources:
            errors.append(f"represented event lacks its official URL: {label}")
        expected_category = special_event_category(entry.get("title"))
        if expected_category and event.get("eventCategory") != expected_category:
            errors.append(f"official special-event row has the wrong category: {label}")
    for event in events:
        if event.get("eventScope") not in VALID_SCOPES:
            errors.append(f"event has invalid eventScope: {event.get('id') or event.get('title')}")
    if previous_index:
        old_entries = [entry for entry in previous_index.get("entries", []) if isinstance(entry, dict)]
        if old_entries and len(entries) < max(1, int(len(old_entries) * 0.80)):
            errors.append(f"official schedule row count dropped sharply: {len(old_entries)} -> {len(entries)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/live-events.json"))
    parser.add_argument("--index", type=Path, default=Path("data/official-schedule-index.json"))
    parser.add_argument("--previous-index", type=Path)
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    index = json.loads(args.index.read_text(encoding="utf-8"))
    previous = json.loads(args.previous_index.read_text(encoding="utf-8")) if args.previous_index and args.previous_index.exists() else None

    # First verify the quarantined candidate against the official index exactly
    # as before. This keeps the coverage safeguard independent from deduping.
    errors = audit(data, index, previous)
    if errors:
        print(json.dumps({"status": "blocked", "errors": errors}, ensure_ascii=False, indent=2))
        return 1

    # Final release boundary. The grouped audit may restore a previous row while
    # quarantining a bad source update. That restoration must never be allowed to
    # resurrect a second card for the same physically impossible occurrence.
    # Source/title/vendor wording is metadata; one group at one date/time/venue
    # is one real special event.
    data, physical_report = enforce_payload(data)
    if physical_report.get("remainingDuplicateCount"):
        print(json.dumps({
            "status": "blocked",
            "errors": ["physical special-event duplicates remain after enforcement"],
            "physicalEventInvariant": physical_report,
        }, ensure_ascii=False, indent=2))
        return 1

    args.data.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Canonical merging can change event IDs, so reconnect every official index
    # row to the final public entity and then verify coverage once more.
    reconcile_report = reconcile(data, index)
    args.index.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    errors = audit(data, index, previous)
    if errors:
        print(json.dumps({
            "status": "blocked",
            "errors": errors,
            "physicalEventInvariant": physical_report,
            "officialIndexReconcile": reconcile_report,
        }, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({
        "status": "ok",
        "officialRows": len(index.get("entries") or []),
        "physicalEventInvariant": physical_report,
        "officialIndexReconcile": reconcile_report,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
