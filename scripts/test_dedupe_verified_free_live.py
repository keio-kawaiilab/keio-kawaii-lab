import unittest

from dedupe_verified_free_live import ARTICLE, collapse


class VerifiedFreeLiveDedupeTests(unittest.TestCase):
    def test_same_central_article_is_one_verified_performance(self):
        canonical = {
            "id": "central-ticket",
            "group": "KAWAII LAB.合同",
            "title": "KAWAII LAB. ファンクラブ限定フリーライブ",
            "eventDate": "2026-11-06",
            "venue": "東京ガーデンシアター",
            "openTime": "16:30",
            "startTime": "18:00",
            "url": ARTICLE,
            "offers": [{"ticketType": "KAWAII LAB. FC先行"}],
        }
        duplicate = {
            **canonical,
            "id": "central-body-discovery",
            "venue": "東京都 東京ガーデンシアター",
            # Regression: a parser once mistook OPEN for START.
            "startTime": "16:30",
        }

        corrected, report = collapse([duplicate, canonical])
        self.assertEqual(1, len(corrected))
        self.assertEqual("18:00", corrected[0]["startTime"])
        self.assertEqual("18:00", corrected[0]["schedule"][0]["startTime"])
        self.assertEqual(
            {"central-ticket", "central-body-discovery"},
            set(corrected[0]["sourceRowIds"]),
        )
        self.assertEqual(1, report["verifiedFreeLiveRowsCollapsed"])

        again, second_report = collapse(corrected)
        self.assertEqual(corrected, again)
        self.assertEqual(0, second_report["verifiedFreeLiveRowsCollapsed"])

    def test_different_schedule_url_remains_as_provenance(self):
        central = {
            "id": "central", "group": "KAWAII LAB.合同",
            "title": "KAWAII LAB. ファンクラブ限定フリーライブ",
            "eventDate": "2026-11-06", "venue": "東京都 東京ガーデンシアター",
            "startTime": "18:00", "url": ARTICLE,
        }
        schedule = {
            **central,
            "id": "more-star-schedule",
            "group": "MORE STAR",
            "url": "https://morestar.asobisystem.com/live_information/detail/46834",
        }
        corrected, report = collapse([central, schedule])
        self.assertEqual(2, len(corrected))
        self.assertEqual(0, report["verifiedFreeLiveRowsCollapsed"])


if __name__ == "__main__":
    unittest.main()

