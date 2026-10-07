#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path('.')
EVIDENCE_FILES = (
    Path('data/transit/fukutoshin/sotetsu-official-line13-columns.json'),
    Path('data/transit/meguro/sotetsu-official-meguro-columns.json'),
)
ENTITY_FILES = (
    Path('data/transit/tokyu/entities.json'),
    Path('data/transit/tokyo-metro/entities.json'),
    Path('data/transit/toei/entities.json'),
    Path('data/transit/sotetsu/entities.json'),
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


def normalized_calendar(value: Any) -> str:
    text = str(value or '').lower()
    if text == 'weekday':
        return 'odpt.Calendar:Weekday'
    if text in {'holiday', 'saturdayholiday'}:
        return 'odpt.Calendar:SaturdayHoliday'
    return str(value or '')


def hhmm_to_minutes(value: Any) -> int | None:
    text = str(value or '').replace(':', '')
    if not text.isdigit() or len(text) > 4:
        return None
    number = int(text)
    hour, minute = divmod(number, 100)
    if minute >= 60:
        return None
    return hour * 60 + minute


def exact_hits(
    fragment: dict[str, Any],
    titles: dict[str, str],
    printed_times: dict[str, Any],
) -> list[str]:
    hits: set[str] = set()
    for stop in fragment.get('stops') or []:
        if not isinstance(stop, list) or not stop:
            continue
        name = titles.get(str(stop[0] or ''), '')
        if not name or name not in printed_times:
            continue
        expected = hhmm_to_minutes(printed_times.get(name))
        if expected is None:
            continue
        if any(
            isinstance(value, (int, float)) and int(value) == expected
            for value in stop[1:3]
        ):
            hits.add(name)
    return sorted(hits)


def boundary_for(indexes: dict[str, Any], source: str, target: str) -> dict[str, Any] | None:
    for row in (indexes.get('graph') or {}).get(source, []):
        if str(row.get('toRailway') or '') == target:
            return row
    return None


def evidence_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel in EVIDENCE_FILES:
        data = load_json(root / rel, {}) or {}
        policy = data.get('identityPolicy') or {}
        if policy.get('officialSamePrintedColumnMayEstablishIdentity') is not True:
            raise RuntimeError(f'Official same-column identity policy missing: {rel}')
        for key in ('timeProximityMayEstablishIdentity', 'trainNumberAloneMayEstablishIdentity', 'destinationAloneMayEstablishIdentity'):
            if policy.get(key) is not False:
                raise RuntimeError(f'Unsafe official column policy {key}: {rel}')
        for row in data.get('authoritativeColumns') or []:
            if not isinstance(row, dict):
                continue
            if row.get('identityEvidence') != 'official-same-printed-column' or row.get('status') != 'verified':
                continue
            match_policy = row.get('matchPolicy') or {}
            if match_policy.get('officialSamePrintedColumnRequired') is not True:
                continue
            if match_policy.get('exactPrintedStationTimesRequired') is not True:
                continue
            if any(match_policy.get(key) is not False for key in (
                'timeProximityAloneMayEstablishIdentity',
                'trainNumberAloneMayEstablishIdentity',
                'destinationAloneMayEstablishIdentity',
            )):
                continue
            url = str(row.get('sourceUrl') or '')
            if not url.startswith('https://cdn.sotetsu.co.jp/'):
                continue
            if not isinstance(row.get('printedTimes'), dict) or not row.get('printedTimes'):
                continue
            if len(row.get('publishedBoundaryStops') or []) < 3:
                continue
            rows.append(row)
    return rows


def apply_existing_official_column_evidence(
    fragments: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    indexes: dict[str, Any],
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    titles = station_titles(root)
    evidence = evidence_rows(root)

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
            or source.get('sourceOperator') != 'tokyu'
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

        candidates: list[tuple[dict[str, Any], list[str]]] = []
        for row in evidence:
            if str(row.get('fromRailway') or '') != path[0]:
                continue
            if str(row.get('toRailway') or '') != target_railway:
                continue
            if normalized_calendar(row.get('calendar')) != str(source.get('calendar') or ''):
                continue
            source_hits = exact_hits(source, titles, row.get('printedTimes') or {})
            if source_hits:
                candidates.append((row, source_hits))
        if len(candidates) != 1:
            continue

        row, source_hits = candidates[0]
        target_matches: list[tuple[dict[str, Any], list[str]]] = []
        for target in by_railway_calendar.get((target_railway, str(source.get('calendar') or '')), []):
            target_hits = exact_hits(target, titles, row.get('printedTimes') or {})
            if len(target_hits) >= 2:
                target_matches.append((target, target_hits))
        if len(target_matches) != 1:
            continue

        target, target_hits = target_matches[0]
        required_stops = {str(value) for value in row.get('publishedBoundaryStops') or [] if value}
        matched_stops = set(source_hits) | set(target_hits)
        if len(matched_stops) < 3 or not required_stops.issubset(matched_stops):
            continue

        target_id = str(target.get('id') or '')
        key = (source_id, target_id)
        if not target_id or key in seen:
            continue
        seen.add(key)
        linked_from.add(source_id)
        resolved_sources.add(source_id)
        output.append({
            'fromFragment': source_id,
            'toFragment': target_id,
            'classification': 'same-train',
            'identityLevel': 'evidence-backed',
            'evidence': [
                'operator-official-same-printed-column',
                'existing-official-column-evidence-bridge',
                str(row.get('id') or ''),
            ],
            'sourceUrls': [str(row.get('sourceUrl') or '')],
            'boundary': {
                'station': str(boundary.get('station') or ''),
                'fromRailway': path[0],
                'toRailway': target_railway,
            },
            'exactMatch': {
                'sourceStations': source_hits,
                'targetStations': target_hits,
                'publishedBoundaryStops': sorted(required_stops),
                'printedTimes': row.get('printedTimes') or {},
                'pdfPage': row.get('pdfPage'),
                'columnX': row.get('columnX'),
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
