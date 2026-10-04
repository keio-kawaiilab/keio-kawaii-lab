#!/usr/bin/env python3
from __future__ import annotations

import unittest

import audit_venue_coverage as audit


def venue(venue_id: str, name: str, aliases=None):
    return {
        "id": venue_id,
        "name": name,
        "aliases": aliases or [],
        "prefecture": "東京都",
        "area": "テスト",
        "type": "ホール",
        "address": "東京都テスト1-1",
        "access": ["テスト駅から徒歩1分"],
        "capacityNote": "100席",
        "officialUrl": "https://example.com/",
        "mapUrl": "https://maps.google.com/",
    }


class VenueCoverageTests(unittest.TestCase):
    def test_alias_matches_exact_normalized_schedule_label(self):
        venues = {"venues": [venue("a", "東京ガーデンシアター", ["東京・東京ガーデンシアター"])]}
        events = {"events": [{"eventDate": "2026-12-09", "venue": "東京・東京ガーデンシアター"}]}
        report = audit.audit(venues, events, "2026-10-04")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["unmatchedVenues"], [])

    def test_multi_venue_locations_are_checked_independently(self):
        venues = {"venues": [
            venue("a", "SGC HALL ARIAKE", ["東京都 SGC HALL ARIAKE"]),
            venue("b", "TOYOTA ARENA TOKYO", ["東京都 TOYOTA ARENA TOKYO"]),
        ]}
        events = {"events": [{
            "eventDate": "2026-11-28",
            "venue": "複数会場（SGCホール有明・TOYOTA ARENA TOKYO）",
            "venueLocations": ["東京都 SGC HALL ARIAKE", "東京都 TOYOTA ARENA TOKYO"],
        }]}
        report = audit.audit(venues, events, "2026-10-04")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["checkedFuturePhysicalOccurrences"], 2)

    def test_opaque_multi_venue_label_is_flagged(self):
        venues = {"venues": [venue("a", "SGC HALL ARIAKE")]}
        events = {"events": [{"eventDate": "2026-11-28", "venue": "複数会場（2会場）"}]}
        report = audit.audit(venues, events, "2026-10-04")
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(len(report["opaqueMultiVenueRows"]), 1)

    def test_unknown_future_venue_is_flagged_but_online_is_not(self):
        venues = {"venues": [venue("a", "既知会場")]}
        events = {"events": [
            {"eventDate": "2026-11-01", "venue": "東京都 未登録ホール"},
            {"eventDate": "2026-11-02", "venue": "MORE STAR YouTube オンライン"},
        ]}
        report = audit.audit(venues, events, "2026-10-04")
        self.assertEqual(len(report["unmatchedVenues"]), 1)
        self.assertEqual(report["unmatchedVenues"][0]["venue"], "東京都 未登録ホール")

    def test_prefecture_only_is_flagged(self):
        venues = {"venues": [venue("a", "既知会場")]}
        events = {"events": [{"eventDate": "2026-11-29", "venue": "東京都"}]}
        report = audit.audit(venues, events, "2026-10-04")
        self.assertEqual(len(report["prefectureOnlyVenueRows"]), 1)


if __name__ == "__main__":
    unittest.main()
