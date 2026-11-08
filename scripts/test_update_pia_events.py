import unittest

import update_pia_events as p


class PiaParserTests(unittest.TestCase):
    def test_ticket_type(self):
        self.assertEqual(p.ticket_type("先行 プレリザーブ 抽選受付中"), "プレリザーブ")
        self.assertEqual(p.ticket_type("CUTIE STREET 3次プレリザーブ"), "3次プレリザーブ")
        self.assertEqual(p.ticket_type("一般発売／CUTIE STREET"), "一般発売")
        self.assertEqual(p.ticket_type("先行 プレミアム ぴあNICOSカード限定"), "ぴあNICOSカード限定先行")

    def test_single_event_and_deadline(self):
        context = "一般発売 CUTIE STREET 2026/9/14(月) SGC HALL ARIAKE (東京都) 販売期間中 ～2026/9/13(日) 23:59 詳細へ"
        self.assertEqual(p.event_window(context), ("2026-09-14", None))
        self.assertEqual(p.sale_window(context), (None, "2026-09-13T23:59"))
        self.assertEqual(p.availability_status(context), "open")

    def test_event_range_before_sale_status(self):
        context = "プレリザーブ 2026/9/9(水) ～ 2026/9/10(木) 大阪国際会議場 抽選受付中 ～ 2026/8/23(日) 23:59"
        self.assertEqual(p.event_window(context), ("2026-09-09", "2026-09-10"))
        self.assertEqual(p.sale_window(context), (None, "2026-08-23T23:59"))
        self.assertEqual(p.availability_status(context), "open")

    def test_upcoming_general_sale_start(self):
        context = "一般発売 2026/9/14(月) SGC HALL ARIAKE 発売前 2026/8/22(土) 10:00より発売"
        self.assertEqual(p.sale_window(context), ("2026-08-22T10:00", None))
        self.assertEqual(p.availability_status(context), "upcoming")

    def test_upcoming_lottery_full_window(self):
        context = "プレリザーブ 2026/10/2(金) ～ 2026/10/4(日) 北海道 まもなく抽選受付2026/8/15(土) 11:00 ～ 2026/8/23(日) 23:59 詳細はこちら"
        self.assertEqual(p.event_window(context), ("2026-10-02", "2026-10-04"))
        self.assertEqual(p.sale_window(context), ("2026-08-15T11:00", "2026-08-23T23:59"))
        self.assertEqual(p.availability_status(context), "upcoming")

    def test_result_phase_is_not_active(self):
        context = "プレリザーブ 2026/8/29(土) ～ 2026/12/9(水) 抽選結果発表前2026/8/11(火) 20:00 詳細はこちら"
        self.assertIsNone(p.availability_status(context))

    def test_candy_tour_bundle_is_seeded(self):
        seeded = dict(p.SEEDED_EVENT_PAGES)["CANDY TUNE"] if False else p.SEEDED_EVENT_PAGES["CANDY TUNE"]
        self.assertTrue(any("b2669827" in url for url, _ in seeded))

    def test_detail_window_with_deadline_before_sale_start(self):
        text = "販売期間中 ～2026/11/9(月) 23:59 発売開始 2026/10/3(土) 10:00～"
        self.assertEqual(
            p.detail_sale_window_from_text(text),
            ("2026-10-03T10:00", "2026-11-09T23:59"),
        )

    def test_detail_window_with_hiroshima_deadline(self):
        text = "販売期間中 ～2026/11/11(水) 23:59 発売開始 2026/10/3(土) 10:00～"
        self.assertEqual(
            p.detail_sale_window_from_text(text),
            ("2026-10-03T10:00", "2026-11-11T23:59"),
        )

    def test_detail_window_with_sale_start_before_deadline(self):
        text = "販売期間中 発売開始 2026/10/3(土) 10:00～ ～2026/11/9(月) 23:59"
        self.assertEqual(
            p.detail_sale_window_from_text(text),
            ("2026-10-03T10:00", "2026-11-09T23:59"),
        )

    def test_detail_lone_deadline_is_not_sale_start(self):
        text = "販売期間中 ～2026/11/9(月) 23:59"
        self.assertEqual(p.detail_sale_window_from_text(text), (None, "2026-11-09T23:59"))

    def test_generic_lone_period_date_is_left_ambiguous(self):
        text = "販売期間 2026/10/3(土) 10:00"
        self.assertEqual(p.detail_sale_window_from_text(text), (None, None))

    def test_official_schedule_keeps_richest_time_for_same_date(self):
        existing = [
            {
                "group": "CANDY TUNE",
                "title": "CANDY TUNE JAPAN TOUR 2026 -AUTUMN- CANDY CIRCUS",
                "sourceType": "derived",
                "schedule": [{"date": "2026-11-12", "venue": "広島文化学園HBGホール"}],
            },
            {
                "group": "CANDY TUNE",
                "title": "CANDY TUNE JAPAN TOUR 2026 -AUTUMN-",
                "sourceType": "official-schedule",
                "eventDate": "2026-11-12",
                "venue": "広島文化学園HBGホール",
                "openTime": "17:30",
                "startTime": "18:30",
            },
        ]
        self.assertEqual(
            p.official_schedule(
                existing,
                "CANDY TUNE",
                "CANDY TUNE JAPAN TOUR 2026 -AUTUMN- CANDY CIRCUS",
                "2026-11-12",
                None,
            ),
            [{
                "date": "2026-11-12",
                "venue": "広島文化学園HBGホール",
                "openTime": "17:30",
                "startTime": "18:30",
            }],
        )


if __name__ == "__main__":
    unittest.main()
