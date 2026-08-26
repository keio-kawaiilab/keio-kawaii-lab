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


if __name__ == '__main__':
    unittest.main()
