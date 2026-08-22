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

    def test_merges_joint_event_announced_by_multiple_groups(self):
        base = {
            "title": "KAWAII LAB. Christmas SESSION 2026",
            "ticketType": "FC先行",
            "applyStart": "2026-08-22T12:00",
            "applyEnd": "2026-08-30T23:59",
            "eventDate": "2026-12-12",
            "venue": "有明アリーナ",
            "sourceType": "auto",
        }
        payload = {"events": [
            {**base, "id": "a", "group": "FRUITS ZIPPER", "url": "https://example.test/fz"},
            {**base, "id": "b", "group": "CANDY TUNE", "url": "https://example.test/ct"},
            {**base, "id": "c", "group": "CUTIE STREET", "url": "https://example.test/cs"},
        ]}
        result = s.sanitize_payload(payload)["events"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["group"], "KAWAII LAB.合同")
        self.assertEqual(result[0]["participants"], ["FRUITS ZIPPER", "CANDY TUNE", "CUTIE STREET"])
        self.assertEqual(len(result[0]["urls"]), 3)

    def test_merges_consecutive_days_at_same_venue(self):
        base = {
            "group": "SWEET STEADY",
            "title": "2DAYSワンマンライブ",
            "ticketType": "FC先行",
            "applyStart": "2026-08-01T12:00",
            "applyEnd": "2026-08-10T23:59",
            "venue": "サンプルホール",
            "sourceType": "auto",
        }
        payload = {"events": [
            {**base, "id": "d1", "eventDate": "2026-10-03", "url": "https://example.test/1"},
            {**base, "id": "d2", "eventDate": "2026-10-04", "url": "https://example.test/2"},
        ]}
        result = s.sanitize_payload(payload)["events"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["eventDate"], "2026-10-03")
        self.assertEqual(result[0]["eventEndDate"], "2026-10-04")
        self.assertEqual(result[0]["eventDates"], ["2026-10-03", "2026-10-04"])

    def test_joint_two_day_event_becomes_one_range(self):
        events = []
        for date in ("2026-12-12", "2026-12-13"):
            for group in ("FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY"):
                events.append({
                    "id": f"{group}-{date}",
                    "group": group,
                    "title": "KAWAII LAB. Christmas SESSION 2026",
                    "ticketType": "アップグレード抽選",
                    "applyStart": "2026-08-22T12:00",
                    "applyEnd": "2026-08-30T23:59",
                    "eventDate": date,
                    "venue": "有明アリーナ",
                    "url": f"https://example.test/{group}/{date}",
                    "sourceType": "auto",
                })
        result = s.sanitize_payload({"events": events})["events"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["group"], "KAWAII LAB.合同")
        self.assertEqual(result[0]["eventDate"], "2026-12-12")
        self.assertEqual(result[0]["eventEndDate"], "2026-12-13")

    def test_tour_dates_with_same_application_window_become_one_item(self):
        base = {
            "group": "CANDY TUNE",
            "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN - FC先行",
            "ticketType": "FC先行",
            "applyStart": "2026-06-24T18:00",
            "applyEnd": "2026-06-29T23:59",
            "sourceType": "auto",
            "url": "https://example.test/tour",
        }
        payload = {"events": [
            {**base, "id": "t1", "eventDate": "2026-08-29", "venue": "戸田市文化会館"},
            {**base, "id": "t2", "eventDate": "2026-09-04", "venue": "カルッツかわさき"},
            {**base, "id": "t3", "eventDate": "2026-09-09", "venue": "グランキューブ大阪"},
        ]}
        result = s.sanitize_payload(payload)["events"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["eventDate"], "2026-08-29")
        self.assertEqual(result[0]["eventEndDate"], "2026-09-09")
        self.assertEqual(result[0]["eventCount"], 3)
        self.assertEqual(result[0]["venue"], "複数会場（全3公演）")
        self.assertEqual(len(result[0]["schedule"]), 3)

    def test_tour_with_different_application_windows_stays_separate(self):
        common = {
            "group": "CUTIE STREET",
            "title": "CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-",
            "ticketType": "FC先行",
            "eventDate": "2026-09-23",
            "venue": "横浜アリーナ",
            "sourceType": "auto",
        }
        payload = {"events": [
            {**common, "id": "w1", "applyStart": "2026-06-01T12:00", "applyEnd": "2026-06-17T23:59", "url": "https://example.test/1"},
            {**common, "id": "w2", "applyStart": "2026-07-01T12:00", "applyEnd": "2026-07-10T23:59", "url": "https://example.test/2"},
        ]}
        result = s.sanitize_payload(payload)["events"]
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
