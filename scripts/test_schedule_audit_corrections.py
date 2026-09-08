#!/usr/bin/env python3
from __future__ import annotations

import unittest

from schedule_audit_corrections import (
    CHRISTMAS_DAY1_AUDIT_ID,
    apply_christmas_day1_venue_correction,
)
from test_ohanami_two_show_correction import OhanamiTwoShowCorrectionTest  # noqa: F401


class ScheduleAuditCorrectionsTest(unittest.TestCase):
    def fixture(self):
        return {
            "events": [
                {
                    "id": "day1-official",
                    "group": "KAWAII LAB.合同",
                    "title": "KAWAII LAB. Christmas SESSION 2026 Day1 @ 有明アリーナ",
                    "eventTitle": "KAWAII LAB. Christmas SESSION 2026 Day1 @ 有明アリーナ",
                    "eventDate": "2026-12-12",
                    "venue": "有明アリーナ",
                    "openTime": "15:00",
                    "startTime": "17:00",
                    "sourceType": "official-schedule",
                    "url": "https://kawaiilab.asobisystem.com/live_information/detail/44571",
                    "officialScheduleUrl": "https://kawaiilab.asobisystem.com/live_information/detail/44571",
                },
                {
                    "id": "candy-upgrade",
                    "group": "CANDY TUNE",
                    "title": "2026.08.22 「KAWAII LAB. Christmas SESSION 2026」@有明アリーナ アップグレード抽選受付のお知らせ",
                    "eventTitle": "KAWAII LAB. Christmas SESSION 2026",
                    "eventDate": "2026-12-12",
                    "venue": None,
                    "openTime": "15:00",
                    "startTime": "17:00",
                },
                {
                    "id": "multi-day",
                    "group": "MORE STAR",
                    "title": "KAWAII LAB. Christmas SESSION 2026",
                    "eventTitle": "KAWAII LAB. Christmas SESSION 2026",
                    "eventDate": "2026-12-12",
                    "venue": "有明アリーナ",
                    "openTime": "15:00",
                    "startTime": "17:00",
                    "schedule": [
                        {
                            "date": "2026-12-12",
                            "venue": None,
                            "openTime": "15:00",
                            "startTime": "17:00",
                        },
                        {
                            "date": "2026-12-13",
                            "venue": "有明アリーナ",
                            "openTime": "14:00",
                            "startTime": "16:00",
                        },
                    ],
                },
                {
                    "id": "unrelated",
                    "group": "MORE STAR",
                    "title": "Different Christmas Event",
                    "eventDate": "2026-12-12",
                    "venue": None,
                    "openTime": "15:00",
                    "startTime": "17:00",
                },
            ]
        }

    def test_fills_missing_day1_venue_from_official_schedule(self):
        corrected, report = apply_christmas_day1_venue_correction(self.fixture())
        by_id = {event["id"]: event for event in corrected["events"]}

        self.assertEqual(report["authoritativeVenue"], "有明アリーナ")
        self.assertEqual(report["topLevelFilled"], 1)
        self.assertEqual(report["scheduleRowsFilled"], 1)
        self.assertEqual(report["conflicts"], [])
        self.assertEqual(by_id["candy-upgrade"]["venue"], "有明アリーナ")
        self.assertIn(CHRISTMAS_DAY1_AUDIT_ID, by_id["candy-upgrade"]["auditCorrectionIds"])
        self.assertEqual(by_id["multi-day"]["schedule"][0]["venue"], "有明アリーナ")
        self.assertEqual(by_id["multi-day"]["schedule"][1]["venue"], "有明アリーナ")
        self.assertIsNone(by_id["unrelated"]["venue"])

    def test_never_overwrites_conflicting_nonempty_venue(self):
        payload = self.fixture()
        payload["events"][1]["venue"] = "別会場"
        corrected, report = apply_christmas_day1_venue_correction(payload)
        by_id = {event["id"]: event for event in corrected["events"]}
        self.assertEqual(by_id["candy-upgrade"]["venue"], "別会場")
        self.assertEqual(len(report["conflicts"]), 1)

    def test_wrong_time_is_not_reconciled(self):
        payload = self.fixture()
        payload["events"][1]["startTime"] = "19:00"
        corrected, report = apply_christmas_day1_venue_correction(payload)
        by_id = {event["id"]: event for event in corrected["events"]}
        self.assertIsNone(by_id["candy-upgrade"]["venue"])
        self.assertEqual(report["topLevelFilled"], 0)

    def test_is_idempotent(self):
        once, _ = apply_christmas_day1_venue_correction(self.fixture())
        twice, report = apply_christmas_day1_venue_correction(once)
        self.assertEqual(once, twice)
        self.assertEqual(report["topLevelFilled"], 0)
        self.assertEqual(report["scheduleRowsFilled"], 0)


if __name__ == "__main__":
    unittest.main()
