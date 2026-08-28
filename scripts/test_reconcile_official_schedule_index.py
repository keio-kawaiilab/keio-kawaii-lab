import unittest

from reconcile_official_schedule_index import reconcile


class ReconcileOfficialScheduleIndexTests(unittest.TestCase):
    def test_reconnects_same_official_event_after_richer_row_changes_id(self):
        official_url = "https://sweetsteady.asobisystem.com/live_information/detail/43898"
        data = {
            "events": [{
                "id": "rich-special-id",
                "group": "SWEET STEADY",
                "eventDate": "2026-09-06",
                "url": "https://sweetsteady.asobisystem.com/news/detail/88152",
                "urls": [official_url],
                "officialScheduleUrl": official_url,
            }]
        }
        index = {
            "entries": [{
                "group": "SWEET STEADY",
                "date": "2026-09-06",
                "url": official_url,
                "representedBy": "old-core-id",
            }]
        }

        report = reconcile(data, index)

        self.assertEqual(index["entries"][0]["representedBy"], "rich-special-id")
        self.assertEqual(report["reassignedCount"], 1)
        self.assertEqual(report["ambiguousCount"], 0)
        self.assertEqual(report["unresolvedCount"], 0)

    def test_does_not_guess_when_two_final_events_match(self):
        official_url = "https://example.com/live/1"
        base = {
            "group": "SWEET STEADY",
            "eventDate": "2026-09-06",
            "url": official_url,
        }
        data = {"events": [{**base, "id": "one"}, {**base, "id": "two"}]}
        index = {"entries": [{
            "group": "SWEET STEADY",
            "date": "2026-09-06",
            "url": official_url,
            "representedBy": "missing",
        }]}

        report = reconcile(data, index)

        self.assertEqual(index["entries"][0]["representedBy"], "missing")
        self.assertEqual(report["reassignedCount"], 0)
        self.assertEqual(report["ambiguousCount"], 1)

    def test_leaves_missing_row_for_fail_closed_audit(self):
        index = {"entries": [{
            "group": "SWEET STEADY",
            "date": "2026-09-06",
            "url": "https://example.com/live/missing",
            "representedBy": "missing",
        }]}

        report = reconcile({"events": []}, index)

        self.assertEqual(index["entries"][0]["representedBy"], "missing")
        self.assertEqual(report["unresolvedCount"], 1)


if __name__ == "__main__":
    unittest.main()
