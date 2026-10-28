#!/usr/bin/env python3
import unittest

from apply_known_schedule_corrections import (
    CANDY_AICHI_SAME_DAY_NEWS,
    CANDY_AICHI_SCHEDULE,
    CUTIE_FUKUOKA_DAYS,
    CUTIE_FUKUOKA_PIA,
    CUTIE_FUKUOKA_TOUR,
    DISASTER_RELIEF_NEWS,
    DISASTER_RELIEF_PIA,
    MORE_STAR_7TH_FC,
    MORE_STAR_7TH_NEWS,
    MORE_STAR_PACIFICO_HMV,
    MORE_STAR_PACIFICO_NEWS,
    MORE_STAR_PACIFICO_SCHEDULE,
    SWEET_IDOL_HALLOWEEN_OFFICIAL,
    SWEET_IDOL_HALLOWEEN_SCHEDULE,
    SWEET_IDOL_HALLOWEEN_TICKET,
    apply_known_corrections,
)


class KnownScheduleCorrectionsTest(unittest.TestCase):
    def test_cutie_fukuoka_door_exchange_sales_are_one_offer_per_date(self):
        tour = {
            "id": "fukuoka-tour", "group": "CUTIE STREET",
            "title": "CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-",
            "eventDate": "2026-10-28", "eventEndDate": "2026-10-29",
            "eventDates": ["2026-10-28", "2026-10-29"],
            "url": CUTIE_FUKUOKA_TOUR,
            "urls": [details["schedule"] for details in CUTIE_FUKUOKA_DAYS.values()],
            "schedule": [
                {
                    "date": day, "venue": "福岡県 マリンメッセ福岡A館",
                    "openTime": details["openTime"], "startTime": details["startTime"],
                }
                for day, details in CUTIE_FUKUOKA_DAYS.items()
            ],
        }
        corrected, report = apply_known_corrections([tour])
        self.assertEqual(2, report["cutieFukuokaDoorExchangeOffersAdded"])
        offers = [row for row in corrected if row.get("ticketType") == "当日引換券"]
        self.assertEqual(["2026-10-28", "2026-10-29"], sorted(row["eventDate"] for row in offers))
        self.assertEqual(
            ["2026-10-27T23:59", "2026-10-28T23:59"],
            sorted(row["applyEnd"] for row in offers),
        )
        self.assertTrue(all(row["applyStart"] == "2026-10-21T10:00" for row in offers))
        self.assertTrue(all(row["url"] == CUTIE_FUKUOKA_PIA for row in offers))
        self.assertTrue(all(row["applicationWindowSource"] == CUTIE_FUKUOKA_TOUR for row in offers))
        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["cutieFukuokaDoorExchangeOffersAdded"])

    def test_candy_aichi_same_day_sale_is_scoped_to_one_tour_date(self):
        tour = {
            "id": "tour", "group": "CANDY TUNE", "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            "eventDate": "2026-10-27", "eventEndDate": "2026-10-29",
            "eventDates": ["2026-10-27", "2026-10-29"],
            "url": "https://candytune.asobisystem.com/feature/tour",
            "urls": [CANDY_AICHI_SCHEDULE],
            "schedule": [
                {"date": "2026-10-27", "venue": "愛知県 愛知県芸術劇場 大ホール", "openTime": "17:30", "startTime": "18:30"},
                {"date": "2026-10-29", "venue": "三重県 三重県文化会館大ホール", "openTime": "17:30", "startTime": "18:30"},
            ],
        }
        corrected, report = apply_known_corrections([tour])
        self.assertEqual(1, report["candyAichiSameDayOfferAdded"])
        sale = next(row for row in corrected if row["id"] == "known-candy-aichi-20261027-same-day")
        self.assertEqual(["2026-10-27"], sale["eventDates"])
        self.assertEqual("2026-10-27T17:30", sale["applyStart"])
        self.assertIsNone(sale["applyEnd"])
        self.assertEqual(CANDY_AICHI_SAME_DAY_NEWS, sale["applicationWindowSource"])
        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["candyAichiSameDayOfferAdded"])

    def test_candy_aichi_generic_collector_row_is_upgraded_without_duplication(self):
        generic = {
            "id": "official-news-candy-aichi",
            "group": "CANDY TUNE",
            "title": "愛知公演 当日券販売のお知らせ",
            "eventDate": "2026-10-27",
            "startTime": "18:30",
            "ticketType": "当日券",
            "applyStart": "2026-10-27T17:30",
            "applyEnd": None,
            "url": CANDY_AICHI_SAME_DAY_NEWS,
        }
        corrected, report = apply_known_corrections([generic])
        self.assertEqual(1, len(corrected))
        self.assertEqual(1, report["candyAichiSameDayOfferFixed"])
        self.assertEqual(0, report["candyAichiSameDayOfferAdded"])
        sale = corrected[0]
        self.assertEqual("known-candy-aichi-20261027-same-day", sale["id"])
        self.assertEqual("当日券（注釈付き指定席・会場販売）", sale["ticketType"])
        self.assertTrue(sale["applicationWindowVerified"])
        self.assertEqual(CANDY_AICHI_SAME_DAY_NEWS, sale["applicationWindowSource"])
        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["candyAichiSameDayOfferFixed"])
        self.assertEqual(0, second_report["candyAichiSameDayOfferAdded"])

    def test_more_star_pacifico_hmv_reservation_is_restored_once(self):
        schedule_only = {
            "id": "official-more-star-pacifico", "group": "MORE STAR",
            "title": "MORE STAR 大特典@パシフィコ横浜展示ホールD",
            "eventDate": "2026-11-03", "venue": "神奈川県 パシフィコ横浜展示ホールD",
            "ticketType": "現在受付なし", "applicationStatus": "none",
            "url": MORE_STAR_PACIFICO_SCHEDULE, "urls": [MORE_STAR_PACIFICO_SCHEDULE],
            "sourceType": "official-schedule", "primarySource": "official",
            "eventCategory": "large-benefit", "specialDetailsStatus": "awaiting-details",
        }
        corrected, report = apply_known_corrections([schedule_only])
        self.assertEqual(1, report["moreStarPacificoHmvOfferAdded"])
        sale = next(row for row in corrected if row["id"] == "known-more-star-pacifico-20261103-hmv")
        self.assertEqual(MORE_STAR_PACIFICO_HMV, sale["url"])
        self.assertEqual(MORE_STAR_PACIFICO_NEWS, sale["applicationWindowSource"])
        self.assertEqual("2026-10-27T23:59", sale["applyEnd"])
        self.assertEqual(6, len(sale["parts"]))
        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["moreStarPacificoHmvOfferAdded"])

    def test_sweet_idol_halloween_event_span_is_not_published_as_sale_window(self):
        stale = {
            "id": "misread-festival-span",
            "group": "SWEET STEADY",
            "title": "『IDOL HALLOWEEN JAPAN 2026 Supported by Malymoon』",
            "eventDate": "2026-10-30",
            "venue": "埼玉県 埼玉スタジアム2002",
            "ticketType": "チケット受付",
            "applyStart": "2026-10-30",
            "applyEnd": "2026-11-01",
            "url": SWEET_IDOL_HALLOWEEN_SCHEDULE,
            "sourceType": "auto",
            "sourceChannel": "official-continuous",
            "applicationWindowVerified": True,
        }
        corrected, report = apply_known_corrections([stale])
        self.assertEqual(1, report["sweetIdolHalloweenSaleFixed"])
        self.assertEqual("一般発売", corrected[0]["ticketType"])
        self.assertEqual("2026-09-25T17:00", corrected[0]["applyStart"])
        self.assertEqual("2026-10-29T23:59", corrected[0]["applyEnd"])
        self.assertEqual(SWEET_IDOL_HALLOWEEN_TICKET, corrected[0]["url"])
        self.assertEqual(SWEET_IDOL_HALLOWEEN_OFFICIAL, corrected[0]["applicationWindowSource"])
        self.assertTrue(corrected[0]["deadlineVerified"])
        self.assertIn(SWEET_IDOL_HALLOWEEN_SCHEDULE, corrected[0]["urls"])

        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["sweetIdolHalloweenSaleFixed"])

    def test_sweet_idol_halloween_verified_sale_is_restored_after_refresh_drops_it(self):
        schedule_only = {
            "id": "official-schedule-idol-halloween",
            "group": "SWEET STEADY",
            "title": "『IDOL HALLOWEEN JAPAN 2026 Supported by Malymoon』",
            "eventDate": "2026-10-30",
            "venue": "埼玉県 埼玉スタジアム2002",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "url": SWEET_IDOL_HALLOWEEN_SCHEDULE,
            "urls": [SWEET_IDOL_HALLOWEEN_SCHEDULE],
            "sourceType": "official-schedule",
            "primarySource": "official",
            "eventScope": "external",
        }
        corrected, report = apply_known_corrections([schedule_only])
        self.assertEqual(1, report["sweetIdolHalloweenSaleAdded"])
        relevant = [row for row in corrected if row.get("eventDate") == "2026-10-30"]
        self.assertEqual(2, len(relevant))
        sale = next(row for row in corrected if row["id"] == "known-sweet-idol-halloween-20261030-general")
        self.assertEqual("ticketdive", sale["ticketProvider"])
        self.assertEqual("2026-10-29T23:59", sale["applyEnd"])
        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["sweetIdolHalloweenSaleAdded"])

    def test_official_upgrade_title_overrides_misread_annual_course_eligibility(self):
        stale = {
            "id": "body-discovery-upgrade",
            "group": "CUTIE STREET",
            "title": "2026.10.09 「CUTIE STREET 古澤里紗 生誕祭 2026」 アップグレード抽選受付のお知らせ",
            "eventDate": "2026-11-09",
            "ticketType": "年会費コース会員先行",
            "primarySource": "official",
            "sourceType": "auto",
        }
        corrected, report = apply_known_corrections([stale])
        self.assertEqual("アップグレード抽選", corrected[0]["ticketType"])
        self.assertEqual(1, report["titleDeclaredUpgradeReceptionFixed"])

        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["titleDeclaredUpgradeReceptionFixed"])

    def test_title_declared_upgrade_does_not_rewrite_unrelated_or_nonofficial_rows(self):
        from apply_known_schedule_corrections import repair_title_declared_upgrade_reception

        base = {
            "title": "アップグレード抽選受付のお知らせ",
            "ticketType": "年会費コース会員先行",
            "primarySource": "official",
        }
        for changes in (
            {"title": "年会費コース会員先行受付のお知らせ"},
            {"ticketType": "FC先行"},
            {"primarySource": "pia"},
        ):
            row = dict(base, **changes)
            self.assertEqual(row, repair_title_declared_upgrade_reception(row))

    def test_cutie_sano_upgrade_restores_verified_open_start_and_offer_kind(self):
        source = "https://cutiestreet.asobisystem.com/news/detail/93573"
        stale = {
            "id": "official-schedule-sano-birthday",
            "group": "CUTIE STREET",
            "title": "佐野愛花 生誕祭 2026 @SGCホール有明",
            "eventDate": "2026-11-26",
            "venue": "東京都 SGCホール有明",
            "startTime": "17:30",
            "ticketType": "年会費コース会員先行",
            "applyStart": "2026-10-26T12:00",
            "applyEnd": "2026-10-29T23:59",
            "urls": [source],
            "discoverySourceUrl": source,
        }
        corrected, report = apply_known_corrections([stale])
        self.assertEqual("アップグレード抽選", corrected[0]["ticketType"])
        self.assertEqual("17:30", corrected[0]["openTime"])
        self.assertEqual("19:00", corrected[0]["startTime"])
        self.assertEqual(1, report["cutieSanoUpgradeReceptionFixed"])

        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["cutieSanoUpgradeReceptionFixed"])

    def test_cutie_sano_upgrade_offer_is_backfilled_on_verified_performance(self):
        performance = {
            "id": "sano-birthday-performance", "group": "CUTIE STREET",
            "title": "CUTIE STREET 佐野愛花 生誕祭 2026",
            "eventDate": "2026-11-26", "venue": "SGCホール有明",
            "openTime": "17:30", "startTime": "19:00",
            "ticketType": "現在受付なし", "eventScope": "kawaii-lab",
        }
        corrected, report = apply_known_corrections([performance])
        offer = next(row for row in corrected if row.get("id") == "known-cutie-sano-upgrade-20261126")
        self.assertEqual("アップグレード抽選", offer["ticketType"])
        self.assertEqual("2026-10-26T12:00", offer["applyStart"])
        self.assertEqual("2026-10-29T23:59", offer["applyEnd"])
        self.assertEqual(1, report["cutieSanoUpgradeOfferAdded"])

        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["cutieSanoUpgradeOfferAdded"])

    def test_cutie_sano_official_schedule_start_is_reconciled_to_news(self):
        schedule = "https://cutiestreet.asobisystem.com/live_information/detail/46341"
        stale = {
            "id": "official-schedule-sano", "group": "CUTIE STREET",
            "title": "佐野愛花 生誕祭 2026 @SGCホール有明",
            "eventDate": "2026-11-26", "venue": "東京都 SGCホール有明",
            "startTime": "17:30", "ticketType": "現在受付なし", "url": schedule,
        }
        corrected, report = apply_known_corrections([stale])
        self.assertEqual("17:30", corrected[0]["openTime"])
        self.assertEqual("19:00", corrected[0]["startTime"])
        self.assertEqual(1, report["cutieSanoScheduleTimeFixed"])

        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["cutieSanoScheduleTimeFixed"])

    def test_kawaiilab_free_live_keeps_one_performance_and_each_official_fc_route(self):
        from performance_entities import build_public_events

        seed = [
            {"id": group, "group": group, "url": "https://example.com/" + group}
            for group in ("CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR")
        ]
        corrected, report = apply_known_corrections(seed)
        self.assertEqual(1, report["kawaiilabFcFreeLiveAdded"])
        rows = [row for row in corrected if row.get("id") == "known-kawaiilab-fc-free-live-20261106"]
        self.assertEqual(1, len(rows))
        self.assertEqual(5, len(rows[0]["offers"]))
        self.assertEqual(
            {
                "CANDY TUNE FC先行", "SWEET STEADY FC先行", "CUTIE STREET FC先行",
                "MORE STAR FC先行", "KAWAII LAB. FC先行",
            },
            {offer["ticketType"] for offer in rows[0]["offers"]},
        )
        self.assertTrue(all("/feature/" in offer["url"] for offer in rows[0]["offers"]))
        self.assertTrue(all(offer["applicationWindowVerified"] is True for offer in rows[0]["offers"]))

        public, _ = build_public_events(corrected)
        free_live = [row for row in public if row.get("eventDate") == "2026-11-06"]
        self.assertEqual(1, len(free_live))
        self.assertEqual(5, len(free_live[0]["offers"]))
        self.assertEqual("複数受付", free_live[0]["ticketType"])

        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["kawaiilabFcFreeLiveAdded"])
        self.assertEqual(0, second_report["kawaiilabFcFreeLiveOffersUpdated"])

    def test_kawaiilab_free_live_restores_official_title_on_collected_schedule_row(self):
        from performance_entities import build_public_events

        collected = {
            "id": "collector-free-live",
            "group": "KAWAII LAB.合同",
            "title": "KAWAII LAB.",
            "eventTitle": "KAWAII LAB. ファンクラブ限定フリーライブ",
            "eventDate": "2026-11-06",
            "eventDates": ["2026-11-06"],
            "venue": "東京都 東京ガーデンシアター",
            "openTime": "16:30",
            "startTime": "18:00",
            "url": "https://kawaiilab.asobisystem.com/news/detail/93695",
        }
        generic_schedule = {
            "id": "official-schedule-free-live",
            "group": "KAWAII LAB.",
            "title": "KAWAII LAB.",
            "eventTitle": "KAWAII LAB.",
            "eventDate": "2026-11-06",
            "eventDates": ["2026-11-06"],
            "venue": "東京都 東京ガーデンシアター",
            "openTime": "16:30",
            "startTime": "18:00",
            "sourceType": "official-schedule",
            "primarySource": "official",
            "url": "https://kawaiilab.asobisystem.com/live_information/detail/46689",
        }
        context = [
            {"id": group, "group": group, "url": "https://example.com/" + group}
            for group in ("CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR")
        ]
        corrected, report = apply_known_corrections([*context, collected, generic_schedule])
        row = next(item for item in corrected if item.get("id") == "collector-free-live")
        self.assertEqual("KAWAII LAB. ファンクラブ限定フリーライブ", row["title"])
        self.assertEqual(row["title"], row["eventTitle"])
        schedule_row = next(
            item for item in corrected if item.get("id") == "official-schedule-free-live"
        )
        self.assertEqual(row["title"], schedule_row["title"])
        self.assertEqual(row["eventTitle"], schedule_row["eventTitle"])
        self.assertEqual(1, report["kawaiilabFcFreeLiveOffersUpdated"])

        public, _ = build_public_events(corrected)
        free_live = [item for item in public if item.get("eventDate") == "2026-11-06"]
        self.assertEqual(1, len(free_live))
        self.assertEqual("KAWAII LAB. ファンクラブ限定フリーライブ", free_live[0]["title"])

        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["kawaiilabFcFreeLiveOffersUpdated"])

    def test_kawaiilab_free_live_upgrades_single_candy_route_without_duplication(self):
        legacy = {
            "id": "known-kawaiilab-fc-free-live-20261106",
            "group": "KAWAII LAB.合同",
            "participants": ["CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR"],
            "title": "KAWAII LAB. ファンクラブ限定フリーライブ",
            "eventTitle": "KAWAII LAB. ファンクラブ限定フリーライブ",
            "eventDate": "2026-11-06",
            "eventDates": ["2026-11-06"],
            "venue": "東京都 東京ガーデンシアター",
            "startTime": "18:00",
            "ticketType": "FC先行",
            "applyStart": "2026-10-24T12:00",
            "applyEnd": "2026-10-26T23:59",
            "url": "https://candytune.asobisystem.com/news/detail/93706",
        }
        context = [
            {"id": group, "group": group, "url": "https://example.com/" + group}
            for group in ("CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR")
        ]
        corrected, report = apply_known_corrections([*context, legacy])
        rows = [row for row in corrected if "ファンクラブ限定フリーライブ" in str(row.get("title") or "")]
        self.assertEqual(1, len(rows))
        self.assertEqual(5, len(rows[0]["offers"]))
        self.assertNotIn("applyStart", rows[0])
        self.assertEqual(1, report["kawaiilabFcFreeLiveOffersUpdated"])

    def test_fruits_joy_fc_window_merges_into_the_known_performance(self):
        from performance_entities import build_public_events

        seed = {
            "id": "joy-performance",
            "group": "FRUITS ZIPPER",
            "title": "FRUITS ZIPPER FANCLUB LIVE -じょい！×３-",
            "eventDate": "2026-11-08",
            "venue": "東京都 東京ガーデンシアター",
            "openTime": "13:30",
            "startTime": "15:00",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "url": "https://fruitszipper.asobisystem.com/news/detail/93201",
            "eventScope": "kawaii-lab",
        }
        corrected, report = apply_known_corrections([seed])
        self.assertEqual(1, report["fruitsJoyFcOfferAdded"])
        offer_rows = [row for row in corrected if row.get("id") == "known-fruits-joy-fc-offer-20261108"]
        self.assertEqual(1, len(offer_rows))
        self.assertEqual("2026-10-24T12:00", offer_rows[0]["applyStart"])
        self.assertEqual("2026-10-27T23:59", offer_rows[0]["applyEnd"])
        self.assertEqual(
            "https://fruitszipper.asobisystem.com/news/detail/93670",
            offer_rows[0]["applicationWindowSource"],
        )

        public, _ = build_public_events(corrected)
        joy = next(row for row in public if row.get("eventDate") == "2026-11-08")
        self.assertEqual(1, len(joy["offers"]))
        self.assertEqual("FC先行", joy["offers"][0]["ticketType"])

        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["fruitsJoyFcOfferAdded"])

    def test_sweetest_story_observed_parts_have_consistent_external_scope_and_verified_times(self):
        source = "https://sweetsteady.asobisystem.com/news/detail/92529"
        rows = [
            {"id": "observed-1", "group": "SWEET STEADY",
             "eventDate": "2026-11-15",
             "eventTitle": "SWEET STEADYのSWEETEST STORY 第1部",
             "venue": "東京都 お台場特設会場（フジテレビ湾岸スタジオ）",
             "openTime": "14:00", "startTime": "15:00",
             "schedule": [{"date": "2026-11-15", "startTime": "18:00", "openTime": "17:00"}],
             "url": source, "eventScope": "external", "ticketType": "現在受付なし"},
            {"id": "observed-2", "group": "SWEET STEADY",
             "eventDate": "2026-11-15",
             "eventTitle": "SWEET STEADYのSWEETEST STORY 第2部",
             "venue": "東京都 お台場特設会場（フジテレビ湾岸スタジオ）",
             "openTime": "17:00", "startTime": "18:00", "url": source,
             "eventScope": "kawaii-lab", "ticketType": "SWEET STEADY FC先行",
             "applyStart": "2026-10-15T10:00", "applyEnd": None},
        ]
        corrected, report = apply_known_corrections(rows)
        self.assertEqual(0, report["sweetestStoryPerformancesAdded"])
        kept = [r for r in corrected if r["id"].startswith("observed-")]
        self.assertEqual(2, len(kept))
        self.assertTrue(all(r["eventScope"] == "external" for r in kept))
        self.assertEqual({"15:00", "18:00"}, {r["startTime"] for r in kept})
        self.assertTrue(all(r["schedule"][0]["startTime"] == r["startTime"] for r in kept))
        self.assertEqual({"SWEET STEADY FC先行"}, {r["ticketType"] for r in kept})
        self.assertEqual({"2026-10-15T10:00"}, {r["applyStart"] for r in kept})
        self.assertEqual({"2026-10-18T23:59"}, {r["applyEnd"] for r in kept})
        # Archive must retain TWO separate ended-sale rows, not just the
        # evening show and not a duplicated single performance.
        import archive_ticket_history as ticket_history
        registry = {
            "version": 1,
            "sources": {"group-official": {"kind": "official", "publishPolicy": "direct"}},
            "hostRules": {"sweetsteady.asobisystem.com": "group-official"},
        }
        history = ticket_history.archive_payload(
            {"events": kept}, {"entries": []}, registry, "2026-10-26T00:00:00+09:00",
        )
        self.assertEqual({"15:00", "18:00"}, {r["startTime"] for r in history["entries"]})
        self.assertTrue(all(r["publishable"] for r in history["entries"]))
        self.assertEqual(2, len(history["entries"]))
        again, _ = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)

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

    def test_joy_live_occurrence_stays_schedule_only_and_verified_offer_is_separate(self):
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
        offer = [e for e in events if e.get("id") == "known-fruits-joy-fc-offer-20261108"]
        self.assertEqual(1, len(offer))
        self.assertEqual("2026-10-24T12:00", offer[0]["applyStart"])
        self.assertEqual("2026-10-27T23:59", offer[0]["applyEnd"])
        again, report = apply_known_corrections(events)
        self.assertEqual(events, again)
        self.assertEqual(0, report["fruitsJoyFanclubLiveAdded"])
        self.assertEqual(0, report["fruitsJoyFcOfferAdded"])

    def test_joy_live_does_not_duplicate_a_collector_row(self):
        source = {"id": "collected-joy", "group": "FRUITS ZIPPER", "eventDate": "2026-11-08",
                  "title": "FRUITS ZIPPER FANCLUB LIVE -じょい！×３-",
                  "url": "https://fruitszipper.asobisystem.com/news/detail/93201",
                  "applyStart": "2026-10-21T12:00"}
        corrected, report = apply_known_corrections([source])
        self.assertEqual(source, corrected[0])
        self.assertEqual(2, len(corrected))
        self.assertEqual("known-fruits-joy-fc-offer-20261108", corrected[1]["id"])
        self.assertEqual(0, report["fruitsJoyFanclubLiveAdded"])
        self.assertEqual(1, report["fruitsJoyFcOfferAdded"])

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


    def test_christmas_session_gets_current_pia_presale_on_both_days(self):
        events = [
            {
                "id": "christmas-" + day,
                "group": "KAWAII LAB.合同",
                "title": "KAWAII LAB. Christmas SESSION 2026",
                "eventDate": day,
                "url": "https://kawaiilab.asobisystem.com/news/detail/84218",
            }
            for day in ("2026-12-12", "2026-12-13")
        ]
        corrected, report = apply_known_corrections(events)
        self.assertEqual(2, report["christmasPiaPresaleOffersAdded"])
        self.assertEqual({"2026-12-12", "2026-12-13"}, {row["eventDate"] for row in corrected})
        for event in corrected:
            self.assertEqual(1, len(event["offers"]))
            offer = event["offers"][0]
            self.assertEqual("プレリザーブ3次", offer["ticketType"])
            self.assertEqual("2026-10-21T18:00", offer["applyStart"])
            self.assertEqual("2026-10-25T23:59", offer["applyEnd"])
            self.assertEqual("2026-10-29T18:00", offer["resultDate"])
            self.assertEqual(
                "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=30327",
                offer["url"],
            )

        again, report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, report["christmasPiaPresaleOffersAdded"])

    def test_christmas_pia_presale_does_not_touch_unrelated_event(self):
        unrelated = {
            "id": "other",
            "group": "KAWAII LAB.合同",
            "title": "KAWAII LAB. 5th ANNIVERSARY TOUR",
            "eventDate": "2026-12-12",
        }
        corrected, report = apply_known_corrections([unrelated])
        self.assertEqual([unrelated], corrected)
        self.assertEqual(0, report["christmasPiaPresaleOffersAdded"])

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
        self.assertEqual("KAWAII LAB. FC先行", event["ticketType"])
        self.assertEqual("2026-10-17T18:00", event["applyStart"])
        self.assertEqual("2026-10-25T23:59", event["applyEnd"])
        self.assertIn("https://kawaiilab.asobisystem.com/news/detail/93036", event["urls"])
        self.assertNotIn("sourceStale", event)
        self.assertEqual(1, report["moreStarSeventhFixed"])

    def test_more_star_seventh_preserves_distinct_fc_reception_history(self):
        original = {
            "id": "original-fc",
            "group": "MORE STAR",
            "title": "2026.10.07 2026年11月25日（水）「MORE STAR 単独ライブ 7th STAR」開催決定！FC先行受付開始！",
            "eventDate": "2026-11-25",
            "ticketType": "FC先行",
            "applyStart": "2026-10-07T18:00",
            "applyEnd": "2026-10-12T23:59",
            "url": MORE_STAR_7TH_NEWS,
            "sourcePublishedAt": "2026-10-07",
            "discoverySourceUrl": MORE_STAR_7TH_NEWS,
        }
        kawaii_lab = {
            "id": "kawaii-lab-fc",
            "group": "MORE STAR",
            "title": "2026年11月25日（水）「MORE STAR 単独ライブ 7th STAR」開催決定！KAWAII LAB. OFFICIAL FANCLUB先行受付開始！",
            "eventDate": "2026-11-25",
            "ticketType": "KAWAII LAB. FC先行",
            "applyStart": "2026-10-17T18:00",
            "applyEnd": "2026-10-25T23:59",
            "url": MORE_STAR_7TH_NEWS,
            "sourcePublishedAt": "2026-10-17",
        }
        corrected, _ = apply_known_corrections([original, kawaii_lab])
        self.assertEqual(2, len(corrected))
        by_id = {event["id"]: event for event in corrected}
        self.assertEqual("2026-10-07T18:00", by_id["original-fc"]["applyStart"])
        self.assertEqual("2026-10-12T23:59", by_id["original-fc"]["applyEnd"])
        self.assertEqual(MORE_STAR_7TH_NEWS, by_id["original-fc"]["url"])
        self.assertNotIn(MORE_STAR_7TH_FC, by_id["original-fc"]["urls"])
        self.assertEqual("2026-10-17T18:00", by_id["kawaii-lab-fc"]["applyStart"])
        self.assertEqual("2026-10-25T23:59", by_id["kawaii-lab-fc"]["applyEnd"])
        self.assertEqual(MORE_STAR_7TH_FC, by_id["kawaii-lab-fc"]["applicationWindowSource"])

    def test_more_star_seventh_collapses_only_duplicate_current_reception(self):
        original = {
            "id": "original-fc", "group": "MORE STAR",
            "title": "2026.10.07 2026年11月25日（水）「MORE STAR 単独ライブ 7th STAR」開催決定！FC先行受付開始！",
            "eventDate": "2026-11-25", "ticketType": "FC先行",
            "applyStart": "2026-10-07T18:00", "applyEnd": "2026-10-12T23:59",
            "url": MORE_STAR_7TH_NEWS, "sourcePublishedAt": "2026-10-07",
            "discoverySourceUrl": MORE_STAR_7TH_NEWS,
        }
        canonical = {
            "id": "canonical-current", "group": "MORE STAR",
            "title": "MORE STAR 単独ライブ 7th STAR", "eventDate": "2026-11-25",
            "ticketType": "KAWAII LAB. FC先行",
            "applyStart": "2026-10-17T18:00", "applyEnd": "2026-10-25T23:59",
            "url": MORE_STAR_7TH_FC,
        }
        announcement = {
            **canonical, "id": "announcement-current",
            "title": "2026年11月25日（水）「MORE STAR 単独ライブ 7th STAR」開催決定！KAWAII LAB. OFFICIAL FANCLUB先行受付開始！",
            "sourcePublishedAt": "2026-10-17",
        }
        corrected, report = apply_known_corrections([original, canonical, announcement])
        self.assertEqual(2, len(corrected))
        self.assertEqual(1, report["semanticTicketDuplicatesRemoved"])
        self.assertEqual(["canonical-current"], report["semanticTicketDuplicateIds"])
        self.assertEqual(
            {"original-fc", "announcement-current"},
            {event["id"] for event in corrected},
        )

    def test_disaster_relief_concert_gets_verified_joint_facts_and_reception(self):
        row = {
            "id": "charity", "group": "FRUITS ZIPPER",
            "title": "災害支援基金コンサート",
            "eventDate": "2027-01-19", "url": DISASTER_RELIEF_NEWS,
        }
        corrected, report = apply_known_corrections([row])
        event = corrected[0]
        self.assertEqual("KAWAII LAB.合同", event["group"])
        self.assertEqual(["FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY"], event["participants"])
        self.assertEqual(("17:00", "18:00"), (event["openTime"], event["startTime"]))
        self.assertEqual(DISASTER_RELIEF_PIA, event["url"])
        self.assertEqual("pia", event["ticketProvider"])
        self.assertEqual(["official", "pia"], event["sourceCandidates"])
        self.assertTrue(event["applicationWindowVerified"])
        self.assertTrue(event["deadlineVerified"])
        self.assertEqual("2026-11-01T23:59", event["applyEnd"])
        self.assertEqual(1, report["disasterReliefConcertFixed"])

        duplicate = {**row, "id": "charity-schedule", "group": "CANDY TUNE",
                     "sourceType": "official-schedule",
                     "url": "https://candytune.asobisystem.com/live_information/detail/46043"}
        corrected, report = apply_known_corrections([row, duplicate])
        self.assertEqual(1, len(corrected))
        self.assertEqual(1, report["disasterReliefConcertRowsCollapsed"])
        self.assertIn("https://candytune.asobisystem.com/live_information/detail/46043", corrected[0]["urls"])

    def test_removes_birthday_row_whose_event_year_contradicts_title(self):
        impossible = {
            "id": "bad-year", "group": "CANDY TUNE",
            "title": "CANDY TUNE 小川奈々子 生誕祭 2026",
            "eventDate": "2027-08-26",
        }
        corrected, report = apply_known_corrections([impossible])
        self.assertEqual([], corrected)
        self.assertEqual(1, report["impossibleBirthdayYearRowsRemoved"])

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


class CandyOitaEplusLinkTests(unittest.TestCase):
    def test_only_verified_occurrence_provider_and_window_are_corrected(self):
        from apply_known_schedule_corrections import repair_candy_oita_eplus_link
        wrong = "https://eplus.jp/sf/detail/3923750001-P0030012P021001"
        correct = "https://eplus.jp/sf/detail/3923750001-P0030013P021001"
        row = {"id": "keep-id", "group": "CANDY TUNE", "eventDate": "2026-12-01", "startTime": "18:30",
               "url": wrong, "urls": [wrong, correct], "primarySource": "eplus", "ticketType": "先着 ★一般発売",
               "applyStart": "2026-09-26T10:00", "applyEnd": "2026-11-29T20:00",
               "applicationWindowSource": wrong, "deadlineSource": wrong}
        fixed = repair_candy_oita_eplus_link(row, row["group"], row["eventDate"], row["startTime"])
        self.assertEqual(correct, fixed["url"])
        self.assertEqual([correct], fixed["urls"])
        self.assertEqual(correct, fixed["deadlineSource"])
        self.assertEqual("keep-id", fixed["id"])
        self.assertEqual(wrong, row["url"])
        rows, report = apply_known_corrections([row])
        self.assertEqual(correct, rows[0]["url"])
        self.assertEqual(1, report["candyOitaEplusLinkFixed"])
        for changes in ({"eventDate": "2026-11-30"}, {"eventDate": "2026-12-02"},
                        {"startTime": "15:00"}, {"group": "CUTIE STREET"},
                        {"applyEnd": "2026-11-30T20:00"}, {"primarySource": "pia"},
                        {"ticketType": "抽選 プレオーダー受付"}, {"url": "https://example.com/other"}):
            other = dict(row, **changes)
            self.assertEqual(other, repair_candy_oita_eplus_link(other, other["group"], other["eventDate"], other["startTime"]))


class SweetCentralFcReceptionTests(unittest.TestCase):
    def fixture(self):
        return {"id": "recent-body", "group": "SWEET STEADY",
                "title": "SWEET STEADY 白石まゆみ BIRTHDAY LIVE 2026",
                "eventDate": "2026-12-08", "startTime": "19:00", "ticketType": "FC先行",
                "url": "https://kawaiilab.asobisystem.com/news/detail/92282",
                "applyStart": "2026-10-14T12:00", "applyEnd": "2026-10-20T23:59"}

    def test_exact_central_sale_label_is_corrected_and_idempotent(self):
        from apply_known_schedule_corrections import repair_sweet_shiraishi_central_fc
        original = self.fixture()
        corrected = repair_sweet_shiraishi_central_fc(original)
        self.assertEqual(dict(original, ticketType="KAWAII LAB. FC先行"), corrected)
        self.assertEqual("FC先行", original["ticketType"])
        self.assertEqual(corrected, repair_sweet_shiraishi_central_fc(corrected))
        rows, report = apply_known_corrections([original])
        self.assertEqual(1, report["sweetShiraishiCentralFcFixed"])
        self.assertEqual("KAWAII LAB. FC先行", rows[0]["ticketType"])

    def test_group_fc_and_other_times_windows_and_articles_remain_separate(self):
        from apply_known_schedule_corrections import repair_sweet_shiraishi_central_fc
        for changes in ({"url": "https://sweetsteady.asobisystem.com/news/detail/90613"},
                        {"eventDate": "2026-12-09"}, {"startTime": "15:00"},
                        {"group": "CANDY TUNE"}, {"applyStart": "2026-09-29T12:00"},
                        {"applyEnd": "2026-10-21T23:59"}, {"ticketType": "一般発売"}):
            row = dict(self.fixture(), **changes)
            self.assertEqual(row, repair_sweet_shiraishi_central_fc(row))


class SweetOnlineReceptionRoundsTests(unittest.TestCase):
    def test_ebichu_schedule_and_ended_fc_are_one_external_performance(self):
        from apply_known_schedule_corrections import _collapse_sweet_ebichu_20261116
        base = {"id": "schedule", "group": "SWEET STEADY", "eventDate": "2026-11-16",
                "startTime": "18:30", "openTime": "17:30", "eventScope": "external",
                "title": "私立恵比寿中学 放課後ロッケンロール -HYPER- 2026",
                "url": "https://sweetsteady.asobisystem.com/news/detail/91244",
                "ticketType": "現在受付なし"}
        receipt = dict(base, id="receipt", ticketType="チケット受付",
                       applyStart="2026-09-29T18:00", applyEnd="2026-10-04T23:59")
        result, count = _collapse_sweet_ebichu_20261116([base, receipt])
        self.assertEqual((1, 1), (count, len(result)))
        self.assertEqual("external", result[0]["eventScope"])
        self.assertEqual(["schedule", "receipt"], result[0]["sourceRowIds"])
        self.assertEqual("2026-10-04T23:59", result[0]["offers"][0]["applyEnd"])
        self.assertEqual((result, 0), _collapse_sweet_ebichu_20261116(result))
        again, _ = _collapse_sweet_ebichu_20261116([*result, base, receipt])
        self.assertEqual(1, len(again))
        self.assertEqual(1, len(again[0]["offers"]))
        for change in ({"eventDate": "2026-11-17"}, {"startTime": "19:00"},
                       {"url": "https://sweetsteady.asobisystem.com/news/detail/other"}):
            untouched = [base, dict(receipt, **change)]
            self.assertEqual((untouched, 0), _collapse_sweet_ebichu_20261116(untouched))

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


class PiaNoticeAndSweetWinterUpgradeTests(unittest.TestCase):
    def test_candy_niigata_official_and_playguide_rows_merge_into_one_performance(self):
        from performance_entities import build_public_events

        official = {
            "id": "official-niigata", "group": "CANDY TUNE",
            "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            "eventDate": "2026-11-17", "venue": "新潟県 新潟県民会館",
            "openTime": None, "startTime": None,
            "ticketType": "現在受付なし", "eventScope": "kawaii-lab",
            "url": "https://candytune.asobisystem.com/live_information/detail/40736",
            "schedule": [{"date": "2026-11-17", "venue": "新潟県 新潟県民会館",
                          "openTime": "17:30", "startTime": "18:30"}],
        }
        playguide = {
            "id": "eplus-niigata", "group": "CANDY TUNE",
            "title": "JAPAN TOUR 2026 - AUTUMN",
            "eventDate": "2026-11-17", "venue": "新潟県民会館 大ホール",
            "openTime": "17:30", "startTime": "18:30",
            "ticketType": "先着 ★一般発売", "applyStart": "2026-09-19T10:00",
            "applyEnd": "2026-11-15T18:00", "eventScope": "kawaii-lab",
            "url": "https://eplus.jp/sf/detail/3923750001",
        }
        bundled = {
            "id": "eplus-bundle", "group": "CANDY TUNE", "title": "CANDY TUNE",
            "eventTitle": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            "eventDate": "2026-11-17", "eventEndDate": "2026-11-19",
            "venue": "複数会場（全2公演）", "startTime": "18:30",
            "venues": ["新潟県民会館 大ホール", "本多の森北電ホール"],
            "schedule": [
                {"date": "2026-11-17", "venue": "新潟県民会館 大ホール",
                 "openTime": "17:30", "startTime": "18:30"},
                {"date": "2026-11-19", "venue": "本多の森北電ホール",
                 "openTime": "17:30", "startTime": "18:30"},
            ],
            "ticketType": "現在受付なし", "eventScope": "kawaii-lab",
            "url": "https://eplus.jp/sf/detail/3923750001",
        }

        corrected, report = apply_known_corrections([official, playguide, bundled])
        public, _ = build_public_events(corrected)
        niigata = [row for row in public if row.get("eventDate") == "2026-11-17"]

        self.assertEqual(3, report["candyNiigataVenueFixed"])
        self.assertEqual(1, len(niigata))
        self.assertEqual("新潟県 新潟県民会館 大ホール", niigata[0]["venue"])
        self.assertEqual(1, len(niigata[0]["offers"]))
        self.assertEqual("先着 ★一般発売", niigata[0]["offers"][0]["ticketType"])

        again, second_report = apply_known_corrections(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["candyNiigataVenueFixed"])

    def test_exact_pia_notice_offers_gain_result_time_without_new_band(self):
        row = {
            "id": "noel", "group": "FRUITS ZIPPER",
            "title": "FRUITS ZIPPER 早瀬ノエル 生誕祭 2026",
            "eventDate": "2026-12-17", "startTime": "19:00",
            "ticketType": "FC先行", "applyStart": "2026-10-09T12:00",
            "applyEnd": "2026-10-15T23:59",
            "url": "https://fruitszipper.asobisystem.com/news/detail/92290",
        }
        result, report = apply_known_corrections([row])
        corrected = next(item for item in result if item.get("id") == "noel")
        self.assertEqual(1, report["piaResultNoticesAttached"])
        self.assertEqual("2026-10-22T20:00", corrected["resultDate"])
        self.assertIn("https://kawaiilab.asobisystem.com/news/detail/93888", corrected["urls"])
        again, report = apply_known_corrections(result)
        self.assertEqual(result, again)
        self.assertEqual(0, report["piaResultNoticesAttached"])

    def test_pia_notice_result_metadata_survives_public_offer_generation(self):
        from performance_entities import build_public_events

        row = {
            "id": "noel", "group": "FRUITS ZIPPER",
            "title": "FRUITS ZIPPER 早瀬ノエル 生誕祭 2026",
            "eventDate": "2026-12-17", "startTime": "19:00", "venue": "Zepp Shinjuku",
            "eventScope": "kawaii-lab", "ticketType": "FC先行",
            "applyStart": "2026-10-09T12:00", "applyEnd": "2026-10-15T23:59",
            "url": "https://fruitszipper.asobisystem.com/news/detail/92290",
        }
        corrected, _ = apply_known_corrections([row])
        public, _ = build_public_events(corrected)
        performance = next(item for item in public if item.get("eventDate") == "2026-12-17")
        offer = performance["offers"][0]
        self.assertEqual("2026-10-22T20:00", offer["resultDate"])
        self.assertEqual("https://kawaiilab.asobisystem.com/news/detail/93888", offer["resultDateSource"])
        self.assertIn("マイページ", offer["resultDeliveryNotice"])

    def test_pia_notice_enriches_fifth_anniversary_tour(self):
        row = {
            "id": "tour", "group": "KAWAII LAB.合同", "eventDate": "2027-01-30",
            "eventTitle": "KAWAII LAB. 5th ANNIVERSARY TOUR", "ticketType": "FC先行",
            "applyStart": "2026-10-12T18:30", "applyEnd": "2026-10-18T23:59",
            "url": "https://kawaiilab.asobisystem.com/news/detail/92410",
        }
        corrected, report = apply_known_corrections([row])
        self.assertEqual("2026-10-23T18:00", corrected[0]["resultDate"])
        self.assertEqual(1, report["piaResultNoticesAttached"])

    def test_sweet_winter_upgrade_is_one_offer_per_occurrence(self):
        source = "https://sweetsteady.asobisystem.com/feature/sweetsteady_japanhalltour2026"
        seed = {"id": "tour", "group": "SWEET STEADY",
                "title": "SWEET STEADY JAPAN TOUR 2026 -WINTER-",
                "eventDate": "2026-11-13", "eventEndDate": "2026-12-18",
                "startTime": "18:30", "url": source, "ticketType": "現在受付なし"}
        result, report = apply_known_corrections([seed])
        upgrades = [row for row in result if row.get("ticketType") == "アップグレード抽選"]
        self.assertEqual(4, report["sweetWinterUpgradeOffersAdded"])
        self.assertEqual({"2026-11-13", "2026-12-03", "2026-12-06", "2026-12-18"},
                         {row["eventDate"] for row in upgrades})
        self.assertTrue(all(row["applyStart"] == "2026-10-23T18:00" and
                            row["applyEnd"] == "2026-10-26T23:59" for row in upgrades))
        self.assertTrue(all("https://sweetsteady.asobisystem.com/news/detail/93491" in row["urls"]
                            for row in upgrades))
        again, report = apply_known_corrections(result)
        self.assertEqual(result, again)
        self.assertEqual(0, report["sweetWinterUpgradeOffersAdded"])

    def test_sweet_winter_repairs_fc_deadline_title_and_current_presale(self):
        source = "https://sweetsteady.asobisystem.com/feature/sweetsteady_japanhalltour2026"
        seed = {
            "id": "tour", "group": "SWEET STEADY",
            "title": "「SWEET STEADY JAPAN TOUR 2026 -WINTER-」 開催決定!FC先行開始!",
            "eventTitle": "SWEET STEADY JAPAN TOUR 2026 -WINTER-」 開催決定",
            "eventDate": "2026-11-13", "eventEndDate": "2026-12-18",
            "venue": "複数会場（全4公演）", "startTime": "18:30",
            "url": source, "urls": [source], "ticketType": "SWEET STEADY FC先行",
            "applyStart": "2026-08-23T20:00", "applyEnd": "2026-11-13",
        }
        result, report = apply_known_corrections([seed])
        repaired = next(row for row in result if row.get("id") == "tour")
        self.assertEqual("2026-09-13T23:59", repaired["applyEnd"])
        self.assertEqual(
            "SWEET STEADY JAPAN TOUR 2026 -WINTER- Snow Sparkle",
            repaired["eventTitle"],
        )
        presales = [row for row in result if row.get("ticketType") == "プレリザーブ"]
        self.assertEqual(4, report["sweetWinterPresaleOffersAdded"])
        self.assertEqual(
            {"2026-11-13", "2026-12-03", "2026-12-06", "2026-12-18"},
            {row["eventDate"] for row in presales},
        )
        self.assertTrue(all(row["applyStart"] == "2026-10-25T12:00" and
                            row["applyEnd"] == "2026-10-28T23:59" for row in presales))
        self.assertTrue(all(row["url"] == "https://w.pia.jp/t/sweetsteady-winter2026/"
                            for row in presales))
        again, report = apply_known_corrections(result)
        self.assertEqual(result, again)
        self.assertEqual(0, report["sweetWinterPresaleOffersAdded"])

    def test_sweet_winter_atsugi_upgrade_merges_with_the_official_performance(self):
        from performance_entities import build_public_events

        source = "https://sweetsteady.asobisystem.com/feature/sweetsteady_japanhalltour2026"
        official = {
            "id": "atsugi-official", "group": "SWEET STEADY",
            "title": "SWEET STEADY JAPAN TOUR 2026 -WINTER-",
            "eventDate": "2026-11-13", "venue": "神奈川県 厚木市文化会館 大ホール",
            "openTime": "17:30", "startTime": "18:30", "url": source,
            "ticketType": "現在受付なし", "eventScope": "kawaii-lab",
            "primarySource": "official",
        }
        legacy_upgrade = {
            "id": "known-sweet-winter-upgrade-20261113", "group": "SWEET STEADY",
            "title": "SWEET STEADY JAPAN TOUR 2026 -WINTER- Snow Sparkle",
            "eventDate": "2026-11-13", "venue": "神奈川県 厚木市文化会館",
            "openTime": "17:30", "startTime": "18:30", "url": source,
            "urls": [source, "https://sweetsteady.asobisystem.com/news/detail/93491"],
            "ticketType": "アップグレード抽選", "applyStart": "2026-10-23T18:00",
            "applyEnd": "2026-10-26T23:59", "eventScope": "kawaii-lab",
            "primarySource": "official",
        }
        corrected, report = apply_known_corrections([official, legacy_upgrade])
        public, _ = build_public_events(corrected)
        atsugi = [row for row in public if row.get("eventDate") == "2026-11-13"]

        self.assertEqual(1, report["sweetWinterUpgradeOffersFixed"])
        self.assertEqual(1, len(atsugi))
        self.assertEqual("神奈川県 厚木市文化会館 大ホール", atsugi[0]["venue"])
        self.assertEqual(2, len(atsugi[0]["offers"]))
        self.assertEqual(
            {"アップグレード抽選", "プレリザーブ"},
            {offer["ticketType"] for offer in atsugi[0]["offers"]},
        )

    def test_cutie_pacifico_fc_lottery_repairs_occurrence_and_payment_deadline(self):
        row = {
            "id": "fc-lottery", "group": "CUTIE STREET",
            "title": "11/3 CUTIE STREET大特典会",
            "eventCategory": "large-benefit", "eventDate": "2026-11-03",
            "venue": "パシフィコ横浜",
            "schedule": [{"date": "2026-11-03", "venue": "パシフィコ横浜", "startTime": "11:20"}],
            "ticketType": "FC限定・対象商品応募（抽選）",
            "resultDate": "2026-10-27", "paymentEnd": "2026-12-02",
            "url": "https://cutiestreet.asobisystem.com/news/detail/93831",
        }
        result, report = apply_known_corrections([row])
        self.assertEqual(1, report["cutiePacificoFcLotteryFixed"])
        self.assertEqual("神奈川県 パシフィコ横浜 展示ホールD", result[0]["venue"])
        self.assertEqual(result[0]["venue"], result[0]["schedule"][0]["venue"])
        self.assertEqual("2026-10-28T23:59", result[0]["paymentEnd"])
        again, report = apply_known_corrections(result)
        self.assertEqual(result, again)
        self.assertEqual(0, report["cutiePacificoFcLotteryFixed"])

    def test_unrelated_rows_do_not_gain_notice_or_upgrade(self):
        unrelated = {"id": "other", "group": "CANDY TUNE", "eventDate": "2026-12-17",
                     "title": "Other", "ticketType": "FC先行",
                     "applyStart": "2026-10-09T12:00", "applyEnd": "2026-10-15T23:59",
                     "url": "https://candytune.asobisystem.com/news/detail/other"}
        result, report = apply_known_corrections([unrelated])
        self.assertEqual([unrelated], result)
        self.assertEqual(0, report["piaResultNoticesAttached"])
        self.assertEqual(0, report["sweetWinterUpgradeOffersAdded"])


class FruitsSynergyOnlineTests(unittest.TestCase):
    def test_two_reception_rounds_are_one_online_event_with_two_offers(self):
        official = "https://fruitszipper.asobisystem.com/live_information/detail/44318"
        first_goods = "https://sukisuki-shop.com/goods/6500000004023"
        second_goods = "https://sukisuki-shop.com/goods/6500000004943"
        common = {
            "group": "FRUITS ZIPPER",
            "title": "FRUITS ZIPPER 4th Anniversary 写真集 『SYNERGY』オンライン特典会",
            "eventDate": "2026-11-01", "startTime": "18:00",
            "venue": "オンライン（SUKISUKI）", "eventCategory": "online-benefit",
        }
        rows = [
            {"id": "official", "group": "FRUITS ZIPPER",
             "title": "FRUITS ZIPPER 4th Anniversary写真集 オンライン特典会",
             "eventTitle": "FRUITS ZIPPER 4th Anniversary写真集 オンライン特典会",
             "eventDate": "2026-11-01", "venue": "その他 オンライン",
             "eventCategory": "online-benefit", "ticketType": "現在受付なし",
             "url": official, "urls": [official]},
            {**common, "id": "initial", "ticketType": "オンライン特典会",
             "applyStart": "2026-08-28T18:00", "applyEnd": "2026-09-03T23:59",
             "resultDate": "2026-09-30", "url": first_goods, "urls": [first_goods]},
            {**common, "id": "additional", "ticketType": "オンライン特典会・先着販売",
             "applyStart": "2026-10-23T20:00", "applyEnd": "2026-11-01T18:30",
             "url": second_goods, "urls": [second_goods]},
        ]
        result, report = apply_known_corrections(rows)
        self.assertEqual(2, report["fruitsSynergy20261101RowsCollapsed"])
        synergy = [row for row in result if row.get("id") == "known-fruits-synergy-online-20261101"]
        self.assertEqual(1, len(synergy))
        self.assertEqual(official, synergy[0]["url"])
        self.assertEqual(2, len(synergy[0]["offers"]))
        self.assertEqual({first_goods, second_goods}, {offer["url"] for offer in synergy[0]["offers"]})
        self.assertEqual("2026-09-30", synergy[0]["offers"][0]["resultDate"])
        again, second_report = apply_known_corrections(result)
        self.assertEqual(result, again)
        self.assertEqual(0, second_report["fruitsSynergy20261101RowsCollapsed"])

    def test_different_online_event_is_not_collapsed(self):
        unrelated = {
            "id": "other", "group": "FRUITS ZIPPER", "title": "別のオンライン特典会",
            "eventDate": "2026-11-01", "startTime": "18:00",
            "venue": "オンライン（SUKISUKI）", "eventCategory": "online-benefit",
            "ticketType": "オンライン特典会", "url": "https://sukisuki-shop.com/goods/other",
        }
        result, report = apply_known_corrections([unrelated])
        self.assertEqual([unrelated], result)
        self.assertEqual(0, report["fruitsSynergy20261101RowsCollapsed"])


if __name__ == "__main__":
    unittest.main()
