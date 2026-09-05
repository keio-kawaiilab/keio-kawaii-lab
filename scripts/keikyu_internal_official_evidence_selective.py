#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import keikyu_internal_official_evidence as target

MAIN = target.MAIN
AIRPORT = target.AIRPORT
KURIHAMA = target.KURIHAMA
SUPPORTED_PAIRS = {
    (MAIN, AIRPORT),
    (AIRPORT, MAIN),
    (KURIHAMA, MAIN),
    (MAIN, KURIHAMA),
}


def needed_services(coverage_path: Path) -> set[str]:
    try:
        coverage = json.loads(coverage_path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        # Fail safe: if the coverage report is unavailable, parse both calendars.
        return {'weekday', 'holiday'}

    fragments_path = Path('data/transit-v2/fragments/keikyu.json')
    try:
        fragment_payload = json.loads(fragments_path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return {'weekday', 'holiday'}
    by_id = {
        str(row.get('id')): row
        for row in fragment_payload.get('fragments') or []
        if isinstance(row, dict) and row.get('id')
    }

    services: set[str] = set()
    for row in coverage.get('unresolved') or []:
        if not isinstance(row, dict) or row.get('kind') != 'ambiguous-boundary-fragment-alignment':
            continue
        source = by_id.get(str(row.get('fragment') or '')) or {}
        pair = (str(source.get('railway') or ''), str(row.get('nextRailway') or ''))
        if pair not in SUPPORTED_PAIRS:
            continue
        service = target.service_of(source)
        if service:
            services.add(service)
    return services


def main() -> int:
    coverage_path = Path('data/transit-v2/coverage.json')
    services = needed_services(coverage_path)
    print('KEIKYU_MAINLINE_CALENDARS_NEEDED', sorted(services))

    original = target.official_station_time_index

    def selective(service: str, url: str) -> dict[tuple[str, int], list[dict[str, Any]]]:
        if service not in services:
            print('SKIP_UNUSED_KEIKYU_MAINLINE_CALENDAR', service)
            return {}
        return original(service, url)

    target.official_station_time_index = selective
    return target.main()


if __name__ == '__main__':
    raise SystemExit(main())
