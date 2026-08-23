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

    def test_window_slash_format_from_real_style(self):
        text = "受付期間：8/3（日）20:00〜8/25（月）23:59"
        self.assertEqual(
            u.extract_window(text, 2025),
            ("2025-08-03T20:00", "2025-08-25T23:59"),
        )

    def test_cross_year_window(self):
        text = "受付期間：2026年12月28日(月)18:00〜1月3日(日)23:59"
        self.assertEqual(
            u.extract_window(text, 2026),
            ("2026-12-28T18:00", "2027-01-03T23:59"),
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
        text = "当落発表：2026年8月5日(水)18:00\n入金期限：8/8(土)23:59"
        self.assertEqual(u.extract_labeled_date(text, u.RESULT_LABELS, 2026), "2026-08-05T18:00")
        self.assertEqual(u.extract_labeled_date(text, u.PAYMENT_LABELS, 2026), "2026-08-08T23:59")

    def test_multiple_distinct_windows_are_detected(self):
        text = (
            "受付期間：2026年8月1日(土)12:00〜8月5日(水)23:59\n"
            "受付期間：2026年8月8日(土)12:00〜8月12日(水)23:59"
        )
        self.assertEqual(len(u.extract_windows(text, 2026)), 2)

    def test_fruits_zipper_real_article_style(self):
        text = (
            "2026.05.26\n"
            "日程：2026年9月3日（木）\n"
            "時間：OPEN 17:30 / START 18:30\n"
            "会場：神奈川県 よこすか芸術劇場（大劇場）\n"
            "日程：2026年9月16日（水）\n"
            "会場：埼玉県 大宮ソニックシティ 大ホール\n"
            "受付期間：2026年5月26日（火）18:00～2026年6月1日（月）23:59"
        )
        self.assertEqual(u.article_date_from_text(text), "2026-05-26")
        self.assertEqual(
            u.extract_window(text, 2026),
            ("2026-05-26T18:00", "2026-06-01T23:59"),
        )
        lines = [u.normalize_space(x) for x in text.splitlines() if u.normalize_space(x)]
        self.assertEqual(
            u.extract_event_occurrences(lines, "FRUITS ZIPPER JAPAN TOUR 2026 - AUTUMN -", "2026-05-26"),
            [
                ("2026-09-03", "神奈川県 よこすか芸術劇場（大劇場）"),
                ("2026-09-16", "埼玉県 大宮ソニックシティ 大ホール"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
