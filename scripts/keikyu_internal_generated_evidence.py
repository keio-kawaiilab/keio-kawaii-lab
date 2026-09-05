#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import keikyu_official_train_evidence as parser

MAIN = 'odpt.Railway:Keikyu.Main'
AIRPORT = 'odpt.Railway:Keikyu.Airport'
KURIHAMA = 'odpt.Railway:Keikyu.Kurihama'

AIRPORT_BOUNDARY_ID = 'keikyu-main-airport-kamata'
KURIHAMA_BOUNDARY_ID = 'keikyu-main-kurihama-horinouchi'
AIRPORT_MARKER = 'same-printed-column-includes-shinagawa-and-haneda'
KURIHAMA_MARKER = 'same-printed-column-links-shinagawa-and-explicit-kurihama-origin-or-terminal'

# Backward-compatible aliases used by existing tests/callers.
BOUNDARY_ID = AIRPORT_BOUNDARY_ID
MARKER = AIRPORT_MARKER

SPECS = {
    AIRPORT_BOUNDARY_ID: {
        'marker': AIRPORT_MARKER,
        'station': '京急蒲田',
        'pairs': {(MAIN, AIRPORT), (AIRPORT, MAIN)},
        'edgeMarker': 'keikyu-official-main-airport-same-column-two-point',
    },
    KURIHAMA_BOUNDARY_ID: {
        'marker': KURIHAMA_MARKER,
        'station': '堀ノ内',
        'pairs': {(MAIN, KURIHAMA), (KURIHAMA, MAIN)},
        'edgeMarker': 'keikyu-official-main-kurihama-same-column-endpoint-two-point',
    },
}
KURIHAMA_ENDPOINT_SUFFIXES = {'.Misakiguchi', '.Miurakaigan', '.KeikyuKurihama'}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def stop_has_exact(fragment: dict[str, Any], suffix: str, minute: int) -> bool:
    for stop in fragment.get('stops') or []:
        if not isinstance(stop, list) or len(stop) < 3 or not str(stop[0] or '').endswith(suffix):
            continue
        for value in stop[1:3]:
            if isinstance(value, (int, float)) and int(value) % 1440 == minute % 1440:
                return True
    return False


def direction_matches(fragment: dict[str, Any], outbound: bool) -> bool:
    value = str(fragment.get('direction') or '')
    wanted = 'Outbound' if outbound else 'Inbound'
    return value == wanted or value.endswith(':' + wanted)


def kurihama_entry_matches_fragments(
    entry: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
) -> bool:
    policy = entry.get('matchPolicy') or {}
    if (
        policy.get('officialSamePrintedColumnRequired') is not True
        or policy.get('explicitBranchOriginOrTerminalRequired') is not True
        or policy.get('exactShinagawaMinuteRequired') is not True
        or policy.get('exactBranchEndpointMinuteRequired') is not True
        or policy.get('singletonFragmentMatchRequiredAtBothPoints') is not True
        or int(policy.get('stationMinuteTolerance', -1)) != 0
        or policy.get('trainNumberAloneMayEstablishIdentity') is not False
        or policy.get('timeProximityAloneMayEstablishIdentity') is not False
        or policy.get('destinationAloneMayEstablishIdentity') is not False
    ):
        return False

    suffix = str(entry.get('branchEndpointStationSuffix') or '')
    role = str(entry.get('branchEndpointRole') or '')
    if suffix not in KURIHAMA_ENDPOINT_SUFFIXES or role not in {'origin', 'terminal'}:
        return False
    try:
        shinagawa = int(entry['shinagawaMinute'])
        branch_minute = int(entry['branchEndpointMinute'])
    except (KeyError, TypeError, ValueError):
        return False

    public_direction = str(entry.get('direction') or '')
    if public_direction == 'main-to-kurihama':
        main_fragment, branch_fragment, outbound = source, target, True
        if role != 'terminal':
            return False
    elif public_direction == 'kurihama-to-main':
        branch_fragment, main_fragment, outbound = source, target, False
        if role != 'origin':
            return False
    else:
        return False

    if str(main_fragment.get('railway') or '') != MAIN or str(branch_fragment.get('railway') or '') != KURIHAMA:
        return False
    if not parser.calendar_matches(main_fragment.get('calendar'), str(entry.get('calendar') or '')):
        return False
    if not parser.calendar_matches(branch_fragment.get('calendar'), str(entry.get('calendar') or '')):
        return False
    return (
        direction_matches(main_fragment, outbound)
        and direction_matches(branch_fragment, outbound)
        and stop_has_exact(main_fragment, '.Shinagawa', shinagawa)
        and stop_has_exact(branch_fragment, suffix, branch_minute)
    )


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
        spec = SPECS.get(boundary_id)

        reason = ''
        if not spec:
            reason = 'unexpected-boundary-id'
        elif str(spec['marker']) not in evidence:
            reason = 'missing-official-two-point-marker'
        elif source_matches != [source_id] or target_matches != [target_id]:
            reason = 'non-singleton-recorded-match'
        elif not source or not target:
            reason = 'stale-fragment-reference'
        elif pair not in spec['pairs']:
            reason = 'unexpected-railway-pair'
        elif str(source.get('railway') or '') != pair[0] or str(target.get('railway') or '') != pair[1]:
            reason = 'fragment-railway-mismatch'
        elif boundary_id == KURIHAMA_BOUNDARY_ID and not kurihama_entry_matches_fragments(entry, source, target):
            reason = 'kurihama-exact-two-point-revalidation-failed'
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
                'evidence': [str(spec['edgeMarker']), eid],
                'sourceUrls': [str(entry.get('sourceUrl'))] if entry.get('sourceUrl') else [],
                'boundary': {
                    'station': str(spec['station']),
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
