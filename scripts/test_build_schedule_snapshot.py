import unittest

import build_schedule_snapshot as b


class ScheduleSnapshotTests(unittest.TestCase):
    def test_short_multi_date_schedule_lists_each_venue(self):
        event = {
            "schedule": [
                {"date": "2026-11-10", "venue": "米子コンベンションセンター"},
                {"date": "2026-11-12", "venue": "広島文化学園HBGホール"},
            ],
            "venue": "複数会場（全2公演）",
        }
        text = b.venue_text(event)
        self.assertIn("11/10 米子コンベンションセンター", text)
        self.assertIn("11/12 広島文化学園HBGホール", text)
        self.assertNotIn("複数会場（全2公演）", text)

    def test_long_tour_stays_summarized(self):
        event = {
            "schedule": [
                {"date": f"2026-11-{day:02d}", "venue": f"会場{day}"}
                for day in range(1, 8)
            ],
            "venue": "複数会場（全7公演）",
        }
        self.assertEqual(b.venue_text(event), "複数会場（全7公演）")

    def test_single_date_uses_venue_name(self):
        event = {"schedule": [{"date": "2026-10-01", "venue": "SGCホール有明"}]}
        self.assertEqual(b.venue_text(event), "SGCホール有明")

    def test_quoted_announcement_uses_only_performance_name(self):
        event = {
            "group": "KAWAII LAB.合同",
            "title": "「KAWAII LAB. Christmas SESSION 2026」@有明アリーナ アップグレード抽選受付のお知らせ",
        }
        self.assertEqual(
            b.display_title(event),
            "KAWAII LAB. Christmas SESSION 2026",
        )

    def test_quoted_fc_announcement_drops_ticket_wording(self):
        event = {
            "group": "SWEET STEADY",
            "title": "2027年3月4日(木)「SWEET STEADY 3rd ANNIVERSARY LIVE 2027」@日本武道館 開催決定！FC先行スタート！",
        }
        self.assertEqual(
            b.display_title(event),
            "SWEET STEADY 3rd ANNIVERSARY LIVE 2027",
        )


if __name__ == "__main__":
    unittest.main()
