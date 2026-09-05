#!/usr/bin/env python3
from __future__ import annotations

import unittest

import keikyu_internal_official_evidence as target


def frag(fid: str, railway: str, station: str, minute: int, calendar: str = 'odpt.Calendar:Weekday') -> dict:
    return {
        'id': fid,
        'railway': railway,
        'calendar': calendar,
        'stops': [[station, minute, minute]],
    }


def column(direction: str = 'toei-to-keikyu') -> dict:
    return {
        'calendar': 'weekday',
        'pdfPage': 1,
        'columnX': 123.4,
        'direction': direction,
        'shinagawaMinute': 600,
        'hanedaMinute': 620,
        'hanedaStationSuffix': target.HANEDA_T3_SUFFIX,
        'sourceUrl': 'https://www.keikyu.co.jp/example.pdf',
    }


class GeneratorTests(unittest.TestCase):
    def base_fragments(self) -> list[dict]:
        return [
            frag('m1', target.MAIN, 'odpt.Station:Keikyu.Main.Shinagawa', 600),
            frag('a1', target.AIRPORT, 'odpt.Station:Keikyu.Airport.HanedaAirportTerminal3', 620),
        ]

    def test_exact_two_point_singletons_generate_entry(self) -> None:
        entries, summary = target.match_columns([column()], self.base_fragments())
        self.assertEqual(1, len(entries))
        self.assertEqual('m1', entries[0]['fromFragment'])
        self.assertEqual('a1', entries[0]['toFragment'])
        self.assertEqual(["m1"], entries[0]['sourceMatches'])
        self.assertEqual(["a1"], entries[0]['targetMatches'])
        self.assertEqual(1, summary['matchedSingleton'])

    def test_reverse_direction_reverses_fragment_pair(self) -> None:
        entries, _ = target.match_columns([column('keikyu-to-toei')], self.base_fragments())
        self.assertEqual('a1', entries[0]['fromFragment'])
        self.assertEqual('m1', entries[0]['toFragment'])

    def test_one_minute_nearby_does_not_match(self) -> None:
        fragments = [
            frag('m1', target.MAIN, 'odpt.Station:Keikyu.Main.Shinagawa', 601),
            frag('a1', target.AIRPORT, 'odpt.Station:Keikyu.Airport.HanedaAirportTerminal3', 620),
        ]
        entries, summary = target.match_columns([column()], fragments)
        self.assertEqual([], entries)
        self.assertEqual(1, summary['reasons']['missing-main-exact'])

    def test_ambiguity_fails_closed(self) -> None:
        fragments = self.base_fragments() + [
            frag('m2', target.MAIN, 'odpt.Station:Keikyu.Main.Shinagawa', 600),
        ]
        entries, summary = target.match_columns([column()], fragments)
        self.assertEqual([], entries)
        self.assertEqual(1, summary['reasons']['ambiguous-exact'])

    def test_calendar_must_match(self) -> None:
        fragments = [
            frag('m1', target.MAIN, 'odpt.Station:Keikyu.Main.Shinagawa', 600, 'odpt.Calendar:SaturdayHoliday'),
            frag('a1', target.AIRPORT, 'odpt.Station:Keikyu.Airport.HanedaAirportTerminal3', 620),
        ]
        entries, _ = target.match_columns([column()], fragments)
        self.assertEqual([], entries)


if __name__ == '__main__':
    unittest.main()
