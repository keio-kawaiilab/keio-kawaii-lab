#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

MODULE_PATH = Path(__file__).with_name('build_transit_v2.py')
spec = importlib.util.spec_from_file_location('build_transit_v2', MODULE_PATH)
assert spec and spec.loader
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


def test_unique_shortest_path() -> None:
    graph = {
        'A': [{'toRailway': 'B', 'fromRailway': 'A', 'station': 'X', 'kind': 'verified', 'evidence': 'x'}],
        'B': [{'toRailway': 'C', 'fromRailway': 'B', 'station': 'Y', 'kind': 'same', 'evidence': 'y'}],
    }
    result = v2.unique_shortest_path(graph, 'A', {'C'})
    assert result['status'] == 'matched'
    assert result['railways'] == ['A', 'B', 'C']

    ambiguous = {
        'A': [
            {'toRailway': 'B', 'fromRailway': 'A', 'station': 'X', 'kind': 'x', 'evidence': ''},
            {'toRailway': 'D', 'fromRailway': 'A', 'station': 'Z', 'kind': 'x', 'evidence': ''},
        ],
        'B': [{'toRailway': 'C', 'fromRailway': 'B', 'station': 'Y', 'kind': 'x', 'evidence': ''}],
        'D': [{'toRailway': 'C', 'fromRailway': 'D', 'station': 'W', 'kind': 'x', 'evidence': ''}],
    }
    result = v2.unique_shortest_path(ambiguous, 'A', {'C'})
    assert result['status'] == 'ambiguous'


def test_alignment_never_uses_train_number() -> None:
    source = {'stops': [['A.X', None, 600]], 'trainNumber': '123'}
    far = {'stops': [['B.X', 620, 620]], 'trainNumber': '123'}
    ok, _ = v2.candidate_alignment(source, far)
    assert not ok, 'same train number must not establish identity'


def synthetic_repo(root: Path) -> None:
    transit = root / 'data/transit'
    transit.mkdir(parents=True)
    (root / 'data/transit-v2').mkdir(parents=True)
    manifest = {
        'fetchedAt': '2026-09-04T00:00:00+09:00',
        'operators': {
            'a': {'operator': 'op:A', 'status': 'ok'},
            'b': {'operator': 'op:B', 'status': 'ok'},
            'c': {'operator': 'op:C', 'status': 'ok'},
        },
    }
    (transit / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def write_operator(slug: str, operator: str, railway: str, stations: list[tuple[str, str]], table: dict) -> None:
        op = transit / slug
        (op / 'timetables').mkdir(parents=True)
        entity_stations = [
            {'owl:sameAs': sid, 'odpt:operator': operator, 'odpt:railway': railway, 'odpt:stationTitle': {'ja': station_title}}
            for sid, station_title in stations
        ]
        entity_railway = [{
            'owl:sameAs': railway,
            'odpt:operator': operator,
            'odpt:railwayTitle': {'ja': railway},
            'odpt:stationOrder': [
                {'odpt:index': i + 1, 'odpt:station': sid, 'odpt:stationTitle': {'ja': station_title}}
                for i, (sid, station_title) in enumerate(stations)
            ],
        }]
        (op / 'entities.json').write_text(json.dumps({'Station': entity_stations, 'Railway': entity_railway}), encoding='utf-8')
        (op / 'timetables/t.json').write_text(json.dumps(table), encoding='utf-8')
        (op / 'timetable-index.json').write_text(json.dumps({'version': 1, 'lines': {railway: {'file': 'timetables/t.json'}}}), encoding='utf-8')

    write_operator('a', 'op:A', 'rail:A', [('A.1', 'A1'), ('A.X', 'X')], {
        'timeBasis': 'train-timetable',
        'stations': ['A.1', 'A.X'],
        'calendars': ['weekday'],
        'trainTypes': ['local'],
        'tripSchema': ['calendarIndex', 'trainTypeIndex', 'trainNumber', 'stops', 'destination', 'trainId', 'timetableId'],
        'trips': [[0, 0, 'N1', [[0, None, 590], [1, 600, None]], 'B.2', 'train-a', 'tt-a']],
    })
    write_operator('b', 'op:B', 'rail:B', [('B.X', 'X'), ('B.2', 'B2')], {
        'timeBasis': 'train-timetable',
        'stations': ['B.X', 'B.2'],
        'calendars': ['weekday'],
        'trainTypes': ['local'],
        'tripSchema': ['calendarIndex', 'trainTypeIndex', 'trainNumber', 'stops', 'destination', 'trainId', 'timetableId'],
        'trips': [
            [0, 0, 'DIFFERENT', [[0, None, 600], [1, 610, None]], 'B.2', 'train-b', 'tt-b'],
            [0, 0, 'N1', [[0, None, 620], [1, 630, None]], 'B.2', 'train-c', 'tt-c'],
        ],
    })
    write_operator('c', 'op:C', 'rail:C', [('C.X', 'X'), ('C.2', 'C2')], {
        'timeBasis': 'train-timetable',
        'stations': ['C.X', 'C.2'],
        'calendars': ['weekday'],
        'trainTypes': ['local'],
        'tripSchema': ['calendarIndex', 'trainTypeIndex', 'trainNumber', 'stops', 'destination', 'trainId', 'timetableId'],
        'trips': [[0, 0, 'N1', [[0, None, 600], [1, 610, None]], 'C.2', 'train-z', 'tt-z']],
    })

    identity = {
        'version': 1,
        'records': [
            {'timetableId': 'tt-a', 'railway': 'rail:A', 'nextTrainTimetables': ['tt-b', 'tt-z'], 'previousTrainTimetables': [], 'origin': ['A.1'], 'destination': ['B.2']},
            {'timetableId': 'tt-b', 'railway': 'rail:B', 'nextTrainTimetables': [], 'previousTrainTimetables': ['tt-a'], 'origin': ['B.X'], 'destination': ['B.2']},
            {'timetableId': 'tt-z', 'railway': 'rail:C', 'nextTrainTimetables': [], 'previousTrainTimetables': ['tt-a'], 'origin': ['C.X'], 'destination': ['C.2']},
        ],
    }
    (transit / 'odpt-train-identities.json').write_text(json.dumps(identity), encoding='utf-8')
    boundaries = {
        'version': 1,
        'boundaries': [
            {'id': 'ab', 'station': 'X', 'fromRailway': 'rail:A', 'toRailway': 'rail:B', 'bidirectional': True, 'status': 'verified', 'sourceUrls': ['official:a-b']},
            {'id': 'ac', 'station': 'X', 'fromRailway': 'rail:A', 'toRailway': 'rail:C', 'bidirectional': True, 'status': 'verified', 'sourceUrls': ['official:a-c']},
        ],
    }
    (root / 'data/transit-v2/service-boundaries.json').write_text(json.dumps(boundaries), encoding='utf-8')


def test_authoritative_split_and_no_number_inference() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        synthetic_repo(root)
        old = (v2.ROOT, v2.V1, v2.OUT, v2.BOUNDARIES, v2.IDENTITY)
        try:
            v2.ROOT = root
            v2.V1 = root / 'data/transit'
            v2.OUT = root / 'data/transit-v2'
            v2.BOUNDARIES = v2.OUT / 'service-boundaries.json'
            v2.IDENTITY = v2.V1 / 'odpt-train-identities.json'
            coverage = v2.build()
            edges = json.loads((v2.OUT / 'same-train-edges.json').read_text())['edges']
            fragment_rows = []
            for path in (v2.OUT / 'fragments').glob('*.json'):
                fragment_rows += json.loads(path.read_text())['fragments']
            ids = {row['timetableId']: row['id'] for row in fragment_rows if row['timetableId']}
            pairs = {(edge['fromFragment'], edge['toFragment']) for edge in edges}
            assert (ids['tt-a'], ids['tt-b']) in pairs
            assert (ids['tt-a'], ids['tt-z']) in pairs
            assert (ids['tt-b'], ids['tt-z']) not in pairs
            assert (ids['tt-z'], ids['tt-b']) not in pairs
            assert (ids['tt-a'], ids['tt-c']) not in pairs, 'same train number without official link must not be through'
            assert coverage['summary']['authoritativeSameTrainEdges'] == 2
        finally:
            v2.ROOT, v2.V1, v2.OUT, v2.BOUNDARIES, v2.IDENTITY = old


def main() -> None:
    test_unique_shortest_path()
    test_alignment_never_uses_train_number()
    test_authoritative_split_and_no_number_inference()
    print('transit-v2 tests passed')


if __name__ == '__main__':
    main()
