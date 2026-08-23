import unittest
from datetime import date

import update_sukisuki_events as s


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, timeout=25):
        self.calls.append(url)
        return FakeResponse(self.pages.get(url, ""))


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

    def test_sale_type先着(self):
        self.assertEqual(
            s.sale_type("〖二次ビンゴ先着販売〗CANDY TUNE オンライン特典会", "先着販売"),
            "オンライン特典会・先着販売",
        )

    def test_application_window(self):
        text = "抽選申込期間：2026年8月20日 18:00～2026年8月22日 23:59"
        self.assertEqual(
            s.date_window_after(text, ("抽選申込期間",), 2026),
            ("2026-08-20T18:00", "2026-08-22T23:59"),
        )

    def test_discovery_reads_api_even_when_normal_list_has_results(self):
        pages = {
            "https://api.sukisuki-shop.com/goods": (
                '<a href="/goods/6500000004999">〖二次ビンゴ先着販売〗2026年8月24日 CANDY TUNE オンライン特典会</a>'
            ),
            "https://sukisuki-shop.com/goods": (
                '<a href="/goods/6500000004000">〖抽選販売〗2026年8月24日 CANDY TUNE オンライン特典会</a>'
            ),
            "https://sukisuki-shop.com/": "",
        }
        session = FakeSession(pages)
        urls, failures = s.discover(session)
        self.assertEqual(failures, [])
        self.assertIn("https://sukisuki-shop.com/goods/6500000004999", urls)
        self.assertIn("https://sukisuki-shop.com/goods/6500000004000", urls)
        self.assertEqual(session.calls, list(s.LIST_URLS))
        self.assertGreater(s.goods_rank(urls[0]), s.goods_rank(urls[1]))

    def test_api_goods_detail_url_is_normalized_to_shop_host(self):
        self.assertEqual(
            s.canonical_goods_url("https://api.sukisuki-shop.com/goods/6500000004999?sku=1"),
            "https://sukisuki-shop.com/goods/6500000004999",
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

    def test_old_ticket_year_hint_keeps_old_christmas_event_old(self):
        text = "当落発表日：2025年12月18日 入金期限：12月19日"
        hint = s.explicit_year_hint(text)
        self.assertEqual(hint, 2025)
        match = s.DATE_RE.search("12月21日FRUITS ZIPPERオンライン特典会")
        self.assertEqual(
            s.resolve_event_date(match, date(2026, 8, 23), hint),
            "2025-12-21",
        )

    def test_year_end_ticket_hint_can_roll_event_into_next_january(self):
        text = "抽選申込期間：2026年12月20日～12月25日"
        hint = s.explicit_year_hint(text)
        self.assertEqual(hint, 2026)
        match = s.DATE_RE.search("1月10日オンライン特典会")
        self.assertEqual(
            s.resolve_event_date(match, date(2026, 12, 20), hint),
            "2027-01-10",
        )


if __name__ == "__main__":
    unittest.main()
