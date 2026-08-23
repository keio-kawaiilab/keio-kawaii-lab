import unittest

import update_pia_events as p


class PiaParserTests(unittest.TestCase):
    def test_ticket_type(self):
        self.assertEqual(p.ticket_type("先行 プレリザーブ 抽選受付中"), "プレリザーブ")
        self.assertEqual(p.ticket_type("一般発売／CUTIE STREET"), "一般発売")
        self.assertEqual(p.ticket_type("先行 プレミアム ぴあNICOSカード限定"), "ぴあNICOSカード限定先行")

    def test_single_event_and_deadline(self):
        context = "一般発売 CUTIE STREET 2026/9/14(月) SGC HALL ARIAKE (東京都) 販売期間中 ～2026/9/13(日) 23:59 詳細へ"
        self.assertEqual(p.event_window(context), ("2026-09-14", None))
        self.assertEqual(p.sale_window(context), (None, "2026-09-13T23:59"))

    def test_event_range_before_sale_status(self):
        context = "プレリザーブ 2026/9/9(水) ～ 2026/9/10(木) 大阪国際会議場 抽選受付中 ～ 2026/8/23(日) 23:59"
        self.assertEqual(p.event_window(context), ("2026-09-09", "2026-09-10"))
        self.assertEqual(p.sale_window(context), (None, "2026-08-23T23:59"))

    def test_upcoming_general_sale_start(self):
        context = "一般発売 2026/9/14(月) SGC HALL ARIAKE 発売前 2026/8/22(土) 10:00より発売"
        self.assertEqual(p.sale_window(context), ("2026-08-22T10:00", None))


if __name__ == "__main__":
    unittest.main()
