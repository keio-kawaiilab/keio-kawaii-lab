#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import keikyu_generated_evidence as generated

ROOT = Path('data/transit-v2')
GENERATED_EDGE_MARKER = 'independently-verified-cross-boundary-continuation'
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


def evidence_values(row: dict[str, Any]) -> set[str]:
    return {str(value) for value in row.get('evidence') or [] if value}


def is_verified_production_entry(row: dict[str, Any]) -> bool:
    verification = row.get('verification') if isinstance(row.get('verification'), dict) else {}
    return (
        row.get('matchStatus') == 'matched-singleton'
        and generated.SAFE_CONTINUATION_MARKER in evidence_values(row)
        and verification.get('crossBoundaryContinuationVerified') is True
    )


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument('--repair-report', default='')
    args = cli.parse_args()

    evidence = load(ROOT / 'keikyu-official-train-evidence.json')
    entries = [row for row in evidence.get('entries') or [] if isinstance(row, dict)]
    safe_entries = [row for row in entries if is_verified_production_entry(row)]
    safe_ids = {str(row.get('id') or '') for row in safe_entries if row.get('id')}
    legacy_entries = [
        row for row in entries
        if generated.LEGACY_COLUMN_MARKER in evidence_values(row)
        and generated.SAFE_CONTINUATION_MARKER not in evidence_values(row)
    ]

    edge_rows = [row for row in load(ROOT / 'same-train-edges.json').get('edges') or [] if isinstance(row, dict)]
    runtime_rows = load(ROOT / 'runtime-same-train.json').get('edges') or []
    runtime = {
        tuple(str(value or '') for value in row)
        for row in runtime_rows
        if isinstance(row, list) and len(row) == 4
    }
    fragments = load_fragments()

    leaked_legacy_edges = [
        row for row in edge_rows
        if generated.LEGACY_COLUMN_MARKER in evidence_values(row)
        or 'keikyu-official-connection-timetable-same-column' in evidence_values(row)
    ]

    generated_edges = [row for row in edge_rows if GENERATED_EDGE_MARKER in evidence_values(row)]
    generated_by_evidence: dict[str, list[dict[str, Any]]] = {}
    unknown_generated_edges: list[dict[str, Any]] = []
    for edge in generated_edges:
        ids = [value for value in evidence_values(edge) if value in safe_ids]
        if len(ids) != 1:
            unknown_generated_edges.append(edge)
            continue
        generated_by_evidence.setdefault(ids[0], []).append(edge)

    missing_same_train_ids = sorted(
        safe_ids - set(generated_by_evidence)
    )
    duplicate_same_train_ids = sorted(
        evidence_id for evidence_id, rows in generated_by_evidence.items() if len(rows) != 1
    )

    expected_runtime: set[tuple[str, str, str, str]] = set()
    missing_runtime_refs: list[dict[str, str]] = []
    safe_directions: dict[str, int] = {}
    for entry in safe_entries:
        direction = str(entry.get('direction') or '')
        safe_directions[direction] = safe_directions.get(direction, 0) + 1
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

    summary: dict[str, Any] = {
        'candidateEvidence': len(entries),
        'legacySameColumnCandidates': len(legacy_entries),
        'verifiedProductionEvidence': len(safe_entries),
        'verifiedProductionDirections': safe_directions,
        'generatedVerifiedSameTrainEdges': len(generated_edges),
        'leakedLegacySameTrainEdges': len(leaked_legacy_edges),
        'unknownGeneratedEdges': len(unknown_generated_edges),
        'missingVerifiedSameTrainEvidenceIds': len(missing_same_train_ids),
        'duplicateVerifiedSameTrainEvidenceIds': len(duplicate_same_train_ids),
        'expectedRuntimeEdges': len(expected_runtime),
        'missingRuntimeRefs': len(missing_runtime_refs),
        'missingRuntimeEdges': len(missing_runtime),
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
    if leaked_legacy_edges:
        print('LEAKED_LEGACY_EDGE_EXAMPLES', json.dumps(leaked_legacy_edges[:10], ensure_ascii=False, indent=2))
    if unknown_generated_edges:
        print('UNKNOWN_GENERATED_EDGE_EXAMPLES', json.dumps(unknown_generated_edges[:10], ensure_ascii=False, indent=2))
    if missing_same_train_ids:
        print('MISSING_VERIFIED_EDGE_IDS', json.dumps(missing_same_train_ids[:20], ensure_ascii=False, indent=2))
    if duplicate_same_train_ids:
        print('DUPLICATE_VERIFIED_EDGE_IDS', json.dumps(duplicate_same_train_ids[:20], ensure_ascii=False, indent=2))
    if missing_runtime_refs:
        print('MISSING_RUNTIME_REF_EXAMPLES', json.dumps(missing_runtime_refs[:20], ensure_ascii=False, indent=2))
    if missing_runtime:
        print('MISSING_RUNTIME_EDGE_EXAMPLES', json.dumps(missing_runtime[:20], ensure_ascii=False, indent=2))

    # Candidate extraction should remain alive, but it is valid for independently
    # verified production evidence to be zero.  Unknown means "do not promote".
    assert entries, 'official Keikyu boundary candidate evidence is empty'
    assert not leaked_legacy_edges, 'legacy same-column evidence leaked into production same-train edges'
    assert not unknown_generated_edges, 'generated continuation edge lacks exactly one independently verified evidence id'
    assert not missing_same_train_ids, 'independently verified production evidence did not materialize as same-train'
    assert not duplicate_same_train_ids, 'independently verified evidence materialized more than once'
    assert not missing_runtime_refs, 'verified production evidence references fragments that cannot materialize at runtime'
    assert not missing_runtime, 'verified production evidence did not materialize in runtime-same-train.json'
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
