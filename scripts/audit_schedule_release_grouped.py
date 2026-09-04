#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
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
LOCAL_KEY_COLON_ERROR_RE = re.compile(
    r"^(?:future performance dates disappeared|active deadline disappeared|deadline moved earlier) for (.+?)(?: \[[^\]]+\])?: "
)
LOCAL_KEY_BARE_ERROR_RE = re.compile(r"^deadline changed without source evidence for (.+)$")
DUPLICATE_ID_RE = re.compile(r"^duplicate event id: (.+)$")
DUPLICATE_PIA_RE = re.compile(r"^duplicate Pia lot (pia:[^:]+):")


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
    the full per-group date set instead. Real removals remain fail-closed at the
    audit layer and are quarantined by the CLI release path.
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


def _events(payload: dict) -> list[dict]:
    return [event for event in payload.get("events", []) if isinstance(event, dict)]


def _same_event_candidates(previous_events: list[dict], current: dict) -> list[dict]:
    current_id = str(current.get("id") or "").strip()
    if current_id:
        exact = [event for event in previous_events if str(event.get("id") or "").strip() == current_id]
        if exact:
            return exact

    keys = set(stable_keys(current))
    if keys:
        keyed = [event for event in previous_events if keys.intersection(stable_keys(event))]
        if keyed:
            return keyed

    group = str(current.get("group") or "")
    title = str(current.get("title") or "")
    ticket_type = str(current.get("ticketType") or "")
    return [
        event for event in previous_events
        if str(event.get("group") or "") == group
        and str(event.get("title") or "") == title
        and str(event.get("ticketType") or "") == ticket_type
    ]


def _replace_candidate_rows(candidate: dict, predicate, replacements: list[dict]) -> bool:
    rows = _events(candidate)
    kept = [event for event in rows if not predicate(event)]
    if len(kept) == len(rows) and not replacements:
        return False
    candidate["events"] = kept + [copy.deepcopy(event) for event in replacements]
    return True


def _restore_key(previous: dict, candidate: dict, key: str) -> tuple[bool, int]:
    previous_matches = [event for event in _events(previous) if key in stable_keys(event)]
    if not previous_matches:
        return False, 0
    changed = _replace_candidate_rows(
        candidate,
        lambda event: key in stable_keys(event),
        previous_matches,
    )
    return changed, len(previous_matches)


def _restore_label(previous: dict, candidate: dict, target_label: str) -> tuple[bool, int]:
    previous_matches = [event for event in _events(previous) if label(event) == target_label]
    if not previous_matches:
        return False, 0
    changed = _replace_candidate_rows(
        candidate,
        lambda event: label(event) == target_label,
        previous_matches,
    )
    return changed, len(previous_matches)


def _quarantine_candidate_label(previous: dict, candidate: dict, target_label: str) -> tuple[bool, int, str]:
    previous_events = _events(previous)
    target_rows = [event for event in _events(candidate) if label(event) == target_label]
    if not target_rows:
        return False, 0, ""

    replacements: list[dict] = []
    for current in target_rows:
        matches = _same_event_candidates(previous_events, current)
        if len(matches) == 1:
            replacement = matches[0]
            if not any(str(item.get("id") or "") == str(replacement.get("id") or "") for item in replacements):
                replacements.append(replacement)

    changed = _replace_candidate_rows(candidate, lambda event: label(event) == target_label, replacements)
    action = "restored previous row" if replacements else "withheld new/ambiguous row"
    return changed, len(target_rows), action


def _unchanged_previous_row_label_for_error(previous: dict, candidate: dict, error: str) -> str | None:
    """Return the label only when the errored row is byte-for-byte unchanged from last-good.

    This is deliberately narrower than ordinary row matching. A newly fetched row
    that merely shares a title/source with a previous row must never inherit this
    exemption. The exemption exists only to prevent a newly tightened validator
    from freezing every unrelated update because an already-public legacy row is
    still waiting for richer official metadata.
    """
    candidate_rows = _events(candidate)
    for previous_row in _events(previous):
        previous_label = label(previous_row)
        if not previous_label or previous_label not in error:
            continue
        if any(current_row == previous_row for current_row in candidate_rows):
            return previous_label
    return None


def _downgrade_unchanged_baseline_errors(
    previous: dict,
    candidate: dict,
    errors: list[str],
    warnings: list[str],
    report: dict,
    baseline_errors: set[str],
) -> tuple[list[str], list[str], dict, list[dict]]:
    """Downgrade only local errors already present on an unchanged last-good row."""
    legacy_actions: list[dict] = []
    remaining: list[str] = []
    for error in errors:
        if error not in baseline_errors:
            remaining.append(error)
            continue
        target_label = _unchanged_previous_row_label_for_error(previous, candidate, error)
        if not target_label:
            remaining.append(error)
            continue
        legacy_actions.append({
            "error": error,
            "label": target_label,
            "action": "retained unchanged previous row; validator regression downgraded to warning",
        })

    if not legacy_actions:
        return errors, warnings, report, []

    legacy_warnings = [
        "protected unchanged last-good row still fails newer completeness checks; retained without blocking unrelated updates: "
        + item["error"]
        for item in legacy_actions
    ]
    updated_warnings = legacy_warnings + list(warnings)
    updated_report = dict(report)
    updated_report["status"] = "blocked" if remaining else "ok"
    updated_report["errorCount"] = len(remaining)
    updated_report["warningCount"] = len(updated_warnings)
    updated_report["errors"] = remaining
    updated_report["warnings"] = updated_warnings
    updated_report["legacyProtectedErrorCount"] = len(legacy_actions)
    updated_report["legacyProtectedErrors"] = legacy_actions
    return remaining, updated_warnings, updated_report, legacy_actions


def repair_local_errors(previous: dict, candidate: dict, now: datetime, max_rounds: int = 64):
    """Quarantine event-scoped audit failures while preserving unrelated fresh rows.

    Global integrity failures (for example an invalid top-level timestamp or a
    catastrophic count spike) still fail closed. Event/source-level failures are
    rolled back to the previous known-good rows, or withheld when a brand-new row
    cannot be matched safely, and then the entire repaired candidate is re-audited.
    """
    repaired = copy.deepcopy(candidate)
    quarantine_actions: list[dict] = []
    seen_states: set[str] = set()
    baseline_errors, _, _ = audit_grouped(previous, previous, now)
    baseline_error_set = set(baseline_errors)

    for _ in range(max_rounds):
        errors, warnings, report = audit_grouped(previous, repaired, now)
        errors, warnings, report, _ = _downgrade_unchanged_baseline_errors(
            previous,
            repaired,
            errors,
            warnings,
            report,
            baseline_error_set,
        )
        if not errors:
            report = dict(report)
            if quarantine_actions:
                quarantine_warnings = [
                    "quarantined one event/source update and kept the previous known-good data: "
                    + str(item.get("error") or "")
                    for item in quarantine_actions
                ]
                report["warnings"] = quarantine_warnings + list(report.get("warnings") or [])
                report["warningCount"] = len(report["warnings"])
                warnings = report["warnings"]
            report["quarantineCount"] = len(quarantine_actions)
            report["quarantineActions"] = quarantine_actions
            report["status"] = "ok"
            report["errorCount"] = 0
            report["errors"] = []
            return repaired, [], warnings, report, quarantine_actions

        state = json.dumps(repaired.get("events", []), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if state in seen_states:
            break
        seen_states.add(state)
        changed_this_round = False
        candidate_labels = sorted({label(event) for event in _events(repaired)}, key=len, reverse=True)

        for error in errors:
            changed = False
            restored_count = 0
            action = ""

            if error.startswith(DISAPPEARED_PREFIX):
                target = error[len(DISAPPEARED_PREFIX):]
                changed, restored_count = _restore_label(previous, repaired, target)
                action = "restored disappeared previous row"
            else:
                key_match = LOCAL_KEY_COLON_ERROR_RE.match(error)
                bare_match = LOCAL_KEY_BARE_ERROR_RE.match(error)
                if key_match or bare_match:
                    key = (key_match or bare_match).group(1).strip()
                    changed, restored_count = _restore_key(previous, repaired, key)
                    action = f"restored previous rows for {key}"
                else:
                    id_match = DUPLICATE_ID_RE.match(error)
                    if id_match:
                        event_id = id_match.group(1).strip()
                        previous_matches = [
                            event for event in _events(previous)
                            if str(event.get("id") or "").strip() == event_id
                        ]
                        changed = _replace_candidate_rows(
                            repaired,
                            lambda event: str(event.get("id") or "").strip() == event_id,
                            previous_matches[:1],
                        )
                        restored_count = len(previous_matches[:1])
                        action = "restored previous duplicate-id row" if previous_matches else "withheld duplicate new rows"
                    else:
                        pia_match = DUPLICATE_PIA_RE.match(error)
                        if pia_match:
                            key = pia_match.group(1)
                            previous_matches = [event for event in _events(previous) if key in stable_keys(event)]
                            changed = _replace_candidate_rows(
                                repaired,
                                lambda event: key in stable_keys(event),
                                previous_matches,
                            )
                            restored_count = len(previous_matches)
                            action = "restored previous Pia lot rows" if previous_matches else "withheld duplicate Pia lot rows"
                        else:
                            target_label = next((value for value in candidate_labels if value and value in error), None)
                            if target_label:
                                changed, restored_count, action = _quarantine_candidate_label(
                                    previous, repaired, target_label
                                )

            if changed:
                changed_this_round = True
                quarantine_actions.append({
                    "error": error,
                    "action": action,
                    "restoredPreviousRows": restored_count,
                })

        if not changed_this_round:
            break

    errors, warnings, report = audit_grouped(previous, repaired, now)
    errors, warnings, report, _ = _downgrade_unchanged_baseline_errors(
        previous,
        repaired,
        errors,
        warnings,
        report,
        baseline_error_set,
    )
    report = dict(report)
    report["quarantineCount"] = len(quarantine_actions)
    report["quarantineActions"] = quarantine_actions
    if not errors:
        report["status"] = "ok"
        report["errorCount"] = 0
        report["errors"] = []
    return repaired, errors, warnings, report, quarantine_actions


def _reconcile_default_official_index(candidate: dict) -> dict | None:
    index_path = Path("data/official-schedule-index.json")
    if not index_path.exists():
        return None
    try:
        from reconcile_official_schedule_index import reconcile

        index = json.loads(index_path.read_text(encoding="utf-8"))
        result = reconcile(candidate, index)
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result
    except Exception as exc:  # pragma: no cover - release-path safety net
        return {"error": f"official index reconciliation after quarantine failed: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Schedule release audit that quarantines bad event rows and only fail-closes on global integrity failures"
    )
    parser.add_argument("--previous", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--now", help="ISO-8601 time used by tests")
    parser.add_argument(
        "--no-quarantine",
        action="store_true",
        help="disable row-level recovery and use strict fail-closed audit behavior",
    )
    args = parser.parse_args()

    now = parse_dt(args.now) if args.now else datetime.now(JST)
    if now is None:
        raise SystemExit("invalid --now")

    previous = load(args.previous)
    candidate = load(args.candidate)
    quarantine_actions: list[dict] = []

    if args.no_quarantine:
        errors, warnings, report = audit_grouped(previous, candidate, now)
    else:
        candidate, errors, warnings, report, quarantine_actions = repair_local_errors(
            previous, candidate, now
        )
        if quarantine_actions and not errors:
            args.candidate.write_text(
                json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            index_result = _reconcile_default_official_index(candidate)
            if index_result is not None:
                report["officialIndexReconciledAfterQuarantine"] = index_result

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
    if quarantine_actions:
        print(f"Quarantined {len(quarantine_actions)} event/source update(s); unrelated fresh rows remain publishable.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
