#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import build_keikyu_cross_page_identity_audit as base


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise RuntimeError(f'expected JSON object: {path}')
    return value


def calendarize(stop_times: dict[str, Any], references: dict[str, Any]) -> dict[str, Any]:
    ref_policy = references.get('identityPolicy') or {}
    for field in (
        'literalPrintedCalendarRequired',
        'unclassifiedCalendarPagesExcludedFromIdentity',
        'currentReferenceFragmentMustExistInCalendarStopDataset',
        'targetReferenceFragmentMustExistInCalendarStopDataset',
        'currentAndTargetPrintedCalendarsMustMatch',
    ):
        if ref_policy.get(field) is not True:
            raise RuntimeError(f'unsafe calendar-filtered reference policy: {field}')
    if ref_policy.get('calendarMayBeInferredFromPageNumber') is not False:
        raise RuntimeError('calendar inference from page number is unsafe')
    if ref_policy.get('calendarMayBeInferredFromNeighboringPages') is not False:
        raise RuntimeError('calendar inference from neighboring pages is unsafe')

    audit = base.build_audit(stop_times, references)
    by_id = {
        str(row.get('id') or ''): row
        for row in stop_times.get('fragments') or []
        if isinstance(row, dict) and row.get('id')
    }
    issues = list(audit.get('issues') or [])
    calendar_edges: list[dict[str, Any]] = []
    for raw in audit.get('edges') or []:
        edge = dict(raw)
        source = by_id.get(str(edge.get('fromFragment') or ''))
        target = by_id.get(str(edge.get('toFragment') or ''))
        if not source or not target:
            issues.append({'kind': 'calendar-edge-stale-fragment'})
            continue
        source_calendar = str(source.get('calendar') or '')
        target_calendar = str(target.get('calendar') or '')
        if source_calendar not in {'weekday', 'holiday'} or target_calendar not in {'weekday', 'holiday'}:
            issues.append({
                'kind': 'calendar-edge-missing-literal-calendar',
                'fromFragment': edge.get('fromFragment'),
                'toFragment': edge.get('toFragment'),
            })
            continue
        if source_calendar != target_calendar:
            issues.append({
                'kind': 'cross-calendar-previous-publication-edge',
                'fromFragment': edge.get('fromFragment'),
                'toFragment': edge.get('toFragment'),
                'fromCalendar': source_calendar,
                'toCalendar': target_calendar,
            })
            continue
        edge['calendar'] = source_calendar
        calendar_edges.append(edge)

    if len(calendar_edges) != len(audit.get('edges') or []):
        issues.append({
            'kind': 'calendar-edge-count-mismatch',
            'baseEdges': len(audit.get('edges') or []),
            'calendarEdges': len(calendar_edges),
        })

    policy = dict(audit.get('identityPolicy') or {})
    policy.update({
        'literalPrintedCalendarRequired': True,
        'unclassifiedCalendarPagesExcludedFromIdentity': True,
        'crossPageEdgesStayWithinPrintedCalendar': True,
        'calendarMayBeInferredFromPageNumber': False,
        'calendarMayBeInferredFromNeighboringPages': False,
    })
    output = dict(audit)
    output.update({
        'version': max(3, int(audit.get('version') or 0)),
        'calendarExcludedPages': list(stop_times.get('calendarExcludedPages') or []),
        'materializedCandidateEdgeCount': len(calendar_edges),
        'issues': issues,
        'edges': calendar_edges,
        'identityPolicy': policy,
        'calendarEdgeCounts': {
            'weekday': sum(1 for row in calendar_edges if row.get('calendar') == 'weekday'),
            'holiday': sum(1 for row in calendar_edges if row.get('calendar') == 'holiday'),
        },
    })
    return output


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('stop_times', type=Path)
    ap.add_argument('references', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    payload = calendarize(load(args.stop_times), load(args.references))
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(json.dumps({
        'output': str(args.output),
        'candidateReferences': payload.get('candidateReferenceCount'),
        'candidateEdges': payload.get('materializedCandidateEdgeCount'),
        'calendarEdgeCounts': payload.get('calendarEdgeCounts'),
        'calendarExcludedPages': payload.get('calendarExcludedPages'),
        'issues': len(payload.get('issues') or []),
        'runtimeSameTrainPromotions': 0,
    }, ensure_ascii=False, indent=2))
    if payload.get('issues'):
        raise SystemExit('calendar-safe cross-page identity audit contains issues')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
