import json
import unittest
from datetime import date

import update_official_x_birthday_events as b


class OfficialXBirthdayFallbackTests(unittest.TestCase):
    def _html(
        self,
        text: str,
        tweet_id: str = "2100000000000000000",
        official_url: str | None = None,
    ) -> str:
        tweet = {
            "id_str": tweet_id,
            "text": text,
        }
        if official_url:
            tweet["entities"] = {
                "urls": [{
                    "url": "https://t.co/example",
                    "expanded_url": official_url,
                }]
            }
        payload = {
            "props": {
                "pageProps": {
                    "timeline": {
                        "entries": [
                            {
                                "content": {
                                    "tweet": tweet
                                }
                            }
                        ]
                    }
                }
            }
        }
        return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload, ensure_ascii=False) + '</script>'

    def test_extracts_birthday_post_and_official_detail_url(self):
        text = (
            "✨🎂〖生誕祭開催決定〗🎂✨\n"
            "🧡庄司なぎさ生誕祭2026🧡\n"
            "10/26(月) 『SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026』\n"
            "📍SGCホール有明\n"
            "🕰️OPEN 17:30/START 19:00"
        )
        official = "https://sweetsteady.asobisystem.com/news/detail/88999"
        posts = b.extract_posts_from_next_data(self._html(text, official_url=official), "SWEET_STEADY")
        self.assertEqual(len(posts), 1)
        url, parsed_text, official_urls = posts[0]
        self.assertEqual(url, "https://x.com/SWEET_STEADY/status/2100000000000000000")
        self.assertIn("庄司なぎさ", parsed_text)
        self.assertEqual(official_urls, [official])

        events = b.event_from_post("SWEET STEADY", url, parsed_text, date(2026, 8, 31), official_urls)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["eventDate"], "2026-10-26")
        self.assertEqual(event["venue"], "SGCホール有明")
        self.assertEqual(event["eventCategory"], "solo-live")
        self.assertIn("庄司なぎさ BIRTHDAY LIVE 2026", event["title"])
        self.assertEqual(event["url"], official)
        self.assertIn(url, event["urls"])
        self.assertEqual(event["sourceChannel"], "official-x-syndication")

    def test_shoji_fc_window_is_not_thrown_away(self):
        text = (
            "✨庄司なぎさ生誕祭2026 開催決定✨\n"
            "10/26(月) 『SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026』\n"
            "📍SGCホール有明\n"
            "SWEET STEADY FC先行受付\n"
            "受付期間：8/31(月)19:00〜9/8(火)23:59"
        )
        official = "https://sweetsteady.asobisystem.com/news/detail/88999"
        x_url = "https://x.com/SWEET_STEADY/status/2100000000000000000"
        event = b.event_from_post(
            "SWEET STEADY", x_url, text, date(2026, 8, 31), [official]
        )[0]
        self.assertEqual(event["ticketType"], "FC先行")
        self.assertEqual(event["applyStart"], "2026-08-31T19:00")
        self.assertEqual(event["applyEnd"], "2026-09-08T23:59")
        self.assertEqual(event["applicationStatus"], "open")
        self.assertEqual(event["applicationDisplayMode"], "band")
        self.assertEqual(event["url"], official)
        self.assertEqual(event["applicationWindowSource"], x_url)

    def test_cutie_three_birthdays_share_verified_fc_window(self):
        text = (
            "【古澤里紗 板倉可奈 佐野愛花 生誕祭 開催決定】\n"
            "11/9(月) CUTIE STREET 古澤里紗 生誕祭 2026\n"
            "📍SGCホール有明\n"
            "11/11(水) CUTIE STREET 板倉可奈 生誕祭 2026\n"
            "📍SGCホール有明\n"
            "11/26(木) CUTIE STREET 佐野愛花 生誕祭 2026\n"
            "📍SGCホール有明\n"
            "FC会員 年会費コース限定先行受付\n"
            "受付期間：8/31(月)19:00〜9/7(月)23:59"
        )
        x_url = "https://x.com/CUTIE_STREET_/status/2100000000000000001"
        events = b.event_from_post("CUTIE STREET", x_url, text, date(2026, 8, 31))
        self.assertEqual([event["eventDate"] for event in events], [
            "2026-11-09", "2026-11-11", "2026-11-26"
        ])
        for event in events:
            self.assertEqual(event["ticketType"], "年会費コース会員先行")
            self.assertEqual(event["applyStart"], "2026-08-31T19:00")
            self.assertEqual(event["applyEnd"], "2026-09-07T23:59")
            self.assertNotEqual(event["applicationDisplayMode"], "schedule-only")

    def test_ignores_non_birthday_posts(self):
        text = "10/26(月) SWEET STEADY 通常ライブ\n📍SGCホール有明"
        self.assertEqual(b.extract_posts_from_next_data(self._html(text), "SWEET_STEADY"), [])

    def test_merge_keeps_ticket_rich_official_site_row_over_social_fallback(self):
        payload = {"events": [{
            "id": "official",
            "group": "SWEET STEADY",
            "title": "庄司なぎさ 生誕祭 2026",
            "eventCategory": "solo-live",
            "eventDate": "2026-10-26",
            "venue": "SGCホール有明",
            "ticketType": "FC先行",
            "applyStart": "2026-08-31T19:00",
            "applyEnd": "2026-09-08T23:59",
            "url": "https://sweetsteady.asobisystem.com/news/detail/88999",
            "sourceType": "auto",
            "primarySource": "official",
        }]}
        fallback = [{
            "id": "fallback",
            "group": "SWEET STEADY",
            "title": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventCategory": "solo-live",
            "eventDate": "2026-10-26",
            "venue": "SGCホール有明",
            "ticketType": "現在受付なし",
            "sourceType": "official-social",
            "primarySource": "official",
        }]
        merged = b.merge_birthday_events(payload, fallback)
        self.assertEqual(len(merged["events"]), 1)
        self.assertEqual(merged["events"][0]["id"], "official")
        self.assertEqual(merged["events"][0]["ticketType"], "FC先行")

    def test_merge_replaces_promoter_placeholder_with_official_social_ticket(self):
        promoter_url = "https://red-hot.ne.jp/play/detail.php?pid=py28687"
        official_url = "https://sweetsteady.asobisystem.com/news/detail/88999"
        x_url = "https://x.com/SWEET_STEADY/status/2100000000000000000"
        payload = {"events": [{
            "id": "promoter",
            "group": "SWEET STEADY",
            "title": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventTitle": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventCategory": "solo-live",
            "eventDate": "2026-10-26",
            "venue": "SGC HALL ARIAKE",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "url": promoter_url,
            "urls": [promoter_url],
            "sourceType": "promoter",
            "primarySource": "promoter",
            "sourceCandidates": ["promoter"],
        }]}
        fresh = [{
            "id": "social",
            "group": "SWEET STEADY",
            "title": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventTitle": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventCategory": "solo-live",
            "eventDate": "2026-10-26",
            "venue": "SGCホール有明",
            "ticketType": "FC先行",
            "applicationStatus": "open",
            "applyStart": "2026-08-31T19:00",
            "applyEnd": "2026-09-08T23:59",
            "url": official_url,
            "urls": [official_url, x_url],
            "sourceType": "official-social",
            "primarySource": "official",
            "sourceCandidates": ["official"],
        }]
        merged = b.merge_birthday_events(payload, fresh)
        self.assertEqual(len(merged["events"]), 1)
        event = merged["events"][0]
        self.assertEqual(event["url"], official_url)
        self.assertEqual(event["ticketType"], "FC先行")
        self.assertIn(promoter_url, event["urls"])
        self.assertIn(x_url, event["urls"])
        self.assertEqual(event["primarySource"], "official")

    def test_merge_enriches_official_schedule_placeholder_in_place(self):
        schedule_url = "https://cutiestreet.asobisystem.com/live_information/detail/45000"
        x_url = "https://x.com/CUTIE_STREET_/status/2100000000000000001"
        payload = {"events": [{
            "id": "schedule",
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 古澤里紗 生誕祭 2026",
            "eventTitle": "CUTIE STREET 古澤里紗 生誕祭 2026",
            "eventCategory": "solo-live",
            "eventDate": "2026-11-09",
            "venue": "SGCホール有明",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "url": schedule_url,
            "urls": [schedule_url],
            "sourceType": "official-schedule",
            "primarySource": "official",
            "sourceCandidates": ["official"],
        }]}
        fresh = [{
            "id": "social",
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 古澤里紗 生誕祭 2026",
            "eventTitle": "CUTIE STREET 古澤里紗 生誕祭 2026",
            "eventCategory": "solo-live",
            "eventDate": "2026-11-09",
            "venue": "SGCホール有明",
            "ticketType": "年会費コース会員先行",
            "applicationStatus": "open",
            "applyStart": "2026-08-31T19:00",
            "applyEnd": "2026-09-07T23:59",
            "url": "https://cutiestreet.asobisystem.com/news/detail/88998",
            "urls": ["https://cutiestreet.asobisystem.com/news/detail/88998", x_url],
            "sourceType": "official-social",
            "primarySource": "official",
            "sourceCandidates": ["official"],
        }]
        merged = b.merge_birthday_events(payload, fresh)
        self.assertEqual(len(merged["events"]), 1)
        event = merged["events"][0]
        self.assertEqual(event["id"], "schedule")
        self.assertEqual(event["url"], schedule_url)
        self.assertEqual(event["ticketType"], "年会費コース会員先行")
        self.assertEqual(event["applyEnd"], "2026-09-07T23:59")
        self.assertIn(x_url, event["urls"])


if __name__ == "__main__":
    unittest.main()
