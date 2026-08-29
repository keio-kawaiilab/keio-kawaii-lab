import unittest
from datetime import date

import update_resale_events as resale


class ResaleParserTests(unittest.TestCase):
    def setUp(self):
        self.existing = [{
            "id": "show",
            "group": "CANDY TUNE",
            "eventTitle": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN - CANDY CIRCUS",
            "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN - CANDY CIRCUS",
            "ticketType": "現在受付なし",
            "eventDate": "2026-08-29",
            "venue": "戸田市文化会館",
            "openTime": "16:00",
            "startTime": "17:30",
            "sourceType": "schedule",
        }, {
            "id": "show2",
            "group": "CANDY TUNE",
            "eventTitle": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN - CANDY CIRCUS",
            "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN - CANDY CIRCUS",
            "ticketType": "現在受付なし",
            "eventDate": "2026-08-30",
            "venue": "戸田市文化会館",
            "sourceType": "schedule",
        }]

    def test_multiple_resale_windows_map_to_each_show(self):
        html = """
        <html><body>
        <p>2026.08.26</p>
        <h1>「CANDY TUNE JAPAN TOUR 2026 - AUTUMN - CANDY CIRCUS 」公演 リセールサービスのお知らせ</h1>
        <p>8月29日(土) 埼玉・戸田市文化会館</p>
        <p>【リセール受付・購入期間】8月27日(木)10:00〜8月28日(金)23:59まで</p>
        <p>8月30日(日) 埼玉・戸田市文化会館</p>
        <p>【リセール受付・購入期間】8月28日(金)10:00〜8月29日(土)23:59まで</p>
        </body></html>
        """
        rows, review = resale.parse_resale_article(
            html,
            "https://kawaiilab.asobisystem.com/news/detail/88214",
            "「CANDY TUNE JAPAN TOUR 2026 - AUTUMN - CANDY CIRCUS 」公演 リセールサービスのお知らせ",
            self.existing,
        )
        self.assertIsNone(review)
        self.assertEqual([row["eventDate"] for row in rows], ["2026-08-29", "2026-08-30"])
        self.assertEqual(rows[0]["applyStart"], "2026-08-27T10:00")
        self.assertEqual(rows[1]["applyEnd"], "2026-08-29T23:59")
        self.assertTrue(all(row["ticketType"] == "公式リセール" for row in rows))
        self.assertTrue(all(row["saleFamily"] == "resale" for row in rows))

    def test_one_common_window_can_cover_multiple_dates(self):
        event_days = [(10, "2026-05-02"), (11, "2026-05-03")]
        windows = [(20, "2026-04-21T12:00", "2026-04-23T23:59")]
        self.assertEqual(
            resale.map_windows_to_days(event_days, windows),
            [
                ("2026-05-02", "2026-04-21T12:00", "2026-04-23T23:59"),
                ("2026-05-03", "2026-04-21T12:00", "2026-04-23T23:59"),
            ],
        )

    def test_ambiguous_multiple_windows_are_not_guessed(self):
        event_days = [(10, "2026-09-04")]
        windows = [
            (20, "2026-09-01T10:00", "2026-09-02T23:59"),
            (30, "2026-09-03T10:00", "2026-09-04T23:59"),
        ]
        self.assertIsNone(resale.map_windows_to_days(event_days, windows))

    def test_merge_replaces_only_resale_source_rows(self):
        payload = {"events": [
            {"id": "normal", "sourceType": "auto", "eventDate": "2026-12-01"},
            {"id": "old-resale", "sourceType": "resale-official", "eventDate": "2026-12-01", "applyEnd": "2026-11-30T23:59"},
        ]}
        fresh = [{
            "id": "new-resale", "sourceType": "resale-official", "eventDate": "2026-12-01",
            "applyEnd": "2099-11-30T23:59", "group": "CANDY TUNE",
        }]
        merged = resale.merge_resale(payload, fresh, date(2026, 8, 30))
        self.assertEqual({x["id"] for x in merged["events"]}, {"normal", "new-resale"})


if __name__ == "__main__":
    unittest.main()
