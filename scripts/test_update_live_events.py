import unittest

import update_live_events as u


class ParserTests(unittest.TestCase):
    def test_window_with_years(self):
        text = "受付期間：2026年7月26日(日)12:00～2026年8月2日(日)23:59"
        self.assertEqual(
            u.extract_window(text, 2026),
            ("2026-07-26T12:00", "2026-08-02T23:59"),
        )

    def test_window_without_years(self):
        text = "受付期間：6月6日(土)18:00〜6月14日(日)23:59"
        self.assertEqual(
            u.extract_window(text, 2026),
            ("2026-06-06T18:00", "2026-06-14T23:59"),
        )

    def test_multiple_event_dates_with_venues(self):
        lines = [
            "日程：2026年8月29日（土）",
            "会場：戸田市文化会館",
            "日程：9月4日（金）",
            "会場：カルッツかわさき",
        ]
        self.assertEqual(
            u.extract_event_occurrences(lines, "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -", "2026-06-06"),
            [
                ("2026-08-29", "戸田市文化会館"),
                ("2026-09-04", "カルッツかわさき"),
            ],
        )

    def test_labeled_deadlines(self):
        text = "当落発表：2026年8月5日(水)18:00\n入金期限：8月8日(土)23:59"
        self.assertEqual(u.extract_labeled_date(text, u.RESULT_LABELS, 2026), "2026-08-05T18:00")
        self.assertEqual(u.extract_labeled_date(text, u.PAYMENT_LABELS, 2026), "2026-08-08T23:59")


if __name__ == "__main__":
    unittest.main()
