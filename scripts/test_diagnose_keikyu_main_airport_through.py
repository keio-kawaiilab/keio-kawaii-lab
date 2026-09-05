#!/usr/bin/env python3
from __future__ import annotations

import unittest

import diagnose_keikyu_main_airport_through as target


class DiagnosticPolicyTests(unittest.TestCase):
    def test_exact_stop_minute_required(self) -> None:
        fragment = {
            'railway': target.MAIN,
            'calendar': 'odpt.Calendar:Weekday',
            'stops': [['odpt.Station:Keikyu.Main.Shinagawa', 600, 600]],
        }
        self.assertTrue(target.fragment_has_exact(fragment, target.MAIN, 'weekday', target.SHINAGAWA_SUFFIX, 600))
        self.assertFalse(target.fragment_has_exact(fragment, target.MAIN, 'weekday', target.SHINAGAWA_SUFFIX, 601))

    def test_wrong_railway_fails(self) -> None:
        fragment = {
            'railway': target.AIRPORT,
            'calendar': 'odpt.Calendar:Weekday',
            'stops': [['odpt.Station:Keikyu.Airport.HanedaAirportTerminal1and2', 600, 600]],
        }
        self.assertFalse(target.fragment_has_exact(fragment, target.MAIN, 'weekday', target.HANEDA_T12_SUFFIX, 600))

    def test_calendar_must_match(self) -> None:
        fragment = {
            'railway': target.MAIN,
            'calendar': 'odpt.Calendar:SaturdayHoliday',
            'stops': [['odpt.Station:Keikyu.Main.Shinagawa', 600, 600]],
        }
        self.assertFalse(target.fragment_has_exact(fragment, target.MAIN, 'weekday', target.SHINAGAWA_SUFFIX, 600))
        self.assertTrue(target.fragment_has_exact(fragment, target.MAIN, 'holiday', target.SHINAGAWA_SUFFIX, 600))


if __name__ == '__main__':
    unittest.main()
