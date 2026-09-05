#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAIN = 'odpt.Railway:Keikyu.Main'
AIRPORT = 'odpt.Railway:Keikyu.Airport'
KURIHAMA = 'odpt.Railway:Keikyu.Kurihama'
BOUNDARY_ID = 'keikyu-main-airport-kamata'
KURIHAMA_BOUNDARY_ID = 'keikyu-main-kurihama-horinouchi'
LEGACY_MARKER = 'same-printed-column-includes-shinagawa-and-haneda'
MARKER = 'same-printed-column-two-exact-station-times'

BOUNDARY_SPECS: dict[str, dict[str, Any]] = {
    BOUNDARY_ID: {
        'station': '京急蒲田',
        'pairs': {(MAIN, AIRPORT), (AIRPORT, MAIN)},
    },
    KURIHAMA_BOUNDARY_ID: {
        'station': '堀ノ内',
        'pairs': {(KURIHAMA, MAIN), (MAIN, KURIHAMA)},
    },
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def apply_generated_evidence(
    fragments: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    indexes: dict[str, Any],
    evidence_path: Path,
) -> list[dict[str, Any]]:
    payload = load_json(evidence_path)
    if not payload:
        return list(edges)
    policy = payload.get('policy') or {}
    if (
        policy.get('trainNumberAloneMayEstablishIdentity') is not False
        or policy.get('timeProximityAloneMayEstablishIdentity') is not False
        or policy.get('officialSamePrintedColumnRequired') is not True
        or policy.get('twoExactPublishedStationTimesRequired') is not True
        or policy.get('singletonFragmentMatchRequiredAtBothPoints') is not True
    ):
        unresolved.append({'kind': 'keikyu-internal-generated-evidence-unsafe-policy', 'path': str(evidence_path)})
        return list(edges)

    by_id = {str(row.get('id') or ''): row for row in fragments if row.get('id')}
    output = list(edges)
    seen = {(str(row.get('fromFragment') or ''), str(row.get('toFragment') or '')) for row in output}
    resolved_sources: set[str] = set()

    for entry in payload.get('entries') or []:
        if not isinstance(entry, dict) or entry.get('matchStatus') != 'matched-singleton':
            continue
        eid = str(entry.get('id') or '')
        source_id = str(entry.get('fromFragment') or '')
        target_id = str(entry.get('toFragment') or '')
        source = by_id.get(source_id)
        target = by_id.get(target_id)
        evidence = [str(value) for value in entry.get('evidence') or []]
        source_matches = [str(value) for value in entry.get('sourceMatches') or []]
        target_matches = [str(value) for value in entry.get('targetMatches') or []]
        pair = (str(entry.get('fromRailway') or ''), str(entry.get('toRailway') or ''))
        boundary_id = str(entry.get('boundaryId') or '')
        spec = BOUNDARY_SPECS.get(boundary_id)

        reason = ''
        if not spec or not ({MARKER, LEGACY_MARKER} & set(evidence)):
            reason = 'missing-official-two-point-marker'
        elif source_matches != [source_id] or target_matches != [target_id]:
            reason = 'non-singleton-recorded-match'
        elif not source or not target:
            reason = 'stale-fragment-reference'
        elif pair not in spec['pairs']:
            reason = 'unexpected-railway-pair'
        elif str(source.get('railway') or '') != pair[0] or str(target.get('railway') or '') != pair[1]:
            reason = 'fragment-railway-mismatch'
        else:
            boundary = next((
                row for row in indexes.get('graph', {}).get(pair[0], [])
                if str(row.get('toRailway') or '') == pair[1]
                and str(row.get('boundaryId') or '') == boundary_id
            ), None)
            if not boundary:
                reason = 'unverified-operational-boundary'

        if reason:
            unresolved.append({
                'kind': 'keikyu-internal-generated-evidence-rejected',
                'evidenceId': eid,
                'reason': reason,
                'fromFragment': source_id,
                'toFragment': target_id,
            })
            continue

        key = (source_id, target_id)
        if key not in seen:
            seen.add(key)
            output.append({
                'fromFragment': source_id,
                'toFragment': target_id,
                'classification': 'same-train',
                'identityLevel': 'evidence-backed',
                'evidence': ['keikyu-official-internal-same-column-two-point', eid],
                'sourceUrls': [str(entry.get('sourceUrl'))] if entry.get('sourceUrl') else [],
                'boundary': {
                    'station': spec['station'],
                    'fromRailway': pair[0],
                    'toRailway': pair[1],
                },
            })
        resolved_sources.add(source_id)

    if resolved_sources:
        unresolved[:] = [
            row for row in unresolved
            if not (
                row.get('kind') == 'ambiguous-boundary-fragment-alignment'
                and str(row.get('fragment') or '') in resolved_sources
            )
        ]
    return output
