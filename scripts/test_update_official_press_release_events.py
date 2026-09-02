import unittest
from datetime import date

import update_official_press_release_events as p


class OfficialPressReleaseEventTests(unittest.TestCase):
    def test_candy_tune_inline_release_schedule_keeps_all_future_rows(self):
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
        self.assertEqual(events[1]["group"], "CANDY TUNE")
        self.assertEqual(events[1]["applicationDisplayMode"], "schedule-only")
        self.assertEqual(events[1]["sourceChannel"], "official-prtimes")

    def test_fruits_zipper_section_style_schedule_parses_multiple_venues(self):
        html = '''
        <html><head><title>FRUITS ZIPPER 5thシングルのタイトル＆ジャケットが解禁</title></head><body>
          <h1>FRUITS ZIPPER 5thシングルのタイトル＆ジャケットが解禁</h1>
          <p>2026年6月22日</p>
          <p>＜リリースイベント＞</p>
          <p>2026年7月16日（木）</p>
          <p>関東某所 参加メンバー：仲川瑠夏、早瀬ノエル、真中まな</p>
          <p>千葉県某所 参加メンバー：松本かれん</p>
          <p>※詳細はオフィシャルサイトをご確認ください。</p>
          <p>＜開催中アリーナツアー情報＞</p>
        </body></html>
        '''
        events = p.parse_article(
            "https://prtimes.jp/main/html/rd/p/000000797.000017258.html",
            html,
            date(2026, 6, 23),
        )
        self.assertEqual(
            [(e["eventDate"], e["eventCategory"], e["venue"]) for e in events],
            [
                ("2026-07-16", "release-event", "関東某所"),
                ("2026-07-16", "release-event", "千葉県某所"),
            ],
        )

    def test_pr_placeholder_does_not_override_richer_official_row(self):
        payload = {
            "events": [{
                "id": "rich",
                "group": "CANDY TUNE",
                "eventDate": "2026-09-11",
                "eventCategory": "release-event",
                "sourceType": "official-special",
                "sourceChannel": "official-site",
                "primarySource": "official",
                "venue": "神戸ハーバーランド スペースシアター",
            }]
        }
        pr = p.make_event(
            "CANDY TUNE",
            date(2026, 9, 11),
            "release-event",
            "神戸ハーバーランド スペースシアター",
            "https://prtimes.jp/main/html/rd/p/000000861.000017258.html",
        )
        merged = p.merge_payload(payload, [pr], date(2026, 9, 2))
        self.assertEqual(merged["events"], payload["events"])


if __name__ == "__main__":
    unittest.main()
