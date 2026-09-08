#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ohanami_two_show_correction import (
    AUDIT_ID,
    VENUE,
    apply_ohanami_two_show_correction,
)


class OhanamiTwoShowCorrectionTest(unittest.TestCase):
    def fixture(self):
        return {
            "events": [
                {
                    "id": "ohanami-physical",
                    "group": "SWEET STEADY",
                    "title": "SWEET STEADY 単独公演 お花見会",
                    "eventTitle": "SWEET STEADY 単独公演 お花見会",
                    "ticketType": "現在受付なし",
                    "eventDate": "2026-09-21",
                    "venue": "東京都 Zepp Shinjuku(TOKYO)",
                    "openTime": "13:00",
                    "startTime": "14:00",
                    "url": "https://sweetsteady.asobisystem.com/news/detail/88352",
                    "urls": [
                        "https://sweetsteady.asobisystem.com/news/detail/88352",
                        "https://sweetsteady.asobisystem.com/live_information/detail/44458",
                    ],
                    "sourceType": "derived",
                    "primarySource": "official",
                    "officialScheduleUrl": "https://sweetsteady.asobisystem.com/live_information/detail/44458",
                },
                {
                    "id": "ohanami-fc",
                    "group": "SWEET STEADY",
                    "title": "2026.08.27 9月21日(月・祝)「SWEET STEADY 単独公演 お花見会」＠Zepp Shinjuku (TOKYO)開催決定！FC先行受付開始！",
                    "eventTitle": "SWEET STEADY 単独公演 お花見会",
                    "ticketType": "FC先行",
                    "applyStart": "2026-08-27T18:00",
                    "applyEnd": "2026-09-01T23:59",
                    "eventDate": "2026-09-21",
                    "venue": None,
                    "openTime": "13:00",
                    "startTime": "14:00",
                    "url": "https://sweetsteady.asobisystem.com/news/detail/88352",
                    "urls": [
                        "https://sweetsteady.asobisystem.com/news/detail/88352",
                    ],
                    "sourceType": "auto",
                    "primarySource": "official",
                },
                {
                    "id": "unrelated",
                    "group": "SWEET STEADY",
                    "title": "別イベント",
                    "eventDate": "2026-09-21",
                    "venue": "別会場",
                    "startTime": "18:00",
                },
            ]
        }

    def _ohanami(self, payload):
        return [
            event
            for event in payload["events"]
            if event.get("group") == "SWEET STEADY"
            and "SWEET STEADY 単独公演 お花見会" in str(event.get("eventTitle") or event.get("title") or "")
            and str(event.get("eventDate") or "")[:10] == "2026-09-21"
        ]

    def test_folds_duplicate_sources_into_exactly_two_physical_shows(self):
        corrected, report = apply_ohanami_two_show_correction(self.fixture())
        shows = sorted(self._ohanami(corrected), key=lambda event: event["startTime"])

        self.assertEqual(report["matchedEvents"], 2)
        self.assertTrue(report["secondShowCreated"])
        self.assertEqual(report["canonicalRows"], 2)
        self.assertEqual(report["conflicts"], [])
        self.assertEqual(len(shows), 2)
        self.assertEqual(
            [(show["openTime"], show["startTime"]) for show in shows],
            [("13:00", "14:00"), ("16:30", "17:30")],
        )
        self.assertTrue(all(show["venue"] == VENUE for show in shows))
        self.assertTrue(all(AUDIT_ID in show["auditCorrectionIds"] for show in shows))
        self.assertTrue(all(show["ticketType"] == "FC先行" for show in shows))
        self.assertTrue(all(show["applyStart"] == "2026-08-27T18:00" for show in shows))
        self.assertTrue(all(show["applyEnd"] == "2026-09-01T23:59" for show in shows))
        self.assertTrue(all(len(show["auditMergedTicketOffers"]) == 1 for show in shows))
        self.assertEqual(shows[1]["auditCloneOf"], shows[0]["id"])
        self.assertEqual(len([event for event in corrected["events"] if event.get("id") == "unrelated"]), 1)

    def test_never_overwrites_conflicting_nonempty_venue(self):
        payload = self.fixture()
        payload["events"][1]["venue"] = "別会場"
        corrected, report = apply_ohanami_two_show_correction(payload)

        self.assertEqual(corrected, payload)
        self.assertEqual(len(report["conflicts"]), 1)
        self.assertEqual(report["conflicts"][0]["field"], "venue")

    def test_native_second_show_is_reused(self):
        payload = self.fixture()
        payload["events"].append(
            {
                "id": "ohanami-second-native",
                "group": "SWEET STEADY",
                "title": "SWEET STEADY 単独公演 お花見会 第二回",
                "eventTitle": "SWEET STEADY 単独公演 お花見会",
                "ticketType": "現在受付なし",
                "eventDate": "2026-09-21",
                "venue": VENUE,
                "openTime": "16:30",
                "startTime": "17:30",
            }
        )

        corrected, report = apply_ohanami_two_show_correction(payload)
        shows = self._ohanami(corrected)
        self.assertEqual(len(shows), 2)
        self.assertFalse(report["secondShowCreated"])
        self.assertEqual({show["startTime"] for show in shows}, {"14:00", "17:30"})

    def test_is_idempotent(self):
        once, _ = apply_ohanami_two_show_correction(self.fixture())
        twice, report = apply_ohanami_two_show_correction(once)
        self.assertEqual(once, twice)
        self.assertEqual(report["canonicalRows"], 2)
        self.assertFalse(report["secondShowCreated"])
        self.assertEqual(report["conflicts"], [])

    def test_current_repository_data_corrects_to_two_verified_shows(self):
        path = Path(__file__).resolve().parents[1] / "data" / "live-events.json"
        if not path.exists():
            self.skipTest("repository data file is unavailable")

        payload = json.loads(path.read_text(encoding="utf-8"))
        corrected, report = apply_ohanami_two_show_correction(payload)
        self.assertEqual(report["conflicts"], [])
        shows = sorted(self._ohanami(corrected), key=lambda event: event["startTime"])
        self.assertEqual(len(shows), 2)
        self.assertEqual(
            [(show["openTime"], show["startTime"]) for show in shows],
            [("13:00", "14:00"), ("16:30", "17:30")],
        )
        self.assertTrue(all(show["venue"] == VENUE for show in shows))


if __name__ == "__main__":
    unittest.main()
