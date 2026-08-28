import time
import unittest
from datetime import date

import update_official_schedule_parallel as parallel


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class SlowSession:
    def get(self, url, timeout=25):
        time.sleep(0.12)
        group_token = url.split("//", 1)[-1].split(".", 1)[0]
        html = f'''
        <a href="/live_information/detail/{group_token}">
          <span class="category">LIVE</span>
          <span class="block--date__month">9</span>
          <span class="block--date__date">1</span>
          <span class="tit">{group_token} TEST LIVE</span>
        </a>
        '''
        return FakeResponse(html)

    def close(self):
        pass


class OfficialScheduleParallelTests(unittest.TestCase):
    def test_group_month_requests_run_concurrently(self):
        groups = {
            "A": "https://a.example.com",
            "B": "https://b.example.com",
            "C": "https://c.example.com",
        }
        started = time.monotonic()
        rows, status, diagnostics = parallel.collect_parallel(
            date(2026, 8, 28),
            max_workers=3,
            groups=groups,
            months=[(2026, 9)],
            session_factory=SlowSession,
        )
        elapsed = time.monotonic() - started
        self.assertEqual(3, len(rows))
        self.assertTrue(all(status[group]["count"] == 1 for group in groups))
        self.assertEqual("parallel", diagnostics["listMode"])
        self.assertLess(elapsed, 0.30)

    def test_missing_event_needs_detail_prefetch(self):
        row = parallel.official.OfficialRow(
            "CANDY TUNE",
            "2026-09-01",
            "LIVE",
            "TEST LIVE",
            "https://candytune.asobisystem.com/live_information/detail/1",
            "hosted",
        )
        urls = parallel.detail_urls_needed({"events": []}, [row])
        self.assertEqual([row.url], urls)

    def test_complete_existing_event_skips_detail_prefetch(self):
        row = parallel.official.OfficialRow(
            "CANDY TUNE",
            "2026-09-01",
            "LIVE",
            "TEST LIVE",
            "https://candytune.asobisystem.com/live_information/detail/1",
            "hosted",
        )
        payload = {"events": [{
            "id": "existing",
            "group": "CANDY TUNE",
            "participants": ["CANDY TUNE"],
            "title": "TEST LIVE",
            "eventTitle": "TEST LIVE",
            "eventDate": "2026-09-01",
            "sourceType": "official-news",
            "venue": "Test Hall",
            "openTime": "17:00",
            "startTime": "18:00",
            "eventScope": "hosted",
        }]}
        self.assertEqual([], parallel.detail_urls_needed(payload, [row]))


if __name__ == "__main__":
    unittest.main()
