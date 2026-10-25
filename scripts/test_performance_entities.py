#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from performance_entities import build_public_events


class PerformanceEntitiesTest(unittest.TestCase):
    def test_guard_rejected_ticket_row_is_schedule_only(self):
        row = {
            "id": "rejected-annual",
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 古澤里紗 生誕祭 2026",
            "eventDate": "2026-11-09",
            "startTime": "19:00",
            "venue": "SGCホール有明",
            "url": "https://cutiestreet.asobisystem.com/news/detail/92297",
            "ticketType": "年会費コース会員先行",
            "applyStart": "2026-10-09T12:00",
            "applyEnd": "2026-10-14T23:59",
            "ticketGuardRejected": True,
            "ticketGuardReason": "upgrade notice cannot support an annual-fee ticket sale",
        }
        public, _ = build_public_events([row])
        self.assertEqual(1, len(public))
        self.assertEqual([], public[0]["offers"])
        self.assertEqual("現在受付なし", public[0]["ticketType"])
        self.assertEqual("schedule-only", public[0]["applicationDisplayMode"])

    def test_verified_oita_offer_does_not_reuse_fukuoka_application_link(self):
        fukuoka = "https://eplus.jp/sf/detail/3923750001-P0030012P021001"
        oita = "https://eplus.jp/sf/detail/3923750001-P0030013P021001"
        offer = {"sourceRowId": "legacy-sale", "provider": "eplus", "url": fukuoka,
                 "urls": [fukuoka, fukuoka + "?P1=0175", oita], "ticketType": "先着 ★一般発売",
                 "applyStart": "2026-09-26T10:00", "applyEnd": "2026-11-29T20:00"}
        bundled = {"id": "legacy-bundle", "group": "CANDY TUNE", "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                   "eventScope": "kawaii-lab", "eventDate": "2026-11-30", "eventEndDate": "2026-12-01",
                   "eventDates": ["2026-11-30", "2026-12-01"], "startTime": "18:30", "offers": [offer],
                   "schedule": [{"date": "2026-11-30", "venue": "福岡サンパレス", "startTime": "18:30"},
                                {"date": "2026-12-01", "venue": "大分iichikoグランシアタ", "startTime": "18:30"}]}
        direct = dict(bundled, id="oita-direct", eventDate="2026-12-01", eventDates=["2026-12-01"],
                      schedule=[bundled["schedule"][1]], offers=[dict(offer, sourceRowId="oita-sale", url=oita, urls=[oita])])
        original = deepcopy([bundled, direct])
        public, _ = build_public_events(original)
        self.assertEqual([bundled, direct], original)
        self.assertEqual(2, len(public))
        by_day = {e["eventDate"]: e for e in public}
        for day, url in (("2026-11-30", fukuoka), ("2026-12-01", oita)):
            self.assertEqual(1, len(by_day[day]["offers"]))
            self.assertEqual(url, by_day[day]["offers"][0]["url"])
            self.assertEqual("2026-11-29T20:00", by_day[day]["offers"][0]["applyEnd"])
        self.assertEqual({"legacy-bundle", "oita-direct"}, set(by_day["2026-12-01"]["sourceRowIds"]))
        again, _ = build_public_events(public)
        self.assertEqual([(e["eventDate"], e["offers"][0]["url"]) for e in public],
                         [(e["eventDate"], e["offers"][0]["url"]) for e in again])

    def christmas_fixture(self):
        rows = []
        for day, opened, start in (("2026-12-12", "15:00", "17:00"), ("2026-12-13", "14:00", "16:00")):
            for group in ("FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR", "KAWAII LAB. MATES", "KAWAII LAB. SOUTH"):
                rows.append({
                    "id": group + day, "group": group,
                    "title": "2026.08.22 KAWAII LAB. Christmas SESSION 2026 アップグレード抽選受付",
                    "eventDate": day, "venue": "有明アリーナ",
                    "openTime": opened, "startTime": start,
                    "url": "https://kawaiilab.asobisystem.com/news/detail/87775",
                    "ticketType": "アップグレード", "applyStart": "2026-08-22T12:00",
                    "applyEnd": "2026-08-30T23:59", "sourceType": "auto",
                    "primarySource": "official", "eventScope": "kawaii-lab",
                })
            rows.append({
                "id": "joint" + day, "group": "KAWAII LAB.合同",
                "title": "KAWAII LAB. Christmas SESSION 2026 Day" + ("1" if day.endswith("12") else "2"),
                "eventDate": day, "venue": "有明アリーナ",
                "schedule": [{"date": day, "venue": "有明アリーナ", "openTime": "15:00", "startTime": "17:00"}],
                "url": "https://kawaiilab.asobisystem.com/live_information/detail/" + ("44571" if day.endswith("12") else "44572"),
                "sourceType": "official-schedule", "primarySource": "official",
                "eventScope": "kawaii-lab",
            })
        return rows

    def test_christmas_joint_performances_keep_days_history_and_raw_rows(self):
        rows = self.christmas_fixture()
        original = deepcopy(rows)
        public, _ = build_public_events(rows)
        self.assertEqual(rows, original)
        self.assertEqual(len(public), 2)
        self.assertEqual({(row["eventDate"], row["openTime"], row["startTime"]) for row in public}, {
            ("2026-12-12", "15:00", "17:00"), ("2026-12-13", "14:00", "16:00"),
        })
        for event in public:
            self.assertEqual(event["group"], "KAWAII LAB.合同")
            self.assertEqual(len(event["participants"]), 7)
            self.assertEqual(len(event["sourceRowIds"]), 8)
            self.assertEqual(len(event["offers"]), 1)
            self.assertEqual(event["offers"][0]["applyEnd"], "2026-08-30T23:59")
            self.assertIn("https://kawaiilab.asobisystem.com/news/detail/87775", event["urls"])
            self.assertEqual(len(event["performanceFactSources"]), 2)

    def test_out_of_scope_solo_groups_are_not_published_but_joint_sources_remain(self):
        joint_rows = self.christmas_fixture()[:8]
        solo_rows = [
            {
                "id": "mates-solo",
                "group": "KAWAII LAB. MATES",
                "title": "KAWAII LAB. MATES 定期公演",
                "eventDate": "2026-11-12",
                "venue": "ヒューリックホール東京",
                "startTime": "19:00",
                "eventScope": "external",
            },
            {
                "id": "south-solo",
                "group": "KAWAII LAB. SOUTH",
                "title": "KAWAII LAB. SOUTH 単独公演",
                "eventDate": "2026-11-13",
                "venue": "Zepp Fukuoka",
                "startTime": "19:00",
                "eventScope": "external",
            },
        ]

        public, report = build_public_events(joint_rows + solo_rows)

        self.assertEqual(["KAWAII LAB.合同"], [event.get("group") for event in public])
        self.assertIn("KAWAII LAB. MATES", public[0]["participants"])
        self.assertIn("KAWAII LAB. SOUTH", public[0]["participants"])
        self.assertEqual(2, report["outOfScopeSoloEventCount"])

    def test_christmas_unknown_source_date_and_distinct_start_are_not_forced(self):
        original = self.christmas_fixture()[0]
        unknown = dict(original, id="unknown", group="CUTIE STREET", url="https://cutiestreet.asobisystem.com/news/detail/99999")
        other_day = dict(original, id="other-day", eventDate="2026-12-14")
        other_start = dict(original, id="other-start", startTime="20:00")
        public, _ = build_public_events([original, unknown, other_day, other_start])
        self.assertEqual(len(public), 4)
        self.assertEqual(len([e for e in public if e["group"] == "KAWAII LAB.合同"]), 2)
        self.assertTrue(any(e.get("startTime") == "20:00" for e in public))

    def test_christmas_day2_new_time_is_not_overwritten_by_old_correction(self):
        row = self.christmas_fixture()[-1]
        row["schedule"][0].update(openTime="18:00", startTime="20:00")
        public, _ = build_public_events([row])
        self.assertEqual(public[0]["startTime"], "20:00")

    def fixture(self):
        return [
            {
                "id": "tour-master",
                "group": "CANDY TUNE",
                "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                "eventTitle": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                "ticketType": "現在受付なし",
                "applicationStatus": "none",
                "eventDate": "2026-10-08",
                "eventEndDate": "2026-10-09",
                "eventDates": ["2026-10-08", "2026-10-09"],
                "eventCount": 2,
                "venue": "複数会場（全2公演）",
                "url": "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026",
                "urls": ["https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026"],
                "officialTourUrl": "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026",
                "sourceType": "derived",
                "primarySource": "official",
                "eventScope": "kawaii-lab",
                "schedule": [
                    {
                        "date": "2026-10-08",
                        "venue": "宮城県 仙台サンプラザホール",
                        "openTime": "17:30",
                        "startTime": "18:30",
                    },
                    {
                        "date": "2026-10-09",
                        "venue": "栃木県 宇都宮市文化会館 大ホール",
                        "openTime": "17:30",
                        "startTime": "18:30",
                    },
                ],
            },
            {
                "id": "fc-sendai",
                "group": "CANDY TUNE",
                "title": "2026.07.05 CANDY TUNE JAPAN TOUR 2026 - AUTUMN - 開催決定！FC先行開始！",
                "eventTitle": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                "ticketType": "FC先行",
                "applyStart": "2026-07-05T18:00",
                "applyEnd": "2026-07-13T23:59",
                "eventDate": "2026-10-08",
                "venue": "宮城県 仙台サンプラザホール",
                "openTime": "17:30",
                "startTime": "18:30",
                "url": "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026",
                "sourceType": "auto",
                "primarySource": "official",
                "eventScope": "kawaii-lab",
            },
            {
                "id": "eplus-sendai",
                "group": "CANDY TUNE",
                "title": "CANDY TUNE",
                "eventTitle": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                "ticketType": "先着 ★一般発売",
                "ticketProvider": "eplus",
                "applyStart": "2026-09-05T10:00",
                "applyEnd": "2026-10-05T18:00",
                "eventDate": "2026-10-08",
                "venue": "仙台サンプラザホール",
                "openTime": "17:30",
                "startTime": "18:30",
                "url": "https://eplus.jp/sendai",
                "sourceType": "eplus",
                "primarySource": "eplus",
                "eventScope": "kawaii-lab",
            },
            {
                "id": "lawson-multi",
                "group": "CANDY TUNE",
                "title": "CANDY TUNE",
                "eventTitle": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                "ticketType": "現在受付なし",
                "ticketProvider": "lawson",
                "eventDate": "2026-10-08",
                "eventDates": ["2026-10-08", "2026-10-09"],
                "schedule": [
                    {"date": "2026-10-08", "venue": "仙台サンプラザホール"},
                    {"date": "2026-10-09", "venue": "宇都宮市文化会館 大ホール"},
                ],
                "url": "https://l-tike.com/order/example",
                "sourceType": "derived",
                "primarySource": "lawson",
                "eventScope": "kawaii-lab",
            },
            {
                "id": "other-show",
                "group": "CANDY TUNE",
                "title": "別の単独公演",
                "eventTitle": "別の単独公演",
                "ticketType": "現在受付なし",
                "eventDate": "2026-10-08",
                "venue": "別会場",
                "startTime": "20:00",
                "url": "https://candytune.asobisystem.com/live_information/detail/example",
                "sourceType": "official-schedule",
                "primarySource": "official",
                "eventScope": "kawaii-lab",
            },
            {
                "id": "external",
                "group": "CANDY TUNE",
                "title": "外部フェス",
                "eventDate": "2026-10-08",
                "venue": "外部会場",
                "startTime": "18:30",
                "ticketType": "現在受付なし",
                "eventScope": "external",
            },
        ]

    def test_one_physical_performance_contains_multiple_ticket_offers(self):
        public, report = build_public_events(self.fixture())
        sendai = [
            event for event in public
            if event.get("entityType") == "performance"
            and event.get("group") == "CANDY TUNE"
            and event.get("eventDate") == "2026-10-08"
            and event.get("startTime") == "18:30"
        ]
        self.assertEqual(len(sendai), 1)
        event = sendai[0]
        self.assertEqual(event["venue"], "宮城県 仙台サンプラザホール")
        self.assertEqual(event["openTime"], "17:30")
        self.assertEqual(event["ticketType"], "複数受付")
        self.assertEqual({offer["ticketType"] for offer in event["offers"]}, {"FC先行", "先着 ★一般発売"})
        self.assertEqual({offer["provider"] for offer in event["offers"]}, {"official", "eplus"})
        self.assertTrue({"tour-master", "fc-sendai", "eplus-sendai", "lawson-multi"}.issubset(set(event["sourceRowIds"])))
        self.assertGreaterEqual(report["mergedSourceOccurrences"], 3)

    def test_same_central_fc_window_with_generic_alias_is_one_offer(self):
        base = {
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 佐野愛花 生誕祭 2026",
            "eventDate": "2026-11-26",
            "venue": "SGCホール有明",
            "startTime": "19:00",
            "ticketType": "FC先行",
            "applyStart": "2026-10-20T12:00",
            "applyEnd": "2026-10-25T23:59",
            "url": "https://kawaiilab.asobisystem.com/news/detail/92827",
            "sourceType": "auto",
            "primarySource": "official",
            "eventScope": "kawaii-lab",
        }
        group_fc = dict(
            base,
            id="group-fc",
            url="https://cutiestreet.asobisystem.com/news/detail/90590",
            applyStart="2026-09-28T12:00",
            applyEnd="2026-10-07T23:59",
        )
        generic_central = dict(base, id="generic-central")
        specific_central = dict(base, id="specific-central", ticketType="KAWAII LAB. FC先行")

        public, _ = build_public_events([group_fc, generic_central, specific_central])

        self.assertEqual(len(public), 1)
        self.assertEqual(
            [offer["ticketType"] for offer in public[0]["offers"]],
            ["FC先行", "KAWAII LAB. FC先行"],
        )
        self.assertEqual(
            {"group-fc", "generic-central", "specific-central"},
            set(public[0]["sourceRowIds"]),
        )

    def test_same_group_article_fc_window_with_central_label_is_one_offer(self):
        base = {
            "group": "MORE STAR",
            "title": "MORE STAR 単独ライブ 7th STAR",
            "eventDate": "2026-11-25",
            "venue": "ヒューリックホール東京",
            "startTime": "18:00",
            "applyStart": "2026-10-17T18:00",
            "applyEnd": "2026-10-25T23:59",
            "url": "https://morestar.asobisystem.com/news/detail/92107",
            "sourceType": "auto",
            "primarySource": "official",
            "eventScope": "kawaii-lab",
        }
        generic = dict(base, id="generic", ticketType="FC先行")
        specific = dict(base, id="specific", ticketType="KAWAII LAB. FC先行")

        public, _ = build_public_events([generic, specific])

        self.assertEqual(len(public), 1)
        self.assertEqual(
            ["KAWAII LAB. FC先行"],
            [offer["ticketType"] for offer in public[0]["offers"]],
        )
        self.assertEqual({"generic", "specific"}, set(public[0]["sourceRowIds"]))

    def test_fifth_tour_group_mirrors_are_one_joint_show_with_official_time(self):
        base = {
            "eventDate": "2027-01-30", "eventScope": "kawaii-lab",
            "ticketType": "現在受付なし",
        }
        joint = dict(base, id="joint", group="KAWAII LAB.合同",
                     title="KAWAII LAB. 5th ANNIVERSARY TOUR@宮城セキスイハイムスーパーアリーナ",
                     venue="宮城県 宮城セキスイハイムスーパーアリーナ",
                     url="https://fruitszipper.asobisystem.com/live_information/detail/46295",
                     sourceType="official-schedule", primarySource="official")
        more = dict(base, id="more", group="MORE STAR",
                    title="KAWAII LAB. 5th ANNIVERSARY TOUR 宮城公演 DAY1",
                    venue="宮城セキスイハイムスーパーアリーナ",
                    url="https://morestar.asobisystem.com/live_information/detail/46449",
                    sourceType="official-schedule", primarySource="official")
        public, _ = build_public_events([joint, more])
        self.assertEqual(1, len(public))
        event = public[0]
        self.assertEqual("KAWAII LAB.合同", event["group"])
        self.assertEqual("15:00", event["openTime"])
        self.assertEqual("17:00", event["startTime"])
        self.assertEqual({"joint", "more"}, set(event["sourceRowIds"]))
        self.assertIn("MORE STAR", event["participants"])
        self.assertIn("https://kawaiilab.asobisystem.com/news/detail/92410", event["urls"])

    def test_fifth_tour_other_performance_and_second_date_stay_distinct(self):
        base = {
            "group": "MORE STAR",
            "title": "KAWAII LAB. 5th ANNIVERSARY TOUR",
            "eventScope": "kawaii-lab", "ticketType": "現在受付なし",
            "venue": "宮城セキスイハイムスーパーアリーナ",
        }
        day1 = dict(base, id="day1", eventDate="2027-01-30")
        day2 = dict(base, id="day2", eventDate="2027-01-31")
        unrelated = dict(base, id="other", eventDate="2027-01-30", venue="Zepp Haneda",
                         title="MORE STAR OTHER LIVE")
        public, _ = build_public_events([day1, day2, unrelated])
        self.assertEqual(3, len(public))
        by_day = {e["eventDate"]: e for e in public if e["group"]=="KAWAII LAB.合同"}
        self.assertEqual({"2027-01-30", "2027-01-31"}, set(by_day))
        self.assertEqual("17:00", by_day["2027-01-30"]["startTime"])
        self.assertEqual("16:00", by_day["2027-01-31"]["startTime"])
        self.assertTrue(any(e["group"]=="MORE STAR" and e["venue"]=="Zepp Haneda" for e in public))

    def test_tbd_and_known_start_are_one_performance(self):
        base = {
            "group": "FRUITS ZIPPER", "eventDate": "2026-11-15",
            "venue": "横浜アリーナ", "eventScope": "kawaii-lab",
            "ticketType": "現在受付なし",
        }
        unknown = dict(base, id="announce", title="FRUITS ZIPPER 横浜ライブ", startTime="未定",
                       url="https://fruitszipper.asobisystem.com/live_information/detail/100")
        known = dict(base, id="detail", title="FRUITS ZIPPER 横浜ライブ 詳細発表", startTime="18:00",
                     url="https://fruitszipper.asobisystem.com/news/detail/101")
        public, _ = build_public_events([unknown, known])
        self.assertEqual(1, len(public))
        self.assertEqual("18:00", public[0]["startTime"])
        self.assertEqual({"announce", "detail"}, set(public[0]["sourceRowIds"]))

    def test_missing_venue_can_join_unique_known_venue(self):
        base = {
            "group": "SWEET STEADY", "eventDate": "2026-11-17",
            "eventScope": "kawaii-lab", "ticketType": "現在受付なし",
        }
        unknown = dict(base, id="short-news", title="SWEET STEADY ライブ", startTime="未発表",
                       venue="",
                       url="https://sweetsteady.asobisystem.com/news/detail/102")
        known = dict(base, id="schedule", title="SWEET STEADY ライブ", startTime="19:00",
                     venue="Zepp Haneda",
                     url="https://sweetsteady.asobisystem.com/live_information/detail/103")
        public, _ = build_public_events([unknown, known])
        self.assertEqual(1, len(public))
        self.assertEqual("Zepp Haneda", public[0]["venue"])
        self.assertEqual("19:00", public[0]["startTime"])

    def test_same_day_same_start_different_venues_are_not_merged(self):
        base = {
            "group": "MORE STAR", "eventDate": "2026-11-18", "startTime": "19:00",
            "eventScope": "kawaii-lab", "ticketType": "現在受付なし",
        }
        one = dict(base, id="one", venue="Zepp Haneda", title="ライブA")
        two = dict(base, id="two", venue="有明アリーナ", title="ライブB")
        public, _ = build_public_events([one, two])
        self.assertEqual(2, len(public))
        self.assertEqual({"Zepp Haneda", "有明アリーナ"}, {row["venue"] for row in public})

    def test_fc_generic_and_named_alias_same_signup_are_one_offer(self):
        base = {
            "group": "FRUITS ZIPPER", "eventDate": "2026-11-19",
            "venue": "横浜アリーナ", "startTime": "18:00",
            "eventScope": "kawaii-lab", "sourceType": "auto", "primarySource": "official",
            "applyStart": "2026-10-20T12:00", "applyEnd": "2026-10-27T23:59",
            "url": "https://fruitszipper.asobisystem.com/news/detail/201",
        }
        generic = dict(base, id="generic", ticketType="FC先行")
        named = dict(base, id="named", ticketType="FRUITS ZIPPER FC先行")
        public, _ = build_public_events([generic, named])
        self.assertEqual(1, len(public))
        self.assertEqual(["FRUITS ZIPPER FC先行"], [o["ticketType"] for o in public[0]["offers"]])
        self.assertEqual({"generic", "named"}, set(public[0]["sourceRowIds"]))

    def test_fc_named_fanclubs_and_different_signup_rounds_stay_distinct(self):
        base = {
            "group": "FRUITS ZIPPER", "eventDate": "2026-11-19",
            "venue": "横浜アリーナ", "startTime": "18:00",
            "eventScope": "kawaii-lab", "sourceType": "auto", "primarySource": "official",
            "applyStart": "2026-10-20T12:00", "applyEnd": "2026-10-27T23:59",
            "url": "https://fruitszipper.asobisystem.com/news/detail/201",
        }
        group_fc = dict(base, id="group", ticketType="FRUITS ZIPPER FC先行")
        lab_fc = dict(base, id="lab", ticketType="KAWAII LAB. FC先行")
        later = dict(base, id="later", ticketType="FC先行",
                     applyStart="2026-10-28T12:00", applyEnd="2026-11-01T23:59")
        different_link = dict(base, id="link", ticketType="FC先行",
                              url="https://fruitszipper.asobisystem.com/news/detail/202")
        public, _ = build_public_events([group_fc, lab_fc, later, different_link])
        self.assertEqual(1, len(public))
        self.assertEqual(4, len(public[0]["offers"]))

    def test_multiday_schedule_source_is_split_into_physical_performances(self):
        public, _ = build_public_events(self.fixture())
        tour = [
            event for event in public
            if event.get("entityType") == "performance"
            and event.get("group") == "CANDY TUNE"
            and "JAPAN TOUR 2026" in str(event.get("eventTitle") or event.get("title") or "")
        ]
        self.assertEqual({event["eventDate"] for event in tour}, {"2026-10-08", "2026-10-09"})
        self.assertTrue(all(event.get("eventCount") == 1 for event in tour))
        self.assertTrue(all(len(event.get("schedule") or []) == 1 for event in tour))

    def test_different_start_time_remains_a_different_performance(self):
        public, _ = build_public_events(self.fixture())
        hosted = [
            event for event in public
            if event.get("entityType") == "performance"
            and event.get("group") == "CANDY TUNE"
            and event.get("eventDate") == "2026-10-08"
        ]
        self.assertEqual({event.get("startTime") for event in hosted}, {"18:30", "20:00"})

    def test_external_rows_are_not_rewritten(self):
        public, _ = build_public_events(self.fixture())
        external = [event for event in public if event.get("id") == "external"]
        self.assertEqual(len(external), 1)
        self.assertNotEqual(external[0].get("entityType"), "performance")

    def test_current_repository_sendai_tour_is_one_public_performance(self):
        path = Path(__file__).resolve().parents[1] / "data" / "live-events.json"
        if not path.exists():
            self.skipTest("repository data file is unavailable")
        payload = json.loads(path.read_text(encoding="utf-8"))
        public, _ = build_public_events(payload.get("events") or [])
        sendai = [
            event for event in public
            if event.get("entityType") == "performance"
            and event.get("group") == "CANDY TUNE"
            and event.get("eventDate") == "2026-10-08"
            and event.get("startTime") == "18:30"
        ]
        self.assertEqual(len(sendai), 1)
        event = sendai[0]
        self.assertIn("仙台サンプラザホール", str(event.get("venue") or ""))
        ticket_types = {str(offer.get("ticketType") or "") for offer in event.get("offers") or []}
        today_jst = datetime.now(ZoneInfo("Asia/Tokyo")).date()
        if today_jst <= date.fromisoformat("2026-10-08"):
            self.assertTrue(any("一般発売" in ticket_type for ticket_type in ticket_types))
        else:
            self.assertFalse(any("一般発売" in ticket_type for ticket_type in ticket_types))
        self.assertEqual(len([row for row in public if row.get("id") == "1d39bd5dbf1e137a"]), 0)


if __name__ == "__main__":
    unittest.main()
