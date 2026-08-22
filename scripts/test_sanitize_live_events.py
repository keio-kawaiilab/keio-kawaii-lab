import unittest

import sanitize_live_events as s


class SanitizerTests(unittest.TestCase):
    def test_removes_result_date_false_event_and_cleans_title(self):
        payload = {
            "events": [
                {
                    "id": "wrong",
                    "group": "CUTIE STREET",
                    "title": "2026.08.12 2026年10月11日 STARフェス",
                    "eventDate": "2026-08-29",
                    "resultDate": "2026-08-29",
                    "url": "https://example.test/1",
                    "ticketType": "FC先行",
                    "applyStart": "2026-08-12T13:00",
                },
                {
                    "id": "right",
                    "group": "CUTIE STREET",
                    "title": "2026.08.12 2026年10月11日 STARフェス",
                    "eventDate": "2026-10-11",
                    "resultDate": "2026-08-29",
                    "url": "https://example.test/1",
                    "ticketType": "FC先行",
                    "applyStart": "2026-08-12T13:00",
                },
            ]
        }
        result = s.sanitize_payload(payload)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["id"], "right")
        self.assertEqual(result["events"][0]["title"], "2026年10月11日 STARフェス")


if __name__ == "__main__":
    unittest.main()
