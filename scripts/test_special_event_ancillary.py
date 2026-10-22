import unittest
from datetime import datetime, timedelta, timezone

import update_special_events as s

JST = timezone(timedelta(hours=9))


class AncillarySpecialEventTests(unittest.TestCase):
    def test_special_lottery_article_is_not_a_new_event(self):
        html = '''
        <html><body>
          <h1>8/16（日）FRUITS ZIPPER大特典会＠パシフィコ横浜にて特別抽選会開催決定！</h1>
          <p>2026.08.14</p>
          <p>【対象イベント】</p><p>2026年8月16日(日)＠パシフィコ横浜 展示ホールB</p>
          <p>CD購入者を対象に豪華景品が当たる抽選会を開催します。</p>
        </body></html>
        '''
        self.assertEqual(s.parse_page('FRUITS ZIPPER', 'https://example.com/lottery', html, datetime(2026, 8, 14, tzinfo=JST)), [])

    def test_merchandise_article_is_not_a_new_event(self):
        html = '''
        <html><body>
          <h1>8/15（土）MORE STAR 大特典会 物販情報</h1>
          <p>2026.08.11</p>
          <p>会場：東京流通センター 第二展示場Fホール</p>
          <p>販売時間：11:30〜20:00予定</p>
        </body></html>
        '''
        self.assertEqual(s.parse_page('MORE STAR', 'https://example.com/goods', html, datetime(2026, 8, 11, tzinfo=JST)), [])

    def test_main_release_announcement_is_still_parsed(self):
        html = '''
        <html><body>
          <h1>3rdシングル『SWEET STEP』発売記念リリースイベント</h1>
          <p>2026.08.26</p>
          <p>開催日時</p><p>2026年9月14日(月)</p>
          <p>場所</p><p>サッポロファクトリー アトリウム</p>
          <p>詳細は追ってお知らせします。</p>
        </body></html>
        '''
        parsed = s.parse_page('SWEET STEADY', 'https://example.com/main', html, datetime(2026, 8, 26, tzinfo=JST))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]['eventDate'], '2026-09-14')
        self.assertEqual(parsed[0]['specialDetailsStatus'], 'awaiting-details')

    def test_shared_benefit_article_keeps_group_details_separate(self):
        html = '''
        <html><body>
          <h1>11/3(火・祝) CUTIE STREET/MORE STAR大特典会を開催決定！</h1>
          <p>2026.10.22</p>
          <p>開催日程</p><p>2026年11月3日(火・祝)</p>
          <p>開催会場</p><p>パシフィコ横浜 展示ホールD</p>
          <p>&lt;CUTIE STREET&gt;</p>
          <p>&lt;第1部&gt; プリントチェキお渡し会 10:00〜11:00 (受付開始9:45／受付終了10:40)</p>
          <p>&lt;MORE STAR&gt;</p>
          <p>&lt;第1部&gt; 2ショットチェキ撮影会 11:20〜12:20 (受付開始11:05／受付終了12:00)</p>
          <p>イベント参加対象商品</p>
          <p>●CUTIE STREET</p>
          <p>2026年12月2日(水)発売</p>
          <p>CUTIE STREET 1stアルバム『CUTIE LAND』 通常盤 ¥3,300(税込)</p>
          <p>●MORE STAR</p>
          <p>2026年8月26日(水)発売</p>
          <p>MORE STAR 1stシングル『サマーゴー！！』 通常盤 ¥1,200(税込)</p>
          <p>&lt;CUTIE STREET&gt;</p>
          <p>対象商品予約期間：10月23日(金)21:00～10月27日(火)23:59まで</p>
          <a href="https://img.hmv.co.jp/cont/online/cutielandevent_lp/">CUTIE</a>
          <p>&lt;MORE STAR&gt;</p>
          <p>対象商品予約期間：10月24日(土)21:00～10月28日(水)23:59まで</p>
          <a href="https://img.hmv.co.jp/cont/online/morestarevent_lp/">MORE</a>
        </body></html>
        '''
        now = datetime(2026, 10, 23, tzinfo=JST)
        cutie = s.parse_page('CUTIE STREET', 'https://example.com/shared', html, now)[0]
        more = s.parse_page('MORE STAR', 'https://example.com/shared', html, now)[0]

        self.assertEqual(cutie['applyStart'], '2026-10-23T21:00')
        self.assertEqual(more['applyStart'], '2026-10-24T21:00')
        self.assertEqual([part['content'] for part in cutie['parts']], ['プリントチェキお渡し会'])
        self.assertEqual([part['content'] for part in more['parts']], ['2ショットチェキ撮影会'])
        self.assertIn('CUTIE LAND', cutie['product'])
        self.assertNotIn('サマーゴー', cutie['product'])
        self.assertIn('サマーゴー', more['product'])
        self.assertNotIn('CUTIE LAND', more['product'])
        self.assertTrue(any('cutielandevent_lp' in url for url in cutie['urls']))
        self.assertFalse(any('morestarevent_lp' in url for url in cutie['urls']))
        self.assertTrue(any('morestarevent_lp' in url for url in more['urls']))
        self.assertFalse(any('cutielandevent_lp' in url for url in more['urls']))

    def test_abbreviated_schedule_benefit_is_replaced_by_detail_article(self):
        payload = {"events": [{
            "id": "schedule-row",
            "group": "MORE STAR",
            "title": "MORE STAR 大特典＠パシフィコ横浜展示ホールD",
            "eventDate": "2026-11-03",
            "venue": "神奈川県 パシフィコ横浜展示ホールD",
            "sourceType": "auto",
            "sourceChannel": "official-continuous",
            "primarySource": "official",
            "url": "https://morestar.asobisystem.com/live_information/detail/46447",
            "officialScheduleUrl": "https://morestar.asobisystem.com/live_information/detail/46447",
        }]}
        fresh = [{
            "id": "article-row",
            "group": "MORE STAR",
            "eventTitle": "MORE STAR 大特典会",
            "eventCategory": "large-benefit",
            "eventDate": "2026-11-03",
            "venue": "神奈川県 パシフィコ横浜 展示ホールD",
            "sourceType": "official-special",
            "url": "https://morestar.asobisystem.com/news/detail/93714",
        }]
        merged = s.merge_payload(payload, fresh, datetime(2026, 10, 23, tzinfo=JST).date())
        self.assertEqual(len(merged["events"]), 1)
        self.assertEqual(merged["events"][0]["id"], "schedule-row")
        self.assertEqual(merged["events"][0]["eventCategory"], "large-benefit")
        self.assertEqual(
            merged["events"][0]["officialScheduleUrl"],
            "https://morestar.asobisystem.com/live_information/detail/46447",
        )


if __name__ == '__main__':
    unittest.main()
