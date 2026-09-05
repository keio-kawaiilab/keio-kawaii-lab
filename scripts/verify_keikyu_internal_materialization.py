#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path('data/transit-v2')
MAIN = 'odpt.Railway:Keikyu.Main'
AIRPORT = 'odpt.Railway:Keikyu.Airport'
KURIHAMA = 'odpt.Railway:Keikyu.Kurihama'
AIRPORT_BOUNDARY_ID = 'keikyu-main-airport-kamata'
KURIHAMA_BOUNDARY_ID = 'keikyu-main-kurihama-horinouchi'
EDGE_MARKERS = {
    AIRPORT_BOUNDARY_ID: 'keikyu-official-main-airport-same-column-two-point',
    KURIHAMA_BOUNDARY_ID: 'keikyu-official-main-kurihama-same-column-endpoint-two-point',
}


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

    entries_by_boundary: dict[str, list[dict]] = defaultdict(list)
    for row in entries:
        entries_by_boundary[str(row.get('boundaryId') or '')].append(row)

    production_pairs = {
        (str(row.get('fromFragment') or ''), str(row.get('toFragment') or ''))
        for row in entries
    }
    materialized = [
        row for row in edges
        if any(marker in (row.get('evidence') or []) for marker in EDGE_MARKERS.values())
    ]
    edge_pairs = {
        (str(row.get('fromFragment') or ''), str(row.get('toFragment') or ''))
        for row in materialized
    }
    missing_edges = production_pairs - edge_pairs

    wrong_marker_pairs: list[tuple[str, str, str]] = []
    edge_by_pair = {
        (str(row.get('fromFragment') or ''), str(row.get('toFragment') or '')): row
        for row in materialized
    }
    for row in entries:
        pair = (str(row.get('fromFragment') or ''), str(row.get('toFragment') or ''))
        boundary_id = str(row.get('boundaryId') or '')
        marker = EDGE_MARKERS.get(boundary_id, '')
        edge = edge_by_pair.get(pair)
        if not marker or not edge or marker not in (edge.get('evidence') or []):
            wrong_marker_pairs.append((pair[0], pair[1], boundary_id))

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

    boundary_summary = {}
    for boundary_id, rows in sorted(entries_by_boundary.items()):
        boundary_summary[boundary_id] = {
            'entries': len(rows),
            'directions': dict(Counter(str(row.get('direction') or '') for row in rows)),
        }

    result = {
        'productionEvidence': len(entries),
        'boundaries': boundary_summary,
        'officialSameTrainEdges': len(materialized),
        'missingSameTrainPairs': len(missing_edges),
        'wrongMarkerPairs': len(wrong_marker_pairs),
        'missingFragmentRefs': len(missing_fragment_refs),
        'expectedRuntimeEdges': len(expected_runtime),
        'missingRuntimeEdges': len(missing_runtime),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    airport_entries = entries_by_boundary.get(AIRPORT_BOUNDARY_ID, [])
    kurihama_entries = entries_by_boundary.get(KURIHAMA_BOUNDARY_ID, [])
    airport_directions = Counter(str(row.get('direction') or '') for row in airport_entries)
    kurihama_directions = Counter(str(row.get('direction') or '') for row in kurihama_entries)

    if not airport_entries:
        raise RuntimeError('Keikyu Main-Airport production evidence is empty')
    if airport_directions['main-to-airport'] <= 0 or airport_directions['airport-to-main'] <= 0:
        raise RuntimeError(f'Both Keikyu Main-Airport directions are required: {dict(airport_directions)}')
    if not kurihama_entries:
        raise RuntimeError('Keikyu Main-Kurihama production evidence is empty')
    if kurihama_directions['kurihama-to-main'] <= 0 and kurihama_directions['main-to-kurihama'] <= 0:
        raise RuntimeError(f'No Keikyu Main-Kurihama direction materialized: {dict(kurihama_directions)}')
    if any(row.get('matchStatus') != 'matched-singleton' for row in entries):
        raise RuntimeError('Non-singleton Keikyu internal evidence leaked into production')
    if missing_fragment_refs:
        raise RuntimeError(f'Stale Keikyu internal fragment refs: {missing_fragment_refs[:5]}')
    if missing_edges:
        raise RuntimeError(f'Keikyu internal evidence missing same-train edges: {list(missing_edges)[:5]}')
    if wrong_marker_pairs:
        raise RuntimeError(f'Keikyu internal edge marker mismatch: {wrong_marker_pairs[:5]}')
    if any(row.get('identityLevel') != 'evidence-backed' for row in materialized):
        raise RuntimeError('Unexpected Keikyu internal identity level')
    if missing_runtime:
        raise RuntimeError(f'Keikyu internal evidence missing runtime edges: {list(missing_runtime)[:5]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
