import unittest
from datetime import datetime, timedelta, timezone

import update_special_events as s


JST = timezone(timedelta(hours=9))


class SpecialEventTests(unittest.TestCase):
    def test_discovery_scans_homepage_when_information_index_lags(self):
        base = "https://sweetsteady.asobisystem.com"
        article_url = f"{base}/news/detail/88152"
        home = f'<a href="{article_url}">9/6(日)SWEET STEADY 大特典会を開催決定！</a>'
        article = """
        <html><head><title>SWEET STEADY 大特典会</title></head><body>
        <h1>9/6(日)SWEET STEADY 大特典会をベルサール汐留にて開催決定！</h1>
        <p>2026.08.24</p><p>■開催日程</p><p>2026年9月6日(日)</p>
        <p>■開催会場</p><p>ベルサール汐留</p>
        <p>対象商品予約期間：8月25日(火)21:00～8月27日(木)11:59まで</p>
        <p>■イベント参加対象商品</p><p>2026年3月25日(水)発売</p>
        <p>通常盤(KLS-10009)／¥1,200 (税込)</p>
        <a href="https://www.hmv.co.jp/example">HMV</a>
        </body></html>
        """

        class Response:
            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                return None

        class Session:
            def get(self, url, timeout=20):
                if url == f"{base}/":
                    return Response(home)
                if url == article_url:
                    return Response(article)
                return Response('<a href="/news/detail/1">通常のお知らせ</a>')

        events, failures, reachable = s.discover(
            Session(), "SWEET STEADY", base, today=datetime(2026, 8, 24).date()
        )
        self.assertTrue(reachable)
        self.assertEqual(failures, [])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["url"], article_url)
        self.assertEqual(events[0]["applyStart"], "2026-08-25T21:00")

    def test_recent_homepage_announcement_parse_failure_is_critical(self):
        base = "https://sweetsteady.asobisystem.com"
        article_url = f"{base}/news/detail/99999"
        home = f'<a href="{article_url}">SWEET STEADY 大特典会を開催決定！</a>'
        article = """
        <html><head><title>SWEET STEADY 大特典会</title></head><body>
        <h1>SWEET STEADY 大特典会を開催決定！</h1>
        <p>2026.08.24</p><p>詳細は後日発表します。</p>
        </body></html>
        """

        class Response:
            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                return None

        class Session:
            def get(self, url, timeout=20):
                if url == f"{base}/":
                    return Response(home)
                if url == article_url:
                    return Response(article)
                return Response('<a href="/news/detail/1">通常のお知らせ</a>')

        events, failures, reachable = s.discover(
            Session(), "SWEET STEADY", base, today=datetime(2026, 8, 24).date()
        )
        self.assertTrue(reachable)
        self.assertEqual(events, [])
        self.assertTrue(any(failure.get("critical") for failure in failures))

    def test_homepage_master_article_can_delegate_to_linked_live_detail(self):
        base = "https://morestar.asobisystem.com"
        article_url = f"{base}/news/detail/12345"
        detail_url = f"{base}/live_information/detail/67890"
        home = f'<a href="{article_url}">1stシングル発売記念イベント</a>'
        article = f"""
        <html><head><title>発売記念イベントまとめ</title></head><body>
        <p>2026.08.24</p><a href="{detail_url}">開催詳細</a>
        </body></html>
        """
        detail = """
        <html><head><title>MORE STAR 発売記念リリースイベント</title></head><body>
        <h1>MORE STAR 発売記念リリースイベント</h1>
        <p>■開催日時</p><p>2026年8月26日(水)</p><p>■場所</p><p>テスト会場</p>
        <p>受付時間：2026年8月25日(火)21:00〜2026年8月26日(水)9:00</p>
        </body></html>
        """

        class Response:
            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                return None

        class Session:
            def get(self, url, timeout=20):
                return Response({
                    f"{base}/": home,
                    article_url: article,
                    detail_url: detail,
                }.get(url, '<a href="/news/detail/1">通常のお知らせ</a>'))

        events, failures, _ = s.discover(
            Session(), "MORE STAR", base, today=datetime(2026, 8, 24).date()
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(failures, [])
        self.assertEqual(events[0]["url"], detail_url)
        self.assertEqual(events[0]["discoverySourceUrl"], article_url)

    def test_release_event_detection_includes_plain_release_commemoration_title(self):
        self.assertRegex("3rdシングル発売記念イベント", s.SPECIAL_RE)

    def test_priority_announcement_source_outage_is_critical(self):
        base = "https://sweetsteady.asobisystem.com"

        class Response:
            text = '<a href="/news/detail/1">通常のお知らせ</a>'

            def raise_for_status(self):
                return None

        class Session:
            def get(self, url, timeout=20):
                if url == f"{base}/":
                    raise s.requests.RequestException("homepage unavailable")
                return Response()

        _, failures, reachable = s.discover(
            Session(), "SWEET STEADY", base, today=datetime(2026, 8, 24).date()
        )
        self.assertTrue(reachable)
        self.assertTrue(any(
            failure.get("stage") == "discovery" and failure.get("critical")
            for failure in failures
        ))

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

    def test_large_benefit_extracts_plain_reservation_period(self):
        html = """
        <html><head><title>FRUITS ZIPPER大特典会</title></head><body>
        <h1>9/6(日)FRUITS ZIPPER大特典会をベルサール汐留にて開催決定！</h1>
        <p>2026.08.24</p><p>■開催日程</p><p>2026年9月6日(日)</p>
        <p>■開催会場</p><p>ベルサール汐留</p>
        <p>&lt;第2部&gt; プリントチェキお渡し会(先着) 11:20〜12:20 (受付開始11:00／受付終了12:00)</p>
        <p>対象商品予約期間：8月25日(火)21:00～8月27日(木)11:59まで</p>
        <p>■イベント参加対象商品</p><p>2026年7月15日(水)発売</p>
        <p>通常盤(KLF-10026)／¥1,200 (税込)</p>
        <a href="https://www.hmv.co.jp/example">HMV</a>
        <a href="https://sukisuki-shop.com/contact">電子チケット問い合わせ</a>
        </body></html>
        """
        events = s.parse_page("FRUITS ZIPPER", "https://fruitszipper.asobisystem.com/news/detail/88153", html, datetime(2026, 8, 24, tzinfo=JST))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["applyStart"], "2026-08-25T21:00")
        self.assertEqual(events[0]["applyEnd"], "2026-08-27T11:59")
        self.assertEqual(events[0]["ticketProvider"], "hmv")

    def test_large_benefit_without_announced_window_is_published_as_schedule_only(self):
        html = """
        <html><head><title>SWEET STEADY大特典会</title></head><body>
        <h1>SWEET STEADY大特典会を開催決定！</h1>
        <p>2026.09.01</p><p>■開催日程</p><p>2026年9月22日(火・祝)</p>
        <p>■開催会場</p><p>東京流通センター 第二展示場 Fホール</p>
        <p>参加方法の詳細は後日お知らせします。</p>
        </body></html>
        """
        events = s.parse_page(
            "SWEET STEADY",
            "https://sweetsteady.asobisystem.com/news/detail/1",
            html,
            datetime(2026, 9, 1, tzinfo=JST),
        )
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["ticketType"], "現在受付なし")
        self.assertEqual(event["specialDetailsStatus"], "awaiting-details")
        self.assertEqual(event["applicationDisplayMode"], "schedule-only")

    def test_fc_lottery_extracts_entry_result_and_payment_windows(self):
        html = """
        <html><head><title>FRUITS ZIPPER大特典会 ファンクラブ限定部 抽選</title></head><body>
        <h1>9/6(日) FRUITS ZIPPER大特典会のファンクラブ限定部 抽選が決定！</h1>
        <p>2026.08.24</p><p>■開催日程</p><p>2026年9月6日(日)</p>
        <p>■開催会場</p><p>ベルサール汐留</p>
        <p>&lt;第1部&gt; 2ショットチェキ撮影会 10:00〜11:00 (受付開始9:40／受付終了10:40)</p>
        <p>&lt;第2部&gt; プリントチェキお渡し会 11:20〜12:20 (受付開始11:00／受付終了12:00)</p>
        <p>&lt;第5部&gt; 2ショットチェキ撮影会 16:40〜17:40 (受付開始16:20／受付終了17:20)</p>
        <p>第1部、第5部はファンクラブ限定抽選です。1部、5部のみ実施します。</p>
        <p>イベント参加対象商品 応募期間：8月25日(火)21:00～8月26日(水)23:59</p>
        <p>■当選発表日時</p><p>2026年8月28日(金) 中</p>
        <p>購入期間：当選発表後 ~ 8月29日(土)23:59</p>
        <p>1部、5部1次エントリー受付：8月25日(火)21:00～8月26日(水)23:59</p>
        <p>電子チケットの発行は9/1（火）中を予定しております。</p>
        <p>■イベント参加対象商品</p><p>2026年7月15日(水)発売</p>
        <p>通常盤(KLF-10026)／¥1,200 (税込)</p>
        <a href="https://sukisuki-shop.com/goods/6500000004022">SUKISUKI</a>
        </body></html>
        """
        events = s.parse_page(
            "FRUITS ZIPPER",
            "https://fruitszipper.asobisystem.com/news/detail/88156",
            html,
            datetime(2026, 8, 24, tzinfo=JST),
        )
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["ticketProvider"], "sukisuki")
        self.assertEqual(event["applyStart"], "2026-08-25T21:00")
        self.assertEqual(event["applyEnd"], "2026-08-26T23:59")
        self.assertEqual(event["resultDate"], "2026-08-28")
        self.assertEqual(event["paymentEnd"], "2026-08-29T23:59")
        self.assertIn("抽選", event["ticketType"])
        self.assertIn("1部・5部1次エントリー受付", event["ticketType"])
        self.assertEqual([part["part"] for part in event["parts"]], ["第1部", "第5部"])
        self.assertIn("9月1日", event["ticketIssueMethod"])

    def test_fresh_detail_replaces_schedule_placeholder_without_changing_id(self):
        placeholder = {
            "id": "official-row", "group": "FRUITS ZIPPER",
            "title": "FRUITS ZIPPER 5thシングルCD発売記念イベント 大特典会@ベルサール汐留",
            "eventDate": "2026-09-06", "sourceType": "official-schedule",
            "url": "https://fruitszipper.asobisystem.com/live_information/detail/42630",
        }
        fresh = {
            "id": "fresh", "group": "FRUITS ZIPPER", "title": "FRUITS ZIPPER大特典会",
            "eventDate": "2026-09-06", "eventCategory": "large-benefit",
            "sourceType": "official-special", "url": "https://fruitszipper.asobisystem.com/news/detail/88153",
            "urls": ["https://fruitszipper.asobisystem.com/news/detail/88153"],
        }
        merged = s.merge_payload({"events": [placeholder]}, [fresh], today=datetime(2026, 8, 24).date())
        self.assertEqual(len(merged["events"]), 1)
        self.assertEqual(merged["events"][0]["id"], "official-row")
        self.assertEqual(merged["events"][0]["sourceType"], "official-special")
        self.assertIn(placeholder["url"], merged["events"][0]["urls"])

    def test_followup_refresh_keeps_upgraded_placeholder_id(self):
        current = {
            "id": "official-row", "group": "FRUITS ZIPPER", "title": "FRUITS ZIPPER大特典会",
            "eventDate": "2026-09-06", "eventCategory": "large-benefit",
            "sourceType": "official-special", "applyStart": "2026-08-25T21:00",
            "applyEnd": "2026-08-27T11:59",
            "url": "https://fruitszipper.asobisystem.com/news/detail/88153",
            "officialScheduleUrl": "https://fruitszipper.asobisystem.com/live_information/detail/42630",
        }
        refreshed = dict(current, id="generated-id", ticketType="更新済み")
        merged = s.merge_payload({"events": [current]}, [refreshed], today=datetime(2026, 8, 24).date())
        self.assertEqual(len(merged["events"]), 1)
        self.assertEqual(merged["events"][0]["id"], "official-row")
        self.assertEqual(merged["events"][0]["ticketType"], "更新済み")

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
