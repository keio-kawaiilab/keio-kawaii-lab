import unittest

import merge_distributed_schedule_snapshots as merger


class DistributedSnapshotMergerTests(unittest.TestCase):
    def test_each_source_replaces_only_its_owned_rows(self):
        core = {"events": [
            {"id": "official", "sourceType": "auto", "group": "A", "eventDate": "2026-09-01"},
            {"id": "old-eplus", "sourceType": "eplus", "ticketProvider": "eplus", "group": "A", "eventDate": "2026-09-02"},
            {"id": "old-suki", "sourceType": "sukisuki", "group": "A", "eventDate": "2026-09-03", "url": "https://sukisuki-shop.com/goods/1"},
            {"id": "old-special", "sourceType": "official-special", "group": "A", "eventDate": "2026-09-04", "title": "発売記念リリースイベント"},
        ]}
        playguide = {"events": [
            {"id": "new-eplus", "sourceType": "eplus", "ticketProvider": "eplus", "group": "A", "eventDate": "2026-09-02"},
        ]}
        suki = {"events": [
            {"id": "new-suki", "sourceType": "sukisuki", "group": "A", "eventDate": "2026-09-03", "url": "https://sukisuki-shop.com/goods/2"},
        ]}
        special = {"events": [
            {"id": "new-special", "sourceType": "official-special", "group": "A", "eventDate": "2026-09-04", "title": "発売記念リリースイベント"},
        ]}
        result = merger.merge_payloads(core, playguide, suki, special)
        ids = {row["id"] for row in result["events"]}
        self.assertEqual({"official", "new-eplus", "new-suki", "new-special"}, ids)

    def test_physical_special_event_with_sukisuki_link_is_not_owned_by_sukisuki(self):
        event = {
            "id": "release",
            "sourceType": "official-special",
            "eventCategory": "release-event",
            "title": "シングル発売記念リリースイベント",
            "url": "https://example.com/event",
            "urls": ["https://sukisuki-shop.com/goods/999"],
        }
        self.assertTrue(merger.is_special_event(event))
        self.assertFalse(merger.is_sukisuki_event(event))

    def test_official_schedule_placeholder_for_special_is_special_owned(self):
        event = {
            "id": "placeholder",
            "sourceType": "official-schedule",
            "title": "CANDY TUNE 大特典会",
            "eventDate": "2026-10-10",
        }
        self.assertTrue(merger.is_special_event(event))

    def test_playguide_diagnostics_are_taken_from_playguide_snapshot(self):
        result = merger.merge_payloads(
            {"events": []},
            {"events": [], "playguideDiagnostics": {"collectorMode": "parallel"}, "playguideFailures": []},
            {"events": []},
            {"events": []},
        )
        self.assertEqual("parallel", result["playguideDiagnostics"]["collectorMode"])

    def test_replacement_keeps_core_official_schedule_link_for_same_id(self):
        official_url = "https://sweetsteady.asobisystem.com/live_information/detail/12345"
        core = {"events": [{
            "id": "same-event",
            "sourceType": "official-special",
            "eventCategory": "release-event",
            "title": "発売記念リリースイベント",
            "eventDate": "2026-10-03",
            "url": "https://sweetsteady.asobisystem.com/news/detail/1",
            "urls": ["https://sweetsteady.asobisystem.com/news/detail/1", official_url],
            "officialScheduleUrl": official_url,
        }]}
        special = {"events": [{
            "id": "same-event",
            "sourceType": "official-special",
            "eventCategory": "release-event",
            "title": "発売記念リリースイベント",
            "eventDate": "2026-10-03",
            "url": "https://sweetsteady.asobisystem.com/news/detail/1",
            "urls": ["https://sweetsteady.asobisystem.com/news/detail/1"],
        }]}
        result = merger.merge_payloads(core, {"events": []}, {"events": []}, special)
        event = next(row for row in result["events"] if row["id"] == "same-event")
        self.assertEqual(official_url, event["officialScheduleUrl"])
        self.assertIn(official_url, event["urls"])
        self.assertEqual(1, result["distributedMergeDiagnostics"]["officialLinksPreserved"])

    def test_final_merge_rejects_cross_year_birthday_row(self):
        core = {"events": [
            {
                "id": "stale-2025-birthday",
                "sourceType": "auto",
                "group": "CANDY TUNE",
                "title": "小川奈々子生誕祭2025",
                "eventDate": "2026-10-01",
                "eventDates": ["2026-10-01"],
            },
            {
                "id": "correct-2026-birthday",
                "sourceType": "auto",
                "group": "CANDY TUNE",
                "title": "小川奈々子生誕祭2026",
                "eventDate": "2026-10-01",
                "eventDates": ["2026-10-01"],
            },
        ]}
        result = merger.merge_payloads(core, {"events": []}, {"events": []}, {"events": []})
        ids = {row["id"] for row in result["events"]}
        self.assertNotIn("stale-2025-birthday", ids)
        self.assertIn("correct-2026-birthday", ids)
        guard = result["distributedMergeDiagnostics"]["birthdayYearGuard"]
        self.assertEqual(1, guard["removedCount"])
        self.assertEqual(
            "explicit-title-year-does-not-match-performance-year",
            guard["removed"][0]["reason"],
        )


if __name__ == "__main__":
    unittest.main()
