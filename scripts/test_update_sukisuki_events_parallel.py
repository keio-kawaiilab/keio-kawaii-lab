import sys
import unittest
from unittest.mock import patch

import update_sukisuki_events_parallel as parallel


class SukisukiCompatibilityEntrypointTests(unittest.TestCase):
    def test_workers_option_reaches_maintained_collector_without_leaking_arg(self):
        original = sys.argv[:]
        seen = []

        def fake_main():
            seen.append(sys.argv[:])
            return 0

        try:
            sys.argv = ["update_sukisuki_events_parallel.py", "--workers", "5"]
            with patch.object(parallel.update_sukisuki_events, "main", side_effect=fake_main):
                self.assertEqual(0, parallel.main())
        finally:
            sys.argv = original

        self.assertEqual([["update_sukisuki_events_parallel.py"]], seen)


if __name__ == "__main__":
    unittest.main()
