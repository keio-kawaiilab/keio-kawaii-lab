import unittest
from datetime import date

import reconcile_pia_retention as r


class PiaRetentionTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 8, 23)

    def event(self, **overrides):
        base = {
            "id": "old",
            "group": "CANDY TUNE",
            "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            "ticketType": "プレリザーブ",
            "applyStart": None,
            "applyEnd": "2026-08-24T11:00",
            "eventDates": ["2026-11-10", "2026-11-12"],
            "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=20981",
            "sourceType": "pia",
            "primarySource": "pia",
            "applicationStatus": "open",
        }
        base.update(overrides)
        return base

    def test_missing_known_active_sale_is_retained(self):
        merged, retained, enriched = r.reconcile([], [self.event()], self.today)
        self.assertEqual(retained, ["lot:20981"])
        self.assertFalse(enriched)
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0]["retainedFromPreviousPiaRun"])

    def test_past_deadline_is_not_retained(self):
        old = self.event(applyEnd="2026-08-22T23:59")
        merged, retained, _ = r.reconcile([], [old], self.today)
        self.assertEqual(merged, [])
        self.assertEqual(retained, [])

    def test_same_lot_is_not_duplicated(self):
        current = self.event(id="new")
        merged, retained, _ = r.reconcile([current], [self.event()], self.today)
        self.assertEqual(len(merged), 1)
        self.assertEqual(retained, [])
        self.assertEqual(merged[0]["id"], "new")

    def test_known_deadline_can_fill_thinner_current_row(self):
        current = self.event(id="new", applyEnd=None)
        merged, _, enriched = r.reconcile([current], [self.event()], self.today)
        self.assertEqual(enriched, ["lot:20981"])
        self.assertEqual(merged[0]["applyEnd"], "2026-08-24T11:00")
        self.assertTrue(merged[0]["deadlineRecoveredFromPreviousRun"])
        self.assertIsNone(merged[0]["applyStart"])

    def test_derived_pia_winner_is_still_recognized(self):
        derived = self.event(sourceType="derived", primarySource="pia")
        self.assertTrue(r.is_pia(derived))
        self.assertTrue(r.known_active(derived, self.today))


if __name__ == "__main__":
    unittest.main()
