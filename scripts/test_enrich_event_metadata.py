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

    def test_unrelated_event_is_not_changed(self):
        payload = {
            "events": [
                {
                    "group": "CANDY TUNE",
                    "title": "CANDY TUNE JAPAN TOUR 2026",
                    "eventDate": "2026-10-01",
                    "venue": None,
                    "url": "https://candytune.asobisystem.com/news/detail/86518",
                }
            ]
        }
        result, changed = e.enrich_payload(payload)
        self.assertEqual(changed, 0)
        self.assertIsNone(result["events"][0]["venue"])


if __name__ == "__main__":
    unittest.main()
