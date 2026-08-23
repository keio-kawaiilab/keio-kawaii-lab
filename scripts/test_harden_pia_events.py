import unittest

import harden_pia_events as h


class DummyResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class DummySession:
    def __init__(self, text):
        self.text = text

    def get(self, *_args, **_kwargs):
        return DummyResponse(self.text)


class HardenPiaEventsTests(unittest.TestCase):
    def test_exact_period_requires_both_bounds(self):
        text = "抽選受付期間 2026/8/15(土) 11:00 ～ 2026/8/25(火) 23:59"
        self.assertEqual(
            h.exact_period_from_text(text),
            ("2026-08-15T11:00", "2026-08-25T23:59"),
        )

    def test_deadline_only_is_not_treated_as_source_period(self):
        text = "抽選受付中 ～2026/8/25(火) 23:59"
        self.assertEqual(h.exact_period_from_text(text), (None, None))
        self.assertEqual(h.deadline_from_text(text), "2026-08-25T23:59")

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
            "eventDates": ["2026-11-10", "2026-11-12"],
            "sourceType": "pia",
            "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=20981",
        }
        fixed = h.repair_title_and_schedule(pia, [official, pia])
        self.assertEqual(fixed["title"], "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -")
        self.assertEqual(fixed["venue"], "複数会場（全2公演）")

    def test_deadline_only_pia_is_kept_for_today_to_deadline_band(self):
        official = {
            "id": "official",
            "group": "CANDY TUNE",
            "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            "ticketType": "現在受付なし",
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
            "applyStart": None,
            "applyEnd": "2026-08-24T11:00",
            "eventDates": ["2026-11-10", "2026-11-12"],
            "sourceType": "pia",
            "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=20981",
        }
        kept, rejected = h.harden(
            [official, pia],
            DummySession("抽選受付中 ～2026/8/24(月) 11:00"),
        )
        self.assertFalse(rejected)
        fixed = next(x for x in kept if x.get("id") == "pia")
        self.assertEqual(fixed["title"], "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -")
        self.assertIsNone(fixed["applyStart"])
        self.assertEqual(fixed["applyEnd"], "2026-08-24T11:00")
        self.assertTrue(fixed["deadlineVerified"])
        self.assertEqual(fixed["applicationDisplayMode"], "band-from-today")
        self.assertEqual(h.validate_public_pia(kept), [])

    def test_pia_without_timing_is_still_kept(self):
        pia = {
            "id": "pia",
            "group": "CANDY TUNE",
            "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            "ticketType": "プレリザーブ",
            "eventDate": "2026-11-24",
            "sourceType": "pia",
            "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=21416",
        }
        kept, rejected = h.harden([pia], DummySession("販売情報"))
        self.assertFalse(rejected)
        self.assertEqual(kept[0]["applicationDisplayMode"], "pia-listing")
        self.assertEqual(h.validate_public_pia(kept), [])

    def test_pia_fc_and_upgrade_are_excluded(self):
        for label in ("FC先行", "アップグレード抽選"):
            pia = {
                "id": label,
                "group": "CANDY TUNE",
                "title": "CANDY TUNE LIVE",
                "ticketType": label,
                "eventDate": "2026-11-24",
                "sourceType": "pia",
                "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=x",
            }
            kept, rejected = h.harden([pia], DummySession("販売情報"))
            self.assertFalse(kept)
            self.assertTrue(rejected)

    def test_full_verified_period_keeps_actual_band(self):
        pia = {
            "id": "pia",
            "group": "CANDY TUNE",
            "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            "ticketType": "2次プレリザーブ",
            "eventDate": "2026-11-24",
            "sourceType": "pia",
            "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=21416",
        }
        kept, rejected = h.harden(
            [pia],
            DummySession("抽選受付期間 2026/8/17(月) 11:00 ～ 2026/8/25(火) 23:59"),
        )
        self.assertFalse(rejected)
        fixed = kept[0]
        self.assertEqual(fixed["applyStart"], "2026-08-17T11:00")
        self.assertEqual(fixed["applyEnd"], "2026-08-25T23:59")
        self.assertTrue(fixed["applicationWindowVerified"])
        self.assertEqual(fixed["applicationDisplayMode"], "band")


if __name__ == "__main__":
    unittest.main()
