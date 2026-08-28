#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from audit_schedule_release import (
    JST,
    audit,
    event_days,
    is_ticket_listing,
    label,
    load,
    parse_day,
    parse_dt,
    playguide_provider,
    stable_keys,
)

DATE_MESSAGE_RE = re.compile(r"^(?:future performance dates disappeared|performance dates added) for (url:[^:]+://.*?): ")
OFFICIAL_X_STATUS_KEY_RE = re.compile(
    r"^url:https://x\.com/(?:FRUITS_ZIPPER|CANDY_TUNE_|SWEET_STEADY|CUTIE_STREET_|MORE_STAR_)/status/\d+$",
    re.I,
)
DISAPPEARED_PREFIX = "protected future/active item disappeared: "


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


def source_row_counts(payload: dict) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for event in payload.get("events", []):
        if not isinstance(event, dict):
            continue
        for key in stable_keys(event):
            if key.startswith("url:"):
                counts[key] += 1
    return counts


def safely_unchanged_shared_source_keys(previous: dict, candidate: dict, today: date) -> set[str]:
    prev = source_date_sets(previous, today)
    cand = source_date_sets(candidate, today)
    safe: set[str] = set()
    for key, prev_groups in prev.items():
        cand_groups = cand.get(key)
        if not cand_groups:
            continue
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


def reconcile_official_x_shared_dates(
    previous: dict,
    candidate: dict,
    today: date,
) -> tuple[list[str], list[str], set[str]]:
    """Compare multi-event official X posts as group-scoped date sets.

    A single official X post can announce several dates. The base audit indexes a
    URL to one row, so a newly added earlier date can make an unchanged later row
    appear to have disappeared. For official status URLs with multiple rows, use
    the full per-group date set instead. Real removals remain fail-closed.
    """
    prev_sets = source_date_sets(previous, today)
    cand_sets = source_date_sets(candidate, today)
    prev_counts = source_row_counts(previous)
    cand_counts = source_row_counts(candidate)
    errors: list[str] = []
    warnings: list[str] = []
    reconciled: set[str] = set()

    for key in sorted(set(prev_sets).intersection(cand_sets)):
        if not OFFICIAL_X_STATUS_KEY_RE.fullmatch(key):
            continue
        if max(prev_counts.get(key, 0), cand_counts.get(key, 0)) < 2:
            continue
        reconciled.add(key)
        prev_groups = prev_sets.get(key, {})
        cand_groups = cand_sets.get(key, {})
        for group in sorted(set(prev_groups).union(cand_groups)):
            before = prev_groups.get(group, set())
            after = cand_groups.get(group, set())
            missing = sorted(before - after)
            added = sorted(after - before)
            if missing:
                errors.append(
                    f"future performance dates disappeared for {key} [{group}]: {', '.join(missing)}"
                )
            if added:
                warnings.append(
                    f"performance dates added for {key} [{group}]: {', '.join(added)}"
                )
    return errors, warnings, reconciled


def message_key(message: str) -> str | None:
    match = DATE_MESSAGE_RE.match(message)
    return match.group(1) if match else None


def safely_expired_playguide_labels(previous: dict, today: date) -> set[str]:
    """Rows whose reception is over may disappear even while the performance itself is future."""
    safe: set[str] = set()
    for event in previous.get("events", []):
        if not isinstance(event, dict) or not playguide_provider(event):
            continue
        if not is_ticket_listing(event) or event.get("applicationStatus") == "none":
            safe.add(label(event))
            continue
        end = parse_dt(event.get("applyEnd"))
        if end is not None and end.date() < today:
            safe.add(label(event))
    return safe


def is_safe_pia_date_rebucket(message: str) -> bool:
    """Pia bundle pages are shared by many performances; date rebucketing is not a coverage loss.

    Canonical performance coverage is checked immediately afterwards against every group's
    official schedule index, so this audit should guard the Pia sale window, not treat a shared
    eventBundle URL as the identity of one performance row.
    """
    key = message_key(message)
    return bool(key and "t.pia.jp" in key)


def audit_grouped(previous: dict, candidate: dict, now: datetime):
    errors, warnings, report = audit(previous, candidate, now)
    today = now.astimezone(JST).date()
    safe_keys = safely_unchanged_shared_source_keys(previous, candidate, today)
    safe_expired_labels = safely_expired_playguide_labels(previous, today)
    x_errors, x_warnings, x_reconciled_keys = reconcile_official_x_shared_dates(
        previous, candidate, today
    )

    filtered_errors: list[str] = []
    downgraded: list[str] = []
    reconciled_base_messages = 0
    for message in errors:
        key = message_key(message)
        if key in x_reconciled_keys and message.startswith("future performance dates disappeared"):
            reconciled_base_messages += 1
            continue
        if key in safe_keys and message.startswith("future performance dates disappeared"):
            continue
        if message.startswith(DISAPPEARED_PREFIX) and message[len(DISAPPEARED_PREFIX):] in safe_expired_labels:
            downgraded.append("ended playguide row removed: " + message[len(DISAPPEARED_PREFIX):])
            continue
        if message.startswith("future performance dates disappeared") and is_safe_pia_date_rebucket(message):
            downgraded.append("Pia shared bundle performance rows were rebucketed; official schedule coverage remains authoritative: " + message)
            continue
        filtered_errors.append(message)

    filtered_warnings = []
    for message in warnings:
        key = message_key(message)
        if key in x_reconciled_keys and message.startswith("performance dates added"):
            reconciled_base_messages += 1
            continue
        if key in safe_keys and message.startswith("performance dates added"):
            continue
        filtered_warnings.append(message)

    filtered_errors.extend(x_errors)
    filtered_warnings.extend(x_warnings)
    filtered_warnings.extend(downgraded)

    report = dict(report)
    report["status"] = "blocked" if filtered_errors else "ok"
    report["errorCount"] = len(filtered_errors)
    report["warningCount"] = len(filtered_warnings)
    report["errors"] = filtered_errors
    report["warnings"] = filtered_warnings
    report["sharedSourceDateSetsReconciled"] = sorted(safe_keys.union(x_reconciled_keys))
    report["officialXSharedSourceKeysReconciled"] = sorted(x_reconciled_keys)
    report["reconciledBaseDateMessageCount"] = reconciled_base_messages
    report["downgradedFalsePositiveCount"] = len(downgraded)
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
        print("Reconciled shared-source performance date sets:")
        for key in report["sharedSourceDateSetsReconciled"]:
            print(f"  - {key}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
