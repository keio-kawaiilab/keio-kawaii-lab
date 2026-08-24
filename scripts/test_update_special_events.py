import unittest
from datetime import datetime, timedelta, timezone

import update_special_events as s


JST = timezone(timedelta(hours=9))


class SpecialEventTests(unittest.TestCase):
    def test_release_event_extracts_ticket_window_and_call_times(self):
        html = """
        <html><head><title>MORE STAR 発売記念リリースイベント</title></head><body>
        <h1>〖MORE STAR〗1stシングル『サマーゴー！！』発売記念リリースイベント</h1>
        <p>2026.08.22</p><p>■開催日時</p><p>2026年8月26日(水)</p>
        <p>■場所</p><p>ららぽーと立川立飛 2Fイベント広場</p>
        <p>販売開始時間：10:00</p><p>優先エリア入場集合時間：13:20</p><p>開演時間：14:00</p>
        <p>〈受付時間〉 2026年8月25日（火）21:00〜2026年8月26日（水）9:00まで</p>
        <p>・1〜200番＝9:50</p><p>・201番〜400番＝10:05</p>
        <p>■対象商品</p><p>2026年8月26日(水)発売</p><p>1stシングル『サマーゴー！！』 通常盤 ¥1,200（税込）</p>
        <a href="https://kawaiilab.goods-order.com">アプリ</a>
        </body></html>
        """
        events = s.parse_page("MORE STAR", "https://morestar.asobisystem.com/live_information/detail/1", html, datetime(2026, 8, 24, tzinfo=JST))
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["eventCategory"], "release-event")
        self.assertEqual(event["applyStart"], "2026-08-25T21:00")
        self.assertEqual(event["applyEnd"], "2026-08-26T09:00")
        self.assertEqual(event["salesStartTime"], "10:00")
        self.assertEqual(event["gatheringTime"], "13:20")
        self.assertEqual(event["numberedCallTimes"][0], {"numbers": "1〜200番", "time": "09:50"})

    def test_large_benefit_extracts_parts_and_purchase_round(self):
        html = """
        <html><head><title>CANDY TUNE大特典会</title></head><body>
        <h1>4thシングル発売記念！CANDY TUNE大特典会</h1><p>2026.08.15</p>
        <p>■開催日程</p><p>2026年9月5日（土）</p><p>■開催会場</p><p>ベルサール汐留</p>
        <p>&lt;第1部&gt; 2ショットチェキ撮影会10:00〜11:00 (受付開始9:45／受付終了10:40)</p>
        <p>イベント参加対象商品 1次受付：8月17日(月)20:00～8月19日(水)23:59</p>
        <p>■イベント参加対象商品</p><p>2026年9月30日(水)発売</p><p>通常盤 ¥1,200 (税込)</p>
        <a href="https://r10.to/example">楽天ブックス</a>
        </body></html>
        """
        events = s.parse_page("CANDY TUNE", "https://candytune.asobisystem.com/news/detail/1", html, datetime(2026, 8, 24, tzinfo=JST))
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["eventCategory"], "large-benefit")
        self.assertEqual(event["ticketProvider"], "rakuten")
        self.assertEqual(event["parts"][0]["receptionEnd"], "10:40")
        self.assertEqual(event["parts"][0]["receptionStart"], "09:45")
        self.assertIn("参加権", event["purchaseMethod"])

    def test_merge_replaces_same_official_special_source(self):
        old = {"id": "old", "sourceType": "official-special", "url": "https://example.test/a", "eventDate": "2026-09-01"}
        normal = {"id": "normal", "sourceType": "official", "eventDate": "2026-10-01"}
        fresh = {"id": "new", "sourceType": "official-special", "url": "https://example.test/a", "eventDate": "2026-09-01"}
        merged = s.merge_payload({"events": [old, normal]}, [fresh], today=datetime(2026, 8, 24).date())
        self.assertEqual({event["id"] for event in merged["events"]}, {"normal", "new"})

    def test_timestamp_only_refresh_is_unchanged(self):
        previous = {"updatedAt": "2026-08-24T10:00:00+09:00", "events": [{"id": "same"}]}
        candidate = {"updatedAt": "2026-08-24T10:15:00+09:00", "events": [{"id": "same"}]}
        self.assertFalse(s.event_data_changed(previous, candidate))

    def test_active_master_article_is_kept_as_a_discovery_seed(self):
        payload = {"events": [{
            "group": "MORE STAR",
            "sourceType": "official-special",
            "eventDate": "2026-08-30",
            "discoverySourceUrl": "https://morestar.asobisystem.com/news/detail/79271",
        }]}
        seeds = s.discovery_seed_urls(payload, "MORE STAR", datetime(2026, 8, 24).date())
        self.assertEqual(seeds, ["https://morestar.asobisystem.com/news/detail/79271"])

    def test_discovery_source_is_saved_with_the_event(self):
        event = {"url": "https://example.test/live/1", "urls": ["https://example.test/live/1"]}
        source = "https://example.test/news/1"
        enriched = s.add_discovery_source(event, source)
        self.assertEqual(enriched["discoverySourceUrl"], source)
        self.assertIn(source, enriched["urls"])


if __name__ == "__main__":
    unittest.main()
