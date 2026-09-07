#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import keikyu_internal_official_evidence as base
import keikyu_missing_boundary_evidence as target

BOUNDARY_ID = 'keikyu-main-zushi-kanazawahakkei'


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    return value if isinstance(value, dict) else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--calendar', choices=('weekday', 'holiday'), required=True)
    ap.add_argument('--coverage', default='data/transit-v2/coverage.json')
    ap.add_argument('--fragments', default='data/transit-v2/fragments/keikyu.json')
    ap.add_argument('--report', required=True)
    ap.add_argument('--entries-output')
    args = ap.parse_args()

    coverage = load(Path(args.coverage))
    fragment_payload = load(Path(args.fragments))
    fragments = [row for row in fragment_payload.get('fragments') or [] if isinstance(row, dict) and row.get('id')]
    by_id = {str(row['id']): row for row in fragments}

    filtered_unresolved = []
    for row in coverage.get('unresolved') or []:
        if not isinstance(row, dict) or row.get('kind') != target.CURRENT_KIND:
            continue
        fragment = by_id.get(str(row.get('fragment') or ''))
        if not fragment or base.service_of(fragment) != args.calendar:
            continue
        filtered_unresolved.append(row)

    filtered_coverage = {**coverage, 'unresolved': filtered_unresolved}
    entries, summary = target.build_entries(
        filtered_coverage,
        fragments,
        boundary_id=BOUNDARY_ID,
    )
    summary = {
        **summary,
        'calendarFilter': args.calendar,
        'entryIds': [str(row.get('id') or '') for row in entries],
        'pairs': [
            [str(row.get('fromFragment') or ''), str(row.get('toFragment') or '')]
            for row in entries
        ],
    }
    Path(args.report).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.entries_output:
        Path(args.entries_output).write_text(
            json.dumps({
                'calendar': args.calendar,
                'boundaryId': BOUNDARY_ID,
                'entries': entries,
            }, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
