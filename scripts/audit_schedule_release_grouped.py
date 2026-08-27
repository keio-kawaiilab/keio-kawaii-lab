#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from audit_schedule_release import JST, audit, event_days, load, parse_day, parse_dt, stable_keys

DATE_MESSAGE_RE = re.compile(r"^(?:future performance dates disappeared|performance dates added) for (url:[^:]+://.*?): ")


def source_date_sets(payload: dict, today: date) -> dict[str, dict[str, set[str]]]:
    grouped: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for event in payload.get("events", []):
        if not isinstance(event, dict):
            continue
        group = str(event.get("group") or "")
        if not group:
            continue
        days = {
            value
            for value in event_days(event)
            if parse_day(value) is not None and parse_day(value) >= today
        }
        if not days:
            continue
        for key in stable_keys(event):
            if key.startswith("url:"):
                grouped[key][group].update(days)
    return grouped


def safely_unchanged_shared_source_keys(previous: dict, candidate: dict, today: date) -> set[str]:
    prev = source_date_sets(previous, today)
    cand = source_date_sets(candidate, today)
    safe: set[str] = set()
    for key, prev_groups in prev.items():
        cand_groups = cand.get(key)
        if not cand_groups:
            continue
        # Only reconcile a genuinely shared source. Single-event sources should stay on the
        # original per-event audit path.
        prev_rows = [
            event for event in previous.get("events", [])
            if isinstance(event, dict) and key in stable_keys(event)
        ]
        cand_rows = [
            event for event in candidate.get("events", [])
            if isinstance(event, dict) and key in stable_keys(event)
        ]
        if max(len(prev_rows), len(cand_rows)) < 2:
            continue
        if set(prev_groups) != set(cand_groups):
            continue
        if all(prev_groups[group] == cand_groups[group] for group in prev_groups):
            safe.add(key)
    return safe


def message_key(message: str) -> str | None:
    match = DATE_MESSAGE_RE.match(message)
    return match.group(1) if match else None


def audit_grouped(previous: dict, candidate: dict, now: datetime):
    errors, warnings, report = audit(previous, candidate, now)
    today = now.astimezone(JST).date()
    safe_keys = safely_unchanged_shared_source_keys(previous, candidate, today)

    filtered_errors = [
        message for message in errors
        if not (message_key(message) in safe_keys and message.startswith("future performance dates disappeared"))
    ]
    filtered_warnings = [
        message for message in warnings
        if not (message_key(message) in safe_keys and message.startswith("performance dates added"))
    ]

    report = dict(report)
    report["status"] = "blocked" if filtered_errors else "ok"
    report["errorCount"] = len(filtered_errors)
    report["warningCount"] = len(filtered_warnings)
    report["errors"] = filtered_errors
    report["warnings"] = filtered_warnings
    report["sharedSourceDateSetsReconciled"] = sorted(safe_keys)
    return filtered_errors, filtered_warnings, report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed schedule release audit with safe shared-source date reconciliation"
    )
    parser.add_argument("--previous", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--now", help="ISO-8601 time used by tests")
    args = parser.parse_args()

    now = parse_dt(args.now) if args.now else datetime.now(JST)
    if now is None:
        raise SystemExit("invalid --now")

    previous = load(args.previous)
    candidate = load(args.candidate)
    errors, warnings, report = audit_grouped(previous, candidate, now)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Schedule release audit: {report['status']} ({len(errors)} errors, {len(warnings)} warnings)")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if report.get("sharedSourceDateSetsReconciled"):
        print("Reconciled unchanged shared-source performance date sets:")
        for key in report["sharedSourceDateSetsReconciled"]:
            print(f"  - {key}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
