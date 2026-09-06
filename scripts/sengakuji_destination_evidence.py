#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from typing import Any

TOEI = 'odpt.Railway:Toei.Asakusa'
KEIKYU = 'odpt.Railway:Keikyu.Main'
TOEI_SENGAKUJI = 'odpt.Station:Toei.Asakusa.Sengakuji'
KEIKYU_SENGAKUJI = 'odpt.Station:Keikyu.Main.Sengakuji'
BOUNDARY_ID = 'toei-keikyu-sengakuji'
MAX_GAP_MINUTES = 2
MIN_RECONSTRUCTION_CONFIDENCE = 97
MARKER = 'operator-published-through-endpoint-across-sengakuji-v1'

DIRECTIONS = (
    {
        'name': 'toei-to-keikyu',
        'fromRailway': TOEI,
        'toRailway': KEIKYU,
        'fromStation': TOEI_SENGAKUJI,
        'toStation': KEIKYU_SENGAKUJI,
        'sourceKind': 'exact-train-timetable',
        'targetKind': 'station-timetable-reconstruction',
        'sourceOperator': 'toei',
        'targetOperator': 'keikyu',
        'sourceDestinationPrefix': 'odpt.Station:Keikyu.',
        'targetOriginPrefix': '',
    },
    {
        'name': 'keikyu-to-toei',
        'fromRailway': KEIKYU,
        'toRailway': TOEI,
        'fromStation': KEIKYU_SENGAKUJI,
        'toStation': TOEI_SENGAKUJI,
        'sourceKind': 'station-timetable-reconstruction',
        'targetKind': 'exact-train-timetable',
        'sourceOperator': 'keikyu',
        'targetOperator': 'toei',
        'sourceDestinationPrefix': '',
        'targetOriginPrefix': 'odpt.Station:Keikyu.',
    },
)


def stop_station(stop: Any) -> str:
    return str(stop[0] or '') if isinstance(stop, list) and stop else ''


def stop_arrival(stop: Any) -> int | None:
    if not isinstance(stop, list) or len(stop) < 2:
        return None
    raw = stop[1] if stop[1] is not None else (stop[2] if len(stop) > 2 else None)
    return int(raw) if isinstance(raw, (int, float)) else None


def stop_departure(stop: Any) -> int | None:
    if not isinstance(stop, list) or len(stop) < 2:
        return None
    raw = stop[2] if len(stop) > 2 and stop[2] is not None else stop[1]
    return int(raw) if isinstance(raw, (int, float)) else None


def references(fragment: dict[str, Any], key: str) -> list[str]:
    return [str(value) for value in fragment.get(key) or [] if value]


def station_railway(station: str) -> str:
    value = str(station or '')
    if not value.startswith('odpt.Station:'):
        return ''
    parts = value.split(':', 1)[1].split('.')
    if len(parts) < 3:
        return ''
    return f'odpt.Railway:{parts[0]}.{parts[1]}'


def boundary_minute(fragment: dict[str, Any], side: str) -> int | None:
    stops = fragment.get('stops') or []
    if not stops:
        return None
    return stop_departure(stops[0]) if side == 'start' else stop_arrival(stops[-1])


def matches_endpoint(fragment: dict[str, Any], railway: str, station: str, side: str) -> bool:
    if str(fragment.get('railway') or '') != railway:
        return False
    stops = fragment.get('stops') or []
    if not stops:
        return False
    endpoint = stops[0] if side == 'start' else stops[-1]
    return stop_station(endpoint) == station


def operator_name(fragment: dict[str, Any]) -> str:
    return str(fragment.get('sourceOperator') or fragment.get('operator') or '').lower()


def confidence(fragment: dict[str, Any]) -> float:
    try:
        return float(fragment.get('confidence') or 0)
    except (TypeError, ValueError):
        return 0


def structurally_eligible(fragment: dict[str, Any], kind: str, operator: str) -> bool:
    if str(fragment.get('sourceKind') or '') != kind:
        return False
    if operator_name(fragment) != operator:
        return False
    if kind == 'exact-train-timetable':
        return confidence(fragment) >= 100
    if kind == 'station-timetable-reconstruction':
        return confidence(fragment) >= MIN_RECONSTRUCTION_CONFIDENCE
    return False


def verified_boundary(indexes: dict[str, Any], from_railway: str, to_railway: str) -> dict[str, Any] | None:
    return next((
        row for row in indexes.get('graph', {}).get(from_railway, [])
        if str(row.get('toRailway') or '') == to_railway
        and str(row.get('boundaryId') or '') == BOUNDARY_ID
    ), None)


def shared_destination(source: dict[str, Any], target: dict[str, Any]) -> list[str]:
    target_set = set(references(target, 'destination'))
    return sorted(set(references(source, 'destination')) & target_set)


def advertised_beyond_source(fragment: dict[str, Any], destination: str) -> bool:
    railway = station_railway(destination)
    return bool(railway and railway != str(fragment.get('railway') or '') and not destination.endswith('.Sengakuji'))


def direction_specific_proof(source: dict[str, Any], target: dict[str, Any], spec: dict[str, Any], destination: str) -> bool:
    source_prefix = str(spec.get('sourceDestinationPrefix') or '')
    if source_prefix and not destination.startswith(source_prefix):
        return False
    target_origin_prefix = str(spec.get('targetOriginPrefix') or '')
    if target_origin_prefix:
        origins = references(target, 'origin')
        if not any(origin.startswith(target_origin_prefix) and not origin.endswith('.Sengakuji') for origin in origins):
            return False
    return True


def source_urls(fragment: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ('sourceUrl', 'url'):
        value = fragment.get(key)
        if isinstance(value, str) and value:
            values.append(value)
    for key in ('sourceUrls', 'urls'):
        raw = fragment.get(key)
        if isinstance(raw, list):
            values.extend(str(value) for value in raw if value)
    return values


def candidate_pairs(fragments: list[dict[str, Any]], indexes: dict[str, Any]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for spec in DIRECTIONS:
        if not verified_boundary(indexes, str(spec['fromRailway']), str(spec['toRailway'])):
            continue
        sources = [
            row for row in fragments
            if matches_endpoint(row, str(spec['fromRailway']), str(spec['fromStation']), 'end')
            and structurally_eligible(row, str(spec['sourceKind']), str(spec['sourceOperator']))
        ]
        targets = [
            row for row in fragments
            if matches_endpoint(row, str(spec['toRailway']), str(spec['toStation']), 'start')
            and structurally_eligible(row, str(spec['targetKind']), str(spec['targetOperator']))
        ]
        raw: list[tuple[dict[str, Any], dict[str, Any], int]] = []
        for source in sources:
            source_minute = boundary_minute(source, 'end')
            if source_minute is None:
                continue
            for target in targets:
                if str(source.get('calendar') or '') != str(target.get('calendar') or ''):
                    continue
                target_minute = boundary_minute(target, 'start')
                if target_minute is None:
                    continue
                gap = target_minute - source_minute
                if 0 <= gap <= MAX_GAP_MINUTES:
                    raw.append((source, target, gap))

        source_counts = Counter(str(source.get('id') or '') for source, _, _ in raw)
        target_counts = Counter(str(target.get('id') or '') for _, target, _ in raw)
        for source, target, gap in raw:
            source_id = str(source.get('id') or '')
            target_id = str(target.get('id') or '')
            if not source_id or not target_id:
                continue
            if source_counts[source_id] != 1 or target_counts[target_id] != 1:
                continue
            destinations = [
                destination for destination in shared_destination(source, target)
                if advertised_beyond_source(source, destination)
                and direction_specific_proof(source, target, spec, destination)
            ]
            if len(destinations) != 1:
                continue
            pairs.append({
                'direction': spec['name'],
                'fromFragment': source_id,
                'toFragment': target_id,
                'fromRailway': spec['fromRailway'],
                'toRailway': spec['toRailway'],
                'calendar': str(source.get('calendar') or ''),
                'gapMinutes': gap,
                'destination': destinations[0],
                'sourceUrls': sorted(set(source_urls(source) + source_urls(target))),
            })
    return pairs


def apply_sengakuji_destination_evidence(
    fragments: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    indexes: dict[str, Any],
) -> list[dict[str, Any]]:
    if not verified_boundary(indexes, TOEI, KEIKYU) or not verified_boundary(indexes, KEIKYU, TOEI):
        unresolved.append({'kind': 'sengakuji-destination-evidence-unverified-boundary', 'boundaryId': BOUNDARY_ID})
        return list(edges)

    output = list(edges)
    seen = {(str(edge.get('fromFragment') or ''), str(edge.get('toFragment') or '')) for edge in output}
    resolved_sources: set[str] = set()
    for pair in candidate_pairs(fragments, indexes):
        key = (str(pair['fromFragment']), str(pair['toFragment']))
        if key not in seen:
            seen.add(key)
            boundary = verified_boundary(indexes, str(pair['fromRailway']), str(pair['toRailway'])) or {}
            output.append({
                'fromFragment': pair['fromFragment'],
                'toFragment': pair['toFragment'],
                'classification': 'same-train',
                'identityLevel': 'evidence-backed',
                'evidence': [
                    MARKER,
                    'exact-shared-published-destination',
                    'unique-boundary-continuation-within-two-minutes',
                ],
                'sourceUrls': pair['sourceUrls'],
                'boundary': {
                    'station': boundary.get('station') or '泉岳寺',
                    'fromRailway': pair['fromRailway'],
                    'toRailway': pair['toRailway'],
                    'gapMinutes': pair['gapMinutes'],
                    'publishedDestination': pair['destination'],
                },
            })
        resolved_sources.add(str(pair['fromFragment']))

    if resolved_sources:
        unresolved[:] = [
            row for row in unresolved
            if not (
                row.get('kind') == 'ambiguous-boundary-fragment-alignment'
                and str(row.get('fragment') or '') in resolved_sources
            )
        ]
    return output
