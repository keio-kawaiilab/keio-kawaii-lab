#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path('.')
V1 = ROOT / 'data/transit'

SEIBU_SOURCE = V1 / 'line8-line13/seibu-official-exact-through-trains.json'
SOTETSU_SOURCE = V1 / 'fukutoshin/sotetsu-official-line13-columns.json'

SOTETSU_BOUNDARY_IDS = {
    'toyoko-tokyushinyokohama-hiyoshi': 'tokyu-toyoko-shinyokohama-hiyoshi',
    'tokyushinyokohama-sotetsushinyokohama-shinyokohama': 'tokyu-sotetsu-shinyokohama',
}

SEIBU_PAIR_SPECS = {
    frozenset({'odpt.Railway:Seibu.Ikebukuro', 'odpt.Railway:Seibu.SeibuYurakucho'}):
        ('seibuyurakucho-ikebukuro-nerima', 'seibu-ikebukuro-yurakucho-nerima'),
    frozenset({'odpt.Railway:Seibu.SeibuYurakucho', 'odpt.Railway:TokyoMetro.Yurakucho'}):
        ('yurakucho-seibu-kotake-mukaihara', 'yurakucho-seibu-kotakemukaihara'),
    frozenset({'odpt.Railway:Seibu.SeibuYurakucho', 'odpt.Railway:TokyoMetro.Fukutoshin'}):
        ('fukutoshin-seibu-kotake-mukaihara', 'fukutoshin-seibu-kotakemukaihara'),
    frozenset({'odpt.Railway:Tokyu.Toyoko', 'odpt.Railway:TokyoMetro.Fukutoshin'}):
        ('metro-tokyu-shibuya', 'toyoko-fukutoshin-shibuya'),
    frozenset({'odpt.Railway:Tokyu.Toyoko', 'manual.Railway:YokohamaMinatomirai.Minatomirai'}):
        ('tokyu-minatomirai-yokohama', 'minatomirai-toyoko-yokohama'),
}


def load_json(path: Path, default: Any = None) -> Any:
    try:
        text = path.read_text(encoding='utf-8').strip()
        return json.loads(text) if text else default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def station_names() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(V1.glob('*/entities.json')):
        payload = load_json(path, {}) or {}
        for row in payload.get('Station') or []:
            if not isinstance(row, dict):
                continue
            station_id = str(row.get('owl:sameAs') or '')
            title = row.get('dc:title')
            if not isinstance(title, str) or not title:
                titles = row.get('odpt:stationTitle') or {}
                title = str(titles.get('ja') or titles.get('en') or '') if isinstance(titles, dict) else ''
            if station_id and title:
                result[station_id] = title
    return result


def fragment_times(fragment: dict[str, Any], names: dict[str, str]) -> dict[str, set[int]]:
    result: dict[str, set[int]] = defaultdict(set)
    for stop in fragment.get('stops') or []:
        if not isinstance(stop, list) or not stop:
            continue
        name = names.get(str(stop[0] or ''), '')
        if not name:
            continue
        for raw in stop[1:3]:
            if raw is None:
                continue
            try:
                result[name].add(int(raw) % 1440)
            except (TypeError, ValueError):
                pass
    return result


def parse_clock(value: Any) -> int | None:
    text = str(value or '').strip()
    if not text:
        return None
    if ':' in text:
        parts = text.split(':', 1)
        if not all(part.isdigit() for part in parts):
            return None
        hour, minute = int(parts[0]), int(parts[1])
    else:
        digits = ''.join(ch for ch in text if ch.isdigit())
        if len(digits) < 3:
            return None
        hour, minute = int(digits[:-2]), int(digits[-2:])
    if minute > 59:
        return None
    return (hour * 60 + minute) % 1440


def published_page_times(row: dict[str, Any]) -> dict[str, set[int]]:
    result: dict[str, set[int]] = defaultdict(set)
    for stop in row.get('stops') or []:
        if not isinstance(stop, dict):
            continue
        name = str(stop.get('station') or '')
        if not name:
            continue
        for key in ('arrival', 'departure'):
            minute = parse_clock(stop.get(key))
            if minute is not None:
                result[name].add(minute)
    return result


def published_column_times(row: dict[str, Any]) -> dict[str, set[int]]:
    result: dict[str, set[int]] = defaultdict(set)
    for name, raw in (row.get('printedTimes') or {}).items():
        minute = parse_clock(raw)
        if minute is not None:
            result[str(name)].add(minute)
    return result


def exact_match_names(fragment: dict[str, Any], published: dict[str, set[int]], names: dict[str, str]) -> list[str]:
    observed = fragment_times(fragment, names)
    return sorted(name for name, minutes in published.items() if observed.get(name, set()) & minutes)


def seibu_calendar(row: dict[str, Any]) -> str:
    dw = str((row.get('sourceParameters') or {}).get('dw') or '')
    if dw == '0':
        return 'odpt.Calendar:Weekday'
    if dw == '1':
        return 'odpt.Calendar:SaturdayHoliday'
    return ''


def sotetsu_calendar(row: dict[str, Any]) -> str:
    value = str(row.get('calendar') or '').lower()
    if value == 'weekday':
        return 'odpt.Calendar:Weekday'
    if value in {'holiday', 'saturdayholiday', 'saturdayandholiday', 'weekend'}:
        return 'odpt.Calendar:SaturdayHoliday'
    return ''


def verified_boundary(indexes: dict[str, Any], source: str, target: str, expected_id: str) -> dict[str, Any] | None:
    for row in (indexes.get('graph') or {}).get(source, []):
        if str(row.get('toRailway') or '') != target:
            continue
        if expected_id and str(row.get('boundaryId') or '') != expected_id:
            continue
        return row
    return None


def add_edge(
    edges: list[dict[str, Any]],
    linked_from: set[str],
    source: dict[str, Any],
    target: dict[str, Any],
    boundary: dict[str, Any],
    evidence: list[str],
    source_matches: list[str],
    target_matches: list[str],
    extra: dict[str, Any],
) -> None:
    source_id = str(source.get('id') or '')
    target_id = str(target.get('id') or '')
    if not source_id or not target_id or source_id in linked_from:
        return
    edges.append({
        'fromFragment': source_id,
        'toFragment': target_id,
        'classification': 'same-train',
        'identityLevel': 'evidence-backed',
        'evidence': evidence,
        'boundary': {
            'station': str(boundary.get('station') or ''),
            'fromRailway': str(source.get('railway') or ''),
            'toRailway': str(target.get('railway') or ''),
        },
        'alignment': {
            'mode': 'exact-published-station-time',
            'sourceMatchedStations': source_matches,
            'targetMatchedStations': target_matches,
        },
        **extra,
    })
    linked_from.add(source_id)


def apply_seibu_pages(
    fragments: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    indexes: dict[str, Any],
    names: dict[str, str],
    linked_from: set[str],
) -> dict[str, int]:
    payload = load_json(SEIBU_SOURCE, {}) or {}
    policy = payload.get('identityPolicy') or {}
    if not payload:
        return {'added': 0, 'sourceAmbiguous': 0, 'targetAmbiguous': 0}
    if policy.get('singlePublishedOneTrainPageMayEstablishIdentity') is not True:
        raise RuntimeError('Seibu official one-train identity policy is missing')
    for key in ('timeProximityMayEstablishIdentity', 'trainNumberAloneMayEstablishIdentity', 'destinationAloneMayEstablishIdentity'):
        if policy.get(key) is not False:
            raise RuntimeError(f'Unsafe Seibu identity policy: {key}')

    rows: list[dict[str, Any]] = []
    for row in payload.get('authoritativeThroughTrains') or []:
        if not isinstance(row, dict) or row.get('identityEvidence') != 'single-published-one-train-page':
            continue
        calendar = seibu_calendar(row)
        published = published_page_times(row)
        if calendar and len(published) >= 2:
            rows.append({'row': row, 'calendar': calendar, 'published': published})

    by_rail_calendar: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for fragment in fragments:
        by_rail_calendar[(str(fragment.get('railway') or ''), str(fragment.get('calendar') or ''))].append(fragment)

    stats = {'added': 0, 'sourceAmbiguous': 0, 'targetAmbiguous': 0}
    for source in fragments:
        source_id = str(source.get('id') or '')
        if not source_id or source_id in linked_from or source.get('sourceKind') != 'station-timetable-reconstruction':
            continue
        path = [str(value) for value in source.get('throughRailwayPath') or [] if value]
        if len(path) < 2:
            continue
        source_railway = str(source.get('railway') or '')
        target_railway = path[1]
        spec = SEIBU_PAIR_SPECS.get(frozenset({source_railway, target_railway}))
        if not spec:
            continue
        published_boundary_id, canonical_boundary_id = spec
        calendar = str(source.get('calendar') or '')
        candidates: list[tuple[dict[str, Any], list[str]]] = []
        for item in rows:
            row = item['row']
            if item['calendar'] != calendar or published_boundary_id not in (row.get('boundaries') or []):
                continue
            matched = exact_match_names(source, item['published'], names)
            if len(matched) >= 2:
                candidates.append((item, matched))
        if len(candidates) != 1:
            if len(candidates) > 1:
                stats['sourceAmbiguous'] += 1
            continue

        item, source_matches = candidates[0]
        target_candidates: list[tuple[dict[str, Any], list[str]]] = []
        for target in by_rail_calendar.get((target_railway, calendar), []):
            matched = exact_match_names(target, item['published'], names)
            if len(matched) >= 2:
                target_candidates.append((target, matched))
        if len(target_candidates) != 1:
            if len(target_candidates) > 1:
                stats['targetAmbiguous'] += 1
            continue

        target, target_matches = target_candidates[0]
        boundary = verified_boundary(indexes, source_railway, target_railway, canonical_boundary_id)
        if not boundary:
            continue
        row = item['row']
        url = str(row.get('url') or '')
        add_edge(
            edges, linked_from, source, target, boundary,
            ['operator-official-single-train-page:seibu', url, 'exact-published-stop-time-alignment'],
            source_matches, target_matches,
            {
                'officialTrainUrl': url,
                'officialTrainParameters': row.get('sourceParameters') or {},
                'officialBoundaryId': published_boundary_id,
            },
        )
        stats['added'] += 1
    return stats


def apply_sotetsu_columns(
    fragments: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    indexes: dict[str, Any],
    names: dict[str, str],
    linked_from: set[str],
) -> dict[str, int]:
    payload = load_json(SOTETSU_SOURCE, {}) or {}
    policy = payload.get('identityPolicy') or {}
    if not payload:
        return {'added': 0, 'sourceAmbiguous': 0, 'targetAmbiguous': 0}
    if policy.get('officialSamePrintedColumnMayEstablishIdentity') is not True:
        raise RuntimeError('Sotetsu official printed-column identity policy is missing')
    if policy.get('exactPrintedStationTimesRequired') is not True:
        raise RuntimeError('Sotetsu exact printed time policy is missing')
    for key in ('timeProximityMayEstablishIdentity', 'trainNumberAloneMayEstablishIdentity', 'destinationAloneMayEstablishIdentity'):
        if policy.get(key) is not False:
            raise RuntimeError(f'Unsafe Sotetsu identity policy: {key}')

    rows: list[dict[str, Any]] = []
    for row in payload.get('authoritativeColumns') or []:
        if not isinstance(row, dict) or row.get('identityEvidence') != 'official-same-printed-column' or row.get('status') != 'verified':
            continue
        calendar = sotetsu_calendar(row)
        published = published_column_times(row)
        if calendar and len(published) >= 3:
            rows.append({'row': row, 'calendar': calendar, 'published': published})

    by_rail_calendar: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for fragment in fragments:
        by_rail_calendar[(str(fragment.get('railway') or ''), str(fragment.get('calendar') or ''))].append(fragment)

    stats = {'added': 0, 'sourceAmbiguous': 0, 'targetAmbiguous': 0}
    for source in fragments:
        source_id = str(source.get('id') or '')
        if not source_id or source_id in linked_from or source.get('sourceKind') != 'station-timetable-reconstruction':
            continue
        path = [str(value) for value in source.get('throughRailwayPath') or [] if value]
        if len(path) < 2:
            continue
        source_railway = str(source.get('railway') or '')
        target_railway = path[1]
        calendar = str(source.get('calendar') or '')

        candidates: list[tuple[dict[str, Any], list[str]]] = []
        for item in rows:
            row = item['row']
            if item['calendar'] != calendar:
                continue
            if str(row.get('fromRailway') or '') != source_railway or str(row.get('toRailway') or '') != target_railway:
                continue
            matched = exact_match_names(source, item['published'], names)
            if len(matched) >= 1:
                candidates.append((item, matched))
        if len(candidates) != 1:
            if len(candidates) > 1:
                stats['sourceAmbiguous'] += 1
            continue

        item, source_matches = candidates[0]
        target_candidates: list[tuple[dict[str, Any], list[str]]] = []
        for target in by_rail_calendar.get((target_railway, calendar), []):
            matched = exact_match_names(target, item['published'], names)
            if len(matched) >= 2:
                target_candidates.append((target, matched))
        if len(target_candidates) != 1:
            if len(target_candidates) > 1:
                stats['targetAmbiguous'] += 1
            continue

        target, target_matches = target_candidates[0]
        row = item['row']
        published_boundary_id = str(row.get('canonicalBoundaryId') or '')
        canonical_boundary_id = SOTETSU_BOUNDARY_IDS.get(published_boundary_id, published_boundary_id)
        boundary = verified_boundary(indexes, source_railway, target_railway, canonical_boundary_id)
        if not boundary:
            continue
        url = str(row.get('sourceUrl') or '')
        add_edge(
            edges, linked_from, source, target, boundary,
            ['operator-official-same-printed-column:sotetsu', url, 'exact-published-stop-time-alignment'],
            source_matches, target_matches,
            {
                'officialColumnId': str(row.get('id') or ''),
                'officialSourceUrl': url,
                'officialPdfPage': row.get('pdfPage'),
                'officialColumnX': row.get('columnX'),
                'officialBoundaryId': published_boundary_id,
                'serviceBoundaryId': canonical_boundary_id,
            },
        )
        stats['added'] += 1
    return stats


def apply(
    fragments: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    indexes: dict[str, Any],
) -> list[dict[str, Any]]:
    del unresolved  # This bridge is fail-closed: unmatched evidence stays unresolved later.
    names = station_names()
    linked_from = {
        str(edge.get('fromFragment') or '')
        for edge in edges
        if edge.get('classification') == 'same-train'
    }
    seibu = apply_seibu_pages(fragments, edges, indexes, names, linked_from)
    sotetsu = apply_sotetsu_columns(fragments, edges, indexes, names, linked_from)
    print(json.dumps({'existingOfficialTrainEvidence': {'seibu': seibu, 'sotetsu': sotetsu}}, ensure_ascii=False))
    return edges
