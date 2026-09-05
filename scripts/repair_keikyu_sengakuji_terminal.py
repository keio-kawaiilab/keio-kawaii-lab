#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import requests

import import_odpt_timetables as importer
import keikyu_official_train_evidence as parser

MAIN = parser.KEIKYU_MAIN
INDEX_PATH = Path('data/transit/keikyu/timetable-index.json')
MANIFEST_PATH = Path('data/transit/manifest.json')


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def minute_of(value: Any) -> int | None:
    text = str(value or '').strip()
    if not text or ':' not in text:
        return None
    try:
        hour, minute = (int(part) for part in text.split(':', 1))
    except ValueError:
        return None
    if hour < 0 or hour > 29 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def first_destination(row: dict[str, Any]) -> str:
    values = as_list(row.get('odpt:destinationStation'))
    return str(next((value for value in values if value), '') or '')


def calendars_of(item: dict[str, Any]) -> list[str]:
    return [str(value or '') for value in as_list(item.get('odpt:calendar')) if value]


def station_id_of(item: dict[str, Any]) -> str:
    return str(item.get('odpt:station') or item.get('odpt:railway') or '')


def row_train_key(row: dict[str, Any]) -> str:
    return str(row.get('odpt:train') or row.get('odpt:trainNumber') or '')


def same_train_type(a: dict[str, Any], b: dict[str, Any]) -> bool:
    left = str(a.get('odpt:trainType') or '')
    right = str(b.get('odpt:trainType') or '')
    return not left or not right or left == right


def service_for_calendar(calendar: str) -> str | None:
    matches = [service for service in ('weekday', 'holiday') if parser.calendar_matches(calendar, service)]
    return matches[0] if len(matches) == 1 else None


def load_main_table() -> tuple[dict[str, Any], Path, dict[str, Any]]:
    index = json.loads(INDEX_PATH.read_text(encoding='utf-8'))
    meta = (index.get('lines') or {}).get(MAIN)
    if not isinstance(meta, dict) or not meta.get('file'):
        raise RuntimeError('Keikyu Main timetable is missing')
    path = INDEX_PATH.parent / str(meta['file'])
    return json.loads(path.read_text(encoding='utf-8')), path, index


def adjacent_minutes(table: dict[str, Any]) -> int:
    stations = table.get('stations') or []
    shinagawa = [i for i, sid in enumerate(stations) if str(sid).endswith('.Shinagawa')]
    sengakuji = [i for i, sid in enumerate(stations) if str(sid).endswith('.Sengakuji')]
    if len(shinagawa) != 1 or len(sengakuji) != 1:
        raise RuntimeError(f'Expected one Shinagawa/Sengakuji station: {shinagawa} / {sengakuji}')
    matches = [
        row for row in table.get('edgeMinutes') or []
        if isinstance(row, list) and len(row) >= 4 and row[0] == shinagawa[0] and row[1] == sengakuji[0]
    ]
    if len(matches) != 1:
        raise RuntimeError(f'Expected one Shinagawa -> Sengakuji duration: {matches}')
    minutes, support = int(matches[0][2]), int(matches[0][3])
    if not 1 <= minutes <= 6 or support < 20:
        raise RuntimeError(f'Unsafe Shinagawa -> Sengakuji duration evidence: {minutes}m / support={support}')
    return minutes


def count_sengakuji_ends(table: dict[str, Any]) -> Counter:
    stations = table.get('stations') or []
    calendars = table.get('calendars') or []
    out = Counter()
    for trip in table.get('inferredTrips') or []:
        if not isinstance(trip, list) or len(trip) < 6 or not trip[5]:
            continue
        calendar = calendars[trip[0]] if isinstance(trip[0], int) and 0 <= trip[0] < len(calendars) else ''
        service = service_for_calendar(str(calendar))
        last = trip[5][-1]
        if not service or not isinstance(last, list) or not last or not isinstance(last[0], int):
            continue
        sid = stations[last[0]] if 0 <= last[0] < len(stations) else ''
        if str(sid).endswith('.Sengakuji'):
            out[service] += 1
    return out


def official_reverse_candidates() -> list[dict[str, Any]]:
    output = []
    for service, url in (
        ('weekday', parser.DEFAULT_WEEKDAY_URL),
        ('holiday', parser.DEFAULT_HOLIDAY_URL),
    ):
        rows = parser.extract_pdf(parser.fetch_pdf(url), service, url)
        output.extend(row for row in rows if row.get('direction') == 'keikyu-to-toei')
    return output


def patch_raw_sengakuji_destinations(
    station_raw: list[dict[str, Any]],
    official: list[dict[str, Any]],
    expected_minutes: int,
) -> dict[str, Any]:
    arrivals = defaultdict(list)
    departures = defaultdict(list)

    for item_index, item in enumerate(station_raw):
        if str(item.get('odpt:railway') or '') != MAIN:
            continue
        station = str(item.get('odpt:station') or '')
        direction = str(item.get('odpt:railDirection') or '')
        calendars = calendars_of(item)
        if not calendars or not direction:
            continue
        for row_index, row in enumerate(item.get('odpt:stationTimetableObject') or []):
            if not isinstance(row, dict):
                continue
            arrival = minute_of(row.get('odpt:arrivalTime'))
            departure = minute_of(row.get('odpt:departureTime'))
            destination = first_destination(row)
            for calendar in calendars:
                service = service_for_calendar(calendar)
                if not service:
                    continue
                record = {
                    'itemIndex': item_index,
                    'rowIndex': row_index,
                    'item': item,
                    'row': row,
                    'service': service,
                    'calendar': calendar,
                    'direction': direction,
                    'arrival': arrival,
                    'departure': departure,
                    'destination': destination,
                    'trainKey': row_train_key(row),
                    'trainType': str(row.get('odpt:trainType') or ''),
                }
                if station.endswith('.Sengakuji') and arrival is not None and departure is None and not destination:
                    arrivals[(service, arrival % 1440)].append(record)
                if station.endswith('.Shinagawa') and departure is not None and destination:
                    departures[(service, direction)].append(record)

    official_keys = defaultdict(list)
    for candidate in official:
        service = str(candidate.get('calendar') or '')
        source = int(candidate.get('sourceBoundaryMinute')) % 1440
        official_keys[(service, source)].append(candidate)

    report_rows = []
    patched_row_keys = set()
    reason_counts = Counter()

    for key, official_rows in sorted(official_keys.items()):
        service, source_minute = key
        arrival_rows = arrivals.get(key, [])
        if len(official_rows) != 1:
            reason = 'ambiguous-official-columns'
            matches = []
        elif len(arrival_rows) != 1:
            reason = 'missing-arrival-row' if not arrival_rows else 'ambiguous-arrival-rows'
            matches = []
        else:
            arrival = arrival_rows[0]
            matches = []
            for departure in departures.get((service, arrival['direction']), []):
                if not same_train_type(arrival['row'], departure['row']):
                    continue
                gap = (source_minute - int(departure['departure']) % 1440) % 1440
                if gap != expected_minutes:
                    continue
                arrival_key = arrival['trainKey']
                departure_key = departure['trainKey']
                if arrival_key and departure_key and arrival_key != departure_key:
                    continue
                matches.append(departure)
            if len(matches) == 1:
                reason = 'patched-singleton'
                arrival_row = arrival['row']
                departure_row = matches[0]['row']
                arrival_row['odpt:destinationStation'] = copy.deepcopy(departure_row.get('odpt:destinationStation'))
                patched_row_keys.add((arrival['itemIndex'], arrival['rowIndex']))
            elif not matches:
                reason = 'no-shinagawa-singleton'
            else:
                reason = 'ambiguous-shinagawa-match'
        reason_counts[reason] += 1
        report_rows.append({
            'service': service,
            'sourceBoundaryMinute': source_minute,
            'officialColumns': len(official_rows),
            'arrivalRows': len(arrival_rows),
            'shinagawaMatches': len(matches),
            'reason': reason,
            'destination': first_destination(matches[0]['row']) if len(matches) == 1 else '',
        })

    return {
        'patchedRows': len(patched_row_keys),
        'reasons': dict(reason_counts),
        'examples': {
            reason: [row for row in report_rows if row['reason'] == reason][:12]
            for reason in reason_counts
        },
    }


def main() -> int:
    challenge_key = os.environ.get('ODPT_CHALLENGE_API_KEY', '').strip() or os.environ.get('ODPT_API_KEY', '').strip()
    if not challenge_key:
        raise RuntimeError('ODPT_CHALLENGE_API_KEY is required for Keikyu repair')

    current_table, table_path, index = load_main_table()
    before_ends = count_sengakuji_ends(current_table)
    expected_minutes = adjacent_minutes(current_table)
    official = official_reverse_candidates()
    if not official:
        raise RuntimeError('No official Keikyu -> Toei candidates found')

    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    operator = str(((manifest.get('operators') or {}).get('keikyu') or {}).get('operator') or importer.TARGETS['keikyu']['fallback'])
    session = requests.Session()
    session.headers.update({'User-Agent': 'keio-kawaii-lab-keikyu-terminal-repair/1.0'})
    base_url = importer.CHALLENGE_BASE_URL

    station_raw = importer.api_get(session, 'odpt:StationTimetable', challenge_key, operator, base_url=base_url)
    railway_raw = importer.api_get(session, 'odpt:Railway', challenge_key, operator, base_url=base_url)
    station_entities_raw = importer.api_get(session, 'odpt:Station', challenge_key, operator, base_url=base_url)
    if not station_raw or not railway_raw or not station_entities_raw:
        raise RuntimeError('Keikyu ODPT source data is incomplete')

    patch_report = patch_raw_sengakuji_destinations(station_raw, official, expected_minutes)
    if patch_report['patchedRows'] <= 0:
        raise RuntimeError(f'No strict Sengakuji terminal rows were repaired: {patch_report}')

    compact_stations = [importer.compact_entity(row) for row in station_entities_raw]
    aliases = importer.canonical_station_aliases(station_entities_raw, compact_stations)
    rebuilt = importer.compact_station_timetables(station_raw, aliases, railway_raw)
    if MAIN not in rebuilt:
        raise RuntimeError('Rebuilt Keikyu Main timetable is missing')
    table, connection_count, departure_count = rebuilt[MAIN]
    after_ends = count_sengakuji_ends(table)
    if sum(after_ends.values()) <= sum(before_ends.values()):
        raise RuntimeError(f'Sengakuji terminal coverage did not improve: before={before_ends}, after={after_ends}')

    table['officialTerminalRepair'] = {
        'boundary': 'Sengakuji',
        'source': 'Keikyu official connection timetable + ODPT adjacent station timetables',
        'policy': {
            'officialThroughColumnRequired': True,
            'arrivalOnlyDestinationMissingRequired': True,
            'sameDirectionRequired': True,
            'sameTrainTypeWhenPublishedRequired': True,
            'adjacentObservedMinutesExactRequired': expected_minutes,
            'singletonMatchRequired': True,
            'trainNumberAloneMayResolve': False,
            'timeProximityAloneMayResolve': False,
        },
        'patchedRows': patch_report['patchedRows'],
        'beforeSengakujiEnds': dict(before_ends),
        'afterSengakujiEnds': dict(after_ends),
    }
    importer.dump_json(table_path, table)

    meta = index['lines'][MAIN]
    meta['trips'] = len(table.get('trips') or [])
    meta['connections'] = connection_count
    meta['inferredTrips'] = len(table.get('inferredTrips') or [])
    meta['inferredConnections'] = int(table.get('inferredConnections') or 0)
    meta['departures'] = departure_count
    meta['source'] = 'station-timetable+official-sengakuji-repair'
    importer.dump_json(INDEX_PATH, index)

    report = {
        'officialReverseCandidates': len(official),
        'expectedShinagawaToSengakujiMinutes': expected_minutes,
        'patch': patch_report,
        'beforeSengakujiEnds': dict(before_ends),
        'afterSengakujiEnds': dict(after_ends),
        'inferredTrips': len(table.get('inferredTrips') or []),
        'inferredConnections': int(table.get('inferredConnections') or 0),
    }
    Path('/tmp/keikyu-sengakuji-repair.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
