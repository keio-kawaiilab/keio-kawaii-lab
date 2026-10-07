#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path('.')
EVIDENCE = Path('data/transit/fukutoshin/seibu-official-linked-through-trains.json')
ENTITY_FILES = (
    Path('data/transit/seibu/entities.json'),
    Path('data/transit/tokyo-metro/entities.json'),
)


def load_json(path: Path, default: Any = None) -> Any:
    try:
        text = path.read_text(encoding='utf-8').strip()
        return json.loads(text) if text else default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def station_titles(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for rel in ENTITY_FILES:
        data = load_json(root / rel, {}) or {}
        for row in data.get('Station') or []:
            if not isinstance(row, dict):
                continue
            sid = str(row.get('owl:sameAs') or '')
            title = row.get('odpt:stationTitle') or {}
            name = str(row.get('dc:title') or (title.get('ja') if isinstance(title, dict) else '') or '')
            if sid and name:
                result[sid] = name
    return result


def parse_clock(value: Any) -> int | None:
    text = str(value or '')
    if ':' not in text:
        return None
    try:
        hour, minute = (int(part) for part in text.split(':', 1))
    except ValueError:
        return None
    if hour < 0 or minute < 0 or minute >= 60:
        return None
    return hour * 60 + minute


def normalized_page_stops(row: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous: int | None = None
    day_offset = 0
    for index, stop in enumerate(row.get('stops') or []):
        if not isinstance(stop, dict):
            continue
        item: dict[str, Any] = {'station': str(stop.get('station') or ''), 'index': index}
        for key in ('arrival', 'departure'):
            raw = parse_clock(stop.get(key))
            if raw is None:
                item[key] = None
                continue
            value = raw + day_offset
            while previous is not None and value < previous:
                day_offset += 1440
                value = raw + day_offset
            previous = value
            item[key] = value
        output.append(item)
    return output


def page_calendar(row: dict[str, Any]) -> str:
    dw = str((row.get('sourceParameters') or {}).get('dw') or '')
    if dw == '0':
        return 'odpt.Calendar:Weekday'
    if dw == '1':
        return 'odpt.Calendar:SaturdayHoliday'
    return ''


def page_index(stops: list[dict[str, Any]]) -> dict[tuple[str, int], set[int]]:
    index: dict[tuple[str, int], set[int]] = defaultdict(set)
    for stop in stops:
        name = str(stop.get('station') or '')
        if not name:
            continue
        for key in ('arrival', 'departure'):
            value = stop.get(key)
            if isinstance(value, int):
                index[(name, value)].add(int(stop.get('index') or 0))
    return index


def fragment_matches(
    fragment: dict[str, Any],
    titles: dict[str, str],
    published_index: dict[tuple[str, int], set[int]],
) -> dict[str, Any] | None:
    matched_names: set[str] = set()
    matched_page_indices: set[int] = set()
    last_page_index = -1
    for stop in fragment.get('stops') or []:
        if not isinstance(stop, list) or not stop:
            continue
        name = titles.get(str(stop[0] or ''), '')
        if not name:
            continue
        candidate_indices: set[int] = set()
        for raw in stop[1:3]:
            if not isinstance(raw, (int, float)):
                continue
            candidate_indices.update(published_index.get((name, int(raw)), set()))
        if not candidate_indices:
            continue
        usable = sorted(value for value in candidate_indices if value >= last_page_index)
        if not usable:
            return None
        chosen = usable[0]
        last_page_index = chosen
        matched_names.add(name)
        matched_page_indices.add(chosen)
    if len(matched_names) < 2:
        return None
    return {
        'stations': sorted(matched_names),
        'pageIndices': sorted(matched_page_indices),
        'firstPageIndex': min(matched_page_indices),
        'lastPageIndex': max(matched_page_indices),
    }


def boundary_for(indexes: dict[str, Any], source: str, target: str) -> dict[str, Any] | None:
    for row in (indexes.get('graph') or {}).get(source, []):
        if str(row.get('toRailway') or '') == target:
            return row
    return None


def validate_evidence(data: dict[str, Any]) -> None:
    policy = data.get('identityPolicy') or {}
    if policy.get('singlePublishedOneTrainPageMayEstablishIdentity') is not True:
        raise RuntimeError('Seibu exact evidence does not authorize a single published train page')
    for key in ('timeProximityMayEstablishIdentity', 'trainNumberAloneMayEstablishIdentity', 'destinationAloneMayEstablishIdentity'):
        if policy.get(key) is not False:
            raise RuntimeError(f'Unsafe Seibu identity policy: {key}')


def apply_existing_seibu_exact_evidence(
    fragments: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    indexes: dict[str, Any],
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    evidence = load_json(root / EVIDENCE, {}) or {}
    validate_evidence(evidence)
    titles = station_titles(root)

    published_pages: list[dict[str, Any]] = []
    for row in evidence.get('authoritativeThroughTrains') or []:
        if not isinstance(row, dict) or row.get('identityEvidence') != 'single-published-one-train-page':
            continue
        url = str(row.get('url') or '')
        if not url.startswith('https://seibu.ekitan.com/norikae/timetable/onetraintimetable/'):
            continue
        stops = normalized_page_stops(row)
        calendar = page_calendar(row)
        if not stops or not calendar:
            continue
        published_pages.append({
            'row': row,
            'url': url,
            'calendar': calendar,
            'index': page_index(stops),
        })

    by_railway_calendar: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for fragment in fragments:
        by_railway_calendar[
            (str(fragment.get('railway') or ''), str(fragment.get('calendar') or ''))
        ].append(fragment)

    output = list(edges)
    seen = {
        (str(edge.get('fromFragment') or ''), str(edge.get('toFragment') or ''))
        for edge in output
    }
    linked_from = {
        str(edge.get('fromFragment') or '')
        for edge in output
        if edge.get('classification') == 'same-train'
    }
    resolved_sources: set[str] = set()

    for source in fragments:
        source_id = str(source.get('id') or '')
        if (
            not source_id
            or source_id in linked_from
            or source.get('sourceOperator') != 'seibu'
            or source.get('sourceKind') != 'station-timetable-reconstruction'
        ):
            continue
        path = [str(value) for value in source.get('throughRailwayPath') or [] if value]
        if len(path) < 2 or path[0] != str(source.get('railway') or ''):
            continue
        target_railway = path[1]
        boundary = boundary_for(indexes, path[0], target_railway)
        if not boundary:
            continue

        source_page_matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for page in published_pages:
            if page['calendar'] != str(source.get('calendar') or ''):
                continue
            proof = fragment_matches(source, titles, page['index'])
            if proof:
                source_page_matches.append((page, proof))
        if len(source_page_matches) != 1:
            continue

        page, source_proof = source_page_matches[0]
        target_matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for target in by_railway_calendar.get((target_railway, str(source.get('calendar') or '')), []):
            target_proof = fragment_matches(target, titles, page['index'])
            if not target_proof:
                continue
            if target_proof['firstPageIndex'] < source_proof['lastPageIndex']:
                continue
            target_matches.append((target, target_proof))
        if len(target_matches) != 1:
            continue

        target, target_proof = target_matches[0]
        key = (source_id, str(target.get('id') or ''))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        linked_from.add(source_id)
        resolved_sources.add(source_id)
        output.append({
            'fromFragment': source_id,
            'toFragment': key[1],
            'classification': 'same-train',
            'identityLevel': 'evidence-backed',
            'evidence': [
                'operator-official-single-train-page',
                'existing-seibu-exact-evidence-bridge',
            ],
            'sourceUrls': [page['url']],
            'boundary': {
                'station': str(boundary.get('station') or ''),
                'fromRailway': path[0],
                'toRailway': target_railway,
            },
            'exactMatch': {
                'sourceStations': source_proof['stations'],
                'targetStations': target_proof['stations'],
                'sourceParameters': page['row'].get('sourceParameters') or {},
            },
        })

    if resolved_sources:
        unresolved[:] = [
            row
            for row in unresolved
            if not (
                row.get('kind') == 'ambiguous-boundary-fragment-alignment'
                and str(row.get('fragment') or '') in resolved_sources
            )
        ]
    return output
