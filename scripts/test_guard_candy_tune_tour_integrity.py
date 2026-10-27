import unittest
from datetime import datetime, timezone

import guard_candy_tune_tour_integrity as guard


class CandyTuneTourGuardTests(unittest.TestCase):
    def test_canonical_data_guard_requires_only_unfinished_tour_dates(self):
        future_dates = sorted(day for day in guard.EXPECTED_DATES if day >= "2026-10-27")
        event = {
            "group": "CANDY TUNE",
            "title": "CANDY TUNE JAPAN TOUR 2026 -AUTUMN-",
            "eventDates": future_dates,
        }
        guard.validate_event_list([event], "test", "2026-10-27")

        event["eventDates"] = future_dates[1:]
        with self.assertRaises(SystemExit):
            guard.validate_event_list([event], "test", "2026-10-27")

    def test_default_publication_day_uses_jst_across_utc_midnight(self):
        utc_time = datetime(2026, 10, 26, 15, 1, tzinfo=timezone.utc)
        self.assertEqual("2026-10-27", guard.jst_today_iso(utc_time))

    def test_snapshot_date_wins_over_runner_calendar(self):
        html = '<script id="snapshot-data" type="application/json">{"updatedAt":"2026-10-27T00:42:03+09:00"}</script>'
        self.assertEqual("2026-10-27", guard.snapshot_publication_date(html))


if __name__ == "__main__":
    unittest.main()
