import unittest

import reconcile_official_schedule_links as reconcile


class OfficialScheduleLinkReconcileTests(unittest.TestCase):
    def test_restores_official_url_to_represented_event(self):
        payload = {"events": [{
            "id": "event-1",
            "url": "https://example.com/news",
            "urls": ["https://example.com/news"],
        }]}
        index = {"entries": [{
            "representedBy": "event-1",
            "url": "https://example.com/live_information/detail/1",
        }]}
        result, report = reconcile.reconcile(payload, index)
        event = result["events"][0]
        self.assertEqual("https://example.com/live_information/detail/1", event["officialScheduleUrl"])
        self.assertIn("https://example.com/live_information/detail/1", event["urls"])
        self.assertEqual(1, report["eventsTouched"])

    def test_multiple_index_rows_for_same_event_keep_all_official_links(self):
        payload = {"events": [{"id": "joint", "urls": []}]}
        index = {"entries": [
            {"representedBy": "joint", "url": "https://a.example/detail/1"},
            {"representedBy": "joint", "url": "https://b.example/detail/2"},
        ]}
        result, _ = reconcile.reconcile(payload, index)
        self.assertEqual(
            ["https://a.example/detail/1", "https://b.example/detail/2"],
            result["events"][0]["urls"],
        )

    def test_missing_represented_id_is_reported(self):
        result, report = reconcile.reconcile(
            {"events": []},
            {"entries": [{"representedBy": "missing", "url": "https://example.com/detail/1"}]},
        )
        self.assertEqual([], result["events"])
        self.assertEqual(["missing"], report["missingRepresentedIds"])


if __name__ == "__main__":
    unittest.main()
