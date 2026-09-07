#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import keikyu_internal_generated_evidence as consumer

BOUNDARY_ID = consumer.ZUSHI_BOUNDARY_ID


def load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def pair(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get('fromFragment') or ''), str(row.get('toFragment') or '')


def validate_local(row: dict[str, Any]) -> None:
    evidence = {str(v) for v in row.get('evidence') or []}
    if consumer.SECTION_LOCAL_MARKER not in evidence:
        raise SystemExit(f'missing section-local V2 marker: {row.get("id")}')
    if evidence & consumer.DEPRECATED_UNBANDED_MARKERS:
        raise SystemExit(f'deprecated marker in section-local proof: {row.get("id")}')
    if row.get('boundaryId') != BOUNDARY_ID:
        raise SystemExit(f'unexpected boundary in incremental proof: {row.get("boundaryId")}')
    reason = consumer.validate_section_local_entry(row)
    if reason:
        raise SystemExit(f'unsafe incremental section-local proof {row.get("id")}: {reason}')
    source, target = pair(row)
    if not source or not target:
        raise SystemExit('incremental proof missing runtime fragment identity')
    if [str(v) for v in row.get('sourceMatches') or []] != [source]:
        raise SystemExit(f'non-singleton source match: {row.get("id")}')
    if [str(v) for v in row.get('targetMatches') or []] != [target]:
        raise SystemExit(f'non-singleton target match: {row.get("id")}')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--existing', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    ap.add_argument('--entries', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--output', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    ap.add_argument('--accepted-output', required=True)
    ap.add_argument('--summary-output', required=True)
    args = ap.parse_args()

    existing = load(Path(args.existing), {}) or {}
    payload = load(Path(args.entries), {}) or {}
    report = load(Path(args.report), {}) or {}
    incoming = [row for row in payload.get('entries') or [] if isinstance(row, dict)]
    if int(report.get('matchedSingleton') or 0) != len(incoming):
        raise SystemExit(f'report/entry mismatch: {report.get("matchedSingleton")} != {len(incoming)}')
    if not incoming:
        raise SystemExit('no incremental Zushi section-local proofs')
    for row in incoming:
        validate_local(row)

    existing_entries = [row for row in existing.get('entries') or [] if isinstance(row, dict)]
    existing_pairs = {pair(row) for row in existing_entries}
    existing_sources = {
        str(row.get('fromFragment') or '')
        for row in existing_entries
        if row.get('boundaryId') == BOUNDARY_ID
    }
    existing_targets = {
        str(row.get('toFragment') or '')
        for row in existing_entries
        if row.get('boundaryId') == BOUNDARY_ID
    }

    incoming_source_counts = Counter(str(row.get('fromFragment') or '') for row in incoming)
    incoming_target_counts = Counter(str(row.get('toFragment') or '') for row in incoming)
    if any(count != 1 for count in incoming_source_counts.values()):
        raise SystemExit('incremental generator emitted duplicate source proofs')
    if any(count != 1 for count in incoming_target_counts.values()):
        raise SystemExit('incremental generator emitted duplicate target proofs')

    accepted: list[dict[str, Any]] = []
    rejected_existing_source = 0
    rejected_existing_target = 0
    duplicate_pair = 0
    for row in incoming:
        source, target = pair(row)
        if (source, target) in existing_pairs:
            duplicate_pair += 1
            continue
        if source in existing_sources:
            rejected_existing_source += 1
            continue
        if target in existing_targets:
            rejected_existing_target += 1
            continue
        accepted.append(row)

    if not accepted:
        raise SystemExit('all incremental proofs conflicted with existing Zushi evidence')

    accepted_targets = [str(row.get('toFragment') or '') for row in accepted]
    accepted_sources = [str(row.get('fromFragment') or '') for row in accepted]
    if len(set(accepted_targets)) != len(accepted_targets):
        raise SystemExit('accepted incremental proofs share a target')
    if len(set(accepted_sources)) != len(accepted_sources):
        raise SystemExit('accepted incremental proofs share a source')
    if set(accepted_targets) & existing_targets:
        raise SystemExit('accepted incremental target overlaps existing Zushi evidence')
    if set(accepted_sources) & existing_sources:
        raise SystemExit('accepted incremental source overlaps existing Zushi evidence')

    merged = existing_entries + accepted
    all_zushi_sources: dict[str, set[str]] = {}
    all_zushi_targets: Counter[str] = Counter()
    for row in merged:
        if row.get('boundaryId') != BOUNDARY_ID:
            continue
        source, target = pair(row)
        all_zushi_sources.setdefault(source, set()).add(target)
        all_zushi_targets[target] += 1
    disagreeing_sources = sorted(source for source, targets in all_zushi_sources.items() if len(targets) != 1)
    duplicated_targets = sorted(target for target, count in all_zushi_targets.items() if count > 1)
    if disagreeing_sources:
        raise SystemExit(f'combined Zushi evidence disagrees on source target: {disagreeing_sources[:5]}')
    if duplicated_targets:
        raise SystemExit(f'combined Zushi evidence reuses runtime target: {duplicated_targets[:5]}')

    policy = dict(existing.get('policy') or {})
    policy.update({
        'officialSamePrintedColumnRequired': True,
        'twoExactPublishedStationTimesRequired': True,
        'singletonFragmentMatchRequiredAtBothPoints': True,
        'trainNumberAloneMayEstablishIdentity': False,
        'timeProximityAloneMayEstablishIdentity': False,
        'officialPageSectionColumnIsExactLocalIdentityForScheduleAll': True,
        'officialSectionIdentityRequiredForScheduleAll': True,
        'literalPrintedCalendarRequiredForScheduleAll': True,
        'runtimeCalendarMustMatchOfficialPrintedCalendarForScheduleAll': True,
        'calendarMayBeInferredFromPageNumberForScheduleAll': False,
        'deprecatedUnbandedScheduleAllMarkersAccepted': False,
    })
    boundary_counts = Counter(str(row.get('boundaryId') or '') for row in merged)
    calendar_counts = Counter(str(row.get('calendar') or '') for row in merged)
    direction_counts = Counter(str(row.get('direction') or '') for row in merged)
    summary = dict(existing.get('summary') or {})
    summary.update({
        'matchedSingleton': len(merged),
        'boundaries': dict(boundary_counts),
        'calendars': dict(calendar_counts),
        'directions': dict(direction_counts),
        'latestZushiIncrementalSectionV2': {
            'generatorReport': report,
            'incoming': len(incoming),
            'accepted': len(accepted),
            'duplicatePair': duplicate_pair,
            'rejectedExistingSource': rejected_existing_source,
            'rejectedExistingTarget': rejected_existing_target,
        },
    })
    output = dict(existing)
    output.update({
        'version': max(5, int(existing.get('version') or 0)),
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'policy': policy,
        'summary': summary,
        'entries': merged,
    })

    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    Path(args.accepted_output).write_text(json.dumps({'entries': accepted}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    audit = {
        'existingEntries': len(existing_entries),
        'incomingFreshProofs': len(incoming),
        'acceptedIncrementalProofs': len(accepted),
        'duplicatePair': duplicate_pair,
        'rejectedExistingSource': rejected_existing_source,
        'rejectedExistingTarget': rejected_existing_target,
        'combinedZushiEvidenceSources': len(all_zushi_sources),
        'combinedZushiEvidenceTargets': len(all_zushi_targets),
    }
    Path(args.summary_output).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
