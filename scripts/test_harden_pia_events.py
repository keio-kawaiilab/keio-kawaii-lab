import unittest

import harden_pia_events as h


class HardenPiaEventsTests(unittest.TestCase):
    def test_exact_period_requires_both_bounds(self):
        text = "抽選受付期間 2026/8/15(土) 11:00 ～ 2026/8/25(火) 23:59"
        self.assertEqual(
            h.exact_period_from_text(text),
            ("2026-08-15T11:00", "2026-08-25T23:59"),
        )

    def test_deadline_only_is_not_treated_as_period(self):
        text = "抽選受付中 ～2026/8/25(火) 23:59"
        self.assertEqual(h.exact_period_from_text(text), (None, None))

    def test_pia_ui_label_is_never_valid_event_title(self):
        self.assertTrue(h.is_bad_title("行きたい!公演アラート"))
        self.assertTrue(h.is_bad_title("メールで通知"))
        self.assertFalse(h.is_bad_title("CANDY TUNE JAPAN TOUR 2026 - AUTUMN -"))

    def test_official_schedule_repairs_generic_title_and_venue(self):
        official = {
            "id": "official",
            "group": "CANDY TUNE",
            "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            "ticketType": "現在受付なし",
            "eventDate": "2026-08-29",
            "eventDates": ["2026-11-10", "2026-11-12"],
            "schedule": [
                {"date": "2026-11-10", "venue": "米子コンベンションセンター"},
                {"date": "2026-11-12", "venue": "広島文化学園HBGホール"},
            ],
            "primarySource": "official",
        }
        pia = {
            "id": "pia",
            "group": "CANDY TUNE",
            "title": "行きたい!公演アラート",
            "ticketType": "プレリザーブ",
            "eventDate": "2026-11-10",
            "eventDates": ["2026-11-10", "2026-11-12"],
            "sourceType": "pia",
            "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=20981",
        }
        fixed = h.repair_title_and_schedule(pia, [official, pia])
        self.assertEqual(fixed["title"], "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -")
        self.assertEqual(fixed["venue"], "複数会場（全2公演）")
        self.assertEqual(fixed["schedule"][0]["venue"], "米子コンベンションセンター")

    def test_validator_rejects_incomplete_public_pia_window(self):
        event = {
            "id": "x",
            "group": "CANDY TUNE",
            "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            "ticketType": "プレリザーブ",
            "applyStart": None,
            "applyEnd": "2026-08-25T23:59",
            "sourceType": "pia",
            "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=1",
        }
        problems = h.validate_public_pia([event])
        self.assertTrue(any("incomplete window" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()
