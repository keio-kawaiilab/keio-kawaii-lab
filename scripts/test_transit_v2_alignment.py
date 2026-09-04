#!/usr/bin/env python3
from __future__ import annotations

import build_transit_v2 as transit


def fragment(fid: str, railway: str, station: str, minute: int, *, path: list[str] | None = None) -> dict:
    row = {
        'id': fid,
        'sourceKind': 'station-timetable-reconstruction',
        'sourceOperator': 'test',
        'railway': railway,
        'calendar': 'weekday',
        'direction': 'inbound',
        'trainType': 'local',
        'destination': ['dest'],
        'stops': [[station, None, minute]],
    }
    if path:
        row['throughRailwayPath'] = path
    return row


def indexes() -> dict:
    return {
        'stationTitle': {
            'before': 'Before',
            'boundary-a': 'Boundary',
            'boundary-b': 'Boundary',
        },
        'graph': {
            'r1': [{
                'fromRailway': 'r1',
                'toRailway': 'r2',
                'station': 'Boundary',
                'kind': 'verified-operational-junction',
            }],
        },
    }


def test_zero_minute_between_distinct_physical_stations_is_rejected() -> None:
    source = fragment('source', 'r1', 'before', 100, path=['r1', 'r2'])
    impossible = fragment('impossible', 'r2', 'boundary-b', 100)
    possible = fragment('possible', 'r2', 'boundary-b', 103)
    unresolved: list[dict] = []
    edges = transit.align_inferred_edges([source, impossible, possible], indexes(), [], unresolved)
    assert [(edge['fromFragment'], edge['toFragment']) for edge in edges] == [('source', 'possible')], edges
    assert not unresolved, unresolved


def test_zero_minute_at_same_physical_boundary_is_allowed() -> None:
    source = fragment('source-boundary', 'r1', 'boundary-a', 100, path=['r1', 'r2'])
    target = fragment('target-boundary', 'r2', 'boundary-b', 100)
    unresolved: list[dict] = []
    edges = transit.align_inferred_edges([source, target], indexes(), [], unresolved)
    assert [(edge['fromFragment'], edge['toFragment']) for edge in edges] == [('source-boundary', 'target-boundary')], edges
    assert edges[0]['alignmentDeltaMinutes'] == 0, edges
    assert not unresolved, unresolved


def main() -> int:
    test_zero_minute_between_distinct_physical_stations_is_rejected()
    test_zero_minute_at_same_physical_boundary_is_allowed()
    print('transit-v2 strict alignment regression tests passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
