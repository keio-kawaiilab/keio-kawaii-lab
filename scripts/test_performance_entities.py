#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

from performance_entities import build_public_events


class PerformanceEntitiesTest(unittest.TestCase):
    def fixture(self):
        return [
            {
                "id": "tour-master",
                "group": "CANDY TUNE",
                "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                "eventTitle": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                "ticketType": "現在受付なし",
                "applicationStatus": "none",
                "eventDate": "2026-10-08",
                "eventEndDate": "2026-10-09",
                "eventDates": ["2026-10-08", "2026-10-09"],
                "eventCount": 2,
                "venue": "複数会場（全2公演）",
                "url": "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026",
                "urls": ["https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026"],
                "officialTourUrl": "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026",
                "sourceType": "derived",
                "primarySource": "official",
                "eventScope": "kawaii-lab",
                "schedule": [
                    {
                        "date": "2026-10-08",
                        "venue": "宮城県 仙台サンプラザホール",
                        "openTime": "17:30",
                        "startTime": "18:30",
                    },
                    {
                        "date": "2026-10-09",
                        "venue": "栃木県 宇都宮市文化会館 大ホール",
                        "openTime": "17:30",
                        "startTime": "18:30",
                    },
                ],
            },
            {
                "id": "fc-sendai",
                "group": "CANDY TUNE",
                "title": "2026.07.05 CANDY TUNE JAPAN TOUR 2026 - AUTUMN - 開催決定！FC先行開始！",
                "eventTitle": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                "ticketType": "FC先行",
                "applyStart": "2026-07-05T18:00",
                "applyEnd": "2026-07-13T23:59",
                "eventDate": "2026-10-08",
                "venue": "宮城県 仙台サンプラザホール",
                "openTime": "17:30",
                "startTime": "18:30",
                "url": "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026",
                "sourceType": "auto",
                "primarySource": "official",
                "eventScope": "kawaii-lab",
            },
            {
                "id": "eplus-sendai",
                "group": "CANDY TUNE",
                "title": "CANDY TUNE",
                "eventTitle": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                "ticketType": "先着 ★一般発売",
                "ticketProvider": "eplus",
                "applyStart": "2026-09-05T10:00",
                "applyEnd": "2026-10-05T18:00",
                "eventDate": "2026-10-08",
                "venue": "仙台サンプラザホール",
                "openTime": "17:30",
                "startTime": "18:30",
                "url": "https://eplus.jp/sendai",
                "sourceType": "eplus",
                "primarySource": "eplus",
                "eventScope": "kawaii-lab",
            },
            {
                "id": "lawson-multi",
                "group": "CANDY TUNE",
                "title": "CANDY TUNE",
                "eventTitle": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                "ticketType": "現在受付なし",
                "ticketProvider": "lawson",
                "eventDate": "2026-10-08",
                "eventDates": ["2026-10-08", "2026-10-09"],
                "schedule": [
                    {"date": "2026-10-08", "venue": "仙台サンプラザホール"},
                    {"date": "2026-10-09", "venue": "宇都宮市文化会館 大ホール"},
                ],
                "url": "https://l-tike.com/order/example",
                "sourceType": "derived",
                "primarySource": "lawson",
                "eventScope": "kawaii-lab",
            },
            {
                "id": "other-show",
                "group": "CANDY TUNE",
                "title": "別の単独公演",
                "eventTitle": "別の単独公演",
                "ticketType": "現在受付なし",
                "eventDate": "2026-10-08",
                "venue": "別会場",
                "startTime": "20:00",
                "url": "https://candytune.asobisystem.com/live_information/detail/example",
                "sourceType": "official-schedule",
                "primarySource": "official",
                "eventScope": "kawaii-lab",
            },
            {
                "id": "external",
                "group": "CANDY TUNE",
                "title": "外部フェス",
                "eventDate": "2026-10-08",
                "venue": "外部会場",
                "startTime": "18:30",
                "ticketType": "現在受付なし",
                "eventScope": "external",
            },
        ]

    def test_one_physical_performance_contains_multiple_ticket_offers(self):
        public, report = build_public_events(self.fixture())
        sendai = [
            event for event in public
            if event.get("entityType") == "performance"
            and event.get("group") == "CANDY TUNE"
            and event.get("eventDate") == "2026-10-08"
            and event.get("startTime") == "18:30"
        ]
        self.assertEqual(len(sendai), 1)
        event = sendai[0]
        self.assertEqual(event["venue"], "宮城県 仙台サンプラザホール")
        self.assertEqual(event["openTime"], "17:30")
        self.assertEqual(event["ticketType"], "複数受付")
        self.assertEqual({offer["ticketType"] for offer in event["offers"]}, {"FC先行", "先着 ★一般発売"})
        self.assertEqual({offer["provider"] for offer in event["offers"]}, {"official", "eplus"})
        self.assertTrue({"tour-master", "fc-sendai", "eplus-sendai", "lawson-multi"}.issubset(set(event["sourceRowIds"])))
        self.assertGreaterEqual(report["mergedSourceOccurrences"], 3)

    def test_multiday_schedule_source_is_split_into_physical_performances(self):
        public, _ = build_public_events(self.fixture())
        tour = [
            event for event in public
            if event.get("entityType") == "performance"
            and event.get("group") == "CANDY TUNE"
            and "JAPAN TOUR 2026" in str(event.get("eventTitle") or event.get("title") or "")
        ]
        self.assertEqual({event["eventDate"] for event in tour}, {"2026-10-08", "2026-10-09"})
        self.assertTrue(all(event.get("eventCount") == 1 for event in tour))
        self.assertTrue(all(len(event.get("schedule") or []) == 1 for event in tour))

    def test_different_start_time_remains_a_different_performance(self):
        public, _ = build_public_events(self.fixture())
        hosted = [
            event for event in public
            if event.get("entityType") == "performance"
            and event.get("group") == "CANDY TUNE"
            and event.get("eventDate") == "2026-10-08"
        ]
        self.assertEqual({event.get("startTime") for event in hosted}, {"18:30", "20:00"})

    def test_external_rows_are_not_rewritten(self):
        public, _ = build_public_events(self.fixture())
        external = [event for event in public if event.get("id") == "external"]
        self.assertEqual(len(external), 1)
        self.assertNotEqual(external[0].get("entityType"), "performance")

    def test_current_repository_sendai_tour_is_one_public_performance(self):
        path = Path(__file__).resolve().parents[1] / "data" / "live-events.json"
        if not path.exists():
            self.skipTest("repository data file is unavailable")
        payload = json.loads(path.read_text(encoding="utf-8"))
        public, _ = build_public_events(payload.get("events") or [])
        sendai = [
            event for event in public
            if event.get("entityType") == "performance"
            and event.get("group") == "CANDY TUNE"
            and event.get("eventDate") == "2026-10-08"
            and event.get("startTime") == "18:30"
        ]
        self.assertEqual(len(sendai), 1)
        event = sendai[0]
        self.assertIn("仙台サンプラザホール", str(event.get("venue") or ""))
        ticket_types = {str(offer.get("ticketType") or "") for offer in event.get("offers") or []}
        self.assertIn("FC先行", ticket_types)
        self.assertTrue(any("一般発売" in ticket_type for ticket_type in ticket_types))
        self.assertEqual(len([row for row in public if row.get("id") == "1d39bd5dbf1e137a"]), 0)


if __name__ == "__main__":
    unittest.main()
