from __future__ import annotations

import unittest

from enforce_physical_event_invariant import duplicate_physical_occurrences, enforce_payload
from expand_special_event_entities import expand_payload
from normalize_special_event_entities import normalize_payload, validate


class SpecialEventEntityTests(unittest.TestCase):
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

    def test_release_series_split_across_dates_becomes_one_event(self):
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
        self.assertEqual(len(normalized["events"]), 1)
        event = normalized["events"][0]
        self.assertEqual(event["eventDates"], ["2027-01-03", "2027-02-04", "2027-02-05"])
        self.assertEqual(event["eventCount"], 3)

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


if __name__ == "__main__":
    unittest.main()
