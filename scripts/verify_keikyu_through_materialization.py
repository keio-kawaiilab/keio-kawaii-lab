#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path('data/transit-v2')
MARKER = 'keikyu-official-connection-timetable-same-column'
KEIKYU = 'odpt.Railway:Keikyu.Main'
TOEI = 'odpt.Railway:Toei.Asakusa'


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise RuntimeError(f'Expected JSON object: {path}')
    return value


def runtime_ref(fragment: dict[str, Any] | None) -> str:
    if not fragment:
        return ''
    source_kind = str(fragment.get('sourceKind') or '')
    if source_kind == 'exact-train-timetable':
        timetable_id = str(fragment.get('timetableId') or '')
        return f'tt:{timetable_id}' if timetable_id else ''
    if source_kind == 'station-timetable-reconstruction':
        trip_index = fragment.get('sourceTripIndex')
        railway = str(fragment.get('railway') or '')
        if isinstance(trip_index, int) and railway:
            return f'inf:{railway}:{trip_index}'
    return ''


def load_fragments() -> dict[str, dict[str, Any]]:
    index = load(ROOT / 'index.json')
    output: dict[str, dict[str, Any]] = {}
    for rel in (index.get('fragmentFiles') or {}).values():
        payload = load(ROOT / str(rel))
        for fragment in payload.get('fragments') or []:
            if isinstance(fragment, dict) and fragment.get('id'):
                output[str(fragment['id'])] = fragment
    return output


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument('--repair-report', default='')
    args = cli.parse_args()

    evidence = load(ROOT / 'keikyu-official-train-evidence.json')
    entries = [row for row in evidence.get('entries') or [] if isinstance(row, dict)]
    edge_rows = [row for row in load(ROOT / 'same-train-edges.json').get('edges') or [] if isinstance(row, dict)]
    runtime_rows = load(ROOT / 'runtime-same-train.json').get('edges') or []
    runtime = {
        tuple(str(value or '') for value in row)
        for row in runtime_rows
        if isinstance(row, list) and len(row) == 4
    }
    fragments = load_fragments()

    directions: dict[str, int] = {}
    for entry in entries:
        direction = str(entry.get('direction') or '')
        directions[direction] = directions.get(direction, 0) + 1

    official_edges = [row for row in edge_rows if MARKER in (row.get('evidence') or [])]
    official_pairs = {
        (str(row.get('fromFragment') or ''), str(row.get('toFragment') or ''))
        for row in official_edges
    }
    production_pairs = {
        (str(row.get('fromFragment') or ''), str(row.get('toFragment') or ''))
        for row in entries
    }
    missing_same_train_pairs = sorted(production_pairs - official_pairs)

    expected_runtime: set[tuple[str, str, str, str]] = set()
    missing_runtime_refs: list[dict[str, str]] = []
    for entry in entries:
        source_id = str(entry.get('fromFragment') or '')
        target_id = str(entry.get('toFragment') or '')
        source = fragments.get(source_id)
        target = fragments.get(target_id)
        source_ref = runtime_ref(source)
        target_ref = runtime_ref(target)
        from_railway = str(entry.get('fromRailway') or '')
        to_railway = str(entry.get('toRailway') or '')
        if not source_ref or not target_ref or not from_railway or not to_railway:
            missing_runtime_refs.append({
                'evidenceId': str(entry.get('id') or ''),
                'fromFragment': source_id,
                'toFragment': target_id,
            })
            continue
        expected_runtime.add((source_ref, target_ref, from_railway, to_railway))

    missing_runtime = sorted(expected_runtime - runtime)
    reverse_runtime = [
        row for row in expected_runtime
        if row[2] == KEIKYU and row[3] == TOEI and row in runtime
    ]
    forward_runtime = [
        row for row in expected_runtime
        if row[2] == TOEI and row[3] == KEIKYU and row in runtime
    ]

    summary: dict[str, Any] = {
        'productionEvidence': len(entries),
        'directions': directions,
        'officialSameTrainEdges': len(official_edges),
        'missingSameTrainPairs': len(missing_same_train_pairs),
        'expectedRuntimeEdges': len(expected_runtime),
        'missingRuntimeRefs': len(missing_runtime_refs),
        'missingRuntimeEdges': len(missing_runtime),
        'runtimeKeikyuToToei': len(reverse_runtime),
        'runtimeToeiToKeikyu': len(forward_runtime),
    }

    if args.repair_report:
        report = load(Path(args.repair_report))
        patch = report.get('patch') or {}
        before = report.get('beforeSengakujiEnds') or {}
        after = report.get('afterSengakujiEnds') or {}
        summary['syntheticRows'] = int(patch.get('syntheticRows') or 0)
        summary['beforeSengakujiEnds'] = before
        summary['afterSengakujiEnds'] = after
        if summary['syntheticRows'] <= 0:
            raise AssertionError('repair generated no strict synthetic Sengakuji rows')
        if sum(int(value or 0) for value in after.values()) <= sum(int(value or 0) for value in before.values()):
            raise AssertionError('repair did not improve Sengakuji endpoint coverage')

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if missing_same_train_pairs:
        print('MISSING_SAME_TRAIN_PAIR_EXAMPLES', json.dumps(missing_same_train_pairs[:20], ensure_ascii=False, indent=2))
    if missing_runtime_refs:
        print('MISSING_RUNTIME_REF_EXAMPLES', json.dumps(missing_runtime_refs[:20], ensure_ascii=False, indent=2))
    if missing_runtime:
        print('MISSING_RUNTIME_EDGE_EXAMPLES', json.dumps(missing_runtime[:20], ensure_ascii=False, indent=2))

    assert entries, 'official production evidence is empty'
    assert all(row.get('matchStatus') == 'matched-singleton' for row in entries), 'non-singleton evidence leaked into production'
    assert directions.get('keikyu-to-toei', 0) > 0, directions
    assert directions.get('toei-to-keikyu', 0) > 0, directions
    assert not missing_same_train_pairs, 'production evidence did not materialize in same-train-edges.json'
    assert not missing_runtime_refs, 'production evidence references fragments that cannot materialize at runtime'
    assert not missing_runtime, 'production evidence did not materialize in runtime-same-train.json'
    assert reverse_runtime, 'no Keikyu -> Toei official runtime same-train edges'
    assert forward_runtime, 'no Toei -> Keikyu official runtime same-train edges'
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
