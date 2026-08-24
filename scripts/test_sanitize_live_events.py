from datetime import date
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
        for day in ("2026-12-12", "2026-12-13"):
            for group in ("FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY"):
                events.append({
                    "id": f"{group}-{day}",
                    "group": group,
                    "title": "KAWAII LAB. Christmas SESSION 2026",
                    "ticketType": "アップグレード抽選",
                    "applyStart": "2026-08-22T12:00",
                    "applyEnd": "2026-08-30T23:59",
                    "eventDate": day,
                    "venue": "有明アリーナ",
                    "url": f"https://example.test/{group}/{day}",
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

    def test_grouped_schedule_keeps_each_performance_time(self):
        base = {
            "group": "CANDY TUNE",
            "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            "ticketType": "FC先行",
            "applyStart": "2026-06-24T18:00",
            "applyEnd": "2026-06-29T23:59",
            "sourceType": "auto",
            "url": "https://example.test/tour",
        }
        payload = {"events": [
            {**base, "id": "t1", "eventDate": "2026-08-29", "venue": "戸田市文化会館", "openTime": "16:00", "startTime": "17:00"},
            {**base, "id": "t2", "eventDate": "2026-09-04", "venue": "カルッツかわさき", "openTime": "17:30", "startTime": "18:30"},
        ]}
        result = s.sanitize_payload(payload)["events"][0]["schedule"]
        self.assertEqual((result[0]["openTime"], result[0]["startTime"]), ("16:00", "17:00"))
        self.assertEqual((result[1]["openTime"], result[1]["startTime"]), ("17:30", "18:30"))

    def test_aggregate_ticket_summary_is_not_published_automatically(self):
        payload = {"events": [{
            "id": "s1",
            "group": "CUTIE STREET",
            "title": "★CUTIE STREET チケット先行まとめ情報★",
            "ticketType": "KAWAII LAB. FC先行",
            "applyStart": "2026-07-26T12:00",
            "applyEnd": "2026-08-02T23:59",
            "eventDate": "2026-09-23",
            "venue": "横浜アリーナ",
            "url": "https://example.test/summary",
        }]}
        self.assertEqual(s.sanitize_payload(payload)["events"], [])

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

    def test_expired_ticket_rounds_become_one_schedule_only_item(self):
        common = {
            "group": "CUTIE STREET",
            "title": "「CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-」FC先行開始！",
            "eventDate": "2026-09-23",
            "eventEndDate": "2026-11-29",
            "eventDates": ["2026-09-23", "2026-11-29"],
            "schedule": [
                {"date": "2026-09-23", "venue": "横浜アリーナ"},
                {"date": "2026-11-29", "venue": "IGアリーナ"},
            ],
            "venue": "複数会場（全2公演）",
        }
        payload = {"events": [
            {**common, "id": "old1", "ticketType": "年会費コース会員先行", "applyStart": "2026-06-01T12:00", "applyEnd": "2026-06-17T23:59", "url": "https://example.test/1"},
            {**common, "id": "old2", "ticketType": "FC先行", "applyStart": "2026-06-28T12:00", "applyEnd": "2026-07-12T23:59", "url": "https://example.test/2"},
        ]}
        result = s.sanitize_payload(payload, today=date(2026, 8, 23))["events"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ticketType"], "現在受付なし")
        self.assertIsNone(result[0]["applyStart"])
        self.assertIsNone(result[0]["applyEnd"])
        self.assertEqual(result[0]["title"], "CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-")

    def test_current_ticket_round_hides_older_round_for_same_event(self):
        common = {
            "group": "CUTIE STREET",
            "title": "「CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-」FC先行",
            "eventDate": "2026-09-23",
            "venue": "横浜アリーナ",
        }
        payload = {"events": [
            {**common, "id": "old", "ticketType": "FC先行", "applyStart": "2026-06-28T12:00", "applyEnd": "2026-07-12T23:59", "url": "https://example.test/old"},
            {**common, "id": "new", "ticketType": "一般先行", "applyStart": "2026-08-20T12:00", "applyEnd": "2026-08-30T23:59", "url": "https://example.test/new"},
        ]}
        result = s.sanitize_payload(payload, today=date(2026, 8, 23))["events"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "new")
        self.assertEqual(result[0]["ticketType"], "一般先行")


if __name__ == "__main__":
    unittest.main()
