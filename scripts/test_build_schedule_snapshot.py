import unittest
from datetime import datetime

import build_schedule_snapshot as b
import fix_schedule_shell as shell


class ScheduleSnapshotTests(unittest.TestCase):
    def test_runtime_parses_ticket_moments_as_jst(self):
        page = "<script>" + shell.MOMENT_LOCAL_JS + "</script>"
        patched = shell.install_jst_ticket_moments(page)
        self.assertIn("Date.UTC", patched)
        self.assertIn("h-9", patched)
        self.assertNotIn("return new Date(+m[1],+m[2]-1,+m[3]", patched)
        self.assertEqual(patched, shell.install_jst_ticket_moments(patched))

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

    def test_joint_special_keeps_participant_names(self):
        event = {
            "group": "KAWAII LAB.合同",
            "displayTitle": "CUTIE STREET／MORE STAR 大特典会",
        }
        self.assertEqual(
            "CUTIE STREET／MORE STAR 大特典会",
            b.display_title(event),
        )

    def test_special_card_renders_each_current_offer_instead_of_parent_none(self):
        event = {
            "id": "joint",
            "group": "KAWAII LAB.合同",
            "eventScope": "kawaii-lab",
            "eventCategory": "large-benefit",
            "displayTitle": "CUTIE STREET／MORE STAR 大特典会",
            "eventDate": "2026-11-03",
            "venue": "パシフィコ横浜 展示ホールD",
            "ticketType": "現在受付なし",
            "offers": [
                {"sourceGroup": "KAWAII LAB.合同", "provider": "hmv", "ticketType": "対象商品予約", "applyStart": "2026-10-23T21:00", "applyEnd": "2026-10-27T23:59", "applicationWindowSource": "https://cutiestreet.asobisystem.com/news/detail/1", "url": "https://example.com/cutie"},
                {"sourceGroup": "KAWAII LAB.合同", "provider": "hmv", "ticketType": "対象商品予約", "applyStart": "2026-10-23T21:00", "applyEnd": "2026-10-27T23:59", "applicationWindowSource": "https://morestar.asobisystem.com/news/detail/2", "url": "https://example.com/more"},
                {"sourceGroup": "CUTIE STREET", "provider": "sukisuki", "ticketType": "FC抽選", "applyStart": "2026-10-23T21:00", "applyEnd": "2026-10-24T23:59", "url": "https://example.com/ended"},
            ],
        }
        page = b.build_card(event, datetime(2026, 10, 27, 2, 0, tzinfo=b.JST))
        self.assertIn("受付中（2件）", page)
        self.assertIn("CUTIE STREET / HMV", page)
        self.assertIn("MORE STAR / HMV", page)
        self.assertNotIn("https://example.com/ended", page)
        self.assertNotIn("<b>受付</b>現在受付なし", page)


if __name__ == "__main__":
    unittest.main()
