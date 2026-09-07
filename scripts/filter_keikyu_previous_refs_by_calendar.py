#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise RuntimeError(f'expected JSON object: {path}')
    return value


def key(page: Any, section: Any, column: Any) -> tuple[int, int, int] | None:
    try:
        return int(page), int(section), int(column)
    except (TypeError, ValueError):
        return None


def filter_payload(stop_times: dict[str, Any], references: dict[str, Any]) -> dict[str, Any]:
    if stop_times.get('kind') != 'keikyu-official-section-local-stop-times':
        raise RuntimeError('unexpected section-local stop-time kind')
    if references.get('kind') != 'keikyu-official-section-previous-publication-reference-audit':
        raise RuntimeError('unexpected previous-reference audit kind')
    stop_sha = str((stop_times.get('source') or {}).get('sha256') or '')
    ref_sha = str((references.get('source') or {}).get('sha256') or '')
    if not stop_sha or stop_sha != ref_sha:
        raise RuntimeError('official source SHA mismatch')
    stop_policy = stop_times.get('identityPolicy') or {}
    required = {
        'pageSectionColumnIsExactLocalIdentity': True,
        'literalPrintedCalendarRequired': True,
        'unclassifiedCalendarPagesExcludedFromIdentity': True,
        'calendarMayBeInferredFromPageNumber': False,
        'calendarMayBeInferredFromNeighboringPages': False,
    }
    for field, expected in required.items():
        if stop_policy.get(field) is not expected:
            raise RuntimeError(f'unsafe stop-time calendar policy: {field}')

    calendar_by_key: dict[tuple[int, int, int], str] = {}
    for row in stop_times.get('fragments') or []:
        if not isinstance(row, dict):
            continue
        k = key(row.get('page'), row.get('section'), row.get('column'))
        calendar = str(row.get('calendar') or '')
        if k is None or calendar not in {'weekday', 'holiday'}:
            raise RuntimeError('identity-bearing stop fragment lacks strict calendar key')
        if k in calendar_by_key and calendar_by_key[k] != calendar:
            raise RuntimeError(f'conflicting calendars for official fragment key {k}')
        calendar_by_key[k] = calendar

    retained: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    dropped_current = 0
    target_calendar_excluded = 0
    target_calendar_mismatch = 0
    for raw in references.get('fragments') or []:
        if not isinstance(raw, dict):
            continue
        current_key = key(raw.get('pdfPage'), raw.get('section'), raw.get('column'))
        calendar = calendar_by_key.get(current_key) if current_key is not None else None
        if calendar not in {'weekday', 'holiday'}:
            dropped_current += 1
            continue
        row = dict(raw)
        row['calendar'] = calendar
        if row.get('targetStatus') == 'unique-explicit-reference-candidate':
            target_key = key(row.get('targetPdfPage'), row.get('targetSection'), row.get('targetColumn'))
            target_calendar = calendar_by_key.get(target_key) if target_key is not None else None
            if target_calendar not in {'weekday', 'holiday'}:
                row['targetStatus'] = 'target-calendar-excluded-or-missing'
                row['targetPdfPage'] = None
                row['targetSection'] = None
                row['targetColumn'] = None
                target_calendar_excluded += 1
            elif target_calendar != calendar:
                row['targetStatus'] = 'target-calendar-mismatch'
                row['targetPdfPage'] = None
                row['targetSection'] = None
                row['targetColumn'] = None
                target_calendar_mismatch += 1
            else:
                row['targetCalendar'] = target_calendar
        status_counts[str(row.get('targetStatus') or '')] += 1
        retained.append(row)

    pages = []
    included_pages = {int(row.get('pdfPage')) for row in retained if row.get('pdfPage') is not None}
    for page in references.get('pages') or []:
        if not isinstance(page, dict) or int(page.get('pdfPage') or -1) not in included_pages:
            continue
        copy = dict(page)
        page_calendars = {
            calendar_by_key[(int(copy['pdfPage']), int(section['section']), column)]
            for section in copy.get('sections') or []
            for column in range(int(section.get('fragmentCount') or 0))
            if (int(copy['pdfPage']), int(section['section']), column) in calendar_by_key
        }
        if len(page_calendars) == 1:
            copy['calendar'] = next(iter(page_calendars))
        pages.append(copy)

    unique = sum(1 for row in retained if row.get('targetStatus') == 'unique-explicit-reference-candidate')
    complete = sum(
        1 for row in retained
        if row.get('previousPrintedPage') is not None and row.get('previousTrainNumber') is not None
    )
    policy = dict(references.get('identityPolicy') or {})
    policy.update({
        'literalPrintedCalendarRequired': True,
        'unclassifiedCalendarPagesExcludedFromIdentity': True,
        'currentReferenceFragmentMustExistInCalendarStopDataset': True,
        'targetReferenceFragmentMustExistInCalendarStopDataset': True,
        'currentAndTargetPrintedCalendarsMustMatch': True,
        'calendarMayBeInferredFromPageNumber': False,
        'calendarMayBeInferredFromNeighboringPages': False,
        'runtimeSameTrainPromotions': 0,
    })
    output = dict(references)
    output.update({
        'version': max(3, int(references.get('version') or 0)),
        'kind': 'keikyu-official-section-previous-publication-reference-audit',
        'pagesAudited': len(pages),
        'sectionsAudited': sum(int(p.get('sectionCount') or 0) for p in pages),
        'calendarExcludedPages': list(stop_times.get('calendarExcludedPages') or []),
        'fragmentCount': len(retained),
        'completePreviousReferenceCount': complete,
        'uniqueExplicitReferenceCandidateCount': unique,
        'targetStatusCounts': dict(status_counts),
        'calendarFilterSummary': {
            'inputReferenceFragments': len(references.get('fragments') or []),
            'retainedCurrentCalendarFragments': len(retained),
            'droppedCurrentCalendarExcludedOrMissing': dropped_current,
            'targetCalendarExcludedOrMissing': target_calendar_excluded,
            'targetCalendarMismatch': target_calendar_mismatch,
            'uniqueSameCalendarExplicitReferences': unique,
        },
        'identityPolicy': policy,
        'pages': pages,
        'fragments': retained,
    })
    return output


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('stop_times', type=Path)
    ap.add_argument('references', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    payload = filter_payload(load(args.stop_times), load(args.references))
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(json.dumps({
        'output': str(args.output),
        'calendarExcludedPages': payload.get('calendarExcludedPages'),
        'calendarFilterSummary': payload.get('calendarFilterSummary'),
        'targetStatusCounts': payload.get('targetStatusCounts'),
        'runtimeSameTrainPromotions': 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
