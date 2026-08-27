import unittest
from datetime import datetime

import prepare_release_candidate as prep


class PrepareReleaseCandidateTests(unittest.TestCase):
    NOW = datetime.fromisoformat("2026-08-27T19:00:00+09:00")

    def test_dedupes_same_id_and_keeps_richer_row(self):
        thin = {"id": "same", "group": "X", "title": "A", "eventDate": "2026-09-01", "sourceType": "derived"}
        rich = {
            "id": "same", "group": "X", "title": "A", "eventDate": "2026-09-01",
            "sourceType": "official-special", "venue": "Hall", "url": "https://example.com/a",
        }
        rows, removed = prep.dedupe_ids([thin, rich])
        self.assertEqual(removed, 1)
        self.assertEqual(rows[0]["sourceType"], "official-special")

    def test_schedule_only_special_is_normalized(self):
        event = {
            "id": "x", "group": "CANDY TUNE", "title": "大特典会", "eventCategory": "large-benefit",
            "ticketType": "現在受付なし", "applicationStatus": "none", "eventDate": "2026-09-05",
            "url": "https://candytune.asobisystem.com/live_information/detail/1",
            "officialScheduleUrl": "https://candytune.asobisystem.com/live_information/detail/1",
            "sourceType": "derived",
        }
        normalized, changed = prep.normalize_special(event)
        self.assertTrue(changed)
        self.assertEqual(normalized["sourceType"], "official-schedule")
        self.assertEqual(normalized["specialDetailsStatus"], "awaiting-details")
        self.assertEqual(normalized["applicationDisplayMode"], "schedule-only")

    def test_expired_playguide_row_is_not_retained(self):
        event = {
            "group": "CANDY TUNE", "title": "Tour", "ticketType": "抽選 プレリク",
            "ticketProvider": "eplus", "applicationStatus": "open",
            "applyEnd": "2026-08-25T23:59", "eventDate": "2026-10-01",
            "url": "https://eplus.jp/sf/detail/1",
        }
        self.assertFalse(prep.should_retain_previous(event, self.NOW.date()))

    def test_missing_future_official_row_is_retained_stale(self):
        old = {
            "id": "old1", "group": "SWEET STEADY", "title": "Festival",
            "ticketType": "現在受付なし", "applicationStatus": "none",
            "eventDate": "2026-10-04", "sourceType": "official-schedule",
            "url": "https://sweetsteady.asobisystem.com/live_information/detail/123",
        }
        prepared, report = prep.prepare({"events": [old]}, {"events": []}, self.NOW)
        self.assertEqual(report["retainedPreviousRows"], 1)
        self.assertTrue(prepared["events"][0]["sourceStale"])


if __name__ == "__main__":
    unittest.main()
