#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path('.')
V1 = ROOT / 'data/transit'
OUT = ROOT / 'data/transit-v2'
BOUNDARIES = OUT / 'service-boundaries.json'
IDENTITY = V1 / 'odpt-train-identities.json'


def load_json(path: Path, default: Any = None) -> Any:
    try:
        text = path.read_text(encoding='utf-8').strip()
        return json.loads(text) if text else default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def stable_id(prefix: str, *parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return f'{prefix}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}'


def title(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if isinstance(value, dict):
        return str(value.get('ja') or value.get('en') or '')
    return str(value or item.get('dc:title') or '')


def stop_time(stop: list[Any], *, entering: bool) -> int | None:
    if not isinstance(stop, list) or len(stop) < 3:
        return None
    arrival, departure = stop[1], stop[2]
    raw = arrival if entering else departure
    if raw is None:
        raw = departure if entering else arrival
    return int(raw) if isinstance(raw, (int, float)) else None


def collapse(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and (not result or result[-1] != value):
            result.append(value)
    return result


def unique_shortest_path(graph: dict[str, list[dict[str, Any]]], start: str, targets: set[str]) -> dict[str, Any]:
    if start in targets:
        return {'status': 'matched', 'railways': [start], 'edges': []}
    queue = deque([(start, [start], [])])
    best_depth: int | None = None
    matches: list[tuple[list[str], list[dict[str, Any]]]] = []
    seen_depth: dict[str, int] = {start: 0}
    while queue:
        node, route, edges = queue.popleft()
        depth = len(edges)
        if best_depth is not None and depth >= best_depth:
            continue
        for edge in graph.get(node, []):
            nxt = edge['toRailway']
            if nxt in route:
                continue
            next_route = route + [nxt]
            next_edges = edges + [edge]
            next_depth = depth + 1
            if nxt in targets:
                if best_depth is None:
                    best_depth = next_depth
                if next_depth == best_depth:
                    matches.append((next_route, next_edges))
                continue
            previous = seen_depth.get(nxt)
            if previous is not None and previous < next_depth:
                continue
            seen_depth[nxt] = next_depth
            queue.append((nxt, next_route, next_edges))
    signatures = {'|'.join(route): (route, edges) for route, edges in matches}
    if not signatures:
        return {'status': 'no-path'}
    if len(signatures) > 1:
        return {'status': 'ambiguous', 'matches': [route for route, _ in signatures.values()]}
    route, edges = next(iter(signatures.values()))
    return {'status': 'matched', 'railways': route, 'edges': edges}


def candidate_alignment(source: dict[str, Any], target: dict[str, Any], max_minutes: int = 4) -> tuple[bool, int | None]:
    source_stops = source.get('stops') or []
    target_stops = target.get('stops') or []
    if not source_stops or not target_stops:
        return False, None
    source_time = stop_time(source_stops[-1], entering=False)
    target_time = stop_time(target_stops[0], entering=True)
    if source_time is None or target_time is None:
        return False, None
    delta = target_time - source_time
    while delta < -720:
        delta += 1440
    return 0 <= delta <= max_minutes, delta


def index_entities(manifest: dict[str, Any]) -> dict[str, Any]:
    railway_operator: dict[str, str] = {}
    railway_source: dict[str, str] = {}
    station_railways: dict[str, set[str]] = defaultdict(set)
    station_title: dict[str, str] = {}
    railway_titles: dict[str, str] = {}
    railway_station_titles: dict[str, set[str]] = defaultdict(set)
    connecting_links: list[tuple[str, str]] = []

    for slug, meta in (manifest.get('operators') or {}).items():
        entities = load_json(V1 / slug / 'entities.json', {}) or {}
        operator = str(meta.get('operator') or '')
        for station in entities.get('Station') or []:
            if not isinstance(station, dict):
                continue
            sid = str(station.get('owl:sameAs') or '')
            name = title(station, 'odpt:stationTitle')
            if sid:
                station_title[sid] = name
            for railway in as_list(station.get('odpt:railway')):
                rid = str(railway or '')
                if rid and sid:
                    station_railways[sid].add(rid)
                    railway_operator.setdefault(rid, operator)
                    railway_source.setdefault(rid, slug)
                    if name:
                        railway_station_titles[rid].add(name)
            for other_sid in as_list(station.get('odpt:connectingStation')):
                if sid and other_sid:
                    connecting_links.append((sid, str(other_sid)))
        for railway in entities.get('Railway') or []:
            if not isinstance(railway, dict):
                continue
            rid = str(railway.get('owl:sameAs') or '')
            if not rid:
                continue
            railway_operator.setdefault(rid, operator)
            railway_source.setdefault(rid, slug)
            railway_titles[rid] = title(railway, 'odpt:railwayTitle')
            for row in railway.get('odpt:stationOrder') or []:
                if not isinstance(row, dict):
                    continue
                sid = str(row.get('odpt:station') or '')
                if sid:
                    station_railways[sid].add(rid)
                    name = station_title.get(sid) or title(row, 'odpt:stationTitle')
                    if name:
                        railway_station_titles[rid].add(name)

    graph: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_edges: set[tuple[str, str, str, str]] = set()

    def add_edge(a: str, b: str, station_name: str, kind: str, evidence: str) -> None:
        if not a or not b or a == b:
            return
        key = (a, b, station_name, kind)
        if key in seen_edges:
            return
        seen_edges.add(key)
        graph[a].append({'fromRailway': a, 'toRailway': b, 'station': station_name, 'kind': kind, 'evidence': evidence})

    by_operator: dict[str, list[str]] = defaultdict(list)
    for rid, operator in railway_operator.items():
        by_operator[operator].append(rid)
    for railways in by_operator.values():
        for i, first in enumerate(railways):
            for second in railways[i + 1:]:
                shared = sorted(railway_station_titles.get(first, set()) & railway_station_titles.get(second, set()))
                for station_name in shared:
                    add_edge(first, second, station_name, 'same-operator-junction', 'shared-official-station')
                    add_edge(second, first, station_name, 'same-operator-junction', 'shared-official-station')

    for sid, other_sid in connecting_links:
        for first in station_railways.get(sid, set()):
            for second in station_railways.get(other_sid, set()):
                if railway_operator.get(first) and railway_operator.get(first) == railway_operator.get(second):
                    station_name = station_title.get(sid) or station_title.get(other_sid) or ''
                    add_edge(first, second, station_name, 'same-operator-junction', 'odpt:connectingStation')

    return {
        'railwayOperator': railway_operator,
        'railwaySource': railway_source,
        'stationRailways': station_railways,
        'stationTitle': station_title,
        'railwayTitles': railway_titles,
        'railwayStationTitles': railway_station_titles,
        'graph': graph,
        'addEdge': add_edge,
    }


def destination_railways(destination: str, indexes: dict[str, Any]) -> set[str]:
    result = set(indexes['stationRailways'].get(destination, set()))
    if result:
        return result
    suffix = destination.rsplit('.', 1)[-1] if destination else ''
    for sid, railways in indexes['stationRailways'].items():
        if sid.rsplit('.', 1)[-1] == suffix:
            result.update(railways)
    return result


def add_cross_operator_boundaries(indexes: dict[str, Any], registry: dict[str, Any]) -> None:
    add_edge = indexes['addEdge']
    for boundary in registry.get('boundaries') or []:
        if not isinstance(boundary, dict) or boundary.get('status') != 'verified':
            continue
        first = str(boundary.get('fromRailway') or '')
        second = str(boundary.get('toRailway') or '')
        station = str(boundary.get('station') or '')
        evidence = '|'.join(boundary.get('sourceUrls') or [])
        add_edge(first, second, station, 'verified-cross-operator', evidence)
        if boundary.get('bidirectional', True):
            add_edge(second, first, station, 'verified-cross-operator', evidence)


def parse_stops(table: dict[str, Any], raw: Any) -> list[list[Any]]:
    stations = table.get('stations') or []
    result: list[list[Any]] = []
    for stop in raw or []:
        if not isinstance(stop, list) or not stop:
            continue
        index = stop[0]
        sid = stations[index] if isinstance(index, int) and 0 <= index < len(stations) else str(index or '')
        result.append([sid, stop[1] if len(stop) > 1 else None, stop[2] if len(stop) > 2 else None])
    return result


def load_all_fragments(manifest: dict[str, Any], indexes: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fragments: list[dict[str, Any]] = []
    networks: list[dict[str, Any]] = []
    for slug, meta in (manifest.get('operators') or {}).items():
        index = load_json(V1 / slug / 'timetable-index.json', {}) or {}
        operator = str(meta.get('operator') or '')
        for railway, row in (index.get('lines') or {}).items():
            if not isinstance(row, dict) or not row.get('file'):
                continue
            table = load_json(V1 / slug / str(row['file']), None)
            if not isinstance(table, dict):
                continue
            basis = str(table.get('timeBasis') or '')
            calendars = table.get('calendars') or []
            types = table.get('trainTypes') or []
            if basis.startswith('train-timetable'):
                for trip_index, trip in enumerate(table.get('trips') or []):
                    if not isinstance(trip, list) or len(trip) < 4:
                        continue
                    calendar = calendars[trip[0]] if isinstance(trip[0], int) and trip[0] < len(calendars) else ''
                    train_type = types[trip[1]] if isinstance(trip[1], int) and trip[1] < len(types) else ''
                    destinations = [str(value) for value in as_list(trip[4] if len(trip) > 4 else '') if value]
                    train_id = str(trip[5] or '') if len(trip) > 5 else ''
                    timetable_id = str(trip[6] or '') if len(trip) > 6 else ''
                    stops = parse_stops(table, trip[3])
                    fragment_id = f'odpt:{timetable_id}' if timetable_id else stable_id('exact', slug, railway, calendar, trip_index, trip[2], stops)
                    fragments.append({
                        'id': fragment_id,
                        'sourceKind': 'exact-train-timetable',
                        'sourceOperator': slug,
                        'operator': operator,
                        'railway': railway,
                        'calendar': calendar,
                        'trainType': train_type,
                        'trainNumber': str(trip[2] or ''),
                        'trainId': train_id,
                        'timetableId': timetable_id,
                        'origin': [stops[0][0]] if stops else [],
                        'destination': destinations,
                        'stops': stops,
                        'confidence': 100,
                        'identityLevel': 'official-fragment',
                    })
            if basis in {'station-departure-only', 'station-departure'}:
                directions = table.get('directions') or []
                destinations = table.get('destinations') or []
                for trip_index, trip in enumerate(table.get('inferredTrips') or []):
                    if not isinstance(trip, list) or len(trip) < 6:
                        continue
                    calendar = calendars[trip[0]] if isinstance(trip[0], int) and trip[0] < len(calendars) else ''
                    direction = directions[trip[1]] if isinstance(trip[1], int) and trip[1] < len(directions) else ''
                    train_type = types[trip[2]] if isinstance(trip[2], int) and trip[2] < len(types) else ''
                    destination = destinations[trip[3]] if isinstance(trip[3], int) and trip[3] < len(destinations) else ''
                    stops = parse_stops(table, trip[5])
                    fragments.append({
                        'id': stable_id('inferred', slug, railway, calendar, direction, train_type, destination, trip_index, stops),
                        'sourceKind': 'station-timetable-reconstruction',
                        'sourceOperator': slug,
                        'operator': operator,
                        'railway': railway,
                        'calendar': calendar,
                        'direction': direction,
                        'trainType': train_type,
                        'trainNumber': '',
                        'trainId': '',
                        'timetableId': '',
                        'origin': [stops[0][0]] if stops else [],
                        'destination': [str(destination)] if destination else [],
                        'stops': stops,
                        'confidence': int(trip[4] or 0),
                        'identityLevel': 'inferred-local-fragment',
                    })

        network = index.get('network')
        if isinstance(network, dict) and network.get('file'):
            table = load_json(V1 / slug / str(network['file']), None)
            if isinstance(table, dict) and table.get('timeBasis') == 'train-timetable-network':
                railways = table.get('railways') or []
                stations = table.get('stations') or []
                calendars = table.get('calendars') or []
                types = table.get('trainTypes') or []
                for trip_index, trip in enumerate(table.get('trips') or []):
                    if not isinstance(trip, list) or len(trip) < 5:
                        continue
                    used = collapse(railways[idx] for edge in trip[4] or [] for idx in as_list(edge) if isinstance(idx, int) and 0 <= idx < len(railways))
                    stops = []
                    for stop in trip[3] or []:
                        if not isinstance(stop, list) or not stop:
                            continue
                        sid = stations[stop[0]] if isinstance(stop[0], int) and stop[0] < len(stations) else ''
                        stops.append([sid, stop[1] if len(stop) > 1 else None, stop[2] if len(stop) > 2 else None])
                    networks.append({
                        'id': stable_id('network', slug, network.get('id') or network.get('file'), trip_index),
                        'sourceKind': 'exact-train-network',
                        'sourceOperator': slug,
                        'operator': operator,
                        'calendar': calendars[trip[0]] if isinstance(trip[0], int) and trip[0] < len(calendars) else '',
                        'trainType': types[trip[1]] if isinstance(trip[1], int) and trip[1] < len(types) else '',
                        'trainNumber': str(trip[2] or ''),
                        'railwayPath': used,
                        'stops': stops,
                        'confidence': 100,
                        'identityLevel': 'official-exact-network',
                    })
    return fragments, networks


def enrich_odpt_identity(fragments: list[dict[str, Any]], unresolved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sidecar = load_json(IDENTITY, {}) or {}
    records = [row for row in sidecar.get('records') or [] if isinstance(row, dict)]
    by_tt = {str(row.get('timetableId') or ''): row for row in records if row.get('timetableId')}
    fragment_by_tt = {fragment['timetableId']: fragment for fragment in fragments if fragment.get('timetableId')}
    for tt, row in by_tt.items():
        fragment = fragment_by_tt.get(tt)
        if not fragment:
            continue
        if row.get('origin'):
            fragment['origin'] = [str(value) for value in row['origin']]
        if row.get('destination'):
            fragment['destination'] = [str(value) for value in row['destination']]
        fragment['previousTrainTimetables'] = [str(value) for value in row.get('previousTrainTimetables') or []]
        fragment['nextTrainTimetables'] = [str(value) for value in row.get('nextTrainTimetables') or []]
        fragment['identityLevel'] = 'official-train-timetable'
    edges: list[dict[str, Any]] = []
    seen = set()
    for tt, row in by_tt.items():
        source = fragment_by_tt.get(tt)
        if not source:
            continue
        for linked in row.get('nextTrainTimetables') or []:
            linked = str(linked)
            target = fragment_by_tt.get(linked)
            if not target:
                unresolved.append({'kind': 'missing-authoritative-linked-timetable', 'fromTimetable': tt, 'toTimetable': linked})
                continue
            key = (source['id'], target['id'])
            if key in seen:
                continue
            seen.add(key)
            edges.append({'fromFragment': source['id'], 'toFragment': target['id'], 'classification': 'same-train', 'identityLevel': 'authoritative', 'evidence': ['odpt:nextTrainTimetable'], 'boundary': {'fromRailway': source['railway'], 'toRailway': target['railway']}})
        for linked in row.get('previousTrainTimetables') or []:
            linked = str(linked)
            previous = fragment_by_tt.get(linked)
            if not previous:
                unresolved.append({'kind': 'missing-authoritative-linked-timetable', 'fromTimetable': linked, 'toTimetable': tt})
                continue
            key = (previous['id'], source['id'])
            if key not in seen:
                seen.add(key)
                edges.append({'fromFragment': previous['id'], 'toFragment': source['id'], 'classification': 'same-train', 'identityLevel': 'authoritative', 'evidence': ['odpt:previousTrainTimetable'], 'boundary': {'fromRailway': previous['railway'], 'toRailway': source['railway']}})
    return edges


def classify_published_routes(fragments: list[dict[str, Any]], indexes: dict[str, Any], unresolved: list[dict[str, Any]]) -> None:
    graph = indexes['graph']
    for fragment in fragments:
        destinations = fragment.get('destination') or []
        if not destinations:
            continue
        target_railways: set[str] = set()
        for destination in destinations:
            target_railways.update(destination_railways(str(destination), indexes))
        target_railways.discard(fragment['railway'])
        if not target_railways:
            continue
        path = unique_shortest_path(graph, fragment['railway'], target_railways)
        fragment['publishedDestinationRailways'] = sorted(target_railways)
        if path['status'] == 'matched':
            fragment['throughRailwayPath'] = path['railways']
            fragment['throughPathEvidence'] = [edge['kind'] for edge in path['edges']]
        else:
            unresolved.append({'kind': 'published-destination-route-' + path['status'], 'fragment': fragment['id'], 'railway': fragment['railway'], 'destination': destinations, 'targetRailways': sorted(target_railways), 'matches': path.get('matches') or []})


def physical_station_match(a: str, b: str, indexes: dict[str, Any], station_name: str) -> bool:
    if a == b:
        return True
    ta = indexes['stationTitle'].get(a, '')
    tb = indexes['stationTitle'].get(b, '')
    if ta and tb and ta == tb:
        return True
    return bool(station_name and (ta == station_name or tb == station_name))


def align_inferred_edges(fragments: list[dict[str, Any]], indexes: dict[str, Any], existing_edges: list[dict[str, Any]], unresolved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_railway: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fragment in fragments:
        if fragment.get('sourceKind') == 'station-timetable-reconstruction':
            by_railway[fragment['railway']].append(fragment)
    output = list(existing_edges)
    seen = {(edge['fromFragment'], edge['toFragment']) for edge in output}
    for source in fragments:
        if source.get('sourceKind') != 'station-timetable-reconstruction':
            continue
        path = source.get('throughRailwayPath') or []
        if len(path) < 2 or path[0] != source['railway']:
            continue
        next_railway = path[1]
        edge_meta = next((edge for edge in indexes['graph'].get(source['railway'], []) if edge['toRailway'] == next_railway), None)
        if not edge_meta:
            continue
        candidates = []
        for target in by_railway.get(next_railway, []):
            if target.get('calendar') != source.get('calendar'):
                continue
            if not set(target.get('destination') or []) & set(source.get('destination') or []):
                continue
            source_stops = source.get('stops') or []
            target_stops = target.get('stops') or []
            if not source_stops or not target_stops:
                continue
            if not physical_station_match(source_stops[-1][0], target_stops[0][0], indexes, edge_meta.get('station') or ''):
                continue
            ok, delta = candidate_alignment(source, target)
            if ok:
                candidates.append((target, delta))
        if len(candidates) == 1:
            target, delta = candidates[0]
            key = (source['id'], target['id'])
            if key not in seen:
                seen.add(key)
                output.append({'fromFragment': source['id'], 'toFragment': target['id'], 'classification': 'same-train', 'identityLevel': 'evidence-backed', 'evidence': ['published-final-destination', edge_meta['kind'], 'unique-boundary-fragment-alignment'], 'alignmentDeltaMinutes': delta, 'boundary': {'station': edge_meta.get('station') or '', 'fromRailway': source['railway'], 'toRailway': target['railway']}})
        elif len(candidates) > 1:
            unresolved.append({'kind': 'ambiguous-boundary-fragment-alignment', 'fragment': source['id'], 'nextRailway': next_railway, 'candidateFragments': [target['id'] for target, _ in candidates]})
    return output


def audit_edge_registry(edges: list[dict[str, Any]], indexes: dict[str, Any], unresolved: list[dict[str, Any]]) -> None:
    registered = {(edge['fromRailway'], edge['toRailway']) for rows in indexes['graph'].values() for edge in rows}
    for edge in edges:
        boundary = edge.get('boundary') or {}
        pair = (boundary.get('fromRailway'), boundary.get('toRailway'))
        if pair[0] != pair[1] and pair not in registered:
            unresolved.append({'kind': 'authoritative-same-train-unregistered-boundary', 'fromFragment': edge['fromFragment'], 'toFragment': edge['toFragment'], 'fromRailway': pair[0], 'toRailway': pair[1]})


def build() -> dict[str, Any]:
    manifest = load_json(V1 / 'manifest.json', {}) or {}
    registry = load_json(BOUNDARIES, {}) or {}
    indexes = index_entities(manifest)
    add_cross_operator_boundaries(indexes, registry)
    fragments, networks = load_all_fragments(manifest, indexes)
    unresolved: list[dict[str, Any]] = []
    edges = enrich_odpt_identity(fragments, unresolved)
    classify_published_routes(fragments, indexes, unresolved)
    edges = align_inferred_edges(fragments, indexes, edges, unresolved)
    audit_edge_registry(edges, indexes, unresolved)

    by_operator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fragment in fragments:
        by_operator[fragment['sourceOperator']].append(fragment)
    fragment_files: dict[str, str] = {}
    for slug, rows in sorted(by_operator.items()):
        filename = f'fragments/{slug}.json'
        fragment_files[slug] = filename
        write_json(OUT / filename, {'version': 1, 'operator': slug, 'fragments': rows})

    generated = datetime.now(timezone.utc).isoformat()
    write_json(OUT / 'same-train-edges.json', {'version': 1, 'generatedAt': generated, 'policy': {'timeGapMayEstablishTrainIdentity': False, 'trainNumberMayEstablishTrainIdentity': False, 'lineNameChangeCountsAsTransfer': False, 'unresolvedMayBeShownAsThrough': False}, 'edges': edges})
    write_json(OUT / 'network-journeys.json', {'version': 1, 'generatedAt': generated, 'journeys': networks})

    source_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for fragment in fragments:
        source_counts[fragment['sourceOperator']][fragment['sourceKind']] += 1
    coverage = {
        'version': 1,
        'generatedAt': generated,
        'summary': {
            'fragments': len(fragments),
            'exactFragments': sum(1 for f in fragments if f['sourceKind'] == 'exact-train-timetable'),
            'inferredFragments': sum(1 for f in fragments if f['sourceKind'] == 'station-timetable-reconstruction'),
            'networkJourneys': len(networks),
            'sameTrainEdges': len(edges),
            'authoritativeSameTrainEdges': sum(1 for e in edges if e['identityLevel'] == 'authoritative'),
            'evidenceBackedSameTrainEdges': sum(1 for e in edges if e['identityLevel'] == 'evidence-backed'),
            'fragmentsWithDestination': sum(1 for f in fragments if f.get('destination')),
            'fragmentsWithThroughRailwayPath': sum(1 for f in fragments if len(f.get('throughRailwayPath') or []) > 1),
            'unresolved': len(unresolved),
        },
        'byOperator': {slug: dict(values) for slug, values in sorted(source_counts.items())},
        'unresolved': unresolved,
    }
    write_json(OUT / 'coverage.json', coverage)
    write_json(OUT / 'index.json', {'version': 1, 'generatedAt': generated, 'sourceManifestFetchedAt': manifest.get('fetchedAt'), 'spec': 'spec.json', 'serviceBoundaries': 'service-boundaries.json', 'sameTrainEdges': 'same-train-edges.json', 'networkJourneys': 'network-journeys.json', 'coverage': 'coverage.json', 'fragmentFiles': fragment_files})
    print(json.dumps(coverage['summary'], ensure_ascii=False, indent=2))
    return coverage


if __name__ == '__main__':
    build()
