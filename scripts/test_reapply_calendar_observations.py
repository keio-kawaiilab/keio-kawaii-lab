import unittest
from reapply_calendar_observations import merge_payload


class ConcurrentPublicationTests(unittest.TestCase):
    def test_remote_edit_and_new_collected_offer_both_survive(self):
        base = {"events": [{"id": "show", "venue": "old", "startTime": None}], "publicEvents": ["stale"]}
        collected = {"events": [{"id": "show", "venue": "old", "startTime": "18:00"}, {"id": "new-sale", "ticketType": "一般発売"}]}
        latest = {"events": [{"id": "show", "venue": "corrected", "startTime": None}, {"id": "remote-new"}]}
        result = merge_payload(base, collected, latest)
        rows = {row["id"]: row for row in result["events"]}
        self.assertEqual(set(rows), {"show", "new-sale", "remote-new"})
        self.assertEqual(rows["show"], {"id": "show", "venue": "corrected", "startTime": "18:00"})
        self.assertNotIn("publicEvents", result)

    def test_newer_remote_correction_is_not_overwritten(self):
        def data(value):
            return {"events": [{"id": "sale", "applicationStatus": value}]}
        result = merge_payload(data("scheduled"), data("open"), data("sold_out"))
        self.assertEqual(result["events"][0]["applicationStatus"], "sold_out")


if __name__ == "__main__":
    unittest.main()
