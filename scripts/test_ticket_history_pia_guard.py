import unittest

import ticket_history_pia_guard as g


class TicketHistoryPiaGuardTests(unittest.TestCase):
    def test_sold_out_status_is_preserved(self):
        self.assertEqual(
            g.guarded_status("一般発売 予定枚数終了 2026/9/14 SGC HALL ARIAKE"),
            "sold_out",
        )

    def test_ended_status_is_preserved(self):
        self.assertEqual(
            g.guarded_status("一般発売 販売終了 2026/9/14 SGC HALL ARIAKE"),
            "ended",
        )

    def test_active_status_stays_open(self):
        self.assertEqual(
            g.guarded_status("一般発売 販売期間中 2026/9/14 SGC HALL ARIAKE"),
            "open",
        )

    def test_guard_row_is_not_removed_by_main_pia_replacement(self):
        row = g.normalize_guard_row({
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 梅田みゆ 生誕祭 2026",
            "eventDate": "2026-09-14",
            "ticketType": "一般発売",
            "applyStart": "2026-08-22T10:00",
            "applyEnd": "2026-09-09T23:59",
            "applicationStatus": "sold_out",
            "url": "https://t.pia.jp/pia/event/event.do?eventBundleCd=b2669934",
            "urls": ["https://t.pia.jp/pia/event/event.do?eventBundleCd=b2669934"],
        })
        self.assertEqual(row["sourceType"], "ticket-history-guard")
        self.assertEqual(row["primarySource"], "pia")
        self.assertTrue(row["historyPreserved"])
        self.assertTrue(row["applicationWindowVerified"])
        self.assertTrue(row["deadlineVerified"])

    def test_merge_keeps_one_general_sale(self):
        payload = {"events": []}
        row = g.normalize_guard_row({
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 梅田みゆ 生誕祭 2026",
            "eventDate": "2026-09-14",
            "ticketType": "一般発売",
            "applyStart": "2026-08-22T10:00",
            "applyEnd": "2026-09-09T23:59",
            "applicationStatus": "sold_out",
            "url": "https://t.pia.jp/pia/event/event.do?eventBundleCd=b2669934",
            "urls": ["https://t.pia.jp/pia/event/event.do?eventBundleCd=b2669934"],
        })
        added, enriched = g.merge(payload, [row, row])
        self.assertEqual(added, 1)
        self.assertEqual(enriched, 0)
        self.assertEqual(len(payload["events"]), 1)


if __name__ == "__main__":
    unittest.main()
