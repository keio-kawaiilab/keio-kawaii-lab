#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import repair_keikyu_sengakuji_terminal as repair

REPORT_PATH = Path('/tmp/keikyu-sengakuji-repair.json')
STRICT_SOURCE = 'Keikyu official connection timetable + ODPT Shinagawa inbound station timetable'
STRICT_POLICY = {
    'officialThroughColumnRequired': True,
    'officialSameColumnShinagawaTimeRequired': True,
    'syntheticInboundBoundaryBoardOnly': True,
    'exactShinagawaPublishedMinuteRequired': True,
    'shinagawaDepartureSingletonRequired': True,
    'publishedDestinationBeyondSengakujiRequired': True,
    'trainNumberAloneMayResolve': False,
    'timeProximityAloneMayResolve': False,
}
SERVICES = ('weekday', 'holiday')


def prior_strict_repair_is_valid(meta: Any) -> bool:
    if not isinstance(meta, dict):
        return False
    if meta.get('boundary') != 'Sengakuji' or meta.get('source') != STRICT_SOURCE:
        return False
    if int(meta.get('syntheticRows') or 0) <= 0:
        return False
    policy = meta.get('policy')
    if not isinstance(policy, dict):
        return False
    for key, expected in STRICT_POLICY.items():
        if policy.get(key) is not expected:
            return False
    prior_after = Counter(meta.get('afterSengakujiEnds') or {})
    return sum(int(prior_after.get(service, 0)) for service in SERVICES) > 0


def idempotent_report_is_safe(
    prior_meta: Any,
    current_ends: Counter,
    report: dict[str, Any],
) -> bool:
    if not prior_strict_repair_is_valid(prior_meta):
        return False

    before = Counter(report.get('beforeSengakujiEnds') or {})
    after = Counter(report.get('afterSengakujiEnds') or {})
    if any(int(current_ends.get(service, 0)) != int(before.get(service, 0)) for service in SERVICES):
        return False
    if any(int(after.get(service, 0)) < int(before.get(service, 0)) for service in SERVICES):
        return False
    if sum(int(after.get(service, 0)) for service in SERVICES) <= 0:
        return False

    patch = report.get('patch') or {}
    if int(patch.get('syntheticRows') or 0) <= 0:
        return False
    if int(patch.get('officialCandidatesWithShinagawaTime') or 0) <= 0:
        return False
    return True


def mark_report(mode: str, prior_strict_repair: bool) -> None:
    if not REPORT_PATH.exists():
        return
    report = json.loads(REPORT_PATH.read_text(encoding='utf-8'))
    report['repairMode'] = mode
    report['priorStrictRepair'] = prior_strict_repair
    repair.write_report(report)


def main() -> int:
    try:
        result = repair.main()
    except RuntimeError as exc:
        if not str(exc).startswith('Sengakuji terminal coverage did not improve:'):
            raise
        if not REPORT_PATH.exists():
            raise

        current_table, _, _ = repair.load_main_table()
        current_ends = repair.count_sengakuji_ends(current_table)
        report = json.loads(REPORT_PATH.read_text(encoding='utf-8'))
        prior_meta = current_table.get('officialTerminalRepair')
        if not idempotent_report_is_safe(prior_meta, current_ends, report):
            raise

        report['repairMode'] = 'idempotent-strict-rerun'
        report['priorStrictRepair'] = True
        repair.write_report(report)
        print('Keikyu Sengakuji strict repair already materialized; idempotent rerun accepted.')
        return 0

    mark_report('first-strict-improvement', False)
    return int(result or 0)


if __name__ == '__main__':
    raise SystemExit(main())
