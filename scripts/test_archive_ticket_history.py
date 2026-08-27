import unittest

import archive_ticket_history as mod


class ArchiveTicketHistoryTests(unittest.TestCase):
    def setUp(self):
        self.registry = {
            "version": 1,
            "sources": {
                "group-official": {"label": "official", "kind": "official", "publishPolicy": "direct"},
                "pia": {"label": "pia", "kind": "playguide", "publishPolicy": "direct"},
                "official-x": {"label": "x", "kind": "social", "publishPolicy": "discovery-only"},
            },
            "hostRules": {
                "example.asobisystem.com": "group-official",
                "t.pia.jp": "pia",
                "x.com": "official-x",
            },
        }

    def test_ended_entry_is_never_removed_when_live_data_no_longer_contains_it(self):
        existing = {
            "version": 1,
            "entries": [{
                "id": "keep-me",
                "group": "CANDY TUNE",
                "eventTitle": "Example",
                "eventDate": "2026-10-01",
                "ticketType": "FC先行",
                "applyStart": "2026-08-01T12:00",
                "applyEnd": "2026-08-05T23:59",
                "sourceKey": "group-official",
                "sourceUrl": "https://example.asobisystem.com/news/detail/1",
                "firstSeenAt": "2026-08-01T00:00:00+09:00",
                "lastSeenAt": "2026-08-01T00:00:00+09:00",
            }],
        }
        result = mod.archive_payload({"events": []}, existing, self.registry, "2026-08-27T12:00:00+09:00")
        self.assertEqual([x["id"] for x in result["entries"]], ["keep-me"])

    def test_direct_official_full_window_is_archived_and_publishable(self):
        live = {"events": [{
            "group": "CANDY TUNE",
            "eventTitle": "Example Live",
            "eventDate": "2026-10-01",
            "ticketType": "FC先行",
            "applyStart": "2026-08-01T12:00",
            "applyEnd": "2026-08-05T23:59",
            "url": "https://example.asobisystem.com/news/detail/2",
        }]}
        result = mod.archive_payload(live, {"entries": []}, self.registry, "2026-08-27T12:00:00+09:00")
        self.assertEqual(len(result["entries"]), 1)
        self.assertTrue(result["entries"][0]["publishable"])
        self.assertEqual(result["entries"][0]["sourceKey"], "group-official")

    def test_discovery_only_source_is_not_archived(self):
        live = {"events": [{
            "group": "CANDY TUNE",
            "eventTitle": "Example Live",
            "eventDate": "2026-10-01",
            "ticketType": "FC先行",
            "applyStart": "2026-08-01T12:00",
            "applyEnd": "2026-08-05T23:59",
            "url": "https://x.com/example/status/1",
        }]}
        result = mod.archive_payload(live, {"entries": []}, self.registry, "2026-08-27T12:00:00+09:00")
        self.assertEqual(result["entries"], [])

    def test_partial_playguide_window_is_archived_but_not_publishable_without_verified_flag(self):
        live = {"events": [{
            "group": "FRUITS ZIPPER",
            "eventTitle": "Example Tour",
            "eventDate": "2026-10-26",
            "ticketType": "2次プレリザーブ",
            "applyStart": None,
            "applyEnd": "2026-08-30T23:59",
            "url": "https://t.pia.jp/pia/event/event.do?eventBundleCd=test",
        }]}
        result = mod.archive_payload(live, {"entries": []}, self.registry, "2026-08-27T12:00:00+09:00")
        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(result["entries"][0]["windowCompleteness"], "end-only")
        self.assertFalse(result["entries"][0]["publishable"])


if __name__ == "__main__":
    unittest.main()
