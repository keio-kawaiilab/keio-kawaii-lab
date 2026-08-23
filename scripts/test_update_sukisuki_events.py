import unittest
from datetime import date

import update_sukisuki_events as s


class SukisukiParserTests(unittest.TestCase):
    def test_clean_event_title(self):
        self.assertEqual(
            s.clean_event_title("〖抽選販売〗2026年8月24日 CANDY TUNE オンライン特典会"),
            "CANDY TUNE オンライン特典会",
        )

    def test_sale_type抽選(self):
        self.assertEqual(
            s.sale_type("CANDY TUNE オンライン特典会", "抽選販売"),
            "オンライン特典会・抽選販売",
        )

    def test_application_window(self):
        text = "抽選申込期間：2026年8月20日 18:00～2026年8月22日 23:59"
        self.assertEqual(
            s.date_window_after(text, ("抽選申込期間",), 2026),
            ("2026-08-20T18:00", "2026-08-22T23:59"),
        )

    def test_yearless_near_event_uses_upcoming_year(self):
        match = s.DATE_RE.search("9月10日オンライン特典会")
        self.assertEqual(
            s.resolve_yearless_date(match, date(2026, 8, 23)),
            "2026-09-10",
        )

    def test_yearless_far_future_event_is_rejected(self):
        match = s.DATE_RE.search("12月21日FRUITS ZIPPERオンライン特典会")
        self.assertIsNone(
            s.resolve_yearless_date(match, date(2026, 8, 23))
        )

    def test_yearless_january_can_roll_to_next_year_when_near(self):
        match = s.DATE_RE.search("1月10日オンライン特典会")
        self.assertEqual(
            s.resolve_yearless_date(match, date(2026, 12, 20)),
            "2027-01-10",
        )


if __name__ == "__main__":
    unittest.main()
