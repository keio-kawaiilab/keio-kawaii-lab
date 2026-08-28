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


if __name__ == "__main__":
    unittest.main()
