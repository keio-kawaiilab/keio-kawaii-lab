from datetime import date
import unittest

from update_official_x_special_events import parse_profile, special_category


class OfficialXSpecialEventTests(unittest.TestCase):
    def test_birthday_live_is_tracked_as_solo_live(self):
        self.assertEqual(special_category("SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026"), "solo-live")
        self.assertEqual(special_category("庄司なぎさ 生誕祭 2026"), "solo-live")
        self.assertEqual(special_category("庄司なぎさ 生誕ライブ"), "solo-live")

    def test_parse_birthday_live_post(self):
        html = '''
        <html><body>
          <article itemtype="https://schema.org/SocialMediaPosting" itemid="https://x.com/SWEET_STEADY/status/123456789">
            <meta content="https://x.com/SWEET_STEADY/status/123456789" />
            <div>SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026</div>
            <div>📅 2026/10/26</div>
            <div>📍 SGCホール有明</div>
          </article>
        </body></html>
        '''
        rows = parse_profile("SWEET STEADY", "SWEET_STEADY", html, today=date(2026, 8, 31))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["eventCategory"], "solo-live")
        self.assertEqual(row["eventDate"], "2026-10-26")
        self.assertEqual(row["venue"], "SGCホール有明")
        self.assertIn("庄司なぎさ BIRTHDAY LIVE 2026", row["title"])
        self.assertEqual(row["sourceChannel"], "official-x")

    def test_legacy_special_event_still_parses(self):
        html = '''
        <html><body>
          <article itemtype="https://schema.org/SocialMediaPosting" itemid="https://x.com/CANDY_TUNE_/status/999">
            <meta content="https://x.com/CANDY_TUNE_/status/999" />
            <div>CANDY TUNE リリースイベント</div>
            <div>📅 2026/09/01</div>
            <div>📍 エミテラス所沢</div>
          </article>
        </body></html>
        '''
        rows = parse_profile("CANDY TUNE", "CANDY_TUNE_", html, today=date(2026, 8, 31))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["eventCategory"], "release-event")


if __name__ == "__main__":
    unittest.main()
