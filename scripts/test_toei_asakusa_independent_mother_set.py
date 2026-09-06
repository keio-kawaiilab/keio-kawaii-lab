#!/usr/bin/env python3
from __future__ import annotations

import unittest

from audit_toei_asakusa_independent_mother_set import ASAKUSA, OSHIAGE, SENGAKUJI, build_audit
from verify_toei_asakusa_independent_mother_set import verify


class ToeiAsakusaIndependentMotherSetTest(unittest.TestCase):
    def fixture(self):
        index = {
            "lines": {
                ASAKUSA: {"trips": 2, "connections": 2}
            }
        }
        timetable = {
            "railway": ASAKUSA,
            "timeBasis": "train-timetable",
            "stations": [SENGAKUJI, "odpt.Station:Toei.Asakusa.Shimbashi", OSHIAGE],
            "calendars": ["odpt.Calendar:Weekday", "odpt.Calendar:SaturdayHoliday"],
            "trainTypes": ["odpt.TrainType:Toei.Local"],
            "tripSchema": [
                "calendarIndex", "trainTypeIndex", "trainNumber", "stops",
                "destination", "trainId", "timetableId",
            ],
            "trips": [
                [0, 0, "100H", [[0, None, 600], [1, 605, None]], "odpt.Station:Keikyu.Main.Shinagawa", "train:100H", "tt:100H:w"],
                [1, 0, "200K", [[2, None, 700], [1, 705, None]], "odpt.Station:Toei.Asakusa.Shimbashi", "train:200K", "tt:200K:h"],
            ],
        }
        return index, timetable

    def test_valid_independent_mother_set_verifies(self):
        index, timetable = self.fixture()
        payload = build_audit(index, timetable)
        result = verify(payload)
        self.assertTrue(result["verified"])
        self.assertEqual(payload["actualTripCount"], 2)
        self.assertEqual(payload["externalDestinationTrips"], 1)
        self.assertEqual(payload["identityPolicy"]["runtimeSameTrainPromotions"], 0)

    def test_duplicate_timetable_id_fails_closed(self):
        index, timetable = self.fixture()
        timetable["trips"][1][6] = timetable["trips"][0][6]
        payload = build_audit(index, timetable)
        self.assertTrue(any(row["kind"] == "duplicate-timetable-id" for row in payload["issues"]))
        with self.assertRaises(RuntimeError):
            verify(payload)

    def test_non_monotonic_station_order_fails_closed(self):
        index, timetable = self.fixture()
        index["lines"][ASAKUSA]["connections"] = 3
        timetable["trips"][0][3] = [[0, None, 600], [2, 605, 606], [1, 607, None]]
        payload = build_audit(index, timetable)
        self.assertTrue(any(row["kind"] == "non-monotonic-station-order" for row in payload["issues"]))
        with self.assertRaises(RuntimeError):
            verify(payload)

    def test_time_regression_fails_closed(self):
        index, timetable = self.fixture()
        timetable["trips"][0][3] = [[0, None, 610], [1, 605, None]]
        payload = build_audit(index, timetable)
        self.assertTrue(any(row["kind"] == "non-monotonic-times" for row in payload["issues"]))
        with self.assertRaises(RuntimeError):
            verify(payload)


if __name__ == "__main__":
    unittest.main()
