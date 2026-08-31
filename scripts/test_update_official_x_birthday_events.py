import json
import unittest
from datetime import date

import update_official_x_birthday_events as b


class OfficialXBirthdayFallbackTests(unittest.TestCase):
    def _html(self, text: str, tweet_id: str = "2100000000000000000") -> str:
        payload = {
            "props": {
                "pageProps": {
                    "timeline": {
                        "entries": [
                            {
                                "content": {
                                    "tweet": {
                                        "id_str": tweet_id,
                                        "text": text,
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }
        return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload, ensure_ascii=False) + '</script>'

    def test_extracts_birthday_post_from_syndication_payload(self):
        text = (
            "✨🎂〖生誕祭開催決定〗🎂✨\n"
            "🧡庄司なぎさ生誕祭2026🧡\n"
            "10/26(月) 『SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026』\n"
            "📍SGCホール有明\n"
            "🕰️OPEN 17:30/START 19:00"
        )
        posts = b.extract_posts_from_next_data(self._html(text), "SWEET_STEADY")
        self.assertEqual(len(posts), 1)
        url, parsed_text = posts[0]
        self.assertEqual(url, "https://x.com/SWEET_STEADY/status/2100000000000000000")
        self.assertIn("庄司なぎさ", parsed_text)

        events = b.event_from_post("SWEET STEADY", url, parsed_text, date(2026, 8, 31))
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["eventDate"], "2026-10-26")
        self.assertEqual(event["venue"], "SGCホール有明")
        self.assertEqual(event["eventCategory"], "solo-live")
        self.assertIn("庄司なぎさ BIRTHDAY LIVE 2026", event["title"])
        self.assertEqual(event["sourceChannel"], "official-x-syndication")

    def test_ignores_non_birthday_posts(self):
        text = "10/26(月) SWEET STEADY 通常ライブ\n📍SGCホール有明"
        self.assertEqual(b.extract_posts_from_next_data(self._html(text), "SWEET_STEADY"), [])

    def test_merge_keeps_official_site_row_over_social_fallback(self):
        payload = {"events": [{
            "id": "official",
            "group": "SWEET STEADY",
            "title": "庄司なぎさ 生誕祭 2026",
            "eventCategory": "solo-live",
            "eventDate": "2026-10-26",
            "venue": "SGCホール有明",
            "sourceType": "official-schedule",
            "primarySource": "official",
        }]}
        fallback = [{
            "id": "fallback",
            "group": "SWEET STEADY",
            "title": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventCategory": "solo-live",
            "eventDate": "2026-10-26",
            "venue": "SGCホール有明",
            "sourceType": "official-social",
            "primarySource": "official",
        }]
        merged = b.merge_birthday_events(payload, fallback)
        self.assertEqual(len(merged["events"]), 1)
        self.assertEqual(merged["events"][0]["id"], "official")


if __name__ == "__main__":
    unittest.main()
