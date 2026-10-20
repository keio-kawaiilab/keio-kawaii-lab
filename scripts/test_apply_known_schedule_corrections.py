#!/usr/bin/env python3
import unittest

from apply_known_schedule_corrections import apply_known_corrections


class KnownScheduleCorrectionsTest(unittest.TestCase):
    def test_sweetest_story_keeps_two_future_starts_after_reception_ends(self):
        seed = {"id": "sweet", "group": "SWEET STEADY", "url": "https://sweetsteady.asobisystem.com/"}
        corrected, report = apply_known_corrections([seed])
        rows = [e for e in corrected if str(e.get("id")).startswith("known-sweetest-story")]
        self.assertEqual(report["sweetestStoryPerformancesAdded"], 2)
        self.assertEqual({(r["openTime"], r["startTime"]) for r in rows}, {("14:00", "15:00"), ("17:00", "18:00")})
        self.assertTrue(all(r["eventDate"] == "2026-11-15" and r["applyEnd"] == "2026-10-18T23:59" for r in rows))
        self.assertTrue(all(r["eventScope"] == "external" for r in rows))
        again, report = apply_known_corrections(corrected)
        self.assertEqual(again, corrected)
        self.assertEqual(report["sweetestStoryPerformancesAdded"], 0)
        # An actual collector occurrence replaces, rather than duplicates, one part.
        collected = {**rows[0], "id": "collector-part1"}
        corrected, report = apply_known_corrections([seed, collected])
        self.assertEqual(report["sweetestStoryPerformancesAdded"], 1)
        self.assertEqual(len(corrected), 3)

    def test_candy_birthdays_fill_missing_facts_and_merge_without_losing_sales(self):
        from performance_entities import build_public_events
        for day, person, news, central in (("2026-12-03", "村川緋杏", "92278", "92965"), ("2026-12-16", "福山梨乃", "91454", "92964")):
            annual = {"id": "annual", "group": "CANDY TUNE", "eventDate": day,
                      "title": "CANDY TUNE " + person + " 生誕祭 2026",
                      "venue": None, "startTime": None, "eventScope": "kawaii-lab",
                      "url": "https://candytune.asobisystem.com/news/detail/" + news,
                      "ticketType": "FC先行", "applyStart": "2026-10-02T18:00", "applyEnd": "2026-10-07T23:59"}
            fc = {**annual, "id": "central", "url": "https://kawaiilab.asobisystem.com/news/detail/" + central,
                  "ticketType": "KAWAII LAB. FC先行", "applyStart": "2026-10-17T18:00", "applyEnd": "2026-10-22T23:59",
                  "schedule": [{"date": day, "venue": None}]}
            known = {**annual, "id": "known", "venue": "SGCホール有明", "openTime": "17:30", "startTime": "19:00"}
            corrected, report = apply_known_corrections([annual, fc, known])
            self.assertEqual(report["candyBirthdayFactsFilled"], 2)
            self.assertIsNone(annual["venue"])
            self.assertEqual(fc["applyEnd"], corrected[1]["applyEnd"])
            self.assertEqual("19:00", corrected[1]["schedule"][0]["startTime"])
            public, _ = build_public_events(corrected)
            self.assertEqual(len(public), 1)
            self.assertEqual(set(public[0]["sourceRowIds"]), {"annual", "central", "known"})
            self.assertEqual(len(public[0]["offers"]), 2)
            self.assertEqual(public[0]["startTime"], "19:00")
            again, report = apply_known_corrections(corrected)
            self.assertEqual(again, corrected)
            self.assertEqual(report["candyBirthdayFactsFilled"], 0)

    def test_candy_birthday_facts_do_not_override_conflicts_or_unknown_sources(self):
        row = {"id": "test", "group": "CANDY TUNE", "eventDate": "2026-12-03", "title": "村川緋杏 生誕祭 2026",
               "url": "https://candytune.asobisystem.com/news/detail/92278"}
        for changes in ({"startTime": "20:00"}, {"venue": "別会場"}, {"eventDate": "2026-12-04"},
                        {"group": "CUTIE STREET"}, {"url": "https://candytune.asobisystem.com/news/detail/99999"},
                        {"schedule": [{"date": "2026-12-03", "startTime": "15:00"}]},
                        {"eventDates": ["2026-12-03", "2026-12-04"]}):
            original = {**row, **changes}
            corrected, report = apply_known_corrections([original])
            self.assertEqual(corrected, [original])
            self.assertEqual(report["candyBirthdayFactsFilled"], 0)

    def test_joy_live_is_added_without_inventing_ticket_window(self):
        seed = {"id": "fruits-official", "group": "FRUITS ZIPPER", "eventDate": "2026-10-26",
                "url": "https://fruitszipper.asobisystem.com/feature/2026tour_autumn"}
        events, report = apply_known_corrections([seed])
        joy = [e for e in events if e.get("id") == "known-fruits-joy-fanclub-live-20261108"]
        self.assertEqual(1, len(joy))
        self.assertEqual("2026-11-08", joy[0]["eventDate"])
        self.assertEqual("15:00", joy[0]["startTime"])
        self.assertNotIn("applyStart", joy[0])
        self.assertNotIn("applyEnd", joy[0])
        self.assertEqual("none", joy[0]["applicationStatus"])
        self.assertEqual(1, report["fruitsJoyFanclubLiveAdded"])
        again, report = apply_known_corrections(events)
        self.assertEqual(events, again)
        self.assertEqual(0, report["fruitsJoyFanclubLiveAdded"])

    def test_joy_live_does_not_duplicate_a_collector_row(self):
        source = {"id": "collected-joy", "group": "FRUITS ZIPPER", "eventDate": "2026-11-08",
                  "title": "FRUITS ZIPPER FANCLUB LIVE -じょい！×３-",
                  "url": "https://fruitszipper.asobisystem.com/news/detail/93201",
                  "applyStart": "2026-10-21T12:00"}
        corrected, report = apply_known_corrections([source])
        self.assertEqual([source], corrected)
        self.assertEqual(0, report["fruitsJoyFanclubLiveAdded"])

    def test_hiroshima_retained_lot_uses_each_official_occurrence(self):
        row = {"id": "old-pia-hiroshima", "group": "CUTIE STREET",
               "title": "CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-",
               "eventDate": "2026-11-14", "eventDates": ["2026-11-14", "2026-11-15"],
               "schedule": [{"date": "2026-11-14", "venue": None}, {"date": "2026-11-15", "venue": None}],
               "venue": "複数会場（全2公演）", "openTime": "16:00", "startTime": "16:00",
               "ticketType": "現在受付なし", "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=88970"}
        corrected, report = apply_known_corrections([row])
        self.assertEqual(1, report["cutieHiroshimaPiaFixed"])
        event = corrected[0]
        self.assertEqual(["18:00", "16:30"], [r["startTime"] for r in event["schedule"]])
        self.assertTrue(all(r["venue"] == "広島県 広島グリーンアリーナ" for r in event["schedule"]))
        self.assertEqual(row["id"], event["id"])
        self.assertEqual(row["url"], event["url"])
        from performance_entities import build_public_events
        official = {**event, "id": "official", "url": "https://cutiestreet.asobisystem.com/news/detail/92733",
                    "ticketType": "アップグレード抽選", "applyEnd": "2026-10-20T23:59"}
        public, _ = build_public_events([event, official])
        self.assertEqual(2, len(public))
        self.assertEqual({"18:00", "16:30"}, {e["startTime"] for e in public})
        self.assertTrue(all(e["offers"][0]["applyEnd"] == "2026-10-20T23:59" for e in public))
        again, report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, report["cutieHiroshimaPiaFixed"])

    def test_hiroshima_repair_does_not_touch_a_different_lot_or_date(self):
        for lot, day in (("88971", "2026-11-14"), ("88970", "2026-12-14")):
            row = {"id": lot, "group": "CUTIE STREET", "eventDate": day,
                   "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=" + lot,
                   "startTime": "13:00"}
            corrected, report = apply_known_corrections([row])
            self.assertEqual(row, corrected[0])
            self.assertEqual(0, report["cutieHiroshimaPiaFixed"])

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

        sweet = [row for row in corrected if row.get("group") == "SWEET STEADY"
                 and row.get("ticketType") == "FC先行" and row.get("applyEnd") == "2026-09-28T23:59"]
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


class CutieUpgradeReceptionTests(unittest.TestCase):
    def test_candy_tokyo_presale_is_two_occurrences_and_idempotent(self):
        anchor = {"id": "tour", "group": "CANDY TUNE", "eventDate": "2026-12-08",
                  "url": "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026"}
        result, report = apply_known_corrections([anchor])
        additions = [row for row in result if row.get("ticketType") == "プリセール（先着先行）"]
        self.assertEqual(2, report["candyTokyoPresaleAdded"])
        self.assertEqual([("2026-12-08", "19:00"), ("2026-12-09", "18:30")],
                         [(row["eventDate"], row["startTime"]) for row in additions])
        self.assertTrue(all(row["applyStart"] == "2026-10-17T12:00"
                            and row["applyEnd"] == "2026-10-22T23:59" for row in additions))
        again, report = apply_known_corrections(result)
        self.assertEqual(0, report["candyTokyoPresaleAdded"])
        self.assertEqual(result, again)
        _, report = apply_known_corrections([dict(anchor, group="SWEET STEADY")])
        self.assertEqual(0, report["candyTokyoPresaleAdded"])

    def test_collector_tokyo_presale_prevents_known_duplicate(self):
        event = {"id": "from-pia", "group": "CANDY TUNE", "eventDate": "2026-12-08",
                 "url": "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026",
                 "ticketType": "プリセール", "applyStart": "2026-10-17T12:00",
                 "applyEnd": "2026-10-22T23:59"}
        result, report = apply_known_corrections([event])
        self.assertEqual(1, report["candyTokyoPresaleAdded"])
        self.assertIn("from-pia", [row["id"] for row in result])
        self.assertNotIn("known-candy-tokyo-presale-20261208", [row["id"] for row in result])

    def fixture(self, day="2026-11-14"):
        return {
            "id": "retained-" + day, "group": "CUTIE STREET",
            "title": "広島・愛知 アップグレード抽選受付のお知らせ",
            "eventDate": day, "startTime": "18:00",
            "ticketType": "年会費コース会員先行",
            "applyStart": "2026-10-15T12:00", "applyEnd": "2026-10-20T23:59",
            "urls": ["https://cutiestreet.asobisystem.com/news/detail/92733"],
        }

    def test_four_occurrences_are_corrected_without_changing_identity_or_window(self):
        from apply_known_schedule_corrections import repair_cutie_upgrade_reception
        for day in ("2026-11-14", "2026-11-15", "2026-11-28", "2026-11-29"):
            original = self.fixture(day)
            expected = dict(original, ticketType="アップグレード抽選")
            self.assertEqual(expected, repair_cutie_upgrade_reception(original))
            self.assertEqual("年会費コース会員先行", original["ticketType"])
        result, report = apply_known_corrections([self.fixture()])
        self.assertEqual("アップグレード抽選", result[0]["ticketType"])
        self.assertEqual(1, report["cutieUpgradeReceptionFixed"])
        _, again = apply_known_corrections(result)
        self.assertEqual(0, again["cutieUpgradeReceptionFixed"])

    def test_other_articles_dates_windows_and_sale_types_are_untouched(self):
        from apply_known_schedule_corrections import repair_cutie_upgrade_reception
        for changes in (
            {"urls": ["https://cutiestreet.asobisystem.com/news/detail/other"]},
            {"eventDate": "2026-11-30"}, {"applyEnd": "2026-10-21T23:59"},
            {"applyStart": None}, {"ticketType": "一般販売"}, {"group": "CANDY TUNE"},
        ):
            event = dict(self.fixture(), **changes)
            self.assertEqual(event, repair_cutie_upgrade_reception(event))


class SweetOnlineReceptionRoundsTests(unittest.TestCase):
    def rows(self):
        common = {"group": "SWEET STEADY", "title": "SWEET STEADY オンライン特典会",
                  "eventDate": "2026-10-23", "startTime": "15:00", "eventCategory": "online-benefit",
                  "ticketType": "オンライン特典会・抽選販売", "sourceType": "sukisuki"}
        return [dict(common, id="first", url="https://sukisuki-shop.com/goods/6500000004624",
                     applyStart="2026-10-13T15:00", applyEnd="2026-10-14T23:59",
                     resultDate="2026-10-15", paymentEnd="2026-10-17T23:59"),
                dict(common, id="second", url="https://sukisuki-shop.com/goods/6500000004625",
                     applyStart="2026-10-18T15:00", applyEnd="2026-10-19T23:59",
                     resultDate="2026-10-20", paymentEnd="2026-10-21T23:59")]

    def test_same_stream_is_one_event_with_both_receipts_and_milestones(self):
        rows = self.rows()
        result, report = apply_known_corrections(rows)
        self.assertEqual(1, len(result))
        self.assertEqual(1, report["sweetOnline20261023RowsCollapsed"])
        self.assertEqual(["first", "second"], result[0]["sourceRowIds"])
        self.assertEqual(["2026-10-15", "2026-10-20"], [o["resultDate"] for o in result[0]["offers"]])
        self.assertEqual(["2026-10-17T23:59", "2026-10-21T23:59"], [o["paymentEnd"] for o in result[0]["offers"]])
        for key in ("applyStart", "applyEnd", "resultDate", "paymentEnd"):
            self.assertNotIn(key, result[0])
        self.assertEqual("オンライン特典会・抽選販売", rows[0]["ticketType"])
        again, report = apply_known_corrections(result)
        self.assertEqual(result, again)
        self.assertEqual(0, report["sweetOnline20261023RowsCollapsed"])
        refreshed, _ = apply_known_corrections([*result, *rows])
        self.assertEqual(1, len(refreshed))
        self.assertEqual(2, len(refreshed[0]["offers"]))

    def test_other_times_dates_goods_or_groups_are_never_forced_together(self):
        for change in ({"startTime": "18:00"}, {"eventDate": "2026-10-24"},
                       {"group": "CANDY TUNE"}, {"url": "https://sukisuki-shop.com/goods/unknown"}):
            rows = self.rows()
            rows[1].update(change)
            result, report = apply_known_corrections(rows)
            self.assertEqual(2, len(result))
            self.assertEqual(0, report["sweetOnline20261023RowsCollapsed"])


if __name__ == "__main__":
    unittest.main()


