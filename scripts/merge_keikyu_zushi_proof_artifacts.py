#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import keikyu_missing_boundary_evidence as target

BOUNDARY_ID = 'keikyu-main-zushi-kanazawahakkei'


def load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--existing', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    ap.add_argument('--entries', nargs='+', required=True)
    ap.add_argument('--reports', nargs='*', default=[])
    ap.add_argument('--output', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    ap.add_argument('--summary-output')
    args = ap.parse_args()

    entries: list[dict[str, Any]] = []
    per_calendar: dict[str, Any] = {}
    reasons: Counter[str] = Counter()
    eligible = 0
    candidates = 0

    for raw in args.entries:
        path = Path(raw)
        payload = load(path, {}) or {}
        calendar = str(payload.get('calendar') or path.stem)
        for row in payload.get('entries') or []:
            if not isinstance(row, dict):
                continue
            if row.get('boundaryId') != BOUNDARY_ID:
                raise SystemExit(f'unexpected boundary in {path}: {row.get("boundaryId")}')
            entries.append(row)
        per_calendar.setdefault(calendar, {})['entryFile'] = str(path)

    for raw in args.reports:
        path = Path(raw)
        report = load(path, {}) or {}
        calendar = str(report.get('calendarFilter') or path.stem)
        per_calendar.setdefault(calendar, {})['report'] = report
        eligible += int(report.get('eligibleUnresolvedSources') or 0)
        candidates += int(report.get('candidatePairsAfterDestinationAndTimeSearch') or 0)
        reasons.update({str(k): int(v) for k, v in (report.get('reasons') or {}).items()})

    pair_map: dict[tuple[str, str], dict[str, Any]] = {}
    source_targets: dict[str, set[str]] = {}
    for row in entries:
        source = str(row.get('fromFragment') or '')
        dest = str(row.get('toFragment') or '')
        if not source or not dest:
            raise SystemExit('proof entry missing fragment identity')
        pair_map[(source, dest)] = row
        source_targets.setdefault(source, set()).add(dest)

    ambiguous_sources = sorted(source for source, targets in source_targets.items() if len(targets) != 1)
    if ambiguous_sources:
        raise SystemExit(f'proof artifacts disagree on target for sources: {ambiguous_sources[:5]}')

    entries = list(pair_map.values())
    summary = {
        'eligibleUnresolvedSources': eligible,
        'candidatePairsAfterDestinationAndTimeSearch': candidates,
        'matchedSingleton': len(entries),
        'reasons': dict(reasons),
        'boundaries': dict(Counter(str(row.get('boundaryId') or '') for row in entries)),
        'directions': dict(Counter(str(row.get('direction') or '') for row in entries)),
        'calendars': dict(Counter(str(row.get('calendar') or '') for row in entries)),
        'perCalendar': per_calendar,
        'policy': {
            'sharedPublishedDestinationIsSearchOnly': True,
            'candidateTimeWindowIsSearchOnly': True,
            'officialSamePrintedColumnRequired': True,
            'twoExactPublishedStationTimesRequired': True,
            'singletonFragmentMatchRequiredAtBothPoints': True,
            'uniqueTargetRequired': True,
            'trainNumberAloneMayEstablishIdentity': False,
            'timeProximityAloneMayEstablishIdentity': False,
        },
    }

    existing = load(Path(args.existing), {}) or {}
    output = target.merge_payload(existing, entries, summary)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.summary_output:
        Path(args.summary_output).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
