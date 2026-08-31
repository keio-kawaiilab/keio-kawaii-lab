import unittest
from datetime import date

import update_promoter_birthday_events as p


class PromoterBirthdayTests(unittest.TestCase):
    def test_month_page_discovers_pid_across_link_variants(self):
        html = '''
        <html><body>
          <a href="detail.php?pid=py28687">詳細</a>
          <a href="?pid=py30001">別公演</a>
          <a href="https://red-hot.ne.jp/play/detail.php?foo=1&amp;pid=py30002">絶対URL</a>
          <script>window.eventHref = "detail.php?pid=py30003";</script>
        </body></html>
        '''
        rows = p.discover_candidates(html)
        self.assertEqual(
            {row.url for row in rows},
            {
                "https://red-hot.ne.jp/play/detail.php?pid=py28687",
                "https://red-hot.ne.jp/play/detail.php?pid=py30001",
                "https://red-hot.ne.jp/play/detail.php?pid=py30002",
                "https://red-hot.ne.jp/play/detail.php?pid=py30003",
            },
        )

    def test_month_page_regression_shoji_pid_is_never_dropped(self):
        html = '''
        <div data-url="detail.php?pid=py28687">
          SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026
        </div>
        '''
        rows = p.discover_candidates(html)
        self.assertIn(
            "https://red-hot.ne.jp/play/detail.php?pid=py28687",
            {row.url for row in rows},
        )

    def test_detail_parses_shoji_birthday(self):
        html = '''
        <html><body>
          <h2>SWEET STEADY</h2>
          <h1>SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026</h1>
          <p>2026年10月26日(月)</p>
          <a href="venue/detail.php?id=pl1297">SGC HALL ARIAKE</a>
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

    def test_detail_ignores_non_birthday_event(self):
        html = '''
        <html><body>
          <h2>SWEET STEADY</h2>
          <h1>SWEET STEADY 通常ライブ</h1>
          <p>2026年10月27日(火)</p>
          <a href="/venue/detail.php?id=pl1297">SGC HALL ARIAKE</a>
          <p>OPEN 17:30</p><p>START 19:00</p>
        </body></html>
        '''
        self.assertIsNone(
            p.parse_detail(
                "https://red-hot.ne.jp/play/detail.php?pid=py30000",
                html,
                date(2026, 8, 31),
            )
        )

    def test_empty_collection_is_exact_noop(self):
        payload = {
            "updatedAt": "2026-08-31T18:00:00+09:00",
            "events": [{"id": "keep"}],
        }
        self.assertIs(p.merge_payload(payload, []), payload)

    def test_official_birthday_wins_over_promoter(self):
        payload = {
            "events": [
                {
                    "id": "official",
                    "group": "SWEET STEADY",
                    "title": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
                    "eventTitle": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
                    "eventCategory": "solo-live",
                    "eventDate": "2026-10-26",
                    "venue": "SGC HALL ARIAKE",
                    "sourceType": "official-schedule",
                    "primarySource": "official",
                }
            ]
        }
        fresh = [
            {
                "id": "promoter",
                "group": "SWEET STEADY",
                "title": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
                "eventTitle": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
                "eventCategory": "solo-live",
                "eventDate": "2026-10-26",
                "venue": "SGC HALL ARIAKE",
                "sourceType": "promoter",
                "primarySource": "promoter",
            }
        ]
        merged = p.merge_payload(payload, fresh)
        self.assertEqual(len(merged["events"]), 1)
        self.assertEqual(merged["events"][0]["id"], "official")


if __name__ == "__main__":
    unittest.main()
