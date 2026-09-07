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

    def test_sold_out_row_keeps_observed_deadline(self):
        start, end = g.guarded_sale_window(
            "一般発売 2026/9/14(月) SGC HALL ARIAKE 予定枚数終了 ～2026/9/9(水) 23:59 詳細へ"
        )
        self.assertIsNone(start)
        self.assertEqual(end, "2026-09-09T23:59")

    def test_result_announcement_is_never_used_as_application_deadline(self):
        start, end = g.guarded_sale_window(
            "2次プレリザーブ 抽選受付終了 ～2026/9/6(日) 23:59 抽選結果発表 2026/9/9(水) 18:00 詳細へ"
        )
        self.assertIsNone(start)
        self.assertEqual(end, "2026-09-06T23:59")

    def test_result_only_context_does_not_invent_deadline(self):
        start, end = g.guarded_sale_window(
            "2次プレリザーブ 抽選結果発表済 2026/9/9(水) 18:00"
        )
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_known_candy_tune_corrections_close_band(self):
        payload = {"events": [{
            "id": "bad",
            "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=35165",
            "applyEnd": "2026-09-09T18:00",
            "applicationStatus": "ended",
            "applicationDisplayMode": "band-from-today",
            "retainedFromPreviousPiaRun": True,
            "piaRetentionReason": "not rediscovered; kept until known deadline",
        }]}
        self.assertEqual(g.apply_known_deadline_corrections(payload), 1)
        row = payload["events"][0]
        self.assertEqual(row["applyEnd"], "2026-09-06T23:59")
        self.assertEqual(row["applicationDisplayMode"], "offers")
        self.assertNotIn("retainedFromPreviousPiaRun", row)
        self.assertNotIn("piaRetentionReason", row)

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
        self.assertEqual(row["applicationDisplayMode"], "offers")

    def test_fresh_same_sale_can_replace_stale_wrong_deadline(self):
        payload = {"events": [{
            "group": "CANDY TUNE",
            "eventDate": "2026-10-02",
            "ticketType": "2次プレリザーブ",
            "ticketProvider": "pia",
            "sourceType": "ticket-history-guard",
            "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=35165",
            "urls": ["https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=35165"],
            "applyEnd": "2026-09-09T18:00",
            "applicationStatus": "ended",
            "applicationDisplayMode": "band-from-today",
            "retainedFromPreviousPiaRun": True,
        }]}
        fresh = g.normalize_guard_row({
            "group": "CANDY TUNE",
            "eventDate": "2026-10-02",
            "ticketType": "2次プレリザーブ",
            "applicationStatus": "ended",
            "applyEnd": "2026-09-06T23:59",
            "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=35165",
            "urls": ["https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=35165"],
        })
        added, enriched = g.merge(payload, [fresh])
        self.assertEqual(added, 0)
        self.assertEqual(enriched, 1)
        row = payload["events"][0]
        self.assertEqual(row["applyEnd"], "2026-09-06T23:59")
        self.assertEqual(row["applicationDisplayMode"], "offers")
        self.assertNotIn("retainedFromPreviousPiaRun", row)

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
