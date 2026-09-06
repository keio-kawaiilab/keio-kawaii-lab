#!/usr/bin/env python3
from __future__ import annotations

import copy

import sengakuji_destination_evidence as evidence

CAL = 'odpt.Calendar:Weekday'


def fragment(
    fid: str,
    railway: str,
    station: str,
    minute: int,
    *,
    side: str,
    kind: str,
    operator: str,
    destination: str,
    origin: str,
    confidence: int = 100,
) -> dict:
    stop = [station, minute, minute]
    return {
        'id': fid,
        'railway': railway,
        'calendar': CAL,
        'sourceKind': kind,
        'sourceOperator': operator,
        'confidence': confidence,
        'origin': [origin],
        'destination': [destination],
        'stops': [stop] if side in {'start', 'end'} else [],
    }


def indexes() -> dict:
    boundary = {
        'boundaryId': evidence.BOUNDARY_ID,
        'station': '泉岳寺',
    }
    return {
        'graph': {
            evidence.TOEI: [{**boundary, 'toRailway': evidence.KEIKYU}],
            evidence.KEIKYU: [{**boundary, 'toRailway': evidence.TOEI}],
        }
    }


def southbound_pair() -> list[dict]:
    destination = 'odpt.Station:Keikyu.Airport.HanedaAirportTerminal1and2'
    return [
        fragment(
            'toei-south', evidence.TOEI, evidence.TOEI_SENGAKUJI, 600,
            side='end', kind='exact-train-timetable', operator='toei',
            destination=destination,
            origin='odpt.Station:Keisei.Oshiage.Aoto',
        ),
        fragment(
            'keikyu-south', evidence.KEIKYU, evidence.KEIKYU_SENGAKUJI, 601,
            side='start', kind='station-timetable-reconstruction', operator='keikyu',
            destination=destination,
            origin=evidence.KEIKYU_SENGAKUJI,
            confidence=98,
        ),
    ]


def northbound_pair() -> list[dict]:
    destination = 'odpt.Station:Keisei.Main.KeiseiTakasago'
    return [
        fragment(
            'keikyu-north', evidence.KEIKYU, evidence.KEIKYU_SENGAKUJI, 700,
            side='end', kind='station-timetable-reconstruction', operator='keikyu',
            destination=destination,
            origin='odpt.Station:Keikyu.Main.Shinagawa',
            confidence=97,
        ),
        fragment(
            'toei-north', evidence.TOEI, evidence.TOEI_SENGAKUJI, 702,
            side='start', kind='exact-train-timetable', operator='toei',
            destination=destination,
            origin='odpt.Station:Keikyu.Airport.HanedaAirportTerminal1and2',
        ),
    ]


def assert_pair_ids(rows: list[dict], expected: list[tuple[str, str]]) -> None:
    actual = [(row['fromFragment'], row['toFragment']) for row in rows]
    assert actual == expected, (actual, expected)


def main() -> None:
    assert_pair_ids(
        evidence.candidate_pairs(southbound_pair(), indexes()),
        [('toei-south', 'keikyu-south')],
    )
    assert_pair_ids(
        evidence.candidate_pairs(northbound_pair(), indexes()),
        [('keikyu-north', 'toei-north')],
    )

    rows = southbound_pair()
    rows[1]['destination'] = ['odpt.Station:Keikyu.Kurihama.Misakiguchi']
    assert evidence.candidate_pairs(rows, indexes()) == []

    rows = southbound_pair()
    rows[0]['destination'] = [evidence.TOEI_SENGAKUJI]
    assert evidence.candidate_pairs(rows, indexes()) == []

    rows = northbound_pair()
    rows[1]['origin'] = [evidence.TOEI_SENGAKUJI]
    assert evidence.candidate_pairs(rows, indexes()) == []

    rows = southbound_pair()
    rows[1]['stops'][0][1] = 603
    rows[1]['stops'][0][2] = 603
    assert evidence.candidate_pairs(rows, indexes()) == []

    rows = southbound_pair()
    ambiguous = copy.deepcopy(rows[1])
    ambiguous['id'] = 'keikyu-south-second'
    ambiguous['stops'][0][1] = 602
    ambiguous['stops'][0][2] = 602
    assert evidence.candidate_pairs(rows + [ambiguous], indexes()) == []

    rows = southbound_pair()
    rows[1]['confidence'] = 96
    assert evidence.candidate_pairs(rows, indexes()) == []

    rows = southbound_pair()
    rows[1]['calendar'] = 'odpt.Calendar:SaturdayHoliday'
    assert evidence.candidate_pairs(rows, indexes()) == []

    unresolved = [{'kind': 'ambiguous-boundary-fragment-alignment', 'fragment': 'toei-south'}]
    output = evidence.apply_sengakuji_destination_evidence(southbound_pair(), [], unresolved, indexes())
    assert len(output) == 1
    assert evidence.MARKER in output[0]['evidence']
    assert output[0]['identityLevel'] == 'evidence-backed'
    assert output[0]['boundary']['gapMinutes'] == 1
    assert unresolved == []

    unsafe_indexes = {'graph': {}}
    unresolved = []
    assert evidence.apply_sengakuji_destination_evidence(southbound_pair(), [], unresolved, unsafe_indexes) == []
    assert unresolved and unresolved[0]['kind'] == 'sengakuji-destination-evidence-unverified-boundary'

    print('sengakuji destination evidence tests passed')


if __name__ == '__main__':
    main()
