from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
