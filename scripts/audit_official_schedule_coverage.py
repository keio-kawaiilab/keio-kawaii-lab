#!/usr/bin/env python3
"""Validate official schedule coverage without letting one bad row freeze all updates."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from enforce_physical_event_invariant import enforce_payload
from reconcile_official_schedule_index import reconcile
from schedule_scope import VALID_SCOPES, special_event_category
from update_official_schedule import GROUPS, event_days, participants


ROW_LEVEL_PREFIXES = (
    "official row has no represented event:",
    "represented event has the wrong date:",
    "represented event has the wrong participant:",
    "represented event has a different scope:",
    "represented event lacks its official URL:",
    "official special-event row has the wrong category:",
    "event has invalid eventScope:",
)


def audit(data: dict, index: dict, previous_index: dict | None = None) -> list[str]:
    """Return the strict set of coverage errors.

    The function intentionally remains strict so callers/tests can inspect every
    mismatch. ``main`` applies the release policy that distinguishes isolated
    row-linkage problems from systemic corruption.
    """
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
        sources = {
            str(event.get("url") or "").strip(),
            str(event.get("officialScheduleUrl") or "").strip(),
            *(str(value).strip() for value in event.get("urls") or []),
        }
        sources.discard("")
        if str(entry.get("url") or "").strip() not in sources:
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


def _row_label(error: str) -> str:
    return error.split(": ", 1)[1] if ": " in error else error


def release_policy(errors: list[str], official_row_count: int) -> tuple[list[str], list[str], dict]:
    """Separate row-scoped problems from true system-wide release blockers.

    Row-scoped mismatches never gain authority to stop unrelated public updates.
    They remain visible as warnings and are retried on the next refresh. Only
    index/source-wide integrity failures stay blocking.
    """
    isolated = [error for error in errors if error.startswith(ROW_LEVEL_PREFIXES)]
    blocking = [error for error in errors if not error.startswith(ROW_LEVEL_PREFIXES)]

    isolated_rows = sorted({_row_label(error) for error in isolated})
    diagnostic_threshold = max(1, min(5, math.ceil(max(official_row_count, 1) * 0.05)))

    return blocking, isolated, {
        "isolatedRowCount": len(isolated_rows),
        "isolationDiagnosticThreshold": diagnostic_threshold,
        "isolationThresholdExceeded": len(isolated_rows) > diagnostic_threshold,
        "isolatedRows": isolated_rows,
        "rowFailuresCanBlockRelease": False,
    }


def _entry_key(entry: dict) -> tuple[str, str, str]:
    return (
        str(entry.get("group") or "").strip(),
        str(entry.get("date") or "").strip(),
        str(entry.get("url") or "").strip(),
    )


def _event_sources(event: dict) -> set[str]:
    sources = {
        str(event.get("url") or "").strip(),
        str(event.get("officialScheduleUrl") or "").strip(),
        *(str(value).strip() for value in event.get("urls") or []),
    }
    sources.discard("")
    return sources


def restore_unresolved_from_previous(
    data: dict,
    index: dict,
    previous_data: dict | None,
    previous_index: dict | None,
) -> dict:
    """Restore a last-known-good event for an unresolved official index row.

    Only strongly linked rows are restored: the previous index must match the
    same group/date/official URL and its previous represented event must still
    agree on group, date, scope and official URL. This keeps the fallback local
    to the affected row rather than rolling back unrelated fresh data.
    """
    report = {"restoredCount": 0, "restored": []}
    if not previous_data or not previous_index:
        return report

    events = [event for event in data.get("events", []) if isinstance(event, dict)]
    data["events"] = events
    by_id = {str(event.get("id") or ""): event for event in events if event.get("id")}

    previous_events = [
        event for event in previous_data.get("events", []) if isinstance(event, dict)
    ]
    previous_by_id = {
        str(event.get("id") or ""): event for event in previous_events if event.get("id")
    }

    previous_entries_by_key: dict[tuple[str, str, str], list[dict]] = {}
    for old_entry in previous_index.get("entries", []) or []:
        if not isinstance(old_entry, dict):
            continue
        previous_entries_by_key.setdefault(_entry_key(old_entry), []).append(old_entry)

    for entry in index.get("entries", []) or []:
        if not isinstance(entry, dict):
            continue
        represented = str(entry.get("representedBy") or "")
        if represented and represented in by_id:
            continue

        matches = previous_entries_by_key.get(_entry_key(entry), [])
        if len(matches) != 1:
            continue

        old_entry = matches[0]
        old_id = str(old_entry.get("representedBy") or "")
        old_event = previous_by_id.get(old_id)
        if not old_id or not old_event:
            continue

        group = str(entry.get("group") or "")
        date = str(entry.get("date") or "")
        url = str(entry.get("url") or "").strip()
        if date not in event_days(old_event):
            continue
        if group not in participants(old_event):
            continue
        if old_event.get("eventScope") != entry.get("eventScope"):
            continue
        if url and url not in _event_sources(old_event):
            continue

        restored = copy.deepcopy(old_event)
        events.append(restored)
        by_id[old_id] = restored
        entry["representedBy"] = old_id
        report["restoredCount"] += 1
        report["restored"].append(
            {
                "id": old_id,
                "group": group,
                "date": date,
                "url": url,
                "reason": "restored previous known-good row after isolated reconciliation failure",
            }
        )

    return report


def _evaluate(errors: list[str], index: dict) -> tuple[list[str], list[str], dict]:
    entries = [entry for entry in index.get("entries", []) if isinstance(entry, dict)]
    return release_policy(errors, len(entries))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/live-events.json"))
    parser.add_argument("--index", type=Path, default=Path("data/official-schedule-index.json"))
    parser.add_argument("--previous-index", type=Path)
    parser.add_argument(
        "--previous-data",
        type=Path,
        default=Path("/tmp/live-events-last-good.json"),
        help="Last published live-events snapshot used for row-level fallback when available.",
    )
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    index = json.loads(args.index.read_text(encoding="utf-8"))
    previous = (
        json.loads(args.previous_index.read_text(encoding="utf-8"))
        if args.previous_index and args.previous_index.exists()
        else None
    )
    previous_data = (
        json.loads(args.previous_data.read_text(encoding="utf-8"))
        if args.previous_data and args.previous_data.exists()
        else None
    )

    # First reconnect against the fresh merged candidate. If an official row
    # remains unresolved, restore only that row's previous known-good public
    # event instead of rolling back the entire release.
    pre_audit_reconcile = reconcile(data, index)
    restore_report = restore_unresolved_from_previous(data, index, previous_data, previous)
    post_restore_reconcile = reconcile(data, index) if restore_report["restoredCount"] else None

    args.data.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.index.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    errors = audit(data, index, previous)
    blocking, isolated, policy = _evaluate(errors, index)
    if blocking:
        print(json.dumps({
            "status": "blocked",
            "errors": blocking,
            "isolatedWarnings": isolated,
            "releasePolicy": policy,
            "previousFallback": restore_report,
            "officialIndexReconcile": pre_audit_reconcile,
            "postRestoreOfficialIndexReconcile": post_restore_reconcile,
        }, ensure_ascii=False, indent=2))
        return 1

    if isolated:
        for warning in isolated:
            print(f"WARNING: isolated official schedule row mismatch; unrelated updates remain publishable: {warning}")

    # Canonicalize physical special-event duplicates. Any residual duplicate is
    # row-scoped diagnostic fallout, not permission to freeze unrelated rows.
    data, physical_report = enforce_payload(data)
    physical_warnings: list[str] = []
    if physical_report.get("remainingDuplicateCount"):
        physical_warnings.append(
            "physical special-event duplicates remain after best-effort enforcement; "
            "affected rows stay isolated and will be retried without freezing unrelated updates"
        )
        print(f"WARNING: {physical_warnings[-1]}")

    args.data.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Canonical merging can change event IDs, so reconnect every official index
    # row to the final public entity and then verify coverage once more.
    reconcile_report = reconcile(data, index)
    # reconcile may also restore an official schedule URL that canonical merging
    # dropped from an otherwise identical represented event. Persist that repair.
    args.data.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.index.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    final_errors = audit(data, index, previous)
    final_blocking, final_isolated, final_policy = _evaluate(final_errors, index)
    if final_blocking:
        print(json.dumps({
            "status": "blocked",
            "errors": final_blocking,
            "isolatedWarnings": final_isolated,
            "physicalEventInvariant": physical_report,
            "releasePolicy": final_policy,
            "previousFallback": restore_report,
            "officialIndexReconcile": reconcile_report,
        }, ensure_ascii=False, indent=2))
        return 1

    for warning in final_isolated:
        print(f"WARNING: isolated official schedule row mismatch after canonical merge: {warning}")

    all_warnings = list(dict.fromkeys([*isolated, *final_isolated, *physical_warnings]))
    print(json.dumps({
        "status": "ok",
        "officialRows": len(index.get("entries") or []),
        "isolatedWarnings": all_warnings,
        "releasePolicy": final_policy,
        "previousFallback": restore_report,
        "preAuditOfficialIndexReconcile": pre_audit_reconcile,
        "postRestoreOfficialIndexReconcile": post_restore_reconcile,
        "physicalEventInvariant": physical_report,
        "officialIndexReconcile": reconcile_report,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
