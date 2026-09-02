import unittest
from datetime import date

import update_official_press_release_events as p


class OfficialPressReleaseEventTests(unittest.TestCase):
    def test_candy_tune_release_schedule_keeps_future_kobe_event(self):
        html = '''
        <html><head><title>CANDY TUNE 4thシングルCDのジャケット解禁</title></head><body>
          <h1>CANDY TUNE 4thシングルCDのジャケット解禁</h1>
          <p>2026年8月22日</p>
          <p>＜リリースイベント＞</p>
          <p>9/1（火）リリースイベント エミテラス所沢2F TOKOROZAWA e-CUBE</p>
          <p>9/5（土）大特典会 ベルサール汐留</p>
          <p>9/11（金）リリースイベント 神戸ハーバーランド スペースシアター</p>
          <p>9/22（火・祝）大特典会 大特典会＠東京流通センター 第二展示場Eホール</p>
        </body></html>
        '''
        events = p.parse_article(
            "https://prtimes.jp/main/html/rd/p/000000861.000017258.html",
            html,
            date(2026, 9, 2),
        )
        rows = [(e["eventDate"], e["eventCategory"], e["venue"]) for e in events]
        self.assertEqual(rows, [
            ("2026-09-05", "large-benefit", "ベルサール汐留"),
            ("2026-09-11", "release-event", "神戸ハーバーランド スペースシアター"),
            ("2026-09-22", "large-benefit", "東京流通センター 第二展示場Eホール"),
        ])
        kobe = events[1]
        self.assertEqual(kobe["group"], "CANDY TUNE")
        self.assertEqual(kobe["applicationDisplayMode"], "schedule-only")
        self.assertEqual(kobe["sourceChannel"], "official-prtimes")


if __name__ == "__main__":
    unittest.main()
