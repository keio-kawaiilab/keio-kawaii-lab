import unittest

import enrich_event_metadata as e


class EnrichEventMetadataTests(unittest.TestCase):
    def test_ogawa_birthday_venue_is_filled(self):
        payload = {
            "events": [
                {
                    "group": "CANDY TUNE",
                    "title": "CANDY TUNE 小川奈々子 生誕祭 2026",
                    "eventDate": "2026-10-01",
                    "venue": None,
                    "url": "https://candytune.asobisystem.com/news/detail/87180",
                    "urls": [
                        "https://candytune.asobisystem.com/news/detail/86518",
                        "https://candytune.asobisystem.com/news/detail/87180",
                    ],
                }
            ]
        }
        result, changed = e.enrich_payload(payload)
        self.assertEqual(changed, 1)
        self.assertEqual(result["events"][0]["venue"], "SGCホール有明")

    def test_tour_news_link_is_replaced_by_official_feature(self):
        payload = {
            "events": [
                {
                    "group": "CANDY TUNE",
                    "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                    "eventDate": "2026-08-29",
                    "sourceType": "derived",
                    "url": "https://candytune.asobisystem.com/news/detail/82537",
                    "urls": ["https://candytune.asobisystem.com/news/detail/82537"],
                }
            ]
        }
        result, changed = e.enrich_payload(payload)
        event = result["events"][0]
        expected = "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026"
        self.assertEqual(changed, 1)
        self.assertEqual(event["url"], expected)
        self.assertEqual(event["officialTourUrl"], expected)
        self.assertEqual(event["urls"][0], expected)
        self.assertIn("https://candytune.asobisystem.com/news/detail/82537", event["urls"])

    def test_all_known_tours_use_their_feature_pages(self):
        cases = [
            (
                "FRUITS ZIPPER",
                "FRUITS ZIPPER JAPAN TOUR 2026 - AUTUMN -",
                "https://fruitszipper.asobisystem.com/feature/2026tour_autumn",
            ),
            (
                "CANDY TUNE",
                "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026",
            ),
            (
                "SWEET STEADY",
                "SWEET STEADY JAPAN HALL TOUR 2026",
                "https://sweetsteady.asobisystem.com/feature/sweetsteady_japanhalltour2026",
            ),
            (
                "CUTIE STREET",
                "CUTIE STREET ARENA TOUR 2026",
                "https://cutiestreet.asobisystem.com/feature/autumntour",
            ),
        ]
        for group, title, expected in cases:
            with self.subTest(group=group):
                payload = {
                    "events": [
                        {
                            "group": group,
                            "title": title,
                            "eventDate": "2026-10-10",
                            "sourceType": "derived",
                            "url": "https://example.invalid/old-source",
                        }
                    ]
                }
                result, changed = e.enrich_payload(payload)
                self.assertEqual(changed, 1)
                self.assertEqual(result["events"][0]["url"], expected)
                self.assertEqual(result["events"][0]["officialTourUrl"], expected)

    def test_playguide_tour_link_is_not_overwritten(self):
        payload = {
            "events": [
                {
                    "group": "FRUITS ZIPPER",
                    "title": "FRUITS ZIPPER JAPAN TOUR 2026 - AUTUMN -",
                    "eventDate": "2026-09-03",
                    "sourceType": "pia",
                    "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=12345",
                }
            ]
        }
        result, changed = e.enrich_payload(payload)
        self.assertEqual(changed, 0)
        self.assertTrue(result["events"][0]["url"].startswith("https://t.pia.jp/"))

    def test_unrelated_event_is_not_changed(self):
        payload = {
            "events": [
                {
                    "group": "CANDY TUNE",
                    "title": "CANDY TUNE 単独ライブ",
                    "eventDate": "2026-10-01",
                    "venue": None,
                    "url": "https://candytune.asobisystem.com/news/detail/99999",
                }
            ]
        }
        result, changed = e.enrich_payload(payload)
        self.assertEqual(changed, 0)
        self.assertIsNone(result["events"][0]["venue"])


if __name__ == "__main__":
    unittest.main()
