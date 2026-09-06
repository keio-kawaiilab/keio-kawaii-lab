#!/usr/bin/env python3
from __future__ import annotations

import unittest
from types import SimpleNamespace

from build_keikyu_official_stop_times import build_page_fragments, fragment_id


class KeikyuOfficialStopTimesTest(unittest.TestCase):
    def grid(self):
        return SimpleNamespace(
            centers=(100.0, 115.0, 130.0),
            explicit_numbers=("1234", None, "5678"),
        )

    def test_groups_only_within_exact_page_column(self):
        resolved = [
            {"column": 0, "station": "品川", "event": "departure", "time": "1200", "x": 100.0, "y": 200.0, "resolution": "same-row-station-title"},
            {"column": 0, "station": "京急蒲田", "event": "arrival", "time": "1210", "x": 100.0, "y": 220.0, "resolution": "same-row-station-title"},
            {"column": 1, "station": "品川", "event": "departure", "time": "1201", "x": 115.0, "y": 200.0, "resolution": "same-row-station-title"},
        ]
        fragments = build_page_fragments(7, self.grid(), resolved, [])
        self.assertEqual(len(fragments), 3)
        self.assertEqual([item["time"] for item in fragments[0]["stopTimes"]], ["1200", "1210"])
        self.assertEqual([item["time"] for item in fragments[1]["stopTimes"]], ["1201"])
        self.assertEqual(fragments[2]["stopTimes"], [])

    def test_anonymous_column_is_preserved_not_discarded(self):
        fragments = build_page_fragments(7, self.grid(), [], [])
        self.assertTrue(fragments[1]["anonymousColumn"])
        self.assertIsNone(fragments[1]["printedTrainNumber"])
        self.assertEqual(fragments[1]["id"], "keikyu-official-pdf:p007:c01")

    def test_same_printed_number_on_different_pages_is_not_same_fragment(self):
        page7 = build_page_fragments(7, self.grid(), [], [])
        page8 = build_page_fragments(8, self.grid(), [], [])
        self.assertEqual(page7[0]["printedTrainNumber"], page8[0]["printedTrainNumber"])
        self.assertNotEqual(page7[0]["id"], page8[0]["id"])
        self.assertEqual(page7[0]["id"], fragment_id(7, 0))
        self.assertEqual(page8[0]["id"], fragment_id(8, 0))

    def test_unresolved_cells_remain_explicit(self):
        unresolved = [
            {"column": 2, "time": "2359", "x": 130.0, "y": 500.0, "left": "", "marker": None, "stationMatches": []}
        ]
        fragments = build_page_fragments(7, self.grid(), [], unresolved)
        self.assertEqual(fragments[2]["unresolvedCells"][0]["time"], "2359")
        self.assertEqual(fragments[2]["stopTimes"], [])

    def test_output_order_follows_printed_vertical_rows_not_clock_guessing(self):
        resolved = [
            {"column": 0, "station": "品川", "event": "departure", "time": "0010", "x": 100.0, "y": 300.0, "resolution": "same-row-station-title"},
            {"column": 0, "station": "京急蒲田", "event": "arrival", "time": "2359", "x": 100.0, "y": 200.0, "resolution": "same-row-station-title"},
        ]
        fragments = build_page_fragments(7, self.grid(), resolved, [])
        self.assertEqual([item["time"] for item in fragments[0]["stopTimes"]], ["2359", "0010"])

    def test_unknown_column_fails_closed(self):
        resolved = [
            {"column": 99, "station": "品川", "event": "departure", "time": "1200", "x": 999.0, "y": 200.0, "resolution": "same-row-station-title"}
        ]
        with self.assertRaises(RuntimeError):
            build_page_fragments(7, self.grid(), resolved, [])


if __name__ == "__main__":
    unittest.main()
