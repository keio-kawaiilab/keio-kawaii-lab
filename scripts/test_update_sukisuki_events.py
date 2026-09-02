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

    def test_sale_typeオンラインリリイベ(self):
        self.assertEqual(
            s.sale_type("CANDY TUNE オンラインリリイベ", "抽選販売"),
            "オンラインリリースイベント・抽選販売",
        )

    def test_application_window(self):
        text = "抽選申込期間：2026年8月20日 18:00～2026年8月22日 23:59"
        self.assertEqual(
            s.date_window_after(text, ("抽選申込期間",), 2026),
            ("2026-08-20T18:00", "2026-08-22T23:59"),
        )

    def test_stream_time_is_kept(self):
        url = "https://sukisuki-shop.com/goods/6500000004999"
        html = """<html><h1>2026年8月24日 CANDY TUNE オンライン特典会</h1>
        <p>配信予定日：2026年8月24日 18:00</p>
        <p>抽選申込期間：2026年8月19日 21:00～2026年8月20日 23:59</p></html>"""
        event = s.parse_goods(FakeSession({url: html}), url, date(2026, 8, 19))
        self.assertEqual("18:00", event["startTime"])

    def test_online_release_event_is_parsed(self):
        url = "https://sukisuki-shop.com/goods/6500000005001"
        html = """<html><h1>〖抽選販売〗2026年9月8日 CANDY TUNE オンラインリリイベ</h1>
        <p>CANDY TUNEのオンラインリリイベを開催します。</p>
        <p>配信予定日：2026年9月8日 17:00</p>
        <p>抽選申込期間：2026年9月2日 21:00～2026年9月4日 23:59</p></html>"""
        event = s.parse_goods(FakeSession({url: html}), url, date(2026, 9, 2))
        self.assertIsNotNone(event)
        self.assertEqual("CANDY TUNE", event["group"])
        self.assertEqual("2026-09-08", event["eventDate"])
        self.assertEqual("17:00", event["startTime"])
        self.assertEqual("オンラインリリースイベント・抽選販売", event["ticketType"])

    def test_discovery_reads_api_even_when_normal_list_has_results(self):
        pages = {
            "https://api.sukisuki-shop.com/goods": (
                '<a href="/goods/6500000004999">新商品A</a>'
            ),
            "https://sukisuki-shop.com/goods": (
                '<a href="/goods/6500000004000">新商品B</a>'
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

    def test_discovery_requires_no_group_or_online_hint_on_list_card(self):
        pages = {
            "https://api.sukisuki-shop.com/goods": (
                '<a href="/goods/6500000005002"><img alt="商品画像"></a>'
            ),
            "https://sukisuki-shop.com/goods": "",
            "https://sukisuki-shop.com/": "",
        }
        session = FakeSession(pages)
        urls, failures = s.discover(session)
        self.assertEqual([], failures)
        self.assertEqual(
            ["https://sukisuki-shop.com/goods/6500000005002"],
            urls,
        )

    def test_detail_page_does_the_actual_online_event_classification(self):
        url = "https://sukisuki-shop.com/goods/6500000005002"
        html = """<html><h1>2026年9月8日 CANDY TUNE オンライン特典会</h1>
        <p>SOUI Knit衣装でオンライン特典会を開催します。</p>
        <p>配信予定日：2026年9月8日 17:00</p>
        <p>販売期間：2026年9月2日 20:00～2026年9月7日 23:59</p></html>"""
        event = s.parse_goods(FakeSession({url: html}), url, date(2026, 9, 2))
        self.assertIsNotNone(event)
        self.assertEqual("CANDY TUNE", event["group"])
        self.assertEqual("2026-09-08", event["eventDate"])
        self.assertEqual("17:00", event["startTime"])
        self.assertEqual("オンライン特典会", event["ticketType"])

    def test_api_goods_detail_url_is_normalized_to_shop_host(self):
        self.assertEqual(
            s.canonical_goods_url("https://api.sukisuki-shop.com/goods/6500000004999?sku=1"),
            "https://sukisuki-shop.com/goods/6500000004999",
        )

    def test_stale_derived_sukisuki_row_is_still_recognized(self):
        event = {
            "sourceType": "derived",
            "primarySource": "sukisuki",
            "url": "https://sukisuki-shop.com/goods/6500000003995",
        }
        self.assertTrue(s.is_sukisuki_event(event))

    def test_sukisuki_url_is_enough_to_identify_source(self):
        event = {
            "sourceType": "derived",
            "url": "https://sukisuki-shop.com/goods/6500000003995",
        }
        self.assertTrue(s.is_sukisuki_event(event))

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
