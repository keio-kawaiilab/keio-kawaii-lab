import unittest

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


if __name__ == "__main__":
    unittest.main()
