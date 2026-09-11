import unittest

import guard_schedule_latest_data_loading as guard


class LatestScheduleDataLoadingGuardTests(unittest.TestCase):
    def legacy_page(self) -> str:
        return (
            "<script>"
            + guard.LEGACY_FETCH
            + ".then(function(data){"
            + guard.RAW_LATEST_SWAP
            + "'ok'})"
            + "</script>"
        )

    def test_installs_timeout_and_candy_tour_integrity_guards(self):
        result = guard.install_guard(self.legacy_page())
        self.assertIn(guard.GUARDED_FETCH, result)
        self.assertIn("function fetchLatestScheduleData(url,timeoutMs)", result)
        self.assertIn("function hasRequiredCandyTuneTour(data)", result)
        self.assertIn(guard.GUARDED_LATEST_SWAP, result)
        self.assertNotIn(guard.LEGACY_FETCH, result)

    def test_upgrades_existing_timeout_only_guard(self):
        page = self.legacy_page().replace(guard.LEGACY_FETCH, guard.HELPER + guard.GUARDED_FETCH)
        result = guard.install_guard(page)
        self.assertIn("function hasRequiredCandyTuneTour(data)", result)
        self.assertIn(guard.GUARDED_LATEST_SWAP, result)

    def test_install_is_idempotent(self):
        once = guard.install_guard(self.legacy_page())
        self.assertEqual(once, guard.install_guard(once))

    def test_refuses_unknown_latest_assignment_shape(self):
        page = guard.HELPER + guard.GUARDED_FETCH + ".then(function(data){events=[]})"
        with self.assertRaisesRegex(RuntimeError, "assignment changed"):
            guard.install_guard(page)


if __name__ == "__main__":
    unittest.main()
