import json
import unittest
from pathlib import Path

from add_verified_missing_ticket_bands import LEGACY_LAWSON_PLACEHOLDER_ID, verified_rows


ROOT = Path(__file__).resolve().parents[1]


class VerifiedMissingTicketBandsTest(unittest.TestCase):
    def test_verified_rows_are_complete_and_unique(self):
        rows = verified_rows("2026-09-22T11:13:29+09:00")
        self.assertEqual(len(rows), 12)
        self.assertEqual(len({row["id"] for row in rows}), 12)
        self.assertTrue(all(row.get("applyStart") and row.get("applyEnd") for row in rows))
        self.assertTrue(all(row.get("applicationWindowVerified") for row in rows))
        self.assertTrue(all(row.get("deadlineVerified") for row in rows))

    def test_repository_contains_rows_and_no_legacy_placeholder(self):
        payload = json.loads((ROOT / "data/live-events.json").read_text(encoding="utf-8"))
        raw = payload["events"]
        expected = verified_rows("2026-09-22T11:13:29+09:00")
        expected_ids = {row["id"] for row in expected}
        actual_ids = {row.get("id") for row in raw}
        self.assertTrue(expected_ids.issubset(actual_ids))
        self.assertNotIn(LEGACY_LAWSON_PLACEHOLDER_ID, actual_ids)

        public = payload["publicEvents"]
        for day in ("2026-10-08", "2026-11-17", "2026-11-19", "2026-11-30", "2026-12-01"):
            matches = [
                event for event in public
                if event.get("group") == "CANDY TUNE" and event.get("eventDate") == day
                and any(offer.get("provider") == "lawson" for offer in event.get("offers") or [])
            ]
            self.assertEqual(len(matches), 1, day)

        duplicate = [
            event for event in public
            if event.get("id") == "performance-CANDY-TUNE-2026-12-01-fallback-iichiko-candytunejapantour2026autumn"
        ]
        self.assertEqual(duplicate, [])


if __name__ == "__main__":
    unittest.main()
