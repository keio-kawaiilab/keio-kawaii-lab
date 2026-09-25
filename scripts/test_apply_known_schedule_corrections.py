#!/usr/bin/env python3
import unittest

from apply_known_schedule_corrections import apply_known_corrections


class KnownScheduleCorrectionsTest(unittest.TestCase):
    def test_verified_corrections_and_semantic_dedupe(self):
        events = [
            {
                "id": "hakata",
                "group": "CUTIE STREET",
                "title": "CUTIE STREET大特典会＠博多国際展示場【FC限定 1部・3部・6部】",
                "eventDate": "2026-09-27",
                "venue": "オンライン（SUKISUKI）",
                "eventCategory": "large-benefit",
                "offers": [{"provider": "sukisuki", "ticketType": "オンライン特典会", "url": "https://sukisuki-shop.com/goods/x"}],
            },
            {
                "id": "bad-pia-bundle",
                "group": "CUTIE STREET",
                "title": "CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-",
                "eventDate": "2026-09-23",
                "eventDates": ["2026-09-23", "2026-11-28", "2026-11-29"],
                "url": "https://t.pia.jp/pia/ticketInformation.do?eventCd=2635331&rlsCd=001",
            },
            {
                "id": "ig",
                "group": "CUTIE STREET",
                "title": "【CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-】@IGアリーナ",
                "eventDate": "2026-11-28",
                "venue": "複数会場（全2公演）",
                "openTime": "16:00",
                "startTime": "16:00",
                "schedule": [{"date": "2026-11-28"}, {"date": "2026-11-29"}],
                "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=52216",
            },
            {
                "id": "joint-xmas",
                "group": "KAWAII LAB.合同",
                "title": "KAWAII LAB. Christmas SESSION 2026",
                "eventDate": "2026-12-12",
                "participants": ["MORE STAR"],
            },
            {
                "id": "stale-more-xmas",
                "group": "MORE STAR",
                "title": "KAWAII LAB. Christmas SESSION 2026",
                "eventDate": "2026-12-12",
                "sourceStale": True,
            },
            {
                "id": "fm",
                "group": "SWEET STEADY",
                "title": "『FM AICHI 公開録音 SWEET STEADY SPECIAL LIVE』",
                "eventDate": "2026-10-18",
                "openTime": "12:00",
                "startTime": "12:00",
                "eventScope": "kawaii-lab",
                "schedule": [{"date": "2026-10-18", "openTime": "12:00", "startTime": "12:00"}],
            },
            {
                "id": "sweet-wrong",
                "group": "SWEET STEADY",
                "title": "「SWEET STEADY JAPAN TOUR 2026 -WINTER-」 開催決定！FC2次先行開始！",
                "eventDate": "2026-11-13",
                "startTime": "18:30",
                "ticketType": "FC先行",
                "applyStart": "2026-09-19T12:00",
                "applyEnd": "2026-09-28T23:59",
                "url": "https://sweetsteady.asobisystem.com/feature/sweetsteady_japanhalltour2026",
                "urls": ["https://sweetsteady.asobisystem.com/news/detail/89498"],
            },
            {
                "id": "sweet-correct",
                "group": "SWEET STEADY",
                "title": "「SWEET STEADY JAPAN TOUR 2026 -WINTER-」 開催決定！FC2次先行開始！",
                "eventDate": "2026-11-13",
                "startTime": "18:30",
                "ticketType": "FC先行",
                "applyStart": "2026-09-19T20:00",
                "applyEnd": "2026-09-28T23:59",
                "url": "https://sweetsteady.asobisystem.com/feature/sweetsteady_japanhalltour2026",
                "urls": ["https://sweetsteady.asobisystem.com/news/detail/89498"],
                "applicationWindowVerified": True,
            },
            {
                "id": "resale-auto",
                "group": "FRUITS ZIPPER",
                "title": "tour resale",
                "eventDate": "2026-11-05",
                "startTime": "18:30",
                "ticketType": "リセール",
                "applyStart": "2026-11-03T10:00",
                "applyEnd": "2026-11-04T23:59",
                "url": "https://fruitszipper.asobisystem.com/feature/2026tour_autumn",
                "sourceType": "auto",
            },
            {
                "id": "resale-official",
                "group": "FRUITS ZIPPER",
                "title": "tour resale",
                "eventDate": "2026-11-05",
                "startTime": "18:30",
                "ticketType": "公式リセール",
                "applyStart": "2026-11-03T10:00",
                "applyEnd": "2026-11-04T23:59",
                "url": "https://fruitszipper.asobisystem.com/feature/2026tour_autumn",
                "sourceType": "resale-official",
                "sourceChannel": "kawaii-lab-resale",
                "applicationWindowVerified": True,
            },
        ]

        corrected, report = apply_known_corrections(events)
        by_id = {row["id"]: row for row in corrected}

        hakata = by_id["hakata"]
        self.assertEqual(hakata["venue"], "福岡県 博多国際展示場＆カンファレンスセンター 3F")
        self.assertEqual(hakata["startTime"], "10:00")
        self.assertEqual(len(hakata["parts"]), 6)
        self.assertEqual(hakata["offers"], [])
        self.assertNotIn("bad-pia-bundle", by_id)

        ig = by_id["ig"]
        self.assertEqual(ig["venue"], "愛知県 IGアリーナ")
        self.assertEqual(ig["schedule"][0]["startTime"], "18:00")
        self.assertEqual(ig["schedule"][1]["openTime"], "14:30")
        self.assertEqual(ig["schedule"][1]["startTime"], "16:30")

        self.assertIn("joint-xmas", by_id)
        self.assertNotIn("stale-more-xmas", by_id)

        fm = by_id["fm"]
        self.assertEqual(fm["startTime"], "13:00")
        self.assertEqual(fm["eventScope"], "external")
        self.assertEqual(fm["organizer"], "FM AICHI")

        sweet = [row for row in corrected if row.get("group") == "SWEET STEADY" and row.get("ticketType") == "FC先行"]
        self.assertEqual(len(sweet), 1)
        self.assertEqual(sweet[0]["applyStart"], "2026-09-19T20:00")

        resale = [row for row in corrected if row.get("group") == "FRUITS ZIPPER" and "リセール" in str(row.get("ticketType") or "")]
        self.assertEqual(len(resale), 1)
        self.assertEqual(resale[0]["id"], "resale-official")

        self.assertEqual(report["hakataSpecialFixed"], 1)
        self.assertEqual(report["cutieWrongPiaBundleRemoved"], 1)
        self.assertEqual(report["cutieIgFixed"], 1)
        self.assertEqual(report["staleChristmasRowsRemoved"], 1)
        self.assertEqual(report["fmAichiFixed"], 1)
        self.assertEqual(report["sweetFcSecondStartFixed"], 1)
        self.assertEqual(report["semanticTicketDuplicatesRemoved"], 2)


if __name__ == "__main__":
    unittest.main()
