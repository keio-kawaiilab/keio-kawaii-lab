import json
import unittest
from datetime import date

import update_official_x_special_events_syndication as s


class OfficialXSyndicationSpecialEventTests(unittest.TestCase):
    def _html(self, text: str, tweet_id: str = "2100000000000000002") -> str:
        payload = {
            "props": {
                "pageProps": {
                    "timeline": {
                        "entries": [{
                            "content": {
                                "tweet": {
                                    "id_str": tweet_id,
                                    "text": text,
                                }
                            }
                        }]
                    }
                }
            }
        }
        return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload, ensure_ascii=False) + '</script>'

    def test_candy_tune_multi_date_release_post_keeps_september_11(self):
        text = (
            "🍬🎸リリースイベント情報解禁🥁🍬\n"
            "9月1日(火) びびなつFEVER ユニット リリースイベント\n"
            "📍エミテラス所沢 2F TOKOROZAWA e-CUBE\n"
            "9月11日(金) CANDY TUNE 4thシングルCD 『総意♡So Free / スペシャル感謝祭』 リリースイベント\n"
            "📍神戸ハーバーランド スペースシアター\n"
            "詳細は後日改めてお知らせします"
        )
        posts = s.extract_posts_from_next_data(self._html(text), "CANDY_TUNE_")
        self.assertEqual(len(posts), 1)
        x_url, parsed_text, official_urls = posts[0]
        events = s.events_from_post("CANDY TUNE", x_url, parsed_text, date(2026, 9, 2), official_urls)
        self.assertEqual(
            [(event["eventDate"], event["venue"], event["eventCategory"]) for event in events],
            [
                ("2026-09-11", "神戸ハーバーランド スペースシアター", "release-event"),
            ],
        )
        self.assertEqual(events[0]["applicationDisplayMode"], "schedule-only")
        self.assertEqual(events[0]["specialDetailsStatus"], "awaiting-details")
        self.assertEqual(events[0]["sourceChannel"], "official-x-syndication")


if __name__ == "__main__":
    unittest.main()
