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


def safe_new_entry(row: dict[str, Any]) -> None:
    evidence = {str(value) for value in row.get('evidence') or []}
    if consumer.SECTION_LOCAL_MARKER not in evidence:
        raise SystemExit(f'missing section-local V2 marker: {row.get("id")}')
    if evidence & consumer.DEPRECATED_UNBANDED_MARKERS:
        raise SystemExit(f'deprecated unbanded marker in V2 proof: {row.get("id")}')
    if row.get('boundaryId') != BOUNDARY_ID:
        raise SystemExit(f'unexpected boundary in V2 proof: {row.get("boundaryId")}')
    reason = consumer.validate_section_local_entry(row)
    if reason:
        raise SystemExit(f'unsafe section-local V2 proof {row.get("id")}: {reason}')
    source = str(row.get('fromFragment') or '')
    target = str(row.get('toFragment') or '')
    if not source or not target:
        raise SystemExit('V2 proof missing runtime fragment identity')
    if [str(value) for value in row.get('sourceMatches') or []] != [source]:
        raise SystemExit(f'V2 proof source match is not singleton: {row.get("id")}')
    if [str(value) for value in row.get('targetMatches') or []] != [target]:
        raise SystemExit(f'V2 proof target match is not singleton: {row.get("id")}')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--existing', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    ap.add_argument('--entries', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--cross-report')
    ap.add_argument('--output', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    ap.add_argument('--summary-output')
    args = ap.parse_args()

    existing = load(Path(args.existing), {}) or {}
    entry_payload = load(Path(args.entries), {}) or {}
    report = load(Path(args.report), {}) or {}
    cross_report = load(Path(args.cross_report), {}) or {} if args.cross_report else {}

    new_entries = [row for row in entry_payload.get('entries') or [] if isinstance(row, dict)]
    if int(report.get('matchedSingleton') or 0) != len(new_entries):
        raise SystemExit(
            f'V2 report/entry mismatch: report={report.get("matchedSingleton")} entries={len(new_entries)}'
        )
    if not new_entries:
        raise SystemExit('no fresh section-local V2 proofs to merge')
    for row in new_entries:
        safe_new_entry(row)

    # Remove every legacy unbanded full-timetable proof before adding V2.  Other
    # independent official evidence (for example Airport-line connection PDF)
    # remains untouched.
    retained: list[dict[str, Any]] = []
    removed_deprecated = 0
    for row in existing.get('entries') or []:
        if not isinstance(row, dict):
            continue
        evidence = {str(value) for value in row.get('evidence') or []}
        if evidence & consumer.DEPRECATED_UNBANDED_MARKERS:
            removed_deprecated += 1
            continue
        retained.append(row)

    pair_map: dict[tuple[str, str], dict[str, Any]] = {}
    source_targets: dict[str, set[str]] = {}
    for row in retained + new_entries:
        source = str(row.get('fromFragment') or '')
        target = str(row.get('toFragment') or '')
        if not source or not target:
            raise SystemExit('evidence entry missing runtime fragment identity')
        pair_map[(source, target)] = row
        source_targets.setdefault(source, set()).add(target)
    ambiguous_sources = sorted(source for source, targets in source_targets.items() if len(targets) != 1)
    if ambiguous_sources:
        raise SystemExit(f'evidence disagrees on target for source fragments: {ambiguous_sources[:5]}')

    entries = list(pair_map.values())
    deprecated_remaining = [
        str(row.get('id') or '')
        for row in entries
        if {str(value) for value in row.get('evidence') or []} & consumer.DEPRECATED_UNBANDED_MARKERS
    ]
    if deprecated_remaining:
        raise SystemExit(f'deprecated evidence survived V2 merge: {deprecated_remaining[:5]}')

    policy = dict(existing.get('policy') or {})
    # Delete old V1 cross-page policy name so the JSON cannot imply that page-only
    # fragment matching remains acceptable.
    policy.pop('pageLocalFragmentMetadataMustMatchForCrossPage', None)
    policy.update({
        'officialSamePrintedColumnRequired': True,
        'twoExactPublishedStationTimesRequired': True,
        'singletonFragmentMatchRequiredAtBothPoints': True,
        'trainNumberAloneMayEstablishIdentity': False,
        'timeProximityAloneMayEstablishIdentity': False,
        'officialPageSectionColumnIsExactLocalIdentityForScheduleAll': True,
        'officialSectionIdentityRequiredForScheduleAll': True,
        'deprecatedUnbandedScheduleAllMarkersAccepted': False,
        'officialPreviousPublicationPageAndTrainNumberRequiredForCrossPage': True,
        'uniquePreviousPublicationTargetRequiredForCrossPage': True,
        'pageSectionLocalFragmentMetadataMustMatchForCrossPage': True,
        'officialSectionIdentityRequiredForCrossPage': True,
        'crossPageGraphMustBeNonBranchingAcyclic': True,
        'directedOfficialContinuationPathRequired': True,
    })

    boundary_counts = Counter(str(row.get('boundaryId') or '') for row in entries)
    direction_counts = Counter(str(row.get('direction') or '') for row in entries)
    calendar_counts = Counter(str(row.get('calendar') or '') for row in entries)
    summary = dict(existing.get('summary') or {})
    summary.update({
        'matchedSingleton': len(entries),
        'boundaries': dict(boundary_counts),
        'directions': dict(direction_counts),
        'calendars': dict(calendar_counts),
        'zushiSectionV2': report,
        'deprecatedUnbandedEntriesRemovedDuringLatestMerge': removed_deprecated,
    })
    if cross_report:
        summary['zushiCrossPageSectionV2'] = cross_report

    output = dict(existing)
    output.update({
        'version': max(3, int(existing.get('version') or 0)),
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'operator': 'keikyu',
        'boundaryIds': sorted(k for k in boundary_counts if k),
        'policy': policy,
        'summary': summary,
        'entries': entries,
    })
    # Stale V1 latestCrossPageSummary is intentionally discarded; if supplied,
    # V2 cross-page status is stored under the recomputed summary above.
    output.pop('latestCrossPageSummary', None)

    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    audit_summary = {
        'retainedExistingEntries': len(retained),
        'freshSectionV2Entries': len(new_entries),
        'deprecatedEntriesRemoved': removed_deprecated,
        'mergedEntries': len(entries),
        'boundaries': dict(boundary_counts),
        'directions': dict(direction_counts),
        'calendars': dict(calendar_counts),
    }
    if args.summary_output:
        Path(args.summary_output).write_text(json.dumps(audit_summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(audit_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
