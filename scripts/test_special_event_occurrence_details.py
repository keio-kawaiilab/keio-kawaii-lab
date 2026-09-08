#!/usr/bin/env python3
from __future__ import annotations

import unittest

from special_event_occurrence_details import (
    AUDIT_ID,
    apply_known_occurrence_corrections,
    expand_occurrence_views,
)


class SpecialEventOccurrenceDetailsTest(unittest.TestCase):
    def fixture(self):
        return {
            "updatedAt": "2026-09-08T09:55:57+09:00",
            "events": [
                {
                    "id": "special-test",
                    "group": "SWEET STEADY",
                    "title": "3rdシングル『SWEET STEP』発売記念リリースイベント",
                    "displayTitle": "3rdシングル『SWEET STEP』発売記念リリースイベント",
                    "eventCategory": "release-event",
                    "eventDate": "2026-09-05",
                    "venue": "複数会場（全3公演）",
                    "salesStartTime": "12:00",
                    "gatheringTime": "16:00",
                    "startTime": "14:00",
                    "purchaseMethod": "mixed-parent-value",
                    "numberedCallTimes": [
                        {"numbers": "1〜200番", "time": "10:00"},
                        {"numbers": "1〜200番", "time": "11:50"},
                    ],
                    "url": "https://sweetsteady.asobisystem.com/news/detail/89031",
                    "schedule": [
                        {
                            "date": "2026-09-05",
                            "venue": "埼玉県 エミテラス所沢2F TOKOROZAWA e-CUBE",
                            "startTime": "14:00",
                        },
                        {
                            "date": "2026-09-07",
                            "venue": "東京都 池袋・サンシャインシティ 噴水広場",
                            "startTime": "16:30",
                        },
                        {
                            "date": "2026-09-14",
                            "venue": "北海道 サッポロファクトリー アトリウム",
                        },
                    ],
                    "eventDates": ["2026-09-05", "2026-09-07", "2026-09-14"],
                    "eventCount": 3,
                    "offers": [],
                }
            ],
        }

    def test_correction_moves_date_specific_data_off_parent(self):
        corrected, report = apply_known_occurrence_corrections(self.fixture())
        self.assertEqual(report["matched"], 1)
        self.assertEqual(report["changed"], 1)
        event = corrected["events"][0]

        for field in (
            "salesStartTime",
            "gatheringTime",
            "startTime",
            "purchaseMethod",
            "numberedCallTimes",
        ):
            self.assertNotIn(field, event)

        self.assertTrue(event["displayByOccurrence"])
        self.assertIn(AUDIT_ID, event["auditCorrectionIds"])

        sep5 = event["occurrenceDetails"]["2026-09-05"]
        self.assertEqual(sep5["salesStartTime"], "10:10")
        self.assertEqual(sep5["gatheringTime"], "13:20")
        self.assertEqual(sep5["startTime"], "14:00")
        self.assertEqual(sep5["numberedCallTimes"][-1], {"numbers": "1,001番〜", "time": "11:40"})

        sep7 = event["occurrenceDetails"]["2026-09-07"]
        self.assertEqual(sep7["salesStartTime"], "12:00")
        self.assertEqual(sep7["gatheringTime"], "16:00")
        self.assertEqual(sep7["startTime"], "16:30")
        self.assertEqual(sep7["numberedCallTimes"][-1], {"numbers": "1,001番〜", "time": "13:30"})

        sep14 = event["occurrenceDetails"]["2026-09-14"]
        self.assertEqual(sep14["specialDetailsStatus"], "awaiting-details")
        self.assertNotIn("startTime", sep14)
        self.assertNotIn("salesStartTime", sep14)
        self.assertNotIn("gatheringTime", sep14)

    def test_display_expansion_never_leaks_details_across_dates(self):
        corrected, _ = apply_known_occurrence_corrections(self.fixture())
        views = expand_occurrence_views(corrected["events"])
        self.assertEqual(len(views), 3)
        by_date = {event["eventDate"]: event for event in views}

        sep5 = by_date["2026-09-05"]
        self.assertEqual(sep5["salesStartTime"], "10:10")
        self.assertEqual(sep5["gatheringTime"], "13:20")
        self.assertEqual(sep5["startTime"], "14:00")
        self.assertEqual(sep5["url"], "https://sweetsteady.asobisystem.com/news/detail/88315")
        self.assertEqual(sep5["eventDates"], ["2026-09-05"])
        self.assertEqual(len(sep5["schedule"]), 1)

        sep7 = by_date["2026-09-07"]
        self.assertEqual(sep7["salesStartTime"], "12:00")
        self.assertEqual(sep7["gatheringTime"], "16:00")
        self.assertEqual(sep7["startTime"], "16:30")
        self.assertNotEqual(sep7["numberedCallTimes"][0]["time"], "10:00")

        sep14 = by_date["2026-09-14"]
        self.assertEqual(sep14["specialDetailsStatus"], "awaiting-details")
        self.assertNotIn("salesStartTime", sep14)
        self.assertNotIn("gatheringTime", sep14)
        self.assertNotIn("startTime", sep14)
        self.assertNotIn("purchaseMethod", sep14)
        self.assertNotIn("numberedCallTimes", sep14)

    def test_correction_is_idempotent(self):
        once, _ = apply_known_occurrence_corrections(self.fixture())
        twice, report = apply_known_occurrence_corrections(once)
        self.assertEqual(once, twice)
        self.assertEqual(report["matched"], 1)
        self.assertEqual(report["changed"], 0)


if __name__ == "__main__":
    unittest.main()
