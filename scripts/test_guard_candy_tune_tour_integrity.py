import unittest
from datetime import datetime, timezone

import guard_candy_tune_tour_integrity as guard


class CandyTuneTourGuardTests(unittest.TestCase):
    def test_default_publication_day_uses_jst_across_utc_midnight(self):
        utc_time = datetime(2026, 10, 26, 15, 1, tzinfo=timezone.utc)
        self.assertEqual("2026-10-27", guard.jst_today_iso(utc_time))


if __name__ == "__main__":
    unittest.main()
