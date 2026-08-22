import unittest
from datetime import date

import update_live_events_v2 as v2


class RetentionPolicyTests(unittest.TestCase):
    def test_future_show_survives_old_application_deadline(self):
        event = {
            "eventDate": "2026-12-12",
            "applyEnd": "2026-08-30T23:59",
        }
        self.assertTrue(v2.should_show(event, date(2026, 11, 30)))

    def test_show_stays_until_one_calendar_month_after(self):
        event = {"eventDate": "2026-08-31"}
        self.assertTrue(v2.should_show(event, date(2026, 9, 30)))
        self.assertFalse(v2.should_show(event, date(2026, 10, 1)))

    def test_consecutive_event_uses_end_date(self):
        event = {
            "eventDate": "2026-12-12",
            "eventEndDate": "2026-12-13",
        }
        self.assertTrue(v2.should_show(event, date(2027, 1, 13)))
        self.assertFalse(v2.should_show(event, date(2027, 1, 14)))

    def test_month_end_clamps_safely(self):
        self.assertEqual(v2.add_one_calendar_month(date(2027, 1, 31)), date(2027, 2, 28))

    def test_old_article_future_event_is_retained(self):
        existing = {
            "events": [{
                "id": "old-future",
                "sourceType": "auto",
                "eventDate": "2027-05-01",
                "applyEnd": "2026-08-01T23:59",
                "url": "https://example.test/old",
            }]
        }
        payload = v2.build_payload(existing, {}, [], [], date(2026, 8, 23))
        self.assertEqual([e["id"] for e in payload["events"]], ["old-future"])


if __name__ == "__main__":
    unittest.main()
