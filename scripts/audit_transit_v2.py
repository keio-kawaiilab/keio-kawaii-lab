#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path('.')
V2 = ROOT / 'data/transit-v2'
COVERAGE = V2 / 'coverage.json'
OUT = V2 / 'unresolved-summary.json'


def load_json(path: Path, default: Any = None) -> Any:
    try:
        text = path.read_text(encoding='utf-8').strip()
        return json.loads(text) if text else default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


def fragment_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    fragment_dir = V2 / 'fragments'
    if not fragment_dir.exists():
        return index
    for path in sorted(fragment_dir.glob('*.json')):
        payload = load_json(path, {}) or {}
        for fragment in payload.get('fragments') or []:
            if not isinstance(fragment, dict) or not fragment.get('id'):
                continue
            index[str(fragment['id'])] = {
                'operator': str(fragment.get('sourceOperator') or payload.get('operator') or ''),
                'railway': str(fragment.get('railway') or ''),
                'sourceKind': str(fragment.get('sourceKind') or ''),
                'destination': fragment.get('destination') or [],
                'calendar': str(fragment.get('calendar') or ''),
                'trainNumber': str(fragment.get('trainNumber') or ''),
                'timetableId': str(fragment.get('timetableId') or ''),
            }
    return index


def context_for(row: dict[str, Any], fragments: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = [
        str(row.get('fragment') or ''),
        str(row.get('fromFragment') or ''),
        str(row.get('toFragment') or ''),
    ]
    contexts = [fragments[value] for value in ids if value and value in fragments]
    operator = next((c['operator'] for c in contexts if c.get('operator')), '')
    railway = str(row.get('railway') or row.get('fromRailway') or '')
    if not railway:
        railway = next((c['railway'] for c in contexts if c.get('railway')), '')
    source_kind = next((c['sourceKind'] for c in contexts if c.get('sourceKind')), '')
    return {'operator': operator or 'unknown', 'railway': railway or 'unknown', 'sourceKind': source_kind or 'unknown'}


def main() -> int:
    coverage = load_json(COVERAGE, {}) or {}
    unresolved = [row for row in coverage.get('unresolved') or [] if isinstance(row, dict)]
    fragments = fragment_index()

    by_kind: Counter[str] = Counter()
    by_operator: Counter[str] = Counter()
    by_railway: Counter[str] = Counter()
    by_source_kind: Counter[str] = Counter()
    kind_operator: dict[str, Counter[str]] = defaultdict(Counter)
    kind_railway: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in unresolved:
        kind = str(row.get('kind') or 'unknown')
        context = context_for(row, fragments)
        operator = context['operator']
        railway = context['railway']
        source_kind = context['sourceKind']
        by_kind[kind] += 1
        by_operator[operator] += 1
        by_railway[railway] += 1
        by_source_kind[source_kind] += 1
        kind_operator[kind][operator] += 1
        kind_railway[kind][railway] += 1
        if len(examples[kind]) < 8:
            sample = dict(row)
            sample['_context'] = context
            examples[kind].append(sample)

    def sorted_counter(counter: Counter[str]) -> list[dict[str, Any]]:
        return [{'key': key, 'count': count} for key, count in counter.most_common()]

    reasons = []
    for kind, count in by_kind.most_common():
        reasons.append({
            'kind': kind,
            'count': count,
            'byOperator': sorted_counter(kind_operator[kind]),
            'byRailway': sorted_counter(kind_railway[kind]),
            'examples': examples[kind],
        })

    result = {
        'version': 1,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'totalUnresolved': len(unresolved),
        'coverageSummary': coverage.get('summary') or {},
        'byReason': reasons,
        'byOperator': sorted_counter(by_operator),
        'byRailway': sorted_counter(by_railway),
        'bySourceKind': sorted_counter(by_source_kind),
        'policy': {
            'unknownMayBePromotedToSameTrain': False,
            'trainNumberAloneMayResolve': False,
            'timeGapAloneMayResolve': False,
        },
    }
    write_json(OUT, result)
    print(json.dumps({
        'totalUnresolved': result['totalUnresolved'],
        'topReasons': result['byReason'][:10],
        'topOperators': result['byOperator'][:10],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
