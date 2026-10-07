#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import existing_seibu_exact_evidence as bridge


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def synthetic_root(root: Path, duplicate_target: bool = False) -> None:
    write_json(root / 'data/transit/seibu/entities.json', {
        'Station': [
            {'owl:sameAs': 'A.1', 'dc:title': '甲'},
            {'owl:sameAs': 'A.2', 'dc:title': '乙'},
            {'owl:sameAs': 'B.1', 'dc:title': '丙'},
            {'owl:sameAs': 'B.2', 'dc:title': '丁'},
        ]
    })
    write_json(root / 'data/transit/tokyo-metro/entities.json', {'Station': []})
    write_json(root / bridge.EVIDENCE, {
        'identityPolicy': {
            'singlePublishedOneTrainPageMayEstablishIdentity': True,
            'timeProximityMayEstablishIdentity': False,
            'trainNumberAloneMayEstablishIdentity': False,
            'destinationAloneMayEstablishIdentity': False,
        },
        'authoritativeThroughTrains': [{
            'url': 'https://seibu.ekitan.com/norikae/timetable/onetraintimetable/?test=1',
            'identityEvidence': 'single-published-one-train-page',
            'sourceParameters': {'dw': '0', 'date': '20261007', 'tx': 'x'},
            'stops': [
                {'station': '甲', 'arrival': '', 'departure': '23:50'},
                {'station': '乙', 'arrival': '23:55', 'departure': '23:56'},
                {'station': '丙', 'arrival': '00:01', 'departure': '00:02'},
                {'station': '丁', 'arrival': '00:05', 'departure': ''},
            ],
        }],
    })


def fragments(duplicate_target: bool = False):
    rows = [
        {
            'id': 'source',
            'sourceOperator': 'seibu',
            'sourceKind': 'station-timetable-reconstruction',
            'railway': 'rail:A',
            'calendar': 'odpt.Calendar:Weekday',
            'throughRailwayPath': ['rail:A', 'rail:B'],
            'trainNumber': 'IGNORED',
            'stops': [['A.1', None, 1430], ['A.2', 1435, 1436]],
        },
        {
            'id': 'target',
            'sourceOperator': 'seibu',
            'sourceKind': 'station-timetable-reconstruction',
            'railway': 'rail:B',
            'calendar': 'odpt.Calendar:Weekday',
            'throughRailwayPath': [],
            'trainNumber': 'DIFFERENT',
            'stops': [['B.1', 1441, 1442], ['B.2', 1445, None]],
        },
    ]
    if duplicate_target:
        rows.append({
            'id': 'target-duplicate',
            'sourceOperator': 'seibu',
            'sourceKind': 'station-timetable-reconstruction',
            'railway': 'rail:B',
            'calendar': 'odpt.Calendar:Weekday',
            'throughRailwayPath': [],
            'trainNumber': 'SAME-AS-SOURCE',
            'stops': [['B.1', 1441, 1442], ['B.2', 1445, None]],
        })
    return rows


def indexes():
    return {'graph': {'rail:A': [{
        'toRailway': 'rail:B',
        'station': '境界',
        'boundaryId': 'a-b',
    }]}}


def test_exact_page_creates_edge_across_midnight() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        synthetic_root(root)
        unresolved = [{'kind': 'ambiguous-boundary-fragment-alignment', 'fragment': 'source'}]
        edges = bridge.apply_existing_seibu_exact_evidence(
            fragments(), [], unresolved, indexes(), root
        )
        assert len(edges) == 1, edges
        assert edges[0]['fromFragment'] == 'source'
        assert edges[0]['toFragment'] == 'target'
        assert edges[0]['identityLevel'] == 'evidence-backed'
        assert 'operator-official-single-train-page' in edges[0]['evidence']
        assert not unresolved


def test_ambiguous_target_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        synthetic_root(root, duplicate_target=True)
        unresolved = []
        edges = bridge.apply_existing_seibu_exact_evidence(
            fragments(duplicate_target=True), [], unresolved, indexes(), root
        )
        assert edges == [], edges


def test_one_station_is_not_enough() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        synthetic_root(root)
        rows = fragments()
        rows[0]['stops'] = [['A.1', None, 1430]]
        edges = bridge.apply_existing_seibu_exact_evidence(
            rows, [], [], indexes(), root
        )
        assert edges == [], edges


def main() -> int:
    test_exact_page_creates_edge_across_midnight()
    test_ambiguous_target_fails_closed()
    test_one_station_is_not_enough()
    print('existing Seibu exact evidence bridge tests passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
