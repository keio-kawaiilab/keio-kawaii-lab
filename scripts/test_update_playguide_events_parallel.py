import time
import unittest
from datetime import date, datetime

import audit_playguide_collection as playguide_audit
import update_playguide_events_parallel as parallel


class DummySession:
    def close(self):
        pass


class ParallelPlayguideTests(unittest.TestCase):
    def test_partial_failure_keeps_successful_source(self):
        def ok(_session, group, _today):
            return [{
                "id": f"ok-{group}",
                "ticketProvider": "eplus",
                "sourceType": "eplus",
                "group": group,
                "eventDate": "2026-09-01",
                "url": "https://eplus.jp/example",
            }]

        def bad(_session, _group, _today):
            raise TimeoutError("source timeout")

        result = parallel.collect_parallel(
            date(2026, 8, 28),
            "2026-08-28T15:00:00+09:00",
            tasks=(
                ("eplus", "CANDY TUNE", ok),
                ("lawson", "CANDY TUNE", bad),
            ),
            max_workers=2,
            session_factory=DummySession,
        )
        self.assertEqual({("eplus", "CANDY TUNE")}, result["refreshed"])
        self.assertEqual(1, len(result["fresh"]))
        self.assertEqual(1, len(result["failures"]))
        self.assertIn("lawson/CANDY TUNE", result["failures"][0])

    def test_independent_sources_run_concurrently(self):
        def slow(_session, group, _today):
            time.sleep(0.12)
            return [{
                "id": group,
                "ticketProvider": "eplus",
                "sourceType": "eplus",
                "group": group,
                "eventDate": "2026-09-01",
                "url": f"https://eplus.jp/{group}",
            }]

        started = time.monotonic()
        result = parallel.collect_parallel(
            date(2026, 8, 28),
            "2026-08-28T15:00:00+09:00",
            tasks=(
                ("eplus", "A", slow),
                ("eplus", "B", slow),
                ("eplus", "C", slow),
            ),
            max_workers=3,
            session_factory=DummySession,
        )
        elapsed = time.monotonic() - started
        self.assertEqual(3, len(result["fresh"]))
        self.assertLess(elapsed, 0.30)

    def test_failed_provider_rows_are_retained(self):
        payload = {
            "events": [{
                "id": "lawson-old",
                "ticketProvider": "lawson",
                "sourceType": "lawson",
                "group": "CANDY TUNE",
                "eventDate": "2026-09-10",
                "applyEnd": "2026-08-31T23:59",
                "url": "https://l-tike.com/old",
            }]
        }
        collection = {
            "fresh": [],
            "freshCounts": {},
            "refreshed": {("eplus", "CANDY TUNE")},
            "failures": ["lawson/CANDY TUNE: TimeoutError: timeout"],
            "workerCount": 2,
            "durationSeconds": 1.0,
        }
        result = parallel.merge_collection(
            payload,
            collection,
            date(2026, 8, 28),
            "2026-08-28T15:00:00+09:00",
        )
        self.assertEqual("lawson-old", result["events"][0]["id"])
        self.assertEqual("parallel", result["playguideDiagnostics"]["collectorMode"])

    def test_missing_active_refreshed_row_is_retained_stale_without_blocking_other_updates(self):
        payload = {
            "events": [{
                "id": "eplus-old",
                "ticketProvider": "eplus",
                "sourceType": "eplus",
                "group": "SWEET STEADY",
                "eventDate": "2026-10-03",
                "applyEnd": "2026-10-02T23:59",
                "url": "https://eplus.jp/old",
            }]
        }
        collection = {
            "fresh": [{
                "id": "eplus-new",
                "ticketProvider": "eplus",
                "sourceType": "eplus",
                "group": "SWEET STEADY",
                "eventDate": "2026-10-04",
                "applyEnd": "2026-10-03T23:59",
                "url": "https://eplus.jp/new",
            }],
            "freshCounts": {"eplus:SWEET STEADY": 1},
            "refreshed": {("eplus", "SWEET STEADY")},
            "failures": [
                "lawson/CANDY TUNE: TimeoutError: timeout",
                "lawson/CUTIE STREET: TimeoutError: timeout",
                "lawson/FRUITS ZIPPER: TimeoutError: timeout",
                "lawson/MORE STAR: TimeoutError: timeout",
                "lawson/SWEET STEADY: TimeoutError: timeout",
            ],
            "workerCount": 10,
            "durationSeconds": 1.0,
        }
        # Account for the other four successful eplus group refreshes so the
        # source-health audit can distinguish guarded source drift from an
        # incomplete collector run.
        collection["refreshed"].update({
            ("eplus", "CANDY TUNE"),
            ("eplus", "CUTIE STREET"),
            ("eplus", "FRUITS ZIPPER"),
            ("eplus", "MORE STAR"),
        })
        result = parallel.merge_collection(
            payload,
            collection,
            date(2026, 8, 28),
            "2026-08-28T15:00:00+09:00",
        )
        by_id = {row["id"]: row for row in result["events"]}
        self.assertTrue(by_id["eplus-old"]["sourceStale"])
        self.assertIn("eplus-new", by_id)
        self.assertEqual(1, result["playguideDiagnostics"]["stillActiveMissingCount"])

        report, code = playguide_audit.audit_payload(
            result,
            datetime.fromisoformat("2026-08-28T15:01:00+09:00"),
        )
        self.assertEqual(0, code)
        self.assertEqual("ok", report["status"])
        self.assertEqual([], report["errors"])
        self.assertEqual(2, len(report["warnings"]))


if __name__ == "__main__":
    unittest.main()
