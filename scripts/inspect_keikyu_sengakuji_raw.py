#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import requests

import import_odpt_timetables as importer


def slim_row(row):
    keys = (
        'odpt:arrivalTime',
        'odpt:departureTime',
        'odpt:destinationStation',
        'odpt:trainType',
        'odpt:trainNumber',
        'odpt:train',
        'odpt:note',
    )
    return {key: row.get(key) for key in keys if key in row}


def slim_item(item):
    objects = item.get('odpt:stationTimetableObject') or []
    return {
        'keys': sorted(item.keys()),
        'id': item.get('owl:sameAs'),
        'station': item.get('odpt:station'),
        'railway': item.get('odpt:railway'),
        'railDirection': item.get('odpt:railDirection'),
        'calendar': item.get('odpt:calendar'),
        'objectCount': len(objects),
        'sampleObjects': [slim_row(row) for row in objects[:12] if isinstance(row, dict)],
    }


def main():
    key = os.environ.get('ODPT_CHALLENGE_API_KEY', '').strip() or os.environ.get('ODPT_API_KEY', '').strip()
    if not key:
        raise RuntimeError('ODPT_CHALLENGE_API_KEY is required')
    session = requests.Session()
    session.headers.update({'User-Agent': 'keio-kawaii-lab-keikyu-raw-inspector/1.0'})
    operator = importer.TARGETS['keikyu']['fallback']
    rows = importer.api_get(
        session,
        'odpt:StationTimetable',
        key,
        operator,
        base_url=importer.CHALLENGE_BASE_URL,
    )
    matched = []
    station_fields = Counter()
    railway_fields = Counter()
    for item in rows:
        station_fields[str(item.get('odpt:station') or '')] += 1
        railway_fields[str(item.get('odpt:railway') or '')] += 1
        serialized = json.dumps(item, ensure_ascii=False)
        if 'Sengakuji' in serialized or 'Shinagawa' in serialized:
            matched.append(slim_item(item))
    payload = {
        'totalStationTimetables': len(rows),
        'topRailwayFields': railway_fields.most_common(12),
        'sengakujiOrShinagawaItems': matched,
        'matchingItemCount': len(matched),
        'stationsContainingSengakuji': [
            [station, count] for station, count in station_fields.items() if 'Sengakuji' in station
        ],
        'stationsContainingShinagawa': [
            [station, count] for station, count in station_fields.items() if 'Shinagawa' in station
        ],
    }
    Path('/tmp/keikyu-sengakuji-raw.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
