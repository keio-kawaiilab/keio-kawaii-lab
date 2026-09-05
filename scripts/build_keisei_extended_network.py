#!/usr/bin/env python3
"""Build the complete Keisei-led exact timetable family.

The retained Keisei official one-train page is the sole train-identity source.
The base builder materializes each physical train across Keisei, Toei Asakusa
and Keikyu. This extension adds Hokusō and Shibayama topology/boundaries and
then projects *every* Keisei/Hokusō/Shibayama per-line timetable back out of
that exact network. No per-line file is allowed to re-infer railway assignment
from a shared station ID, train number, or time proximity.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path('.')
BASE_SCRIPT = ROOT / 'scripts/build_keisei_network_timetable.py'
NETWORK_PATH = ROOT / 'data/transit/keisei/timetables/official-network.json'
REPORT_PATH = ROOT / 'data/transit/keisei/official-network-report.json'
KEISEI_INDEX_PATH = ROOT / 'data/transit/keisei/timetable-index.json'
MANIFEST_PATH = ROOT / 'data/transit/manifest.json'
EXTERNAL_BOUNDARIES = ROOT / 'data/transit/keisei/external-through-boundaries.json'
KEISEI_ENTITIES = ROOT / 'data/transit/keisei/entities.json'
TOEI_ENTITIES = ROOT / 'data/transit/toei/entities.json'
KEIKYU_ENTITIES = ROOT / 'data/transit/keikyu/entities.json'
TOPOLOGY = ROOT / 'data/transit-sources/manual-topology.json'

HOKUSO = 'manual.Railway:Hokuso.Hokuso'
SHIBAYAMA = 'manual.Railway:Shibayama.Shibayama'
KEISEI_MAIN = 'odpt.Railway:Keisei.Main'
KEISEI_NSA = 'odpt.Railway:Keisei.NaritaSkyAccess'
KEISEI_HIGASHI_NARITA = 'odpt.Railway:Keisei.HigashiNarita'
NARITA_AIRPORT = 'odpt.Station:Keisei.NaritaSkyAccess.NaritaAirportTerminal1'
HANEDA_T12 = 'odpt.Station:Keikyu.Airport.HanedaAirportTerminal1and2'

KEISEI_LINE_FILES = {
    'odpt.Railway:Keisei.Main': 'timetables/official-main.json',
    'odpt.Railway:Keisei.Oshiage': 'timetables/official-oshiage.json',
    'odpt.Railway:Keisei.Kanamachi': 'timetables/official-kanamachi.json',
    'odpt.Railway:Keisei.Chiba': 'timetables/official-chiba.json',
    'odpt.Railway:Keisei.Chihara': 'timetables/official-chihara.json',
    'odpt.Railway:Keisei.HigashiNarita': 'timetables/official-higashinarita.json',
    'odpt.Railway:Keisei.NaritaSkyAccess': 'timetables/official-narita-sky-access.json',
    'odpt.Railway:Keisei.Matsudo': 'timetables/official-matsudo.json',
}

HOKUSO_STATIONS = [
    ('京成高砂', 'odpt.Station:Keisei.Main.KeiseiTakasago'),
    ('新柴又', 'manual.Station:hokuso.新柴又'),
    ('矢切', 'manual.Station:hokuso.矢切'),
    ('北国分', 'manual.Station:hokuso.北国分'),
    ('秋山', 'manual.Station:hokuso.秋山'),
    ('東松戸', 'manual.Station:keisei.東松戸'),
    ('松飛台', 'manual.Station:hokuso.松飛台'),
    ('大町', 'manual.Station:hokuso.大町'),
    ('新鎌ヶ谷', 'manual.Station:keisei.新鎌ヶ谷'),
    ('西白井', 'manual.Station:hokuso.西白井'),
    ('白井', 'manual.Station:hokuso.白井'),
    ('小室', 'manual.Station:hokuso.小室'),
    ('千葉ニュータウン中央', 'manual.Station:keisei.千葉ニュータウン中央'),
    ('印西牧の原', 'manual.Station:hokuso.印西牧の原'),
    ('印旛日本医大', 'manual.Station:keisei.印旛日本医大'),
]
SHIBAYAMA_STATIONS = [
    ('東成田', 'manual.Station:keisei.東成田'),
    ('芝山千代田', 'manual.Station:shibayama.芝山千代田'),
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(path)


def load_base():
    spec = importlib.util.spec_from_file_location('keisei_exact_base', BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError('could not load base Keisei network builder')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_extensions(module) -> None:
    original_normalize = module.normalize_name
    original_build_lines = module.build_lines
    original_verified = module.verified_cross_operator_transitions
    original_shortest = module.shortest_line_paths

    def normalize_name(value: Any) -> str:
        result = original_normalize(value)
        return '井土ヶ谷' if result == '井土ケ谷' else result

    module.normalize_name = normalize_name

    def build_lines(keisei_entities, toei_entities, keikyu_entities, topology):
        lines, ids_by_name = original_build_lines(keisei_entities, toei_entities, keikyu_entities, topology)

        def register(railway_id: str, station_pairs: list[tuple[str, str]]) -> None:
            names = [normalize_name(name) for name, _ in station_pairs]
            ids = [station_id for _, station_id in station_pairs]
            lines[railway_id] = {
                'id': railway_id,
                'operator': module.railway_operator(railway_id),
                'names': names,
                'stationIds': ids,
                'stationIdByName': dict(zip(names, ids)),
            }
            for name, station_id in zip(names, ids):
                values = ids_by_name.setdefault(name, [])
                if station_id not in values:
                    values.append(station_id)

        register(HOKUSO, HOKUSO_STATIONS)
        register(SHIBAYAMA, SHIBAYAMA_STATIONS)
        return lines, ids_by_name

    module.build_lines = build_lines

    def verified_cross_operator_transitions(boundaries):
        allowed = set(original_verified(boundaries))
        extra = load_json(EXTERNAL_BOUNDARIES)
        for row in extra.get('boundaries') or []:
            if not isinstance(row, dict) or row.get('status') != 'verified':
                continue
            first = str(row.get('fromRailway') or '')
            second = str(row.get('toRailway') or '')
            station = normalize_name(row.get('station'))
            if not first or not second or not station:
                continue
            allowed.add((first, second, station))
            if row.get('bidirectional', True):
                allowed.add((second, first, station))
        return allowed

    module.verified_cross_operator_transitions = verified_cross_operator_transitions

    def shortest_line_paths(start, goal, graph, common_lines, allowed_cross_operator, limit=4):
        result = original_shortest(start, goal, graph, common_lines, allowed_cross_operator, limit)
        # Hokusō and Narita Sky Access share the corridor from Keisei-Takasago
        # to Inba-Nihon-Idai. If a stop pair is otherwise indistinguishable,
        # prefer the physical Hokusō line. Trains that reach Narita-Yukawa or
        # Narita Airport still require Narita Sky Access elsewhere in the same
        # exact one-train journey and remain correctly classified by the DP.
        def tie_key(route: list[str]):
            if route == [HOKUSO]:
                return (0, route)
            if route == [KEISEI_NSA]:
                return (1, route)
            return (2, route)
        return sorted(result, key=tie_key)

    module.shortest_line_paths = shortest_line_paths


def load_lines(module) -> dict[str, dict[str, Any]]:
    lines, _ = module.build_lines(
        load_json(KEISEI_ENTITIES),
        load_json(TOEI_ENTITIES),
        load_json(KEIKYU_ENTITIES),
        load_json(TOPOLOGY),
    )
    return lines


def station_names_by_id(module, lines: dict[str, dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in lines.values():
        for name, station_id in zip(line.get('names') or [], line.get('stationIds') or []):
            normalized = module.normalize_name(name)
            if not station_id or not normalized:
                continue
            previous = result.get(station_id)
            if previous is not None and previous != normalized:
                raise RuntimeError(f'conflicting physical station names for {station_id}: {previous} / {normalized}')
            result[station_id] = normalized
    return result


def monotonic_runs(rows: list[list[Any]]) -> list[list[list[Any]]]:
    if len(rows) < 2:
        return []
    runs: list[list[list[Any]]] = []
    current = [rows[0]]
    direction = 0
    for row in rows[1:]:
        delta = int(row[0]) - int(current[-1][0])
        sign = 1 if delta > 0 else -1 if delta < 0 else 0
        if sign == 0:
            continue
        if direction and sign != direction:
            if len(current) >= 2:
                runs.append(current)
            current = [current[-1], row]
            direction = sign
        else:
            current.append(row)
            direction = sign
    if len(current) >= 2:
        runs.append(current)
    return runs


def project_line(
    network: dict[str, Any],
    railway_id: str,
    station_pairs: list[tuple[str, str]],
    names_by_network_station_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Project only segments explicitly assigned to railway_id by exact network.

    Station names, not raw line-local IDs, bridge boundary stations that have a
    different Station ID on the adjacent line. Railway assignment itself still
    comes only from the exact network's per-segment link array.
    """
    line_stations = [station_id for _, station_id in station_pairs]
    line_names = [str(name) for name, _ in station_pairs]
    line_index_by_id = {station_id: index for index, station_id in enumerate(line_stations)}
    line_index_by_name = {name: index for index, name in enumerate(line_names)}
    network_stations = network.get('stations') or []
    network_railways = network.get('railways') or []
    projected: list[list[Any]] = []

    def stop_row(stop: list[Any]) -> list[Any] | None:
        if not isinstance(stop, list) or not stop:
            return None
        source_index = stop[0]
        if not isinstance(source_index, int) or not (0 <= source_index < len(network_stations)):
            return None
        station_id = network_stations[source_index]
        target_index = line_index_by_id.get(station_id)
        if target_index is None and names_by_network_station_id is not None:
            target_index = line_index_by_name.get(names_by_network_station_id.get(station_id, ''))
        if target_index is None:
            return None
        return [
            target_index,
            stop[1] if len(stop) > 1 else None,
            stop[2] if len(stop) > 2 else None,
        ]

    for trip_index, trip in enumerate(network.get('trips') or []):
        if not isinstance(trip, list) or len(trip) < 5:
            continue
        stops = trip[3] or []
        links = trip[4] or []
        current: list[list[Any]] = []
        exact_runs: list[list[list[Any]]] = []

        def flush() -> None:
            nonlocal current
            if len(current) >= 2:
                exact_runs.extend(monotonic_runs(current))
            current = []

        for segment_index in range(min(len(links), max(0, len(stops) - 1))):
            linked_ids = {
                network_railways[index]
                for index in (links[segment_index] or [])
                if isinstance(index, int) and 0 <= index < len(network_railways)
            }
            if railway_id not in linked_ids:
                flush()
                continue
            first = stop_row(stops[segment_index])
            second = stop_row(stops[segment_index + 1])
            if first is None or second is None:
                flush()
                continue
            if not current:
                current = [first, second]
            elif current[-1][0] == first[0]:
                current.append(second)
            else:
                flush()
                current = [first, second]
        flush()

        for run in exact_runs:
            destination = line_stations[run[-1][0]]
            identity = f'keisei-official-network:{trip_index}'
            projected.append([
                trip[0], trip[1], str(trip[2] or ''), run,
                destination, identity, identity,
            ])

    return {
        'version': 3,
        'timeBasis': 'train-timetable',
        'source': 'Keisei official one-train timetable / exact network projection',
        'destinationAuthoritative': False,
        'identityBasis': 'same official one-train page / exact railway-link projection',
        'railway': railway_id,
        'stations': line_stations,
        'calendars': network.get('calendars') or [],
        'trainTypes': network.get('trainTypes') or [],
        'trips': projected,
    }


def projection_connections(table: dict[str, Any]) -> int:
    return sum(max(0, len(trip[3] or []) - 1) for trip in table.get('trips') or [] if isinstance(trip, list) and len(trip) >= 4)


def write_keisei_projections(
    module,
    network: dict[str, Any],
    lines: dict[str, dict[str, Any]],
    names_by_id: dict[str, str],
) -> dict[str, dict[str, int]]:
    index = load_json(KEISEI_INDEX_PATH)
    if not isinstance(index, dict):
        raise RuntimeError('invalid Keisei timetable index')
    existing_lines = index.get('lines') if isinstance(index.get('lines'), dict) else {}
    output_lines: dict[str, Any] = {}
    summary: dict[str, dict[str, int]] = {}

    for railway_id, filename in KEISEI_LINE_FILES.items():
        line = lines.get(railway_id)
        if not line:
            raise RuntimeError(f'missing exact topology for {railway_id}')
        station_pairs = list(zip(line.get('names') or [], line.get('stationIds') or []))
        if len(station_pairs) < 2:
            raise RuntimeError(f'invalid station order for {railway_id}')
        table = project_line(network, railway_id, station_pairs, names_by_id)
        trip_count = len(table.get('trips') or [])
        connections = projection_connections(table)
        if trip_count <= 0 or connections <= 0:
            raise RuntimeError(f'empty exact projection for {railway_id}: trips={trip_count} connections={connections}')
        dump_json(ROOT / 'data/transit/keisei' / filename, table)
        prior = existing_lines.get(railway_id) if isinstance(existing_lines, dict) else None
        row = dict(prior) if isinstance(prior, dict) else {}
        row.update({
            'file': filename,
            'trips': trip_count,
            'connections': connections,
            'timeBasis': 'train-timetable',
            'status': 'official-exact-network-projection',
            'identityBasis': 'official-one-train-page',
        })
        output_lines[railway_id] = row
        summary[railway_id] = {'trips': trip_count, 'connections': connections}

    index['version'] = max(3, int(index.get('version') or 0))
    index['source'] = 'Keisei official one-train timetable / exact railway-link projection'
    index['lines'] = output_lines
    # Base builder owns the network descriptor; preserve it verbatim.
    if not isinstance(index.get('network'), dict):
        raise RuntimeError('exact network descriptor disappeared from Keisei timetable index')
    dump_json(KEISEI_INDEX_PATH, index)
    return summary


def write_operator_projection(
    slug: str,
    railway_id: str,
    station_pairs: list[tuple[str, str]],
    network: dict[str, Any],
    names_by_id: dict[str, str],
) -> int:
    table = project_line(network, railway_id, station_pairs, names_by_id)
    filename = f'timetables/official-{slug}.json'
    dump_json(ROOT / f'data/transit/{slug}/{filename}', table)
    trip_count = len(table['trips'])
    connections = projection_connections(table)
    index = {
        'version': 3,
        'lines': {
            railway_id: {
                'file': filename,
                'timeBasis': 'train-timetable',
                'status': 'official-exact-network-projection',
                'identityBasis': 'official-one-train-page',
                'trips': trip_count,
                'connections': connections,
            }
        },
    }
    dump_json(ROOT / f'data/transit/{slug}/timetable-index.json', index)
    coverage = {
        'overall': 'partial',
        'source': 'Keisei official one-train timetable snapshot',
        'identityBasis': 'same official one-train page',
        'railway': railway_id,
        'stations': len(station_pairs),
        'trips': trip_count,
        'connections': connections,
        'note': 'Covers only exact-network segments explicitly assigned to this railway; no shared-station, train-number, or time-proximity inference is used.',
    }
    dump_json(ROOT / f'data/transit/{slug}/coverage-report.json', coverage)
    return trip_count


def update_manifest(report: dict[str, Any], keisei_projection: dict[str, dict[str, int]], hokuso_trips: int, shibayama_trips: int) -> None:
    if not MANIFEST_PATH.exists():
        return
    manifest = load_json(MANIFEST_PATH)
    operators = manifest.get('operators') if isinstance(manifest, dict) else None
    if not isinstance(operators, dict):
        return

    keisei = operators.get('keisei')
    if isinstance(keisei, dict):
        connections = sum(int(row.get('connections') or 0) for row in keisei_projection.values())
        keisei['timetableStatus'] = 'ok'
        keisei['trainTimetables'] = int(report.get('sourceTrainCount') or 0)
        keisei['timetableLines'] = len(keisei_projection)
        keisei['timetableConnections'] = connections
        keisei['inferredConnections'] = 0
        keisei['departures'] = connections
        keisei['timetableSource'] = 'Keisei official one-train timetable / exact railway-link projection'
        keisei['identityBasis'] = 'official-one-train-page'

    for slug, trips in (('hokuso', hokuso_trips), ('shibayama', shibayama_trips)):
        row = operators.get(slug)
        if not isinstance(row, dict):
            continue
        row['trainTimetables'] = int(trips)
        row['timetableLines'] = 1
        row['timetableSource'] = 'Keisei official one-train timetable snapshot / exact railway-link projection'
        row['identityBasis'] = 'official-one-train-page'

    notes = manifest.get('notes')
    if isinstance(notes, list):
        exact_note = 'Keisei, Hokusō and Shibayama per-line timetable files are projections of the exact one-train network; shared station IDs, train numbers, or close times never establish line assignment or same-train identity.'
        notes[:] = [note for note in notes if not (isinstance(note, str) and note.startswith('Hokusō and Shibayama timetable coverage is projected'))]
        if exact_note not in notes:
            notes.append(exact_note)
    dump_json(MANIFEST_PATH, manifest)


def endpoint_through_counts(network: dict[str, Any]) -> dict[str, int]:
    stations = network.get('stations') or []
    by_id = {str(station_id): index for index, station_id in enumerate(stations)}
    narita_index = by_id.get(NARITA_AIRPORT)
    haneda_index = by_id.get(HANEDA_T12)
    if narita_index is None or haneda_index is None:
        raise RuntimeError('airport endpoint IDs are missing from exact network')
    counts = {'naritaToHaneda': 0, 'hanedaToNarita': 0}
    for trip in network.get('trips') or []:
        if not isinstance(trip, list) or len(trip) < 4:
            continue
        sequence = [row[0] for row in trip[3] or [] if isinstance(row, list) and row]
        try:
            narita_pos = sequence.index(narita_index)
            haneda_pos = sequence.index(haneda_index)
        except ValueError:
            continue
        if narita_pos < haneda_pos:
            counts['naritaToHaneda'] += 1
        elif haneda_pos < narita_pos:
            counts['hanedaToNarita'] += 1
    return counts


def main() -> int:
    module = load_base()
    install_extensions(module)
    result = module.main()
    if isinstance(result, int) and result != 0:
        return result

    network = load_json(NETWORK_PATH)
    report = load_json(REPORT_PATH)
    lines = load_lines(module)
    names_by_id = station_names_by_id(module, lines)

    keisei_projection = write_keisei_projections(module, network, lines, names_by_id)
    hokuso_trips = write_operator_projection('hokuso', HOKUSO, HOKUSO_STATIONS, network, names_by_id)
    shibayama_trips = write_operator_projection('shibayama', SHIBAYAMA, SHIBAYAMA_STATIONS, network, names_by_id)
    endpoint_counts = endpoint_through_counts(network)

    report['keiseiLineProjection'] = keisei_projection
    report['externalLineProjection'] = {
        'hokusoTrips': hokuso_trips,
        'shibayamaTrips': shibayama_trips,
        'unsupportedStopRowsAfterExtension': report.get('unsupportedStopRows'),
        'unsupportedStationsAfterExtension': report.get('unsupportedStations'),
    }
    report['endpointThroughCounts'] = endpoint_counts
    dump_json(REPORT_PATH, report)
    update_manifest(report, keisei_projection, hokuso_trips, shibayama_trips)

    print(json.dumps({
        'keiseiLineProjection': keisei_projection,
        'externalLineProjection': report['externalLineProjection'],
        'endpointThroughCounts': endpoint_counts,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
