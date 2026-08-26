import unittest
from datetime import date, datetime, timedelta, timezone

import update_official_x_special_events as s
import update_special_events as site_s


JST = timezone(timedelta(hours=9))


class OfficialXSpecialEventTests(unittest.TestCase):
    def test_profile_parses_future_release_event_placeholder(self):
        html = '''
        <html><body>
        <article itemtype="https://schema.org/SocialMediaPosting" itemid="https://x.com/i/status/2092522442585788839">
          <meta itemprop="url" content="https://x.com/SWEET_STEADY/status/2092522442585788839">
          <meta itemprop="description" content="💐🎡リリースイベント追加情報🎠💐\n『3rdシングル SWEET STEP 発売記念リリースイベント』の追加情報です📣\n9/14(月)\n📍北海道 サッポロファクトリー アトリウム\n詳細は追ってお知らせします📣">
          <span>💐🎡リリースイベント追加情報🎠💐</span>
          <span>『3rdシングル SWEET STEP 発売記念リリースイベント』の追加情報です📣</span>
          <span>9/14(月)</span>
          <span>📍北海道 サッポロファクトリー アトリウム</span>
        </article>
        </body></html>
        '''
        events = s.parse_profile("SWEET STEADY", "SWEET_STEADY", html, date(2026, 8, 26))
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["eventDate"], "2026-09-14")
        self.assertEqual(event["venue"], "北海道 サッポロファクトリー アトリウム")
        self.assertEqual(event["sourceType"], "official-social")
        self.assertEqual(event["specialDetailsStatus"], "awaiting-details")
        self.assertEqual(event["applicationDisplayMode"], "schedule-only")
        self.assertEqual(event["url"], "https://x.com/SWEET_STEADY/status/2092522442585788839")

    def test_profile_parses_multiple_date_venue_pairs_from_one_post(self):
        html = '''
        <html><body>
        <article itemtype="https://schema.org/SocialMediaPosting" itemid="https://x.com/i/status/222">
          <meta itemprop="url" content="https://x.com/CANDY_TUNE_/status/222">
          <meta itemprop="description" content="リリースイベント追加情報\n9/1(火)\n📍埼玉県 エミテラス所沢\n9/14(月)\n📍北海道 サッポロファクトリー アトリウム\n詳細は後日発表">
        </article>
        </body></html>
        '''
        events = s.parse_profile("CANDY TUNE", "CANDY_TUNE_", html, date(2026, 8, 26))
        self.assertEqual([(e["eventDate"], e["venue"]) for e in events], [
            ("2026-09-01", "埼玉県 エミテラス所沢"),
            ("2026-09-14", "北海道 サッポロファクトリー アトリウム"),
        ])

    def test_profile_parses_three_solo_lives_with_individual_titles(self):
        html = '''
        <html><body>
        <article itemtype="https://schema.org/SocialMediaPosting" itemid="https://x.com/i/status/333">
          <meta itemprop="url" content="https://x.com/MORE_STAR_/status/333">
          <meta itemprop="description" content="✨🌟〖単独ライブ〗開催決定🎉✨\n#MORESTAR 3ヶ月連続🔥 単独ライブの開催が決定しました❕💫\n9/24(木) 『MORE STAR 単独ライブ 5th STAR』\n📍ヒューリックホール東京\n🕰️OPEN 17:00\n10/21(水) 『MORE STAR 単独ライブ 6th STAR』\n📍Spotify O-WEST\n11/12(木) 『MORE STAR 単独ライブ 7th STAR』\n📍ヒューリックホール東京">
        </article>
        </body></html>
        '''
        events = s.parse_profile("MORE STAR", "MORE_STAR_", html, date(2026, 8, 26))
        self.assertEqual([(e["eventDate"], e["title"], e["venue"], e["eventCategory"]) for e in events], [
            ("2026-09-24", "MORE STAR 単独ライブ 5th STAR", "ヒューリックホール東京", "solo-live"),
            ("2026-10-21", "MORE STAR 単独ライブ 6th STAR", "Spotify O-WEST", "solo-live"),
            ("2026-11-12", "MORE STAR 単独ライブ 7th STAR", "ヒューリックホール東京", "solo-live"),
        ])

    def test_profile_ignores_past_special_event(self):
        html = '''
        <article itemtype="https://schema.org/SocialMediaPosting" itemid="https://x.com/i/status/1">
          <meta itemprop="url" content="https://x.com/SWEET_STEADY/status/1">
          <span>リリースイベント 8/20(木)</span><span>📍テスト会場</span>
        </article>
        '''
        self.assertEqual(s.parse_profile("SWEET STEADY", "SWEET_STEADY", html, date(2026, 8, 26)), [])

    def test_profile_payload_guard_requires_public_timeline(self):
        self.assertTrue(s.profile_payload_loaded('<article itemtype="SocialMediaPosting"><a href="/status/1">x</a></article>'))
        self.assertFalse(s.profile_payload_loaded('<html><body>login</body></html>'))

    def test_official_site_entry_suppresses_social_placeholder(self):
        payload = {"events": [{
            "id": "official",
            "group": "SWEET STEADY",
            "title": "3rdシングル SWEET STEP 発売記念リリースイベント",
            "eventCategory": "release-event",
            "eventDate": "2026-09-14",
            "venue": "北海道 サッポロファクトリー アトリウム",
            "sourceType": "official-special",
            "primarySource": "official",
        }]}
        social = [{
            "id": "social",
            "group": "SWEET STEADY",
            "title": "リリースイベント",
            "eventCategory": "release-event",
            "eventDate": "2026-09-14",
            "venue": "北海道 サッポロファクトリー アトリウム",
            "sourceType": "official-social",
            "primarySource": "official",
        }]
        merged = s.merge_payload(payload, social, date(2026, 8, 26))
        self.assertEqual(len(merged["events"]), 1)
        self.assertEqual(merged["events"][0]["id"], "official")

    def test_existing_social_placeholder_gets_exact_post_url(self):
        payload = {"events": [{
            "id": "keep-id",
            "group": "SWEET STEADY",
            "title": "リリースイベント",
            "eventCategory": "release-event",
            "eventDate": "2026-09-14",
            "venue": "北海道 サッポロファクトリー アトリウム",
            "url": "https://x.com/SWEET_STEADY",
            "urls": ["https://x.com/SWEET_STEADY"],
            "sourceType": "official-social",
            "primarySource": "official",
        }]}
        social = [{
            "id": "new-id",
            "group": "SWEET STEADY",
            "title": "3rdシングル SWEET STEP 発売記念リリースイベント",
            "eventCategory": "release-event",
            "eventDate": "2026-09-14",
            "venue": "北海道 サッポロファクトリー アトリウム",
            "url": "https://x.com/SWEET_STEADY/status/2092522442585788839",
            "urls": ["https://x.com/SWEET_STEADY/status/2092522442585788839"],
            "sourceType": "official-social",
            "primarySource": "official",
        }]
        merged = s.merge_payload(payload, social, date(2026, 8, 26))
        self.assertEqual(merged["events"][0]["id"], "keep-id")
        self.assertIn("/status/", merged["events"][0]["url"])

    def test_official_site_release_announcement_without_window_is_kept_as_placeholder(self):
        html = '''
        <html><head><title>SWEET STEADY リリースイベント</title></head><body>
          <h1>『3rdシングル SWEET STEP 発売記念リリースイベント』追加情報</h1>
          <p>2026.08.26</p>
          <p>■開催日時</p><p>2026年9月14日(月)</p>
          <p>■場所</p><p>サッポロファクトリー アトリウム</p>
          <p>詳細は追ってお知らせします。</p>
        </body></html>
        '''
        events = site_s.parse_page(
            "SWEET STEADY",
            "https://sweetsteady.asobisystem.com/news/detail/99999",
            html,
            datetime(2026, 8, 26, 19, 0, tzinfo=JST),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["eventDate"], "2026-09-14")
        self.assertEqual(events[0]["applicationDisplayMode"], "schedule-only")
        self.assertEqual(events[0]["specialDetailsStatus"], "awaiting-details")
        self.assertEqual(events[0]["sourceType"], "official-special")


if __name__ == "__main__":
    unittest.main()
