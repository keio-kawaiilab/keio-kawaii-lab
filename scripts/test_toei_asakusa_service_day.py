#!/usr/bin/env python3
from __future__ import annotations

import unittest

from audit_toei_asakusa_service_day import classify_service_day


class ToeiAsakusaServiceDayTest(unittest.TestCase):
    def test_midnight_wrap_is_normalized_once(self):
        normalized, wraps, unsafe = classify_service_day([1437, 1438, 1439, 1, 2, 5])
        self.assertEqual(normalized, [1437, 1438, 1439, 1441, 1442, 1445])
        self.assertEqual(wraps, [{"index": 3, "from": 1439, "to": 1}])
        self.assertEqual(unsafe, [])

    def test_non_midnight_regression_fails_closed(self):
        _normalized, wraps, unsafe = classify_service_day([600, 605, 590])
        self.assertEqual(wraps, [])
        self.assertTrue(unsafe)

    def test_early_evening_to_midnight_is_not_wrap(self):
        _normalized, wraps, unsafe = classify_service_day([1320, 60])
        self.assertEqual(wraps, [])
        self.assertTrue(unsafe)

    def test_late_night_to_after_2am_is_not_wrap(self):
        _normalized, wraps, unsafe = classify_service_day([1439, 121])
        self.assertEqual(wraps, [])
        self.assertTrue(unsafe)

    def test_second_wrap_fails_closed(self):
        _normalized, wraps, unsafe = classify_service_day([1439, 1, 1439, 1])
        self.assertEqual(len(wraps), 1)
        self.assertTrue(unsafe)


if __name__ == "__main__":
    unittest.main()
