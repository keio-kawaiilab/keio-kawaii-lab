#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path('data/transit-v2')
MAIN = 'odpt.Railway:Keikyu.Main'
AIRPORT = 'odpt.Railway:Keikyu.Airport'
EDGE_MARKER = 'keikyu-official-main-airport-same-column-two-point'


def load(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def runtime_ref(fragment: dict) -> str:
    if fragment.get('sourceKind') == 'station-timetable-reconstruction':
        trip_index = fragment.get('sourceTripIndex')
        railway = str(fragment.get('railway') or '')
        return f'inf:{railway}:{trip_index}' if isinstance(trip_index, int) and railway else ''
    timetable = str(fragment.get('timetableId') or '')
    return f'tt:{timetable}' if timetable else ''


def main() -> int:
    evidence = load('keikyu-internal-official-train-evidence.json')
    entries = [row for row in evidence.get('entries') or [] if isinstance(row, dict)]
    edges = [row for row in load('same-train-edges.json').get('edges') or [] if isinstance(row, dict)]
    runtime = load('runtime-same-train.json').get('edges') or []
    fragments = load('fragments/keikyu.json').get('fragments') or []
    by_id = {str(row.get('id') or ''): row for row in fragments if isinstance(row, dict) and row.get('id')}

    production_pairs = {(str(row.get('fromFragment') or ''), str(row.get('toFragment') or '')) for row in entries}
    materialized = [row for row in edges if EDGE_MARKER in (row.get('evidence') or [])]
    edge_pairs = {(str(row.get('fromFragment') or ''), str(row.get('toFragment') or '')) for row in materialized}
    missing_edges = production_pairs - edge_pairs

    expected_runtime: set[tuple[str, str, str, str]] = set()
    missing_fragment_refs: list[tuple[str, str]] = []
    for source_id, target_id in production_pairs:
        source = by_id.get(source_id)
        target = by_id.get(target_id)
        if not source or not target:
            missing_fragment_refs.append((source_id, target_id))
            continue
        expected_runtime.add((
            runtime_ref(source),
            runtime_ref(target),
            str(source.get('railway') or ''),
            str(target.get('railway') or ''),
        ))
    runtime_set = {tuple(row) for row in runtime if isinstance(row, list) and len(row) == 4}
    missing_runtime = expected_runtime - runtime_set
    directions = Counter(str(row.get('direction') or '') for row in entries)

    result = {
        'productionEvidence': len(entries),
        'directions': dict(directions),
        'officialSameTrainEdges': len(materialized),
        'missingSameTrainPairs': len(missing_edges),
        'missingFragmentRefs': len(missing_fragment_refs),
        'expectedRuntimeEdges': len(expected_runtime),
        'missingRuntimeEdges': len(missing_runtime),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not entries:
        raise RuntimeError('Keikyu Main-Airport production evidence is empty')
    if directions['main-to-airport'] <= 0 or directions['airport-to-main'] <= 0:
        raise RuntimeError(f'Both Keikyu Main-Airport directions are required: {dict(directions)}')
    if any(row.get('matchStatus') != 'matched-singleton' for row in entries):
        raise RuntimeError('Non-singleton Keikyu Main-Airport evidence leaked into production')
    if missing_fragment_refs:
        raise RuntimeError(f'Stale Keikyu Main-Airport fragment refs: {missing_fragment_refs[:5]}')
    if missing_edges:
        raise RuntimeError(f'Keikyu Main-Airport evidence missing same-train edges: {list(missing_edges)[:5]}')
    if any(row.get('identityLevel') != 'evidence-backed' for row in materialized):
        raise RuntimeError('Unexpected Keikyu Main-Airport identity level')
    if missing_runtime:
        raise RuntimeError(f'Keikyu Main-Airport evidence missing runtime edges: {list(missing_runtime)[:5]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
