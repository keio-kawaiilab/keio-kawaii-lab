#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import keikyu_kurihama_official_evidence as target


def frag(
    fid: str,
    railway: str,
    station: str,
    minute: int,
    direction: str,
    calendar: str = 'odpt.Calendar:Weekday',
) -> dict:
    return {
        'id': fid,
        'railway': railway,
        'calendar': calendar,
        'direction': direction,
        'stops': [[station, minute, minute]],
    }


def column(direction: str = 'toei-to-keikyu') -> dict:
    return {
        'calendar': 'weekday',
        'pdfPage': 1,
        'columnX': 210.66,
        'direction': direction,
        'shinagawaMinute': 600,
        'branchEndpointStationName': '三崎口',
        'branchEndpointStationSuffix': '.Misakiguchi',
        'branchEndpointMinute': 713 if direction == 'toei-to-keikyu' else 505,
        'branchEndpointRole': 'terminal' if direction == 'toei-to-keikyu' else 'origin',
        'sourceUrl': 'https://www.keikyu.co.jp/example.pdf',
    }


class GeneratorTests(unittest.TestCase):
    def southbound_fragments(self) -> list[dict]:
        return [
            frag('m1', target.MAIN, 'odpt.Station:Keikyu.Main.Shinagawa', 600, 'odpt.RailDirection:Outbound'),
            frag('k1', target.KURIHAMA, 'odpt.Station:Keikyu.Kurihama.Misakiguchi', 713, 'odpt.RailDirection:Outbound'),
        ]

    def northbound_fragments(self) -> list[dict]:
        return [
            frag('m1', target.MAIN, 'odpt.Station:Keikyu.Main.Shinagawa', 600, 'odpt.RailDirection:Inbound'),
            frag('k1', target.KURIHAMA, 'odpt.Station:Keikyu.Kurihama.Misakiguchi', 505, 'odpt.RailDirection:Inbound'),
        ]

    def test_southbound_exact_two_point_singletons_generate_entry(self) -> None:
        entries, summary = target.match_columns([column()], self.southbound_fragments())
        self.assertEqual(1, len(entries))
        self.assertEqual('m1', entries[0]['fromFragment'])
        self.assertEqual('k1', entries[0]['toFragment'])
        self.assertEqual('main-to-kurihama', entries[0]['direction'])
        self.assertEqual(target.BOUNDARY_ID, entries[0]['boundaryId'])
        self.assertEqual(0, entries[0]['matchPolicy']['stationMinuteTolerance'])
        self.assertEqual(1, summary['matchedSingleton'])

    def test_northbound_reverses_fragment_pair(self) -> None:
        entries, _ = target.match_columns([column('keikyu-to-toei')], self.northbound_fragments())
        self.assertEqual(1, len(entries))
        self.assertEqual('k1', entries[0]['fromFragment'])
        self.assertEqual('m1', entries[0]['toFragment'])
        self.assertEqual('kurihama-to-main', entries[0]['direction'])

    def test_one_minute_nearby_does_not_match(self) -> None:
        fragments = [
            frag('m1', target.MAIN, 'odpt.Station:Keikyu.Main.Shinagawa', 601, 'odpt.RailDirection:Outbound'),
            frag('k1', target.KURIHAMA, 'odpt.Station:Keikyu.Kurihama.Misakiguchi', 713, 'odpt.RailDirection:Outbound'),
        ]
        entries, summary = target.match_columns([column()], fragments)
        self.assertEqual([], entries)
        self.assertEqual(1, summary['reasons']['missing-main-exact'])

    def test_wrong_direction_does_not_match(self) -> None:
        fragments = [
            frag('m1', target.MAIN, 'odpt.Station:Keikyu.Main.Shinagawa', 600, 'odpt.RailDirection:Inbound'),
            frag('k1', target.KURIHAMA, 'odpt.Station:Keikyu.Kurihama.Misakiguchi', 713, 'odpt.RailDirection:Inbound'),
        ]
        entries, summary = target.match_columns([column()], fragments)
        self.assertEqual([], entries)
        self.assertEqual(1, summary['reasons']['missing-main-exact'])
        self.assertEqual(1, summary['reasons']['missing-kurihama-exact'])

    def test_ambiguity_fails_closed(self) -> None:
        fragments = self.southbound_fragments() + [
            frag('m2', target.MAIN, 'odpt.Station:Keikyu.Main.Shinagawa', 600, 'odpt.RailDirection:Outbound')
        ]
        entries, summary = target.match_columns([column()], fragments)
        self.assertEqual([], entries)
        self.assertEqual(1, summary['reasons']['ambiguous-main-exact'])

    def test_append_is_idempotent_for_kurihama_boundary(self) -> None:
        base = {
            'version': 1,
            'policy': {
                'officialSamePrintedColumnRequired': True,
                'twoExactPublishedStationTimesRequired': True,
                'singletonFragmentMatchRequiredAtBothPoints': True,
                'trainNumberAloneMayEstablishIdentity': False,
                'timeProximityAloneMayEstablishIdentity': False,
            },
            'summary': {'matchedSingleton': 7},
            'entries': [{'id': 'airport:1', 'boundaryId': 'keikyu-main-airport-kamata'}],
        }
        first = {'id': 'kurihama:old', 'boundaryId': target.BOUNDARY_ID}
        second = {'id': 'kurihama:new', 'boundaryId': target.BOUNDARY_ID}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'evidence.json'
            path.write_text(json.dumps({**base, 'entries': base['entries'] + [first]}), encoding='utf-8')
            target.append_payload(path, [second], {'matchedSingleton': 1})
            payload = json.loads(path.read_text(encoding='utf-8'))
        ids = [row['id'] for row in payload['entries']]
        self.assertEqual(['airport:1', 'kurihama:new'], ids)
        self.assertEqual(2, payload['summary']['totalEntries'])
        self.assertFalse(payload['policy']['destinationAloneMayEstablishIdentity'])


if __name__ == '__main__':
    unittest.main()
