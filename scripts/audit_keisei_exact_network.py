#!/usr/bin/env python3
"""Exhaustively audit the retained Keisei-led exact timetable network.

This is deliberately stricter than the coverage regression test.  It proves
that every retained official one-train page maps one-for-one to the generated
network, that every stop/time survives unchanged after normalization, that no
segment is left without a physical railway assignment, and that Hokusō /
Shibayama projections point back to exact network segments rather than being
reconstructed from nearby times or shared station IDs.
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
EXT_SCRIPT = ROOT / 'scripts/build_keisei_extended_network.py'
BASE_SCRIPT = ROOT / 'scripts/build_keisei_network_timetable.py'

HOKUSO = 'manual.Railway:Hokuso.Hokuso'
SHIBAYAMA = 'manual.Railway:Shibayama.Shibayama'
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


def exact_builder():
    base = load_module(BASE_SCRIPT, 'keisei_exact_audit_base')
    extension = load_module(EXT_SCRIPT, 'keisei_exact_audit_extension')
    extension.install_extensions(base)
    return base, extension


def train_number(module, source: dict[str, Any]) -> str:
    return module.train_number(source.get('sourceTrainId'))


def source_times(module, stops: list[dict[str, Any]]) -> list[tuple[int | None, int | None]]:
    result: list[tuple[int | None, int | None]] = []
    previous: int | None = None
    for stop in stops:
        arrival = module.monotonic(stop.get('arrival'), previous)
        departure = module.monotonic(stop.get('departure'), arrival if arrival is not None else previous)
        effective = departure if departure is not None else arrival
        if effective is not None:
            previous = effective
        result.append((arrival, departure))
    return result


def station_name_map(module, extension) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    keisei = load_json(ROOT / 'data/transit/keisei/entities.json')
    toei = load_json(ROOT / 'data/transit/toei/entities.json')
    keikyu = load_json(ROOT / 'data/transit/keikyu/entities.json')
    topology = load_json(ROOT / 'data/transit-sources/manual-topology.json')
    lines, _ = module.build_lines(keisei, toei, keikyu, topology)
    by_id: dict[str, str] = {}
    for line in lines.values():
        for name, station_id in zip(line.get('names') or [], line.get('stationIds') or []):
            normalized = module.normalize_name(name)
            existing = by_id.get(station_id)
            if existing is not None and existing != normalized:
                raise AssertionError((station_id, existing, normalized))
            by_id[station_id] = normalized
    return by_id, lines


def audit_source_and_network() -> dict[str, int]:
    module, extension = exact_builder()
    details = load_json(DETAILS)
    network = load_json(NETWORK)
    report = load_json(REPORT)
    names_by_station_id, lines = station_name_map(module, extension)

    trains = details.get('trains') or []
    trips = network.get('trips') or []
    assert int(details.get('trainCount') or 0) == len(trains), (details.get('trainCount'), len(trains))
    assert len(trips) == len(trains), (len(trips), len(trains))
    assert int(details.get('weekdayCount') or 0) + int(details.get('holidayCount') or 0) == len(trains)
    assert int(details.get('stopRowCount') or 0) == sum(len(train.get('stops') or []) for train in trains)
    assert report.get('networkTripCount') == len(trains), report.get('networkTripCount')
    assert report.get('skippedUnderTwoMappedStops') == 0
    assert report.get('unresolvedPairCount') == 0
    assert report.get('unsupportedStopRows') == 0
    assert report.get('unsupportedStations') == {}

    keys: set[str] = set()
    total_stops = 0
    total_links = 0
    calendars = network.get('calendars') or []
    types = network.get('trainTypes') or []
    stations = network.get('stations') or []
    railways = network.get('railways') or []

    assert network.get('timeBasis') == 'train-timetable-network'
    assert network.get('identityBasis') == 'Keisei official one-train timetable page'
    policy = network.get('identityPolicy') or {}
    assert policy.get('officialTrainPageEstablishesIdentity') is True
    assert policy.get('trainNumberAloneMayEstablishIdentity') is False
    assert policy.get('timeProximityAloneMayEstablishIdentity') is False
    assert policy.get('crossOperatorTransitionRequiresVerifiedBoundary') is True

    for trip_index, (source, trip) in enumerate(zip(trains, trips)):
        assert isinstance(source, dict), trip_index
        assert isinstance(trip, list) and len(trip) >= 5, trip_index
        source_key = str(source.get('key') or '')
        assert source_key, ('missing source key', trip_index)
        assert source_key not in keys, ('duplicate official train key', source_key)
        keys.add(source_key)

        source_stops = source.get('stops') or []
        assert len(source_stops) >= 2, (source_key, len(source_stops))
        network_stops = trip[3] or []
        links = trip[4] or []
        assert len(network_stops) == len(source_stops), (source_key, len(network_stops), len(source_stops))
        assert len(links) == len(network_stops) - 1, (source_key, len(links), len(network_stops))
        assert 0 <= int(trip[0]) < len(calendars), source_key
        assert 0 <= int(trip[1]) < len(types), source_key
        assert calendars[trip[0]] == str(source.get('calendar') or ''), (source_key, calendars[trip[0]], source.get('calendar'))
        assert str(trip[2] or '') == train_number(module, source), (source_key, trip[2], source.get('sourceTrainId'))

        expected_times = source_times(module, source_stops)
        previous_effective: int | None = None
        for stop_index, (raw_stop, encoded, expected_time) in enumerate(zip(source_stops, network_stops, expected_times)):
            assert isinstance(encoded, list) and len(encoded) >= 3, (source_key, stop_index)
            station_index = encoded[0]
            assert isinstance(station_index, int) and 0 <= station_index < len(stations), (source_key, stop_index, station_index)
            station_id = stations[station_index]
            encoded_name = names_by_station_id.get(station_id)
            source_name = module.normalize_name(raw_stop.get('station'))
            assert encoded_name == source_name, (source_key, stop_index, source_name, station_id, encoded_name)
            assert (encoded[1], encoded[2]) == expected_time, (source_key, source_name, (encoded[1], encoded[2]), expected_time)
            effective = encoded[2] if encoded[2] is not None else encoded[1]
            if effective is not None and previous_effective is not None:
                assert int(effective) >= int(previous_effective), (source_key, source_name, previous_effective, effective)
            if effective is not None:
                previous_effective = int(effective)

        for link_index, link in enumerate(links):
            assert isinstance(link, list) and link, ('empty railway link', source_key, link_index)
            for railway_index in link:
                assert isinstance(railway_index, int) and 0 <= railway_index < len(railways), (source_key, link_index, railway_index)
        total_stops += len(network_stops)
        total_links += len(links)

    assert len(keys) == len(trains)
    assert total_stops == int(details.get('stopRowCount') or 0), (total_stops, details.get('stopRowCount'))

    observed_crossings = {
        frozenset((str(row.get('fromRailway') or ''), str(row.get('toRailway') or '')))
        for row in report.get('crossOperatorTransitions') or []
    }
    assert observed_crossings == EXPECTED_EXTERNAL_CROSSINGS, (observed_crossings, EXPECTED_EXTERNAL_CROSSINGS)

    required_railways = {
        'odpt.Railway:Keisei.Main', 'odpt.Railway:Keisei.Oshiage', 'odpt.Railway:Keisei.Kanamachi',
        'odpt.Railway:Keisei.Chiba', 'odpt.Railway:Keisei.Chihara', 'odpt.Railway:Keisei.HigashiNarita',
        'odpt.Railway:Keisei.NaritaSkyAccess', 'odpt.Railway:Keisei.Matsudo',
        'odpt.Railway:Toei.Asakusa', 'odpt.Railway:Keikyu.Main', 'odpt.Railway:Keikyu.Airport',
        'odpt.Railway:Keikyu.Kurihama', 'odpt.Railway:Keikyu.Zushi', 'odpt.Railway:Keikyu.Daishi',
        HOKUSO, SHIBAYAMA,
    }
    assert required_railways.issubset(set(railways)), required_railways - set(railways)
    assert int(report.get('supportedRailwayCount') or 0) == len(railways)

    return {
        'sourceTrains': len(trains),
        'sourceStops': total_stops,
        'networkLinks': total_links,
        'networkRailways': len(railways),
    }


def audit_projection(slug: str, railway_id: str) -> int:
    network = load_json(NETWORK)
    table = load_json(ROOT / f'data/transit/{slug}/timetables/official-{slug}.json')
    index = load_json(ROOT / f'data/transit/{slug}/timetable-index.json')
    coverage = load_json(ROOT / f'data/transit/{slug}/coverage-report.json')
    stations = table.get('stations') or []
    network_stations = network.get('stations') or []
    network_railways = network.get('railways') or []
    target_index = network_railways.index(railway_id)

    assert table.get('railway') == railway_id
    assert table.get('timeBasis') == 'train-timetable'
    assert table.get('destinationAuthoritative') is False
    rows = list((index.get('lines') or {}).values())
    assert len(rows) == 1
    assert int(rows[0].get('trips') or -1) == len(table.get('trips') or [])
    assert int(coverage.get('trips') or -1) == len(table.get('trips') or [])
    assert coverage.get('identityBasis') == 'same official one-train page'

    for projected_index, trip in enumerate(table.get('trips') or []):
        assert isinstance(trip, list) and len(trip) >= 7, (slug, projected_index)
        assert trip[5] == trip[6], (slug, projected_index, trip[5:7])
        prefix = 'keisei-official-network:'
        identity = str(trip[6] or '')
        assert identity.startswith(prefix), (slug, projected_index, identity)
        source_index = int(identity[len(prefix):])
        assert 0 <= source_index < len(network.get('trips') or []), (slug, projected_index, source_index)
        source = network['trips'][source_index]
        assert network['calendars'][source[0]] == table['calendars'][trip[0]], (slug, projected_index)
        assert network['trainTypes'][source[1]] == table['trainTypes'][trip[1]], (slug, projected_index)
        assert str(source[2] or '') == str(trip[2] or ''), (slug, projected_index)

        projected_ids = []
        for stop in trip[3] or []:
            assert isinstance(stop, list) and len(stop) >= 3, (slug, projected_index, stop)
            station_index = stop[0]
            assert isinstance(station_index, int) and 0 <= station_index < len(stations), (slug, projected_index, station_index)
            projected_ids.append(stations[station_index])
        assert len(projected_ids) >= 2, (slug, projected_index)

        source_ids = [network_stations[row[0]] for row in source[3] or []]
        cursor = -1
        source_positions: list[int] = []
        for station_id in projected_ids:
            try:
                position = source_ids.index(station_id, cursor + 1)
            except ValueError as exc:
                raise AssertionError((slug, projected_index, station_id, source_index)) from exc
            source_positions.append(position)
            cursor = position
        for first, second in zip(source_positions, source_positions[1:]):
            assert second == first + 1, (slug, projected_index, source_positions)
            assert target_index in (source[4][first] or []), (slug, projected_index, source_index, first)

    return len(table.get('trips') or [])


def audit_manifest(hokuso_trips: int, shibayama_trips: int) -> None:
    manifest = load_json(MANIFEST)
    operators = manifest.get('operators') or {}
    keisei = operators.get('keisei') or {}
    hokuso = operators.get('hokuso') or {}
    shibayama = operators.get('shibayama') or {}
    details = load_json(DETAILS)

    assert keisei.get('status') == 'ok'
    assert int(keisei.get('trainTimetables') or 0) == int(details.get('trainCount') or 0)
    assert hokuso.get('status') == 'ok' and int(hokuso.get('stations') or 0) == 15
    assert shibayama.get('status') == 'ok' and int(shibayama.get('stations') or 0) == 2
    assert int(hokuso.get('trainTimetables') or 0) == hokuso_trips, (hokuso.get('trainTimetables'), hokuso_trips)
    assert int(shibayama.get('trainTimetables') or 0) == shibayama_trips, (shibayama.get('trainTimetables'), shibayama_trips)

    boundaries = load_json(ROOT / 'data/transit/keisei/external-through-boundaries.json')
    rows = boundaries.get('boundaries') or []
    assert len(rows) == 2, rows
    expected = {
        frozenset(('manual.Railway:Hokuso.Hokuso', 'odpt.Railway:Keisei.Main')): '京成高砂',
        frozenset(('manual.Railway:Shibayama.Shibayama', 'odpt.Railway:Keisei.HigashiNarita')): '東成田',
    }
    for row in rows:
        pair = frozenset((str(row.get('fromRailway') or ''), str(row.get('toRailway') or '')))
        assert pair in expected, row
        assert str(row.get('station') or '') == expected[pair], row
        assert row.get('status') == 'verified', row
        assert row.get('bidirectional') is True, row
        assert len(row.get('sourceUrls') or []) >= 2, row


def main() -> int:
    summary = audit_source_and_network()
    hokuso = audit_projection('hokuso', HOKUSO)
    shibayama = audit_projection('shibayama', SHIBAYAMA)
    audit_manifest(hokuso, shibayama)
    summary['hokusoProjectedTrips'] = hokuso
    summary['shibayamaProjectedTrips'] = shibayama
    print('Exhaustive Keisei exact-network audit passed')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
