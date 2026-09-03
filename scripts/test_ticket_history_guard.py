import unittest
from datetime import date

import ticket_history_guard as g


class TicketHistoryGuardTests(unittest.TestCase):
    def test_explicit_annual_fee_sale_is_accepted(self):
        text = "CUTIE STREET FC会員 年会費コース会員限定先行受付 8/31 19:00〜9/7 23:59"
        self.assertTrue(g.has_explicit_annual_sale(text))
        self.assertFalse(g.is_upgrade_only_article(text))

    def test_upgrade_is_not_misclassified_as_annual_fee_sale(self):
        text = (
            "CUTIE STREET OFFICIAL FANCLUB会員先行受付のお知らせ。"
            "年会費コースへのアップグレード抽選受付も実施します。"
        )
        self.assertFalse(g.has_explicit_annual_sale(text))
        self.assertTrue(g.is_upgrade_only_article(text))

    def test_promoter_general_sale_start_survives_sold_out(self):
        text = "一般発売 SOLD OUT! 8/22(土)10:00〜 チケットぴあ"
        sale = g.extract_promoter_general_sale(text, "2026-09-14")
        self.assertIsNotNone(sale)
        self.assertEqual(sale["applyStart"], "2026-08-22T10:00")
        self.assertEqual(sale["applicationStatus"], "sold_out")
        self.assertTrue(sale["soldOutObserved"])

    def test_sale_year_rolls_back_when_month_is_after_event(self):
        text = "一般発売 12/20(日)10:00〜"
        sale = g.extract_promoter_general_sale(text, "2027-01-15")
        self.assertEqual(sale["applyStart"], "2026-12-20T10:00")

    def test_merge_does_not_duplicate_existing_general_sale(self):
        payload = {"events": [{
            "id": "existing",
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 梅田みゆ 生誕祭 2026",
            "eventDate": "2026-09-14",
            "ticketType": "一般発売",
            "applyStart": None,
            "urls": ["https://t.pia.jp/example"],
        }]}
        row = {
            "id": "guard",
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 梅田みゆ 生誕祭 2026",
            "eventDate": "2026-09-14",
            "ticketType": "一般発売",
            "applyStart": "2026-08-22T10:00",
            "applicationWindowVerified": True,
            "applicationWindowSource": "https://red-hot.ne.jp/play/detail.php?pid=py28451",
            "urls": ["https://red-hot.ne.jp/play/detail.php?pid=py28451"],
            "soldOutObserved": True,
        }
        added = g.merge_guard_rows(payload, [row])
        self.assertEqual(added, 0)
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["events"][0]["applyStart"], "2026-08-22T10:00")
        self.assertTrue(payload["events"][0]["soldOutObserved"])

    def test_invalid_annual_history_is_removed(self):
        history = {"entries": [
            {
                "id": "bad",
                "ticketType": "年会費コース会員先行",
                "sourceUrl": "https://cutiestreet.asobisystem.com/news/detail/87826",
            },
            {
                "id": "good",
                "ticketType": "年会費コース会員先行",
                "sourceUrl": "https://cutiestreet.asobisystem.com/news/detail/82705",
            },
        ]}
        removed = g.purge_invalid_history(
            history,
            ["https://cutiestreet.asobisystem.com/news/detail/87826"],
        )
        self.assertEqual(removed, 1)
        self.assertEqual([x["id"] for x in history["entries"]], ["good"])


if __name__ == "__main__":
    unittest.main()
