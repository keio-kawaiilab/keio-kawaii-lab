#!/usr/bin/env python3
"""Exhaustively audit the retained Keisei-led exact timetable database.

The official Keisei one-train page is the identity authority.  This audit
checks every retained source train and stop against the exact network, then
checks all eight Keisei line files plus Hokusō and Shibayama as projections of
that network.  Train numbers, close times and shared station IDs are never
accepted as substitutes for an exact network link.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path('.')
DETAILS = ROOT / 'data/transit/keisei/official-train-details.json'
NETWORK = ROOT / 'data/transit/keisei/timetables/official-network.json'
REPORT = ROOT / 'data/transit/keisei/official-network-report.json'
MANIFEST = ROOT / 'data/transit/manifest.json'
BASE_SCRIPT = ROOT / 'scripts/build_keisei_network_timetable.py'
EXT_SCRIPT = ROOT / 'scripts/build_keisei_extended_network.py'

HOKUSO = 'manual.Railway:Hokuso.Hokuso'
SHIBAYAMA = 'manual.Railway:Shibayama.Shibayama'
KEISEI_FILES = {
    'odpt.Railway:Keisei.Main': 'official-main.json',
    'odpt.Railway:Keisei.Oshiage': 'official-oshiage.json',
    'odpt.Railway:Keisei.Kanamachi': 'official-kanamachi.json',
    'odpt.Railway:Keisei.Chiba': 'official-chiba.json',
    'odpt.Railway:Keisei.Chihara': 'official-chihara.json',
    'odpt.Railway:Keisei.HigashiNarita': 'official-higashinarita.json',
    'odpt.Railway:Keisei.NaritaSkyAccess': 'official-narita-sky-access.json',
    'odpt.Railway:Keisei.Matsudo': 'official-matsudo.json',
}
EXPECTED_EXTERNAL_CROSSINGS = {
    frozenset(('odpt.Railway:Keisei.Oshiage', 'odpt.Railway:Toei.Asakusa')),
    frozenset(('odpt.Railway:Toei.Asakusa', 'odpt.Railway:Keikyu.Main')),
    frozenset(('odpt.Railway:Keisei.Main', HOKUSO)),
    frozenset(('odpt.Railway:Keisei.HigashiNarita', SHIBAYAMA)),
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'could not import {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_builder():
    base = load_module(BASE_SCRIPT, 'keisei_audit_base')
    extension = load_module(EXT_SCRIPT, 'keisei_audit_extension')
    extension.install_extensions(base)
    return base


def build_station_names(module) -> dict[str, str]:
    lines, _ = module.build_lines(
        load_json(ROOT / 'data/transit/keisei/entities.json'),
        load_json(ROOT / 'data/transit/toei/entities.json'),
        load_json(ROOT / 'data/transit/keikyu/entities.json'),
        load_json(ROOT / 'data/transit-sources/manual-topology.json'),
    )
    result: dict[str, str] = {}
    for line in lines.values():
        for name, station_id in zip(line.get('names') or [], line.get('stationIds') or []):
            normalized = module.normalize_name(name)
            previous = result.get(station_id)
            assert previous is None or previous == normalized, (station_id, previous, normalized)
            result[station_id] = normalized
    return result


def normalized_source_times(module, stops: list[dict[str, Any]]) -> list[tuple[int | None, int | None]]:
    rows: list[tuple[int | None, int | None]] = []
    previous: int | None = None
    for stop in stops:
        arrival = module.monotonic(stop.get('arrival'), previous)
        departure = module.monotonic(stop.get('departure'), arrival if arrival is not None else previous)
        effective = departure if departure is not None else arrival
        if effective is not None:
            previous = effective
        rows.append((arrival, departure))
    return rows


def audit_source_network(module, names_by_id: dict[str, str]) -> dict[str, int]:
    details = load_json(DETAILS)
    network = load_json(NETWORK)
    report = load_json(REPORT)
    trains = details.get('trains') or []
    trips = network.get('trips') or []
    stations = network.get('stations') or []
    calendars = network.get('calendars') or []
    train_types = network.get('trainTypes') or []
    railways = network.get('railways') or []

    assert int(details.get('trainCount') or 0) == len(trains)
    assert int(details.get('weekdayCount') or 0) + int(details.get('holidayCount') or 0) == len(trains)
    assert int(details.get('stopRowCount') or 0) == sum(len(train.get('stops') or []) for train in trains)
    assert len(trips) == len(trains), (len(trips), len(trains))
    assert report.get('sourceTrainCount') == len(trains)
    assert report.get('networkTripCount') == len(trains)
    assert report.get('skippedUnderTwoMappedStops') == 0
    assert report.get('unresolvedPairCount') == 0
    assert report.get('unsupportedStopRows') == 0
    assert report.get('unsupportedStations') == {}

    assert network.get('timeBasis') == 'train-timetable-network'
    assert network.get('identityBasis') == 'Keisei official one-train timetable page'
    policy = network.get('identityPolicy') or {}
    assert policy.get('officialTrainPageEstablishesIdentity') is True
    assert policy.get('trainNumberAloneMayEstablishIdentity') is False
    assert policy.get('timeProximityAloneMayEstablishIdentity') is False
    assert policy.get('crossOperatorTransitionRequiresVerifiedBoundary') is True

    source_keys: set[str] = set()
    total_stops = 0
    total_links = 0
    for trip_index, (source, trip) in enumerate(zip(trains, trips)):
        source_key = str(source.get('key') or '')
        assert source_key and source_key not in source_keys, (trip_index, source_key)
        source_keys.add(source_key)
        source_stops = source.get('stops') or []
        assert len(source_stops) >= 2, (source_key, len(source_stops))
        assert isinstance(trip, list) and len(trip) >= 5, source_key
        encoded_stops = trip[3] or []
        links = trip[4] or []
        assert len(encoded_stops) == len(source_stops), (source_key, len(encoded_stops), len(source_stops))
        assert len(links) == len(encoded_stops) - 1, (source_key, len(links), len(encoded_stops))
        assert calendars[trip[0]] == str(source.get('calendar') or ''), source_key
        assert train_types[trip[1]] == str(source.get('trainType') or ''), source_key
        assert str(trip[2] or '') == module.train_number(source.get('sourceTrainId')), source_key

        expected_times = normalized_source_times(module, source_stops)
        previous_effective: int | None = None
        for stop_index, (raw, encoded, expected) in enumerate(zip(source_stops, encoded_stops, expected_times)):
            assert isinstance(encoded, list) and len(encoded) >= 3, (source_key, stop_index)
            station_index = encoded[0]
            assert isinstance(station_index, int) and 0 <= station_index < len(stations), (source_key, stop_index)
            station_id = stations[station_index]
            assert names_by_id.get(station_id) == module.normalize_name(raw.get('station')), (
                source_key, stop_index, raw.get('station'), station_id, names_by_id.get(station_id)
            )
            assert (encoded[1], encoded[2]) == expected, (source_key, stop_index, encoded, expected)
            effective = encoded[2] if encoded[2] is not None else encoded[1]
            if effective is not None and previous_effective is not None:
                assert int(effective) >= int(previous_effective), (source_key, stop_index, previous_effective, effective)
            if effective is not None:
                previous_effective = int(effective)

        for link_index, link in enumerate(links):
            assert isinstance(link, list) and link, (source_key, link_index, link)
            for railway_index in link:
                assert isinstance(railway_index, int) and 0 <= railway_index < len(railways), (
                    source_key, link_index, railway_index
                )
        total_stops += len(encoded_stops)
        total_links += len(links)

    assert total_stops == int(details.get('stopRowCount') or 0)
    observed_crossings = {
        frozenset((str(row.get('fromRailway') or ''), str(row.get('toRailway') or '')))
        for row in report.get('crossOperatorTransitions') or []
    }
    assert observed_crossings == EXPECTED_EXTERNAL_CROSSINGS, observed_crossings
    required_railways = {
        *KEISEI_FILES.keys(), HOKUSO, SHIBAYAMA,
        'odpt.Railway:Toei.Asakusa', 'odpt.Railway:Keikyu.Main',
        'odpt.Railway:Keikyu.Airport', 'odpt.Railway:Keikyu.Daishi',
        'odpt.Railway:Keikyu.Kurihama', 'odpt.Railway:Keikyu.Zushi',
    }
    assert required_railways.issubset(set(railways)), required_railways - set(railways)
    assert int(report.get('supportedRailwayCount') or 0) == len(railways)
    return {
        'sourceTrains': len(trains),
        'sourceStops': total_stops,
        'networkLinks': total_links,
        'networkRailways': len(railways),
    }


def connection_count(table: dict[str, Any]) -> int:
    return sum(max(0, len(trip[3] or []) - 1) for trip in table.get('trips') or [] if isinstance(trip, list) and len(trip) >= 4)


def audit_projection(
    names_by_id: dict[str, str],
    railway_id: str,
    table_path: Path,
    index_row: dict[str, Any],
    label: str,
) -> tuple[int, int]:
    network = load_json(NETWORK)
    table = load_json(table_path)
    network_stations = network.get('stations') or []
    network_railways = network.get('railways') or []
    target_railway_index = network_railways.index(railway_id)
    table_stations = table.get('stations') or []

    assert int(table.get('version') or 0) >= 3, label
    assert table.get('railway') == railway_id, label
    assert table.get('timeBasis') == 'train-timetable', label
    assert table.get('destinationAuthoritative') is False, label
    assert 'exact railway-link projection' in str(table.get('identityBasis') or ''), label
    assert index_row.get('status') == 'official-exact-network-projection', label
    assert index_row.get('identityBasis') == 'official-one-train-page', label

    table_names = []
    for station_id in table_stations:
        name = names_by_id.get(station_id)
        assert name, (label, 'unknown projected station', station_id)
        table_names.append(name)

    trips = table.get('trips') or []
    connections = connection_count(table)
    assert int(index_row.get('trips', -1)) == len(trips), label
    assert int(index_row.get('connections', -1)) == connections, label

    for projected_index, trip in enumerate(trips):
        assert isinstance(trip, list) and len(trip) >= 7, (label, projected_index)
        assert trip[5] == trip[6], (label, projected_index, trip[5:7])
        identity = str(trip[6] or '')
        prefix = 'keisei-official-network:'
        assert identity.startswith(prefix), (label, projected_index, identity)
        source_index = int(identity[len(prefix):])
        source = network['trips'][source_index]
        assert network['calendars'][source[0]] == table['calendars'][trip[0]], (label, projected_index)
        assert network['trainTypes'][source[1]] == table['trainTypes'][trip[1]], (label, projected_index)
        assert str(source[2] or '') == str(trip[2] or ''), (label, projected_index)

        source_names = [names_by_id[network_stations[row[0]]] for row in source[3] or []]
        projected_rows = trip[3] or []
        projected_names = [table_names[row[0]] for row in projected_rows]
        assert len(projected_names) >= 2, (label, projected_index)

        cursor = -1
        positions: list[int] = []
        for name in projected_names:
            try:
                position = source_names.index(name, cursor + 1)
            except ValueError as exc:
                raise AssertionError((label, projected_index, name, source_index)) from exc
            positions.append(position)
            cursor = position
        for local_index, source_position in enumerate(positions):
            assert (projected_rows[local_index][1], projected_rows[local_index][2]) == (
                source[3][source_position][1], source[3][source_position][2]
            ), (label, projected_index, projected_names[local_index])
        for first, second in zip(positions, positions[1:]):
            assert second == first + 1, (label, projected_index, positions)
            assert target_railway_index in (source[4][first] or []), (
                label, projected_index, source_index, first, railway_id
            )
        assert trip[4] == table_stations[projected_rows[-1][0]], (label, projected_index)

    return len(trips), connections


def audit_all_projections(names_by_id: dict[str, str]) -> tuple[dict[str, dict[str, int]], int, int]:
    keisei_index = load_json(ROOT / 'data/transit/keisei/timetable-index.json')
    assert int(keisei_index.get('version') or 0) >= 3
    assert 'exact railway-link projection' in str(keisei_index.get('source') or '')
    descriptor = keisei_index.get('network') or {}
    assert descriptor.get('identityBasis') == 'official-one-train-page'
    assert int(descriptor.get('trips') or 0) == len(load_json(NETWORK).get('trips') or [])

    keisei_summary: dict[str, dict[str, int]] = {}
    for railway_id, filename in KEISEI_FILES.items():
        row = (keisei_index.get('lines') or {}).get(railway_id)
        assert isinstance(row, dict), railway_id
        trips, connections = audit_projection(
            names_by_id, railway_id,
            ROOT / 'data/transit/keisei/timetables' / filename,
            row, railway_id,
        )
        keisei_summary[railway_id] = {'trips': trips, 'connections': connections}

    external: dict[str, int] = {}
    for slug, railway_id in (('hokuso', HOKUSO), ('shibayama', SHIBAYAMA)):
        index = load_json(ROOT / f'data/transit/{slug}/timetable-index.json')
        row = (index.get('lines') or {}).get(railway_id)
        assert isinstance(row, dict), slug
        trips, connections = audit_projection(
            names_by_id, railway_id,
            ROOT / f'data/transit/{slug}/timetables/official-{slug}.json',
            row, slug,
        )
        coverage = load_json(ROOT / f'data/transit/{slug}/coverage-report.json')
        assert int(coverage.get('trips', -1)) == trips, slug
        assert int(coverage.get('connections', -1)) == connections, slug
        assert coverage.get('identityBasis') == 'same official one-train page', slug
        external[slug] = trips
    return keisei_summary, external['hokuso'], external['shibayama']


def audit_metadata(keisei_summary: dict[str, dict[str, int]], hokuso_trips: int, shibayama_trips: int) -> None:
    details = load_json(DETAILS)
    report = load_json(REPORT)
    manifest = load_json(MANIFEST)
    operators = manifest.get('operators') or {}
    keisei = operators.get('keisei') or {}
    hokuso = operators.get('hokuso') or {}
    shibayama = operators.get('shibayama') or {}

    assert report.get('keiseiLineProjection') == keisei_summary
    external = report.get('externalLineProjection') or {}
    assert int(external.get('hokusoTrips', -1)) == hokuso_trips
    assert int(external.get('shibayamaTrips', -1)) == shibayama_trips
    assert int(external.get('unsupportedStopRowsAfterExtension', -1)) == 0
    assert external.get('unsupportedStationsAfterExtension') == {}

    expected_connections = sum(row['connections'] for row in keisei_summary.values())
    assert keisei.get('status') == 'ok'
    assert int(keisei.get('trainTimetables', -1)) == int(details.get('trainCount') or 0)
    assert int(keisei.get('timetableLines', -1)) == len(KEISEI_FILES)
    assert int(keisei.get('timetableConnections', -1)) == expected_connections
    assert int(keisei.get('departures', -1)) == expected_connections
    assert int(keisei.get('inferredConnections', -1)) == 0
    assert keisei.get('identityBasis') == 'official-one-train-page'
    assert 'exact railway-link projection' in str(keisei.get('timetableSource') or '')

    assert int(hokuso.get('stations', -1)) == 15 and int(hokuso.get('trainTimetables', -1)) == hokuso_trips
    assert int(shibayama.get('stations', -1)) == 2 and int(shibayama.get('trainTimetables', -1)) == shibayama_trips
    assert hokuso.get('identityBasis') == 'official-one-train-page'
    assert shibayama.get('identityBasis') == 'official-one-train-page'

    boundaries = load_json(ROOT / 'data/transit/keisei/external-through-boundaries.json').get('boundaries') or []
    expected_boundaries = {
        frozenset((HOKUSO, 'odpt.Railway:Keisei.Main')): '京成高砂',
        frozenset((SHIBAYAMA, 'odpt.Railway:Keisei.HigashiNarita')): '東成田',
    }
    assert len(boundaries) == len(expected_boundaries)
    for row in boundaries:
        pair = frozenset((str(row.get('fromRailway') or ''), str(row.get('toRailway') or '')))
        assert pair in expected_boundaries, row
        assert str(row.get('station') or '') == expected_boundaries[pair], row
        assert row.get('status') == 'verified' and row.get('bidirectional') is True, row
        assert len(row.get('sourceUrls') or []) >= 2, row


def main() -> int:
    module = load_builder()
    names_by_id = build_station_names(module)
    summary = audit_source_network(module, names_by_id)
    keisei_summary, hokuso, shibayama = audit_all_projections(names_by_id)
    audit_metadata(keisei_summary, hokuso, shibayama)
    summary['keiseiProjectedTrips'] = sum(row['trips'] for row in keisei_summary.values())
    summary['keiseiProjectedConnections'] = sum(row['connections'] for row in keisei_summary.values())
    summary['hokusoProjectedTrips'] = hokuso
    summary['shibayamaProjectedTrips'] = shibayama
    print('Exhaustive Keisei exact-network and per-line projection audit passed')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
