#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import keikyu_internal_generated_evidence as target


def fragment(
    fid: str,
    railway: str,
    *,
    direction: str = '',
    station: str = '',
    minute: int | None = None,
) -> dict:
    stops = [[station, minute, minute]] if station and minute is not None else []
    return {
        'id': fid,
        'railway': railway,
        'calendar': 'odpt.Calendar:Weekday',
        'direction': direction,
        'stops': stops,
    }


def entry(**changes) -> dict:
    base = {
        'id': 'internal:test',
        'matchStatus': 'matched-singleton',
        'boundaryId': target.AIRPORT_BOUNDARY_ID,
        'fromRailway': target.MAIN,
        'toRailway': target.AIRPORT,
        'fromFragment': 'm1',
        'toFragment': 'a1',
        'sourceMatches': ['m1'],
        'targetMatches': ['a1'],
        'evidence': ['operator-official-connection-timetable', target.AIRPORT_MARKER],
        'sourceUrl': 'https://www.keikyu.co.jp/example.pdf',
    }
    base.update(changes)
    return base


def kurihama_entry(**changes) -> dict:
    base = {
        'id': 'kurihama:test',
        'matchStatus': 'matched-singleton',
        'boundaryId': target.KURIHAMA_BOUNDARY_ID,
        'calendar': 'weekday',
        'direction': 'main-to-kurihama',
        'fromRailway': target.MAIN,
        'toRailway': target.KURIHAMA,
        'fromFragment': 'm1',
        'toFragment': 'k1',
        'sourceMatches': ['m1'],
        'targetMatches': ['k1'],
        'shinagawaMinute': 600,
        'branchEndpointStationSuffix': '.Misakiguchi',
        'branchEndpointMinute': 713,
        'branchEndpointRole': 'terminal',
        'evidence': ['operator-official-connection-timetable', target.KURIHAMA_MARKER],
        'sourceUrl': 'https://www.keikyu.co.jp/example.pdf',
        'matchPolicy': {
            'officialSamePrintedColumnRequired': True,
            'explicitBranchOriginOrTerminalRequired': True,
            'exactShinagawaMinuteRequired': True,
            'exactBranchEndpointMinuteRequired': True,
            'singletonFragmentMatchRequiredAtBothPoints': True,
            'stationMinuteTolerance': 0,
            'trainNumberAloneMayEstablishIdentity': False,
            'timeProximityAloneMayEstablishIdentity': False,
            'destinationAloneMayEstablishIdentity': False,
        },
    }
    base.update(changes)
    return base


def payload(row: dict, *, safe: bool = True) -> dict:
    return {
        'policy': {
            'officialSamePrintedColumnRequired': True,
            'twoExactPublishedStationTimesRequired': True,
            'singletonFragmentMatchRequiredAtBothPoints': True,
            'trainNumberAloneMayEstablishIdentity': False if safe else True,
            'timeProximityAloneMayEstablishIdentity': False,
        },
        'entries': [row],
    }


def graph(
    *,
    verified: bool = True,
    from_railway: str = target.MAIN,
    to_railway: str = target.AIRPORT,
    boundary_id: str = target.AIRPORT_BOUNDARY_ID,
) -> dict:
    rows = [{'toRailway': to_railway, 'boundaryId': boundary_id}] if verified else []
    return {'graph': {from_railway: rows}}


class ConsumerTests(unittest.TestCase):
    def apply(self, data: dict, *, fragments=None, indexes=None):
        fragments = fragments or [fragment('m1', target.MAIN), fragment('a1', target.AIRPORT)]
        unresolved: list[dict] = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'evidence.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            edges = target.apply_generated_evidence(fragments, [], unresolved, indexes or graph(), path)
        return edges, unresolved

    def test_valid_airport_two_point_singleton_adds_edge(self) -> None:
        edges, unresolved = self.apply(payload(entry()))
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        self.assertEqual('evidence-backed', edges[0]['identityLevel'])
        self.assertEqual('京急蒲田', edges[0]['boundary']['station'])
        self.assertIn('keikyu-official-main-airport-same-column-two-point', edges[0]['evidence'])

    def test_non_singleton_record_fails_closed(self) -> None:
        edges, unresolved = self.apply(payload(entry(sourceMatches=['m1', 'm2'])))
        self.assertEqual([], edges)
        self.assertEqual('non-singleton-recorded-match', unresolved[0]['reason'])

    def test_stale_fragment_fails_closed(self) -> None:
        edges, unresolved = self.apply(payload(entry()), fragments=[fragment('m1', target.MAIN)])
        self.assertEqual([], edges)
        self.assertEqual('stale-fragment-reference', unresolved[0]['reason'])

    def test_unverified_boundary_fails_closed(self) -> None:
        edges, unresolved = self.apply(payload(entry()), indexes=graph(verified=False))
        self.assertEqual([], edges)
        self.assertEqual('unverified-operational-boundary', unresolved[0]['reason'])

    def test_unsafe_policy_fails_closed(self) -> None:
        edges, unresolved = self.apply(payload(entry(), safe=False))
        self.assertEqual([], edges)
        self.assertEqual('keikyu-internal-generated-evidence-unsafe-policy', unresolved[0]['kind'])

    def test_wrong_airport_pair_fails_closed(self) -> None:
        edges, unresolved = self.apply(payload(entry(toRailway=target.KURIHAMA)))
        self.assertEqual([], edges)
        self.assertEqual('unexpected-railway-pair', unresolved[0]['reason'])

    def test_valid_kurihama_two_point_singleton_adds_edge(self) -> None:
        fragments = [
            fragment(
                'm1', target.MAIN,
                direction='odpt.RailDirection:Outbound',
                station='odpt.Station:Keikyu.Main.Shinagawa', minute=600,
            ),
            fragment(
                'k1', target.KURIHAMA,
                direction='odpt.RailDirection:Outbound',
                station='odpt.Station:Keikyu.Kurihama.Misakiguchi', minute=713,
            ),
        ]
        indexes = graph(
            from_railway=target.MAIN,
            to_railway=target.KURIHAMA,
            boundary_id=target.KURIHAMA_BOUNDARY_ID,
        )
        edges, unresolved = self.apply(payload(kurihama_entry()), fragments=fragments, indexes=indexes)
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        self.assertEqual('堀ノ内', edges[0]['boundary']['station'])
        self.assertIn('keikyu-official-main-kurihama-same-column-endpoint-two-point', edges[0]['evidence'])

    def test_kurihama_one_minute_tamper_fails_closed(self) -> None:
        fragments = [
            fragment(
                'm1', target.MAIN,
                direction='odpt.RailDirection:Outbound',
                station='odpt.Station:Keikyu.Main.Shinagawa', minute=601,
            ),
            fragment(
                'k1', target.KURIHAMA,
                direction='odpt.RailDirection:Outbound',
                station='odpt.Station:Keikyu.Kurihama.Misakiguchi', minute=713,
            ),
        ]
        indexes = graph(
            from_railway=target.MAIN,
            to_railway=target.KURIHAMA,
            boundary_id=target.KURIHAMA_BOUNDARY_ID,
        )
        edges, unresolved = self.apply(payload(kurihama_entry()), fragments=fragments, indexes=indexes)
        self.assertEqual([], edges)
        self.assertEqual('kurihama-exact-two-point-revalidation-failed', unresolved[0]['reason'])

    def test_kurihama_wrong_direction_fails_closed(self) -> None:
        fragments = [
            fragment(
                'm1', target.MAIN,
                direction='odpt.RailDirection:Inbound',
                station='odpt.Station:Keikyu.Main.Shinagawa', minute=600,
            ),
            fragment(
                'k1', target.KURIHAMA,
                direction='odpt.RailDirection:Inbound',
                station='odpt.Station:Keikyu.Kurihama.Misakiguchi', minute=713,
            ),
        ]
        indexes = graph(
            from_railway=target.MAIN,
            to_railway=target.KURIHAMA,
            boundary_id=target.KURIHAMA_BOUNDARY_ID,
        )
        edges, unresolved = self.apply(payload(kurihama_entry()), fragments=fragments, indexes=indexes)
        self.assertEqual([], edges)
        self.assertEqual('kurihama-exact-two-point-revalidation-failed', unresolved[0]['reason'])


if __name__ == '__main__':
    unittest.main()
