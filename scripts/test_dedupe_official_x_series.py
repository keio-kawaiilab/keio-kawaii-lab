import unittest

import dedupe_official_x_series as dedupe


class OfficialXSeriesDedupeTests(unittest.TestCase):
    def test_split_more_star_release_series_is_recombined(self):
        shared = "https://x.com/MORE_STAR_/status/2093324279639392675"
        older = "https://x.com/MORE_STAR_/status/2092956382366744633"
        aggregate = {
            "id": "aggregate",
            "group": "MORE STAR",
            "title": "『サマーゴー！！/WITH KAWAII論』発売記念リリースイベント",
            "eventTitle": "『サマーゴー！！/WITH KAWAII論』発売記念リリースイベント",
            "displayTitle": "『サマーゴー！！/WITH KAWAII論』発売記念リリースイベント",
            "eventCategory": "release-event",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "eventDate": "2027-01-03",
            "eventEndDate": "2027-02-04",
            "eventDates": [
                "2027-01-03", "2027-01-06", "2027-01-07", "2027-01-09",
                "2027-02-01", "2027-02-02", "2027-02-03", "2027-02-04",
            ],
            "eventCount": 8,
            "schedule": [
                {"date": "2027-01-03", "venue": "テラスモール松戸 2Fこもれびステージ"},
                {"date": "2027-01-06", "venue": "テラスモール松戸 2Fこもれびステージ"},
                {"date": "2027-01-07", "venue": "テラスモール松戸 2Fこもれびステージ"},
                {"date": "2027-01-09", "venue": "テラスモール松戸 2Fこもれびステージ"},
                {"date": "2027-02-01", "venue": "テラスモール松戸 2Fこもれびステージ"},
                {"date": "2027-02-02", "venue": "テラスモール松戸 2Fこもれびステージ"},
                {"date": "2027-02-03", "venue": "animate hall BLACK(アニメイト池袋本店 北館9F)"},
                {"date": "2027-02-04", "venue": "animate hall BLACK(アニメイト池袋本店 北館9F)"},
            ],
            "venue": "複数会場（全8公演）",
            "url": shared,
            "urls": [shared, older],
            "sourceType": "derived",
            "sourceChannel": "official-x",
            "primarySource": "official",
        }
        singleton = {
            "id": "singleton",
            "group": "MORE STAR",
            "title": "『サマーゴー！！/WITH KAWAII論』発売記念リリースイベント",
            "eventTitle": "『サマーゴー！！/WITH KAWAII論』発売記念リリースイベント",
            "displayTitle": "『サマーゴー！！/WITH KAWAII論』発売記念リリースイベント",
            "eventCategory": "release-event",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "eventDate": "2027-02-05",
            "venue": "テラスモール松戸 2Fこもれびステージ",
            "url": shared,
            "urls": [shared],
            "sourceType": "official-social",
            "sourceChannel": "official-x",
            "primarySource": "official",
        }

        rows, report = dedupe.collapse([aggregate, singleton])

        self.assertEqual(1, len(rows))
        self.assertEqual("aggregate", rows[0]["id"])
        self.assertEqual(9, rows[0]["eventCount"])
        self.assertEqual("2027-02-05", rows[0]["eventEndDate"])
        self.assertEqual(9, len(rows[0]["eventDates"]))
        self.assertIn("2027-02-05", rows[0]["eventDates"])
        self.assertIn(
            {"date": "2027-02-05", "venue": "テラスモール松戸 2Fこもれびステージ"},
            rows[0]["schedule"],
        )
        self.assertEqual({shared, older}, set(rows[0]["urls"]))
        self.assertEqual("official-social", rows[0]["sourceType"])
        self.assertEqual("official-x", rows[0]["sourceChannel"])
        self.assertEqual("official", rows[0]["primarySource"])
        self.assertEqual("awaiting-details", rows[0]["specialDetailsStatus"])
        self.assertEqual("schedule-only", rows[0]["applicationDisplayMode"])
        self.assertEqual("none", rows[0]["applicationStatus"])
        self.assertEqual(1, report["officialXSeriesMerged"])
        self.assertEqual(1, report["officialXRowsCollapsed"])

    def test_different_x_posts_do_not_merge_without_overlap(self):
        base = {
            "group": "MORE STAR",
            "title": "MORE STAR リリースイベント",
            "eventTitle": "MORE STAR リリースイベント",
            "displayTitle": "MORE STAR リリースイベント",
            "eventCategory": "release-event",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "sourceType": "official-social",
            "sourceChannel": "official-x",
            "primarySource": "official",
        }
        first = dict(base, id="a", eventDate="2027-02-01", venue="A", url="https://x.com/MORE_STAR_/status/1", urls=["https://x.com/MORE_STAR_/status/1"])
        second = dict(base, id="b", eventDate="2027-02-02", venue="B", url="https://x.com/MORE_STAR_/status/2", urls=["https://x.com/MORE_STAR_/status/2"])

        rows, report = dedupe.collapse([first, second])
        self.assertEqual(2, len(rows))
        self.assertEqual(0, report["officialXSeriesMerged"])


if __name__ == "__main__":
    unittest.main()
