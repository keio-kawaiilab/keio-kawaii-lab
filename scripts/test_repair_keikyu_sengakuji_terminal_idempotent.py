#!/usr/bin/env python3
from __future__ import annotations

import unittest
from collections import Counter

import repair_keikyu_sengakuji_terminal_idempotent as target


def strict_meta() -> dict:
    return {
        'boundary': 'Sengakuji',
        'source': target.STRICT_SOURCE,
        'policy': dict(target.STRICT_POLICY),
        'syntheticRows': 291,
        'afterSengakujiEnds': {'weekday': 184, 'holiday': 155},
    }


def report(before: dict, after: dict) -> dict:
    return {
        'beforeSengakujiEnds': before,
        'afterSengakujiEnds': after,
        'patch': {
            'syntheticRows': 291,
            'officialCandidatesWithShinagawaTime': 295,
        },
    }


class IdempotentRepairTests(unittest.TestCase):
    def test_equal_coverage_requires_prior_strict_repair(self) -> None:
        before = {'weekday': 184, 'holiday': 155}
        self.assertTrue(target.idempotent_report_is_safe(strict_meta(), Counter(before), report(before, before)))
        self.assertFalse(target.idempotent_report_is_safe({}, Counter(before), report(before, before)))

    def test_service_regression_fails_closed(self) -> None:
        before = {'weekday': 184, 'holiday': 155}
        after = {'weekday': 183, 'holiday': 156}
        self.assertFalse(target.idempotent_report_is_safe(strict_meta(), Counter(before), report(before, after)))

    def test_stale_report_fails_closed(self) -> None:
        before = {'weekday': 184, 'holiday': 155}
        stale = {'weekday': 183, 'holiday': 155}
        self.assertFalse(target.idempotent_report_is_safe(strict_meta(), Counter(before), report(stale, stale)))

    def test_missing_strict_policy_flag_fails_closed(self) -> None:
        meta = strict_meta()
        del meta['policy']['exactShinagawaPublishedMinuteRequired']
        before = {'weekday': 184, 'holiday': 155}
        self.assertFalse(target.idempotent_report_is_safe(meta, Counter(before), report(before, before)))

    def test_positive_coverage_with_valid_prior_metadata_is_safe(self) -> None:
        before = {'weekday': 184, 'holiday': 155}
        after = {'weekday': 185, 'holiday': 155}
        self.assertTrue(target.idempotent_report_is_safe(strict_meta(), Counter(before), report(before, after)))


if __name__ == '__main__':
    unittest.main()
