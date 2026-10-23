from __future__ import annotations

import unittest

from enforce_physical_event_invariant import duplicate_physical_occurrences, enforce_payload
from expand_special_event_entities import expand_payload
from normalize_special_event_entities import normalize_payload, validate


class SpecialEventEntityTests(unittest.TestCase):
    def online_rows(self):
        return [
            {"id": "official", "group": "CANDY TUNE", "title": "CANDY TUNE オンライン特典会",
             "eventCategory": "online-benefit", "eventDate": "2026-10-19",
             "eventDates": ["2026-10-19", "2026-10-20"],
             "schedule": [{"date": "2026-10-19", "venue": "その他 オンライン"},
                          {"date": "2026-10-20", "venue": "その他 オンライン"}],
             "ticketType": "現在受付なし", "url": "https://candytune.asobisystem.com/live_information/detail/46277"},
            {"id": "goods19", "group": "CANDY TUNE", "title": "CANDY TUNE lovers book by LARME オンライン特典会",
             "eventCategory": "online-benefit", "eventDate": "2026-10-19", "startTime": "17:00",
             "url": "https://sukisuki-shop.com/goods/6500000004607"},
            {"id": "goods20", "group": "CANDY TUNE", "title": "CANDY TUNE オンライン特典会",
             "eventCategory": "online-benefit", "eventDate": "2026-10-20", "startTime": "17:00",
             "url": "https://sukisuki-shop.com/goods/6500000004622"},
        ]

    def test_online_official_multiday_placeholder_merges_each_day_into_goods(self):
        rows = self.online_rows()
        result, report = normalize_payload({"events": rows})
        self.assertEqual({"goods19", "goods20"}, {row["id"] for row in result["events"]})
        self.assertEqual(2, report["onlinePlaceholderOccurrencesMerged"])
        self.assertEqual("17:00", result["events"][1]["startTime"])
        self.assertIn(rows[0]["url"], result["events"][1]["urls"])
        self.assertNotIn("urls", rows[2])  # caller's data is not mutated
        again, _ = normalize_payload(result)
        self.assertEqual(result["events"], again["events"])

    def test_online_unmatched_days_are_preserved(self):
        result, _ = normalize_payload({"events": self.online_rows()[:2]})
        placeholder = next(row for row in result["events"] if row["id"] == "official")
        self.assertEqual(["2026-10-20"], placeholder["eventDates"])
        self.assertEqual("2026-10-20", placeholder["eventDate"])

    def test_online_multiple_goods_are_not_guessed_or_combined(self):
        rows = self.online_rows()
        other = dict(rows[2], id="other-session", startTime="19:00", url="https://sukisuki-shop.com/goods/999")
        result, _ = normalize_payload({"events": rows + [other]})
        self.assertEqual(4, len(result["events"]))
        self.assertEqual(["2026-10-20"], next(row for row in result["events"] if row["id"] == "official")["eventDates"])

    def test_online_conflicting_times_and_other_groups_are_not_merged(self):
        for change in ({"startTime": "19:00"}, {"group": "SWEET STEADY"}):
            rows = self.online_rows()
            rows[0].update(change)
            result, _ = normalize_payload({"events": rows})
            self.assertEqual(3, len(result["events"]))

    def test_duplicate_ordinary_id_same_logical_row_collapses_before_publication(self):
        payload = {"events": [
            {
                "id": "644a68f1d59b3670",
                "group": "CUTIE STREET",
                "eventTitle": "【CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-】@ IGアリーナ",
                "title": "【CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-】@ IGアリーナ",
                "eventDate": "2026-11-28",
                "venue": "愛知県 IGアリーナ",
                "ticketType": "現在受付なし",
                "sourceType": "official-schedule",
                "url": "https://cutiestreet.asobisystem.com/feature/autumntour",
            },
            {
                "id": "644a68f1d59b3670",
                "group": "CUTIE STREET",
                "eventTitle": "【CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-】@ IGアリーナ",
                "title": "【CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-】@ IGアリーナ",
                "eventDate": "2026-11-28",
                "venue": "愛知県 IGアリーナ",
                "ticketType": "現在受付なし",
                "sourceType": "official-schedule",
                "url": "https://cutiestreet.asobisystem.com/feature/autumntour",
                "officialScheduleUrl": "https://cutiestreet.asobisystem.com/live_information/detail/example",
            },
        ]}

        normalized, report = normalize_payload(payload)

        self.assertEqual(1, len(normalized["events"]))
        self.assertEqual("644a68f1d59b3670", normalized["events"][0]["id"])
        self.assertEqual(1, report["duplicateEventIdCollisions"])
        self.assertEqual(1, report["duplicateEventRowsCollapsed"])
        self.assertEqual(0, report["duplicateEventIdsDisambiguated"])
        self.assertFalse(validate(normalized))

    def test_duplicate_ordinary_id_for_distinct_events_is_disambiguated_not_dropped(self):
        payload = {"events": [
            {
                "id": "reused-id",
                "group": "CUTIE STREET",
                "eventTitle": "ARENA TOUR",
                "eventDate": "2026-11-28",
                "venue": "IGアリーナ",
                "ticketType": "現在受付なし",
                "sourceType": "official-schedule",
            },
            {
                "id": "reused-id",
                "group": "CUTIE STREET",
                "eventTitle": "ARENA TOUR",
                "eventDate": "2026-11-29",
                "venue": "IGアリーナ",
                "ticketType": "現在受付なし",
                "sourceType": "official-schedule",
            },
        ]}

        normalized, report = normalize_payload(payload)

        self.assertEqual(2, len(normalized["events"]))
        ids = {event["id"] for event in normalized["events"]}
        self.assertIn("reused-id", ids)
        self.assertTrue(any(value.startswith("reused-id--") for value in ids))
        self.assertEqual(1, report["duplicateEventIdCollisions"])
        self.assertEqual(0, report["duplicateEventRowsCollapsed"])
        self.assertEqual(1, report["duplicateEventIdsDisambiguated"])
        self.assertFalse(validate(normalized))

    def test_same_large_benefit_different_sales_channels_becomes_one_event(self):
        payload = {"events": [
            {
                "id": "sukisuki-row",
                "group": "FRUITS ZIPPER",
                "eventCategory": "large-benefit",
                "displayTitle": "FRUITS ZIPPER 大特典会",
                "eventDate": "2026-09-06",
                "venue": "ベルサール汐留",
                "startTime": "10:00",
                "ticketProvider": "sukisuki",
                "ticketType": "FC限定・対象商品応募",
                "applyStart": "2026-08-25T21:00",
                "applyEnd": "2026-08-26T23:59",
                "url": "https://sukisuki-shop.com/goods/example",
                "urls": ["https://fruitszipper.asobisystem.com/news/detail/1", "https://sukisuki-shop.com/goods/example"],
                "sourceType": "official-special",
            },
            {
                "id": "hmv-row",
                "group": "FRUITS ZIPPER",
                "eventCategory": "large-benefit",
                "displayTitle": "FRUITS ZIPPER 大特典会",
                "eventDate": "2026-09-06",
                "venue": "ベルサール汐留",
                "startTime": "11:20",
                "ticketProvider": "hmv",
                "ticketType": "対象商品予約（参加権付き）",
                "applyStart": "2026-08-25T21:00",
                "applyEnd": "2026-08-27T11:59",
                "url": "https://www.hmv.co.jp/example",
                "urls": ["https://fruitszipper.asobisystem.com/news/detail/2", "https://www.hmv.co.jp/example"],
                "sourceType": "official-special",
            },
        ]}
        normalized, report = normalize_payload(payload)
        self.assertEqual(report["canonicalSpecialEvents"], 1)
        self.assertEqual(len(normalized["events"]), 1)
        event = normalized["events"][0]
        self.assertEqual(event["entityType"], "special-event")
        self.assertEqual({o["provider"] for o in event["offers"]}, {"sukisuki", "hmv"})
        self.assertEqual(event["ticketType"], "現在受付なし")
        self.assertFalse(validate(normalized))

    def test_same_day_shared_sukisuki_goods_merges_bad_online_venue_into_official_event(self):
        duplicate = {
            "id": "sukisuki-only",
            "group": "CUTIE STREET",
            "eventCategory": "large-benefit",
            "title": "CUTIE STREET大特典会＠パシフィコ横浜【1部・3部・6部】",
            "eventDate": "2026-11-03",
            "venue": "オンライン（SUKISUKI）",
            "ticketProvider": "sukisuki",
            "ticketType": "オンライン特典会・抽選販売",
            "applyStart": "2026-10-23T21:00",
            "applyEnd": "2026-10-24T23:59",
            "url": "https://sukisuki-shop.com/goods/6500000004719",
            "sourceType": "sukisuki",
        }
        official = {
            "id": "official-event",
            "group": "CUTIE STREET",
            "eventCategory": "large-benefit",
            "displayTitle": "CUTIE STREET 大特典会",
            "eventDate": "2026-11-03",
            "venue": "神奈川県 パシフィコ横浜 展示ホールD",
            "url": "https://cutiestreet.asobisystem.com/news/detail/93831",
            "urls": [
                "https://cutiestreet.asobisystem.com/news/detail/93831",
                "https://sukisuki-shop.com/goods/6500000004719",
            ],
            "offers": [{
                "sourceRowId": "official-sukisuki-offer",
                "provider": "sukisuki",
                "ticketProvider": "sukisuki",
                "ticketType": "FC限定・対象商品応募（抽選／応募受付）",
                "applyStart": "2026-10-23T21:00",
                "applyEnd": "2026-10-24T23:59",
                "url": "https://sukisuki-shop.com/goods/6500000004719",
                "urls": ["https://sukisuki-shop.com/goods/6500000004719"],
            }],
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "sourceType": "official-special",
        }
        payload = {"events": [duplicate, official], "publicEvents": [duplicate, official]}

        normalized, report = normalize_payload(payload)

        self.assertEqual(1, len(normalized["events"]))
        self.assertEqual(1, len(normalized["publicEvents"]))
        for collection in ("events", "publicEvents"):
            event = normalized[collection][0]
            self.assertEqual("神奈川県 パシフィコ横浜 展示ホールD", event["venue"])
            self.assertIn("https://cutiestreet.asobisystem.com/news/detail/93831", event["urls"])
            self.assertEqual(1, len(event["offers"]))
            self.assertEqual(
                "FC限定・対象商品応募（抽選／応募受付）",
                event["offers"][0]["ticketType"],
            )
        self.assertEqual(1, report["rowsCollapsed"])
        self.assertEqual(1, report["publicEvents"]["rowsCollapsed"])
        self.assertFalse(validate(normalized))

    def test_multiday_benefit_placeholder_merges_only_matching_detail_day(self):
        payload = {"events": [
            {
                "id": "series",
                "group": "CUTIE STREET",
                "eventCategory": "large-benefit",
                "displayTitle": "CUTIE STREET 大特典会",
                "eventDate": "2026-11-03",
                "eventEndDate": "2026-11-23",
                "eventDates": ["2026-11-03", "2026-11-23"],
                "schedule": [
                    {"date": "2026-11-03", "venue": "【大特典会】神奈川県 パシフィコ横浜展示ホールD"},
                    {"date": "2026-11-23", "venue": "【大特典会】北海道 アクセス札幌"},
                ],
                "ticketType": "現在受付なし",
                "applicationStatus": "none",
                "url": "https://cutiestreet.asobisystem.com/",
                "sourceType": "official-special",
            },
            {
                "id": "detail",
                "group": "CUTIE STREET",
                "eventCategory": "large-benefit",
                "displayTitle": "CUTIE STREET 大特典会",
                "eventDate": "2026-11-03",
                "venue": "神奈川県 パシフィコ横浜 展示ホールD",
                "startTime": "10:00",
                "ticketProvider": "hmv",
                "ticketType": "対象商品予約",
                "applyStart": "2026-10-23T21:00",
                "applyEnd": "2026-10-27T23:59",
                "parts": [{"part": "第1部", "start": "10:00", "end": "11:00"}],
                "url": "https://cutiestreet.asobisystem.com/news/detail/93713",
                "urls": [
                    "https://cutiestreet.asobisystem.com/news/detail/93713",
                    "https://img.hmv.co.jp/cont/online/cutielandevent_lp/",
                ],
                "sourceType": "official-special",
            },
        ]}

        normalized, report = normalize_payload(payload)

        self.assertEqual(2, report["canonicalSpecialEvents"])
        self.assertEqual(2, len(normalized["events"]))
        by_day = {event["eventDate"]: event for event in normalized["events"]}
        self.assertEqual(1, by_day["2026-11-03"]["eventCount"])
        self.assertEqual(1, len(by_day["2026-11-03"]["offers"]))
        self.assertEqual("10:00", by_day["2026-11-03"]["parts"][0]["start"])
        self.assertEqual([], by_day["2026-11-23"]["offers"])
        self.assertNotIn("parts", by_day["2026-11-23"])

    def test_same_physical_event_merges_even_when_titles_differ(self):
        payload = {"events": [
            {
                "id": "second-sale",
                "group": "CANDY TUNE",
                "eventCategory": "large-benefit",
                "displayTitle": "CANDY TUNE 大特典会",
                "eventTitle": "9/5（土）CANDY TUNE 大特典会＠ベルサール汐留 特典会参加券2次販売が決定！",
                "eventDate": "2026-09-05",
                "venue": "ベルサール汐留",
                "startTime": "10:00",
                "ticketType": "現在受付なし",
                "sourceType": "official-special",
                "url": "https://candytune.asobisystem.com/news/detail/second-sale",
            },
            {
                "id": "announcement",
                "group": "CANDY TUNE",
                "eventCategory": "large-benefit",
                "displayTitle": "CANDY TUNE 4thシングル発売記念 大特典会",
                "eventTitle": "4thシングル発売記念！9/5(土) CANDY TUNE大特典会をベルサール汐留にて開催決定！",
                "eventDate": "2026-09-05",
                "venue": "東京都 ベルサール汐留",
                "startTime": "10:00",
                "ticketType": "現在受付なし",
                "sourceType": "official-special",
                "url": "https://candytune.asobisystem.com/news/detail/announcement",
            },
        ]}
        enforced, report = enforce_payload(payload)
        self.assertEqual(report["physicalRowsCollapsed"], 1)
        self.assertEqual(report["internalScheduleRowsCollapsed"], 1)
        self.assertEqual(report["remainingDuplicateCount"], 0)
        self.assertEqual(len(enforced["events"]), 1)
        event = enforced["events"][0]
        self.assertTrue(event["physicalInvariantMerged"])
        self.assertEqual(event["eventCount"], 1)
        self.assertEqual(len(event["schedule"]), 1)
        self.assertFalse(duplicate_physical_occurrences(enforced))

    def test_missing_time_shell_merges_into_same_release_event(self):
        payload = {"events": [
            {
                "id": "detail",
                "group": "CANDY TUNE",
                "eventCategory": "release-event",
                "displayTitle": "4thシングル『総意♡So Free / スペシャル感謝祭』発売記念リリースイベント",
                "eventTitle": "CANDY TUNE 4thシングル『総意♡So Free / スペシャル感謝祭』発売記念リリースイベント @エミテラス所沢2F TOKOROZAWA e-CUBE",
                "eventDate": "2026-09-01",
                "venue": "埼玉県 エミテラス所沢2F TOKOROZAWA e-CUBE",
                "startTime": "18:00",
                "ticketType": "現在受付なし",
                "sourceType": "official-special",
            },
            {
                "id": "official-x-shell",
                "group": "CANDY TUNE",
                "eventCategory": "release-event",
                "displayTitle": "🍬🎸4th single リリースイベント🥁🍬",
                "eventDate": "2026-09-01",
                "venue": "エミテラス所沢 2F TOKOROZAWA e-CUBE",
                "ticketType": "現在受付なし",
                "specialDetailsStatus": "awaiting-details",
                "sourceType": "official-social",
                "sourceChannel": "official-x",
            },
        ]}
        self.assertEqual(len(duplicate_physical_occurrences(payload)), 1)
        enforced, report = enforce_payload(payload)
        self.assertEqual(report["physicalRowsCollapsed"], 1)
        self.assertEqual(report["internalScheduleRowsCollapsed"], 1)
        self.assertEqual(report["remainingDuplicateCount"], 0)
        self.assertEqual(len(enforced["events"]), 1)
        event = enforced["events"][0]
        self.assertTrue(event["physicalInvariantMerged"])
        self.assertEqual(event["eventDate"], "2026-09-01")
        self.assertEqual(event["eventCount"], 1)
        self.assertEqual(len(event["schedule"]), 1)
        self.assertEqual(event["schedule"][0]["startTime"], "18:00")
        self.assertEqual(event["startTime"], "18:00")
        self.assertNotIn("複数会場", event["venue"])
        self.assertFalse(duplicate_physical_occurrences(enforced))

    def test_same_place_and_day_but_different_time_remains_separate(self):
        payload = {"events": [
            {
                "id": "morning",
                "group": "CUTIE STREET",
                "eventCategory": "large-benefit",
                "displayTitle": "午前イベント",
                "eventDate": "2026-10-01",
                "venue": "会場A",
                "startTime": "10:00",
                "ticketType": "現在受付なし",
            },
            {
                "id": "evening",
                "group": "CUTIE STREET",
                "eventCategory": "large-benefit",
                "displayTitle": "夕方イベント",
                "eventDate": "2026-10-01",
                "venue": "会場A",
                "startTime": "17:00",
                "ticketType": "現在受付なし",
            },
        ]}
        enforced, report = enforce_payload(payload)
        self.assertEqual(report["physicalRowsCollapsed"], 0)
        self.assertEqual(len(enforced["events"]), 2)

    def test_release_series_new_date_remains_a_separate_event(self):
        payload = {"events": [
            {
                "id": "old-series",
                "group": "MORE STAR",
                "eventCategory": "release-event",
                "displayTitle": "『サマーゴー！！/WITH KAWAII論』発売記念リリースイベント",
                "eventDate": "2027-01-03",
                "eventEndDate": "2027-02-04",
                "eventDates": ["2027-01-03", "2027-02-04"],
                "schedule": [
                    {"date": "2027-01-03", "venue": "テラスモール松戸 2Fこもれびステージ"},
                    {"date": "2027-02-04", "venue": "アニメイト池袋本店 北館9F"},
                ],
                "ticketType": "現在受付なし",
                "applicationStatus": "none",
                "url": "https://x.com/MORE_STAR_/status/100",
                "sourceType": "official-social",
                "sourceChannel": "official-x",
            },
            {
                "id": "new-day",
                "group": "MORE STAR",
                "eventCategory": "release-event",
                "displayTitle": "『サマーゴー！！/WITH KAWAII論』発売記念リリースイベント",
                "eventDate": "2027-02-05",
                "venue": "テラスモール松戸 2Fこもれびステージ",
                "ticketType": "現在受付なし",
                "applicationStatus": "none",
                "url": "https://x.com/MORE_STAR_/status/101",
                "sourceType": "official-social",
                "sourceChannel": "official-x",
            },
        ]}
        normalized, _ = normalize_payload(payload)
        self.assertEqual(len(normalized["events"]), 2)
        self.assertEqual(len({event["id"] for event in normalized["events"]}), 2)
        by_dates = {tuple(event.get("eventDates") or [event.get("eventDate")]): event for event in normalized["events"]}
        self.assertIn(("2027-01-03", "2027-02-04"), by_dates)
        self.assertIn(("2027-02-05",), by_dates)
        self.assertNotEqual(
            by_dates[("2027-01-03", "2027-02-04")]["id"],
            by_dates[("2027-02-05",)]["id"],
        )

    def test_same_release_occurrence_different_sale_rows_still_merge(self):
        payload = {"events": [
            {
                "id": "detail",
                "group": "CANDY TUNE",
                "eventCategory": "release-event",
                "displayTitle": "4thシングル発売記念リリースイベント",
                "eventDate": "2026-09-30",
                "venue": "イオンモール幕張新都心",
                "ticketProvider": "kawaii-store",
                "ticketType": "商品購入電子整理券（先着）",
                "applyStart": "2026-09-29T21:00",
                "applyEnd": "2026-09-30T10:00",
                "url": "https://candytune.asobisystem.com/news/detail/90321",
            },
            {
                "id": "shell",
                "group": "CANDY TUNE",
                "eventCategory": "release-event",
                "displayTitle": "4thシングル発売記念リリースイベント",
                "eventDate": "2026-09-30",
                "venue": "千葉県 イオンモール幕張新都心",
                "ticketType": "現在受付なし",
                "url": "https://x.com/CANDY_TUNE_/status/1",
            },
        ]}
        normalized, _ = normalize_payload(payload)
        self.assertEqual(len(normalized["events"]), 1)
        self.assertEqual(normalized["events"][0]["eventDate"], "2026-09-30")
        self.assertEqual(len(normalized["events"][0]["offers"]), 1)

    def test_different_large_benefit_dates_remain_different_events(self):
        payload = {"events": [
            {"id": "a", "group": "CANDY TUNE", "eventCategory": "large-benefit", "displayTitle": "CANDY TUNE 大特典会", "eventDate": "2026-09-01", "venue": "会場A", "ticketType": "現在受付なし"},
            {"id": "b", "group": "CANDY TUNE", "eventCategory": "large-benefit", "displayTitle": "CANDY TUNE 大特典会", "eventDate": "2026-09-02", "venue": "会場A", "ticketType": "現在受付なし"},
        ]}
        normalized, _ = normalize_payload(payload)
        self.assertEqual(len(normalized["events"]), 2)

    def test_different_release_products_do_not_merge(self):
        payload = {"events": [
            {"id": "a", "group": "SWEET STEADY", "eventCategory": "release-event", "displayTitle": "発売記念リリースイベント", "product": "Single A", "eventDate": "2026-10-01", "venue": "会場A", "ticketType": "現在受付なし"},
            {"id": "b", "group": "SWEET STEADY", "eventCategory": "release-event", "displayTitle": "発売記念リリースイベント", "product": "Single B", "eventDate": "2026-10-02", "venue": "会場B", "ticketType": "現在受付なし"},
        ]}
        normalized, _ = normalize_payload(payload)
        self.assertEqual(len(normalized["events"]), 2)

    def test_normalize_expand_normalize_is_stable(self):
        payload = {"events": [
            {
                "id": "sale",
                "group": "CUTIE STREET",
                "eventCategory": "release-event",
                "displayTitle": "『Example』発売記念リリースイベント",
                "eventDate": "2026-10-05",
                "venue": "会場A",
                "ticketProvider": "hmv",
                "ticketType": "対象商品予約",
                "applyStart": "2026-09-01T12:00",
                "applyEnd": "2026-10-05T10:00",
                "url": "https://www.hmv.co.jp/example",
                "urls": ["https://cutiestreet.asobisystem.com/news/detail/1", "https://www.hmv.co.jp/example"],
                "sourceType": "official-special",
            }
        ]}
        first, _ = normalize_payload(payload)
        expanded, _ = expand_payload(first)
        second, _ = normalize_payload(expanded)
        self.assertEqual(len(second["events"]), 1)
        self.assertEqual(len(second["events"][0]["offers"]), 1)
        self.assertEqual(first["events"][0]["id"], second["events"][0]["id"])

    def test_public_entity_never_leaks_sale_fields_to_parent(self):
        payload = {"events": [
            {
                "id": "sale-a",
                "group": "CANDY TUNE",
                "eventCategory": "release-event",
                "displayTitle": "『Example』発売記念リリースイベント",
                "eventDate": "2026-11-01",
                "venue": "会場A",
                "ticketProvider": "tower",
                "ticketType": "対象商品予約",
                "applyStart": "2026-10-01T12:00",
                "applyEnd": "2026-11-01T09:00",
                "url": "https://tower.jp/example",
                "sourceType": "official-special",
            }
        ]}
        normalized, _ = normalize_payload(payload)
        parent = normalized["events"][0]
        self.assertEqual(parent["entityType"], "special-event")
        self.assertNotIn("ticketProvider", parent)
        self.assertNotIn("applyStart", parent)
        self.assertNotIn("applyEnd", parent)
        self.assertEqual(parent["ticketType"], "現在受付なし")
        self.assertEqual(parent["applicationStatus"], "none")
        self.assertEqual(len(parent["offers"]), 1)
        self.assertEqual(parent["offers"][0]["provider"], "tower")

    def test_explicit_sales_provider_beats_unrelated_support_link(self):
        payload = {"events": [{
            "id": "tower-sale",
            "group": "CANDY TUNE",
            "eventCategory": "large-benefit",
            "displayTitle": "CANDY TUNE 大特典会",
            "eventDate": "2026-09-22",
            "venue": "東京流通センター 第二展示場 Fホール",
            "ticketProvider": "tower",
            "ticketType": "対象商品予約",
            "applyStart": "2026-09-02T20:00",
            "applyEnd": "2026-09-04T23:59",
            "applicationStatus": "open",
            "applicationWindowVerified": True,
            "url": "https://candytune.asobisystem.com/news/detail/88915",
            "urls": [
                "https://candytune.asobisystem.com/news/detail/88915",
                "https://tower.jp/article/feature_item/example",
                "https://sukisuki-shop.com/contact",
            ],
            "sourceType": "official-special",
        }]}
        normalized, _ = normalize_payload(payload)
        offer = normalized["events"][0]["offers"][0]
        self.assertEqual(offer["provider"], "tower")
        self.assertIn("tower.jp", offer["url"])


if __name__ == "__main__":
    unittest.main()
