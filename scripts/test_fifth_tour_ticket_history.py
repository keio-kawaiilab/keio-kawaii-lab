import json
import unittest
from pathlib import Path

from backfill_ticket_history_oneoffs import merge, validate


ROOT = Path(__file__).resolve().parents[1]


class FifthTourTicketHistoryTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "data/ticket-history-backfill-oneoffs.json").read_text(encoding="utf-8"))
        self.registry = json.loads((ROOT / "data/ticket-source-registry.json").read_text(encoding="utf-8"))
        self.series = next(row for row in self.data["series"] if row["key"] == "kawaii-lab-fifth-anniversary-tour-2027")

    def test_fifth_tour_verified_source_has_all_ten_concert_days(self):
        self.assertEqual([], validate(self.data, self.registry))
        self.assertEqual("KAWAII LAB.合同", self.series["group"])
        self.assertEqual(10, len({row["date"] for row in self.series["events"]}))
        phase, = self.series["phases"]
        self.assertEqual("2026-10-12T18:30", phase["applyStart"])
        self.assertEqual("2026-10-18T23:59", phase["applyEnd"])
        self.assertEqual("https://kawaiilab.asobisystem.com/news/detail/92410", phase["sourceUrl"])

    def test_historical_round_is_idempotent_and_never_a_current_offer(self):
        now = "2026-10-19T01:00:00+09:00"
        first, stats = merge(self.data, {"version": 1, "entries": []}, now)
        rows = [row for row in first["entries"] if row.get("backfillSeriesKey") == self.series["key"]]
        self.assertEqual(10, len(rows))
        self.assertEqual(10, len({row["eventDate"] for row in rows}))
        self.assertTrue(all(row["publishable"] and row["flowEligible"] for row in rows))
        self.assertTrue(all(row["applyEnd"] < now for row in rows))
        second, stats2 = merge(self.data, first, now)
        self.assertEqual(0, stats2["added"])
        self.assertEqual(len(first["entries"]), len(second["entries"]))


if __name__ == "__main__":
    unittest.main()
