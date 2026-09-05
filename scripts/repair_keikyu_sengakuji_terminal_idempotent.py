#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import requests

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


def main() -> int:
    challenge_key = os.environ.get('ODPT_CHALLENGE_API_KEY', '').strip() or os.environ.get('ODPT_API_KEY', '').strip()
    if not challenge_key:
        raise RuntimeError('ODPT_CHALLENGE_API_KEY is required for Keikyu repair')

    current_table, table_path, index = repair.load_main_table()
    prior_meta = current_table.get('officialTerminalRepair')
    prior_valid = prior_strict_repair_is_valid(prior_meta)
    before_ends = repair.count_sengakuji_ends(current_table)
    modal_minutes, modal_support = repair.adjacent_minutes(current_table)
    official = repair.official_reverse_candidates()
    if not official:
        raise RuntimeError('No official Keikyu -> Toei candidates found')

    manifest = json.loads(repair.MANIFEST_PATH.read_text(encoding='utf-8'))
    operator = str(
        ((manifest.get('operators') or {}).get('keikyu') or {}).get('operator')
        or repair.importer.TARGETS['keikyu']['fallback']
    )
    session = requests.Session()
    session.headers.update({'User-Agent': 'keio-kawaii-lab-keikyu-terminal-repair/4.0'})

    station_raw = repair.importer.api_get(
        session,
        'odpt:StationTimetable',
        challenge_key,
        operator,
        base_url=repair.importer.CHALLENGE_BASE_URL,
    )
    railway_raw = repair.importer.api_get(
        session,
        'odpt:Railway',
        challenge_key,
        operator,
        base_url=repair.importer.CHALLENGE_BASE_URL,
    )
    station_entities_raw = repair.importer.api_get(
        session,
        'odpt:Station',
        challenge_key,
        operator,
        base_url=repair.importer.CHALLENGE_BASE_URL,
    )
    if not station_raw or not railway_raw or not station_entities_raw:
        raise RuntimeError('Keikyu ODPT source data is incomplete')

    synthetic_items, patch_report = repair.build_official_inbound_sengakuji_boards(
        station_raw,
        official,
        operator,
    )
    preliminary = {
        'officialReverseCandidates': len(official),
        'existingModalShinagawaToSengakujiMinutes': modal_minutes,
        'existingModalSupport': modal_support,
        'patch': patch_report,
        'beforeSengakujiEnds': dict(before_ends),
    }
    if patch_report['syntheticRows'] <= 0:
        repair.write_report(preliminary)
        raise RuntimeError('No strict synthetic Sengakuji inbound rows were generated')

    augmented_raw = list(station_raw) + synthetic_items
    compact_stations = [repair.importer.compact_entity(row) for row in station_entities_raw]
    aliases = repair.importer.canonical_station_aliases(station_entities_raw, compact_stations)
    rebuilt = repair.importer.compact_station_timetables(augmented_raw, aliases, railway_raw)
    if repair.MAIN not in rebuilt:
        repair.write_report(preliminary)
        raise RuntimeError('Rebuilt Keikyu Main timetable is missing')

    table, connection_count, departure_count = rebuilt[repair.MAIN]
    after_ends = repair.count_sengakuji_ends(table)
    report = {
        **preliminary,
        'afterSengakujiEnds': dict(after_ends),
        'inferredTrips': len(table.get('inferredTrips') or []),
        'inferredConnections': int(table.get('inferredConnections') or 0),
    }

    first_improvement = sum(after_ends.values()) > sum(before_ends.values())
    safe_rerun = idempotent_report_is_safe(prior_meta, before_ends, report)
    if prior_valid and safe_rerun:
        mode = 'idempotent-strict-rerun'
    elif not prior_valid and first_improvement:
        mode = 'first-strict-improvement'
    else:
        report['repairMode'] = 'rejected'
        report['priorStrictRepair'] = prior_valid
        repair.write_report(report)
        raise RuntimeError(
            f'Sengakuji terminal coverage was not a safe strict update: before={before_ends}, after={after_ends}'
        )

    report['repairMode'] = mode
    report['priorStrictRepair'] = prior_valid
    repair.write_report(report)

    table['officialTerminalRepair'] = {
        'boundary': 'Sengakuji',
        'source': STRICT_SOURCE,
        'policy': dict(STRICT_POLICY),
        'syntheticRows': patch_report['syntheticRows'],
        'beforeSengakujiEnds': dict(before_ends),
        'afterSengakujiEnds': dict(after_ends),
        'repairMode': mode,
    }
    repair.importer.dump_json(table_path, table)

    meta = index['lines'][repair.MAIN]
    meta['trips'] = len(table.get('trips') or [])
    meta['connections'] = connection_count
    meta['inferredTrips'] = len(table.get('inferredTrips') or [])
    meta['inferredConnections'] = int(table.get('inferredConnections') or 0)
    meta['departures'] = departure_count
    meta['source'] = 'station-timetable+official-sengakuji-inbound-board'
    repair.importer.dump_json(repair.INDEX_PATH, index)
    print(f'Keikyu Sengakuji repair mode: {mode}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
