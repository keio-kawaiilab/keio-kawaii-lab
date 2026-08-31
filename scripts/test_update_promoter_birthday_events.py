import unittest
from datetime import date

import update_promoter_birthday_events as p


class PromoterBirthdayTests(unittest.TestCase):
    def test_month_page_discovers_birthday_detail(self):
        html = '''
        <html><body>
          <div class="event">
            <a href="/play/detail.php?pid=py28687">SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026</a>
            <span>10月26日(月) START 19:00</span>
          </div>
          <a href="/play/detail.php?pid=other">通常ライブ</a>
        </body></html>
        '''
        rows = p.discover_candidates(html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].url, "https://red-hot.ne.jp/play/detail.php?pid=py28687")

    def test_detail_parses_shoji_birthday(self):
        html = '''
        <html><body>
          <h2>SWEET STEADY</h2>
          <h1>SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026</h1>
          <p>2026年10月26日(月)</p>
          <a href="/venue/detail.php?id=pl1297">SGC HALL ARIAKE</a>
          <p>OPEN 17:30</p>
          <p>START 19:00</p>
        </body></html>
        '''
        event = p.parse_detail(
            "https://red-hot.ne.jp/play/detail.php?pid=py28687",
            html,
            date(2026, 8, 31),
        )
        self.assertIsNotNone(event)
        self.assertEqual(event["group"], "SWEET STEADY")
        self.assertEqual(event["eventDate"], "2026-10-26")
        self.assertEqual(event["venue"], "SGC HALL ARIAKE")
        self.assertEqual(event["openTime"], "17:30")
        self.assertEqual(event["startTime"], "19:00")
        self.assertEqual(event["sourceType"], "promoter")
        self.assertEqual(event["eventScope"], "kawaii-lab")

    def test_empty_collection_is_exact_noop(self):
        payload = {"updatedAt": "2026-08-31T18:00:00+09:00", "events": [{"id": "keep"}]}
        self.assertIs(p.merge_payload(payload, []), payload)

    def test_official_birthday_wins_over_promoter(self):
        payload = {"events": [{
            "id": "official",
            "group": "SWEET STEADY",
            "title": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventTitle": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventCategory": "solo-live",
            "eventDate": "2026-10-26",
            "venue": "SGC HALL ARIAKE",
            "sourceType": "official-schedule",
            "primarySource": "official",
        }]}
        fresh = [{
            "id": "promoter",
            "group": "SWEET STEADY",
            "title": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventTitle": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventCategory": "solo-live",
            "eventDate": "2026-10-26",
            "venue": "SGC HALL ARIAKE",
            "sourceType": "promoter",
            "primarySource": "promoter",
        }]
        merged = p.merge_payload(payload, fresh)
        self.assertEqual(len(merged["events"]), 1)
        self.assertEqual(merged["events"][0]["id"], "official")


if __name__ == "__main__":
    unittest.main()
