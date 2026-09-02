#!/usr/bin/env python3
from __future__ import annotations

import unittest

from augment_recent_official_news import merge_discovered_ticket_event
from augment_kawaiilab_official import infer_target_groups


class RecentOfficialBodyMergeTests(unittest.TestCase):
    def test_existing_rich_metadata_is_not_downgraded(self):
        existing = {
            "id": "same-id",
            "group": "SWEET STEADY",
            "eventTitle": "Example Live",
            "url": "https://example.com/live/detail/1",
            "urls": ["https://example.com/live/detail/1"],
            "source": "official-schedule",
            "sourceChannel": "direct",
            "officialScheduleUrl": "https://example.com/live/detail/1",
            "eventScope": "hosted",
            "eventStart": "18:30",
            "performanceTime": "18:30",
            "performanceTimeSourceUrl": "https://example.com/live/detail/1",
            "doorsOpen": "17:30",
            "doorsOpenSourceUrl": "https://example.com/live/detail/1",
            "ticketType": "FC先行",
            "applyEnd": "2026-09-01T23:59",
            "schedule": [{"date": "2026-12-07", "venue": "Zepp Example", "start": "18:30"}],
        }
        incoming = {
            "id": "same-id",
            "group": "SWEET STEADY",
            "eventTitle": "Example Live",
            "url": "https://example.com/news/detail/99",
            "source": "official-news",
            "sourceChannel": "recent-official-body",
            "ticketType": "一般先着受付",
            "applyEnd": "2026-12-06T23:59",
            "schedule": [{"date": "2026-12-07", "venue": "Zepp Example"}],
            "discoverySourceUrl": "https://example.com/news/detail/99",
        }

        merged = merge_discovered_ticket_event(existing, incoming)

        self.assertEqual(merged["ticketType"], "一般先着受付")
        self.assertEqual(merged["applyEnd"], "2026-12-06T23:59")
        self.assertEqual(merged["url"], existing["url"])
        self.assertEqual(merged["source"], "official-schedule")
        self.assertEqual(merged["sourceChannel"], "direct")
        self.assertEqual(merged["officialScheduleUrl"], existing["officialScheduleUrl"])
        self.assertEqual(merged["eventStart"], "18:30")
        self.assertEqual(merged["performanceTime"], "18:30")
        self.assertEqual(merged["doorsOpen"], "17:30")
        self.assertEqual(merged["eventScope"], "hosted")
        self.assertIn("https://example.com/live/detail/1", merged["urls"])
        self.assertIn("https://example.com/news/detail/99", merged["urls"])
        self.assertEqual(merged["schedule"][0]["start"], "18:30")

    def test_missing_rich_metadata_can_be_filled(self):
        existing = {"id": "same-id", "eventTitle": "Example Live", "url": "https://example.com/news/old"}
        incoming = {
            "id": "same-id",
            "eventTitle": "Example Live",
            "eventScope": "hosted",
            "eventStart": "19:00",
            "discoverySourceUrl": "https://example.com/news/new",
        }
        merged = merge_discovered_ticket_event(existing, incoming)
        self.assertEqual(merged["eventScope"], "hosted")
        self.assertEqual(merged["eventStart"], "19:00")
        self.assertEqual(merged["url"], "https://example.com/news/old")
        self.assertIn("https://example.com/news/new", merged["urls"])


class KawaiiLabUmbrellaDiscoveryTests(unittest.TestCase):
    def test_infers_single_group_from_umbrella_article(self):
        groups = infer_target_groups("CUTIE STREET JAPAN ARENA TOUR 2026 FC先行開始")
        self.assertEqual(groups, ["CUTIE STREET"])

    def test_infers_multiple_explicit_groups(self):
        groups = infer_target_groups("FRUITS ZIPPERとCANDY TUNEが出演します")
        self.assertEqual(groups, ["FRUITS ZIPPER", "CANDY TUNE"])

    def test_infers_mates_and_south(self):
        groups = infer_target_groups("KAWAII LAB. MATES × KAWAII LAB. SOUTH 合同公演")
        self.assertEqual(groups, ["KAWAII LAB. MATES", "KAWAII LAB. SOUTH"])

    def test_does_not_invent_group_for_generic_umbrella_text(self):
        self.assertEqual(infer_target_groups("KAWAII LAB.からのお知らせ"), [])


if __name__ == "__main__":
    unittest.main()
