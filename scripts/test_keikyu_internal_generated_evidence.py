#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import keikyu_internal_generated_evidence as target


def fragment(fid: str, railway: str) -> dict:
    return {'id': fid, 'railway': railway, 'calendar': 'odpt.Calendar:Weekday', 'stops': []}


def entry(**changes) -> dict:
    base = {
        'id': 'internal:test', 'matchStatus': 'matched-singleton',
        'boundaryId': target.BOUNDARY_ID, 'fromRailway': target.MAIN, 'toRailway': target.AIRPORT,
        'fromFragment': 'm1', 'toFragment': 'a1', 'sourceMatches': ['m1'], 'targetMatches': ['a1'],
        'evidence': ['operator-official-mainline-timetable', target.MARKER],
        'sourceUrl': 'https://www.keikyu.co.jp/example.pdf',
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


def graph(pair=None, boundary_id=None, *, verified: bool = True) -> dict:
    pair = pair or (target.MAIN, target.AIRPORT)
    boundary_id = boundary_id or target.BOUNDARY_ID
    rows = [{'toRailway': pair[1], 'boundaryId': boundary_id}] if verified else []
    return {'graph': {pair[0]: rows}}


class ConsumerTests(unittest.TestCase):
    def apply(self, data: dict, *, fragments=None, indexes=None):
        fragments = fragments or [fragment('m1', target.MAIN), fragment('a1', target.AIRPORT)]
        unresolved: list[dict] = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'evidence.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            edges = target.apply_generated_evidence(fragments, [], unresolved, indexes or graph(), path)
        return edges, unresolved

    def test_valid_two_point_singleton_adds_edge(self) -> None:
        edges, unresolved = self.apply(payload(entry()))
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        self.assertEqual('evidence-backed', edges[0]['identityLevel'])
        self.assertEqual('京急蒲田', edges[0]['boundary']['station'])

    def test_valid_kurihama_main_two_point_singleton_adds_edge(self) -> None:
        row = entry(
            boundaryId=target.KURIHAMA_BOUNDARY_ID,
            fromRailway=target.KURIHAMA,
            toRailway=target.MAIN,
            fromFragment='k1', toFragment='m1', sourceMatches=['k1'], targetMatches=['m1'],
        )
        fragments = [fragment('k1', target.KURIHAMA), fragment('m1', target.MAIN)]
        indexes = graph((target.KURIHAMA, target.MAIN), target.KURIHAMA_BOUNDARY_ID)
        edges, unresolved = self.apply(payload(row), fragments=fragments, indexes=indexes)
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        self.assertEqual('堀ノ内', edges[0]['boundary']['station'])

    def test_valid_zushi_main_two_point_singleton_adds_edge(self) -> None:
        row = entry(
            boundaryId=target.ZUSHI_BOUNDARY_ID,
            fromRailway=target.ZUSHI,
            toRailway=target.MAIN,
            fromFragment='z1', toFragment='m1', sourceMatches=['z1'], targetMatches=['m1'],
        )
        fragments = [fragment('z1', target.ZUSHI), fragment('m1', target.MAIN)]
        indexes = graph((target.ZUSHI, target.MAIN), target.ZUSHI_BOUNDARY_ID)
        edges, unresolved = self.apply(payload(row), fragments=fragments, indexes=indexes)
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        self.assertEqual('金沢八景', edges[0]['boundary']['station'])

    def test_legacy_marker_remains_accepted(self) -> None:
        row = entry(evidence=['operator-official-connection-timetable', target.LEGACY_MARKER])
        edges, unresolved = self.apply(payload(row))
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))

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

    def test_wrong_pair_fails_closed(self) -> None:
        edges, unresolved = self.apply(payload(entry(toRailway=target.ZUSHI)))
        self.assertEqual([], edges)
        self.assertEqual('unexpected-railway-pair', unresolved[0]['reason'])


if __name__ == '__main__':
    unittest.main()
