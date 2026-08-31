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
        rows = news.article_events(payload, "SWEET STEADY", article_url, text, date(2026, 9, 1))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "shoji-stable")
        self.assertEqual(rows[0]["eventDate"], "2026-10-26")
        self.assertEqual(rows[0]["applyEnd"], "2026-09-08T23:59")
        self.assertEqual(rows[0]["url"], article_url)

        merged = birthday.merge_birthday_events(payload, rows)
        shoji = [e for e in merged["events"] if e.get("id") == "shoji-stable"]
        self.assertEqual(len(shoji), 1)
        self.assertNotEqual(shoji[0]["ticketType"], "現在受付なし")
        self.assertEqual(shoji[0]["applicationStatus"], "open")
        self.assertEqual(shoji[0]["eventDate"], "2026-10-26")
        self.assertEqual(shoji[0]["url"], article_url)
        self.assertEqual(shoji[0]["applyEnd"], "2026-09-08T23:59")

    def test_cutie_three_people_keep_current_2026_schedule_dates_and_deadlines(self):
        people = [
            ("furusawa", "古澤里紗", "2026-11-09", "2026-09-09T23:59"),
            ("itakura", "板倉可奈", "2026-11-11", "2026-09-09T23:59"),
            ("sano", "佐野愛花", "2026-11-26", "2026-09-10T23:59"),
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
                "url": f"https://red-hot.ne.jp/play/detail.php?pid={event_id}",
                "sourceType": "promoter",
                "primarySource": "official",
                "sourceCandidates": ["promoter"],
            }
            for event_id, person, event_date, _deadline in people
        ]}

        for event_id, person, event_date, deadline in people:
            article_url = f"https://cutiestreet.asobisystem.com/news/detail/{event_id}"
            text = (
                f"CUTIE STREET {person} 生誕祭 2026\n"
                "CUTIE STREET FC会員年会費コース限定先行受付\n"
                f"受付期間：2026年8月31日 20:00〜{deadline[:4]}年{int(deadline[5:7])}月{int(deadline[8:10])}日 23:59\n"
            )
            rows = news.article_events(payload, "CUTIE STREET", article_url, text, date(2026, 9, 1))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], event_id)
            self.assertEqual(rows[0]["eventDate"], event_date)
            self.assertEqual(rows[0]["url"], article_url)
            self.assertEqual(rows[0]["applyEnd"], deadline)
            self.assertEqual(rows[0]["applicationStatus"], "open")

            merged = birthday.merge_birthday_events(payload, rows)
            by_id = {event["id"]: event for event in merged["events"]}
            self.assertEqual(by_id[event_id]["eventDate"], event_date)
            self.assertNotEqual(by_id[event_id]["ticketType"], "現在受付なし")
            self.assertEqual(by_id[event_id]["applicationStatus"], "open")
            self.assertEqual(by_id[event_id]["url"], article_url)
            self.assertEqual(by_id[event_id]["applyEnd"], deadline)


if __name__ == "__main__":
    unittest.main()
