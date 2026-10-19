#!/usr/bin/env python3
import unittest

from apply_known_schedule_corrections import apply_known_corrections


class KnownScheduleCorrectionsTest(unittest.TestCase):
    def test_candy_online_official_and_sukisuki_rows_become_one_event(self):
        official = {
            "id": "official-online",
            "group": "CANDY TUNE",
            "title": "CANDY TUNE オンライン特典会",
            "eventDate": "2026-10-20",
            "startTime": "17:00",
            "eventCategory": "online-benefit",
            "ticketType": "現在受付なし",
            "url": "https://candytune.asobisystem.com/live_information/detail/46277",
        }
        lottery = {
            "id": "sukisuki-lottery",
            "group": "CANDY TUNE",
            "title": "CANDY TUNE オンライン特典会",
            "eventDate": "2026-10-20",
            "startTime": "17:00",
            "eventCategory": "online-benefit",
            "ticketType": "オンライン特典会・抽選販売",
            "applyStart": "2026-10-13T21:00",
            "applyEnd": "2026-10-14T23:59",
            "resultDate": "2026-10-15",
            "paymentEnd": "2026-10-17T23:59",
            "url": "https://sukisuki-shop.com/goods/6500000004622",
            "sourceType": "sukisuki",
        }
        first_come = {
            "id": "sukisuki-first-come",
            "group": "CANDY TUNE",
            "title": "CANDY TUNE オンライン特典会",
            "eventDate": "2026-10-20",
            "startTime": "17:00",
            "eventCategory": "online-benefit",
            "ticketType": "オンライン特典会・先着販売",
            "applyStart": "2026-10-18T20:00",
            "applyEnd": "2026-10-20T17:00",
            "url": "https://sukisuki-shop.com/goods/6500000004623",
            "sourceType": "sukisuki",
        }
        corrected, report = apply_known_corrections([official, lottery, first_come])
        self.assertEqual(1, len(corrected))
        event = corrected[0]
        self.assertEqual("known-candy-tune-online-20261020", event["id"])
        self.assertEqual("複数受付", event["ticketType"])
        self.assertEqual(2, len(event["offers"]))
        self.assertEqual(
            {"オンライン特典会・抽選販売", "オンライン特典会・先着販売"},
            {offer["ticketType"] for offer in event["offers"]},
        )
        self.assertEqual(2, report["candyOnline20261020RowsCollapsed"])

    def test_more_star_seventh_uses_verified_single_performance_date(self):
        malformed = {
            "id": "more-star-7th",
            "group": "MORE STAR",
            "title": "MORE STAR 単独ライブ 7th STAR",
            "eventDate": "2026-11-12",
            "eventEndDate": "2026-11-25",
            "eventDates": ["2026-11-12", "2026-11-25"],
            "schedule": [
                {"date": "2026-11-12", "venue": "ヒューリックホール東京"},
                {"date": "2026-11-25", "venue": "ヒューリックホール東京"},
            ],
            "sourceStale": True,
        }
        corrected, report = apply_known_corrections([malformed])
        event = corrected[0]
        self.assertEqual("2026-11-25", event["eventDate"])
        self.assertEqual(["2026-11-25"], event["eventDates"])
        self.assertEqual(1, event["eventCount"])
        self.assertEqual("17:00", event["openTime"])
        self.assertEqual("18:00", event["startTime"])
        self.assertNotIn("sourceStale", event)
        self.assertEqual(1, report["moreStarSeventhFixed"])

    def test_more_star_gift_requires_verified_discovered_anchor(self):
        unrelated = [{
            "id": "other",
            "group": "CANDY TUNE",
            "title": "Other event",
            "eventDate": "2026-11-28",
        }]
        corrected, report = apply_known_corrections(unrelated)
        self.assertEqual(["other"], [row["id"] for row in corrected])
        self.assertEqual(0, report["giftMoreStarAdded"])

        anchor = {
            "id": "gift-candy",
            "group": "CANDY TUNE",
            "title": "GIFT 〜Girls Idol Festival Tokyo〜",
            "eventDate": "2026-11-28",
            "url": "https://www.gift-idol.jp/",
        }
        corrected, report = apply_known_corrections([anchor])
        self.assertEqual(
            {"gift-candy", "known-gift-more-star-20261128"},
            {row["id"] for row in corrected},
        )
        self.assertEqual(1, report["giftMoreStarAdded"])

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
                "id": "obsolete-pia",
                "group": "CUTIE STREET",
                "title": "CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-",
                "eventDate": "2026-09-23",
                "sourceChannel": "pia-ended-sale",
                "applicationStatus": "ended",
                "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=95188",
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
        self.assertNotIn("obsolete-pia", by_id)

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
        self.assertEqual(report["cutieObsoletePiaRowsRemoved"], 1)
        self.assertEqual(report["cutieIgFixed"], 1)
        self.assertEqual(report["staleChristmasRowsRemoved"], 1)
        self.assertEqual(report["fmAichiFixed"], 1)
        self.assertEqual(report["sweetFcSecondStartFixed"], 1)
        self.assertEqual(report["semanticTicketDuplicatesRemoved"], 2)


if __name__ == "__main__":
    unittest.main()
