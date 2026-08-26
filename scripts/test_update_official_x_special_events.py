import unittest
from datetime import date

import update_official_x_special_events as s


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

    def test_profile_ignores_past_special_event(self):
        html = '''
        <article itemtype="https://schema.org/SocialMediaPosting" itemid="https://x.com/i/status/1">
          <meta itemprop="url" content="https://x.com/SWEET_STEADY/status/1">
          <span>リリースイベント 8/20(木)</span><span>📍テスト会場</span>
        </article>
        '''
        self.assertEqual(s.parse_profile("SWEET STEADY", "SWEET_STEADY", html, date(2026, 8, 26)), [])

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


if __name__ == "__main__":
    unittest.main()
