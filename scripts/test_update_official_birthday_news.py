import unittest
from datetime import date

import update_official_birthday_news as news
import update_official_x_birthday_events as birthday


class OfficialBirthdayNewsTests(unittest.TestCase):
    def test_shoji_official_news_enriches_promoter_row_in_place(self):
        payload = {"events": [{
            "id": "shoji-stable",
            "group": "SWEET STEADY",
            "title": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventTitle": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventCategory": "solo-live",
            "eventDate": "2026-10-26",
            "venue": "SGC HALL ARIAKE",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "applyStart": None,
            "applyEnd": None,
            "url": "https://red-hot.ne.jp/play/detail.php?pid=example",
            "urls": ["https://red-hot.ne.jp/play/detail.php?pid=example"],
            "sourceType": "promoter",
            "primarySource": "official",
            "sourceCandidates": ["promoter"],
        }]}
        article_url = "https://sweetsteady.asobisystem.com/news/detail/99999"
        text = (
            "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026\n"
            "FC先行受付\n"
            "受付期間：2026年8月31日 19:00〜2026年9月8日 23:59\n"
        )
        rows = news.article_events(payload, "SWEET STEADY", article_url, text, date(2026, 8, 31))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "shoji-stable")
        self.assertEqual(rows[0]["eventDate"], "2026-10-26")
        self.assertEqual(rows[0]["applyEnd"], "2026-09-08T23:59")
        self.assertEqual(rows[0]["url"], article_url)

        merged = birthday.merge_birthday_events(payload, rows)
        shoji = [e for e in merged["events"] if e.get("id") == "shoji-stable"]
        self.assertEqual(len(shoji), 1)
        self.assertNotEqual(shoji[0]["ticketType"], "現在受付なし")
        self.assertEqual(shoji[0]["eventDate"], "2026-10-26")
        self.assertEqual(shoji[0]["url"], article_url)
        self.assertEqual(shoji[0]["applyEnd"], "2026-09-08T23:59")

    def test_cutie_three_people_keep_their_individual_schedule_dates(self):
        people = [
            ("furusawa", "古澤里紗", "2026-10-18"),
            ("itakura", "板倉可奈", "2026-11-11"),
            ("sano", "佐野愛花", "2026-11-20"),
        ]
        payload = {"events": [
            {
                "id": event_id,
                "group": "CUTIE STREET",
                "title": f"CUTIE STREET {person} 生誕祭 2026",
                "eventTitle": f"CUTIE STREET {person} 生誕祭 2026",
                "eventCategory": "solo-live",
                "eventDate": event_date,
                "ticketType": "現在受付なし",
                "applicationStatus": "none",
                "applyStart": None,
                "applyEnd": None,
                "url": f"https://cutiestreet.asobisystem.com/live_information/detail/{event_id}",
                "sourceType": "official-schedule",
                "primarySource": "official",
                "sourceCandidates": ["official"],
            }
            for event_id, person, event_date in people
        ]}
        article_url = "https://cutiestreet.asobisystem.com/news/detail/99998"
        text = (
            "CUTIE STREET 古澤里紗・板倉可奈・佐野愛花 生誕祭 2026\n"
            "CUTIE STREET FC先行受付\n"
            "受付期間：2026年8月31日 20:00〜2026年9月9日 23:59\n"
        )
        rows = news.article_events(payload, "CUTIE STREET", article_url, text, date(2026, 8, 31))
        self.assertEqual(len(rows), 3)
        by_id = {row["id"]: row for row in rows}
        for event_id, _person, event_date in people:
            self.assertEqual(by_id[event_id]["eventDate"], event_date)
            self.assertEqual(by_id[event_id]["url"], article_url)
            self.assertEqual(by_id[event_id]["applyEnd"], "2026-09-09T23:59")

        merged = birthday.merge_birthday_events(payload, rows)
        by_id = {event["id"]: event for event in merged["events"]}
        for event_id, _person, event_date in people:
            self.assertEqual(by_id[event_id]["eventDate"], event_date)
            self.assertNotEqual(by_id[event_id]["ticketType"], "現在受付なし")
            self.assertEqual(by_id[event_id]["url"], article_url)
            self.assertEqual(by_id[event_id]["applyEnd"], "2026-09-09T23:59")


if __name__ == "__main__":
    unittest.main()
