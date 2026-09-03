import unittest
from bs4 import BeautifulSoup

import promoter_general_sale_guard as g


class PromoterGeneralSaleGuardTests(unittest.TestCase):
    def test_month_discovery_keeps_only_supported_birthday_cards(self):
        html = """
        <div class="event-card">
          <h3>CUTIE STREET 梅田みゆ 生誕祭 2026</h3>
          <a href="detail.php?pid=py28451">詳細</a>
        </div>
        <div class="event-card">
          <h3>OTHER ARTIST BIRTHDAY LIVE</h3>
          <a href="detail.php?pid=py99999">詳細</a>
        </div>
        <div class="event-card">
          <h3>CUTIE STREET 通常ライブ</h3>
          <a href="detail.php?pid=py30000">詳細</a>
        </div>
        """
        rows = g.discover_birthday_candidates(html)
        self.assertEqual(
            [row.url for row in rows],
            ["https://red-hot.ne.jp/play/detail.php?pid=py28451"],
        )

    def test_sold_out_general_sale_start_is_extracted(self):
        html = """
        <html><body>
          <p>公演日 2026年9月14日</p>
          <section>
            <h3>一般発売 SOLD OUT!</h3>
            <p>8/22(土)10:00〜</p>
            <a href="https://t.pia.jp/pia/event/event.do?eventBundleCd=b2669934">チケットぴあ</a>
          </section>
        </body></html>
        """
        sale = g.extract_general_sale(
            BeautifulSoup(html, "html.parser"),
            "2026-09-14",
            "https://red-hot.ne.jp/play/detail.php?pid=py28451",
        )
        self.assertIsNotNone(sale)
        self.assertEqual(sale["applyStart"], "2026-08-22T10:00")
        self.assertEqual(sale["applicationStatus"], "sold_out")
        self.assertEqual(sale["ticketProvider"], "pia")
        self.assertTrue(sale["soldOutObserved"])

    def test_cross_source_merge_combines_promoter_start_with_pia_deadline(self):
        payload = {"events": [{
            "id": "pia-ended",
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 梅田みゆ 生誕祭 2026",
            "eventDate": "2026-09-14",
            "ticketType": "一般発売",
            "ticketProvider": "pia",
            "applyStart": None,
            "applyEnd": "2026-09-09T23:59",
            "applicationStatus": "sold_out",
            "urls": ["https://t.pia.jp/pia/event/event.do?eventBundleCd=b2669934"],
        }]}
        row = {
            "id": "promoter",
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 梅田みゆ 生誕祭 2026",
            "eventDate": "2026-09-14",
            "ticketType": "一般発売",
            "ticketProvider": "pia",
            "applyStart": "2026-08-22T10:00",
            "applyEnd": None,
            "applicationStatus": "sold_out",
            "applicationWindowSource": "https://red-hot.ne.jp/play/detail.php?pid=py28451",
            "soldOutObserved": True,
            "urls": ["https://red-hot.ne.jp/play/detail.php?pid=py28451"],
        }
        added, enriched = g.merge(payload, [row])
        self.assertEqual(added, 0)
        self.assertEqual(enriched, 1)
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["events"][0]["applyStart"], "2026-08-22T10:00")
        self.assertEqual(payload["events"][0]["applyEnd"], "2026-09-09T23:59")
        self.assertTrue(payload["events"][0]["soldOutObserved"])

    def test_sale_year_rolls_back_across_new_year(self):
        self.assertEqual(
            g.parse_sale_start("一般発売 12/20(日)10:00〜", "2027-01-15"),
            "2026-12-20T10:00",
        )


if __name__ == "__main__":
    unittest.main()
