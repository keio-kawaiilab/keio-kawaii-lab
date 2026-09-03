import unittest

import ticket_classification_guard_v2 as g


class TicketClassificationGuardV2Tests(unittest.TestCase):
    def test_explicit_annual_sale_is_accepted(self):
        text = "FC会員 年会費コース会員限定先行受付\n受付期間 8/31 19:00〜9/7 23:59"
        self.assertTrue(g.has_explicit_annual_sale(text))
        self.assertIn("年会費コース", g.annual_sale_evidence(text))

    def test_upgrade_sentence_never_borrows_fc_sale_words_from_previous_sentence(self):
        text = (
            "CUTIE STREET OFFICIAL FANCLUB会員先行受付のお知らせ。"
            "年会費コースへのアップグレード抽選受付も実施します。"
        )
        self.assertFalse(g.has_explicit_annual_sale(text))

    def test_same_clause_upgrade_is_not_evidence(self):
        text = "年会費コース会員向けアップグレード抽選受付を実施"
        self.assertFalse(g.has_explicit_annual_sale(text))

    def test_legitimate_sale_and_separate_upgrade_can_coexist(self):
        text = (
            "年会費コース会員限定先行受付を開始します。"
            "お見送り会付指定席は後日アップグレードを実施します。"
        )
        self.assertTrue(g.has_explicit_annual_sale(text))

    def test_purge_only_matching_bad_source(self):
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
        self.assertEqual(
            g.purge_invalid_history(history, ["https://cutiestreet.asobisystem.com/news/detail/87826"]),
            1,
        )
        self.assertEqual([x["id"] for x in history["entries"]], ["good"])


if __name__ == "__main__":
    unittest.main()
