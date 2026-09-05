#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import keikyu_official_train_evidence as parser

SERVICES = ('weekday', 'holiday')
V1_INDEX = Path('data/transit/keikyu/timetable-index.json')


def build_endpoint_indexes(fragments):
    indexes = defaultdict(lambda: defaultdict(dict))
    inventory = Counter()
    for fragment in fragments:
        railway = str(fragment.get('railway') or '')
        if railway not in {parser.KEIKYU_MAIN, parser.TOEI_ASAKUSA}:
            continue
        for calendar in SERVICES:
            if not parser.calendar_matches(fragment.get('calendar'), calendar):
                continue
            for first in (False, True):
                stop = parser.endpoint(fragment, first)
                if not stop or not str(stop[0] or '').endswith('.Sengakuji'):
                    continue
                key = (railway, calendar, first)
                inventory[key] += 1
                for value in stop[1:3]:
                    if isinstance(value, (int, float)):
                        indexes[key][int(value) % 1440][str(fragment.get('id'))] = fragment
    return indexes, inventory


def indexed_matches(indexes, railway, calendar, first, minute, tolerance):
    bucket = {}
    table = indexes[(railway, calendar, first)]
    center = int(minute) % 1440
    for delta in range(-tolerance, tolerance + 1):
        for fragment_id, fragment in table.get((center + delta) % 1440, {}).items():
            bucket[fragment_id] = fragment
    return list(bucket.values())


def classify(candidate, indexes):
    calendar = str(candidate['calendar'])
    source_minute = int(candidate['sourceBoundaryMinute'])
    target_minute = int(candidate['targetBoundaryMinute'])
    src0 = indexed_matches(indexes, parser.KEIKYU_MAIN, calendar, False, source_minute, 0)
    dst0 = indexed_matches(indexes, parser.TOEI_ASAKUSA, calendar, True, target_minute, 0)
    src1 = indexed_matches(indexes, parser.KEIKYU_MAIN, calendar, False, source_minute, 1)
    dst1 = indexed_matches(indexes, parser.TOEI_ASAKUSA, calendar, True, target_minute, 1)
    src2 = indexed_matches(indexes, parser.KEIKYU_MAIN, calendar, False, source_minute, 2)
    dst2 = indexed_matches(indexes, parser.TOEI_ASAKUSA, calendar, True, target_minute, 2)
    if len(src0) == 1 and len(dst0) == 1:
        reason = 'exact-singleton-both'
    elif not src0 and not dst0:
        reason = 'missing-both-exact'
    elif not src0:
        reason = 'missing-keikyu-source-exact'
    elif not dst0:
        reason = 'missing-toei-target-exact'
    elif len(src0) > 1 and len(dst0) > 1:
        reason = 'ambiguous-both-exact'
    elif len(src0) > 1:
        reason = 'ambiguous-keikyu-source-exact'
    else:
        reason = 'ambiguous-toei-target-exact'
    return {
        'reason': reason,
        'calendar': calendar,
        'page': candidate.get('pdfPage'),
        'columnX': candidate.get('columnX'),
        'sourceMinute': source_minute,
        'targetMinute': target_minute,
        'trainNumber': candidate.get('boundaryTrainNumber') or '',
        'sourceExact': [row.get('id') for row in src0],
        'targetExact': [row.get('id') for row in dst0],
        'sourceWithin1': [row.get('id') for row in src1],
        'targetWithin1': [row.get('id') for row in dst1],
        'sourceWithin2': [row.get('id') for row in src2],
        'targetWithin2': [row.get('id') for row in dst2],
    }


def load_v1_main_table():
    index = json.loads(V1_INDEX.read_text(encoding='utf-8'))
    meta = (index.get('lines') or {}).get(parser.KEIKYU_MAIN) or {}
    relative = str(meta.get('file') or '')
    if not relative:
        raise RuntimeError('Keikyu Main timetable is missing from v1 index')
    path = V1_INDEX.parent / relative
    table = json.loads(path.read_text(encoding='utf-8'))
    return path, table


def inspect_v1_keikyu_main():
    path, table = load_v1_main_table()
    stations = table.get('stations') or []
    sengakuji_indexes = [i for i, sid in enumerate(stations) if str(sid).endswith('.Sengakuji')]
    sengakuji_ids = [stations[i] for i in sengakuji_indexes]
    calendars = table.get('calendars') or []
    trips = table.get('inferredTrips') or []
    stats = {}
    for service in SERVICES:
        total = contains = starts = ends = 0
        last_stations = Counter()
        first_stations = Counter()
        for trip in trips:
            if not isinstance(trip, list) or len(trip) < 6:
                continue
            calendar = calendars[trip[0]] if isinstance(trip[0], int) and trip[0] < len(calendars) else ''
            if not parser.calendar_matches(calendar, service):
                continue
            total += 1
            raw_stops = trip[5] or []
            if not raw_stops:
                continue
            stop_indexes = [stop[0] for stop in raw_stops if isinstance(stop, list) and stop and isinstance(stop[0], int)]
            stop_ids = [stations[i] for i in stop_indexes if 0 <= i < len(stations)]
            if stop_ids:
                first_stations[str(stop_ids[0])] += 1
                last_stations[str(stop_ids[-1])] += 1
            if any(str(sid).endswith('.Sengakuji') for sid in stop_ids):
                contains += 1
            if stop_ids and str(stop_ids[0]).endswith('.Sengakuji'):
                starts += 1
            if stop_ids and str(stop_ids[-1]).endswith('.Sengakuji'):
                ends += 1
        stats[service] = {
            'inferredTrips': total,
            'containsSengakuji': contains,
            'startsAtSengakuji': starts,
            'endsAtSengakuji': ends,
            'topFirstStations': first_stations.most_common(8),
            'topLastStations': last_stations.most_common(8),
        }
    return {
        'sourceFile': str(path),
        'timeBasis': table.get('timeBasis'),
        'stationCount': len(stations),
        'sengakujiStationIndexes': sengakuji_indexes,
        'sengakujiStationIds': sengakuji_ids,
        'stats': stats,
    }


def strict_sengakuji_repair_simulation(reverse_candidates):
    path, table = load_v1_main_table()
    stations = table.get('stations') or []
    calendars = table.get('calendars') or []
    destinations = table.get('destinations') or []
    order = table.get('order') or []
    trips = table.get('inferredTrips') or []

    sengakuji_indexes = [i for i, sid in enumerate(stations) if str(sid).endswith('.Sengakuji')]
    shinagawa_indexes = [i for i, sid in enumerate(stations) if str(sid).endswith('.Shinagawa')]
    if len(sengakuji_indexes) != 1 or len(shinagawa_indexes) != 1:
        raise RuntimeError(f'Expected one Sengakuji and Shinagawa index: {sengakuji_indexes} / {shinagawa_indexes}')
    sengakuji_index, shinagawa_index = sengakuji_indexes[0], shinagawa_indexes[0]
    sengakuji_id, shinagawa_id = stations[sengakuji_index], stations[shinagawa_index]

    order_pos = {str(sid): i for i, sid in enumerate(order)}
    if sengakuji_id not in order_pos or shinagawa_id not in order_pos:
        raise RuntimeError('Sengakuji/Shinagawa missing from Keikyu Main station order')
    if abs(order_pos[sengakuji_id] - order_pos[shinagawa_id]) != 1:
        raise RuntimeError('Sengakuji and Shinagawa are not adjacent in Keikyu Main order')
    toward_step = 1 if order_pos[sengakuji_id] > order_pos[shinagawa_id] else -1

    edge_rows = []
    for row in table.get('edgeMinutes') or []:
        if not isinstance(row, list) or len(row) < 4:
            continue
        if row[0] == shinagawa_index and row[1] == sengakuji_index:
            edge_rows.append({'minutes': int(row[2]), 'support': int(row[3])})
    if len(edge_rows) != 1:
        raise RuntimeError(f'Expected one Shinagawa -> Sengakuji edge duration, got {edge_rows}')
    edge = edge_rows[0]
    if not 1 <= edge['minutes'] <= 6 or edge['support'] < 2:
        raise RuntimeError(f'Unsafe Shinagawa -> Sengakuji edge evidence: {edge}')

    by_service_minute = defaultdict(list)
    trip_inventory = Counter()
    trip_details = {}
    for trip_index, trip in enumerate(trips):
        if not isinstance(trip, list) or len(trip) < 6:
            continue
        calendar = calendars[trip[0]] if isinstance(trip[0], int) and 0 <= trip[0] < len(calendars) else ''
        services = [service for service in SERVICES if parser.calendar_matches(calendar, service)]
        if len(services) != 1:
            continue
        service = services[0]
        raw_stops = trip[5] or []
        if len(raw_stops) < 2:
            continue
        stop_indexes = [stop[0] for stop in raw_stops if isinstance(stop, list) and stop and isinstance(stop[0], int)]
        if len(stop_indexes) != len(raw_stops) or not stop_indexes or stop_indexes[-1] != shinagawa_index:
            continue
        if sengakuji_index in stop_indexes:
            continue
        previous_station = stations[stop_indexes[-2]] if 0 <= stop_indexes[-2] < len(stations) else ''
        previous_pos = order_pos.get(str(previous_station))
        if previous_pos is None:
            continue
        actual_step = order_pos[shinagawa_id] - previous_pos
        if actual_step == 0 or (1 if actual_step > 0 else -1) != toward_step:
            continue
        destination = destinations[trip[3]] if isinstance(trip[3], int) and 0 <= trip[3] < len(destinations) else ''
        if not destination or str(destination).endswith('.Sengakuji'):
            continue
        last_stop = raw_stops[-1]
        endpoint = last_stop[2] if len(last_stop) > 2 and isinstance(last_stop[2], (int, float)) else last_stop[1] if len(last_stop) > 1 and isinstance(last_stop[1], (int, float)) else None
        if endpoint is None:
            continue
        predicted = int(endpoint) + edge['minutes']
        key = (service, predicted % 1440)
        by_service_minute[key].append(trip_index)
        trip_inventory[service] += 1
        trip_details[trip_index] = {
            'tripIndex': trip_index,
            'calendar': calendar,
            'destination': destination,
            'lastStation': shinagawa_id,
            'lastMinute': int(endpoint),
            'predictedSengakujiMinute': predicted,
        }

    candidate_rows = []
    trip_claims = Counter()
    for candidate in reverse_candidates:
        service = str(candidate.get('calendar') or '')
        source_minute = int(candidate.get('sourceBoundaryMinute'))
        matches = list(by_service_minute.get((service, source_minute % 1440), []))
        row = {
            'candidateId': candidate.get('id'),
            'calendar': service,
            'pdfPage': candidate.get('pdfPage'),
            'columnX': candidate.get('columnX'),
            'trainNumber': candidate.get('boundaryTrainNumber') or '',
            'sourceBoundaryMinute': source_minute,
            'targetBoundaryMinute': int(candidate.get('targetBoundaryMinute')),
            'tripMatches': matches,
        }
        candidate_rows.append(row)
        if len(matches) == 1:
            trip_claims[matches[0]] += 1

    status_counts = Counter()
    repairable = []
    for row in candidate_rows:
        matches = row['tripMatches']
        if not matches:
            status = 'no-v1-shinagawa-match'
        elif len(matches) > 1:
            status = 'ambiguous-v1-shinagawa-match'
        elif trip_claims[matches[0]] != 1:
            status = 'v1-trip-claimed-by-multiple-official-columns'
        else:
            status = 'strict-singleton-repairable'
            row['trip'] = trip_details[matches[0]]
            repairable.append(row)
        row['repairStatus'] = status
        status_counts[status] += 1

    return {
        'sourceFile': str(path),
        'adjacentEdge': {
            'fromStation': shinagawa_id,
            'toStation': sengakuji_id,
            **edge,
        },
        'eligibleShinagawaEndTrips': dict(trip_inventory),
        'officialReverseCandidates': len(reverse_candidates),
        'repairStatus': dict(status_counts),
        'strictRepairable': len(repairable),
        'examples': {
            status: [row for row in candidate_rows if row['repairStatus'] == status][:12]
            for status in status_counts
        },
    }


def main():
    fragments = parser.load_fragments(Path('data/transit-v2/fragments'))
    indexes, endpoint_inventory = build_endpoint_indexes(fragments)
    all_rows = []
    all_reverse = []
    inventory = {}
    for calendar, url in (
        ('weekday', parser.DEFAULT_WEEKDAY_URL),
        ('holiday', parser.DEFAULT_HOLIDAY_URL),
    ):
        candidates = parser.extract_pdf(parser.fetch_pdf(url), calendar, url)
        reverse = [row for row in candidates if row.get('direction') == 'keikyu-to-toei']
        all_reverse.extend(reverse)
        rows = [classify(row, indexes) for row in reverse]
        all_rows.extend(rows)
        inventory[calendar] = {
            'reverseCandidates': len(reverse),
            'keikyuSengakujiEndFragments': endpoint_inventory[(parser.KEIKYU_MAIN, calendar, False)],
            'toeiSengakujiStartFragments': endpoint_inventory[(parser.TOEI_ASAKUSA, calendar, True)],
        }
    reasons = Counter(row['reason'] for row in all_rows)
    repair_simulation = strict_sengakuji_repair_simulation(all_reverse)
    payload = {
        'summary': {
            'totalReverseCandidates': len(all_rows),
            'reasons': dict(reasons),
            'missingExactButSourceWithin1Minute': sum(1 for row in all_rows if not row['sourceExact'] and row['sourceWithin1']),
            'missingExactButTargetWithin1Minute': sum(1 for row in all_rows if not row['targetExact'] and row['targetWithin1']),
            'missingExactButSourceWithin2Minutes': sum(1 for row in all_rows if not row['sourceExact'] and row['sourceWithin2']),
            'missingExactButTargetWithin2Minutes': sum(1 for row in all_rows if not row['targetExact'] and row['targetWithin2']),
            'inventory': inventory,
            'v1KeikyuMain': inspect_v1_keikyu_main(),
            'strictSengakujiRepairSimulation': repair_simulation,
        },
        'examples': {
            reason: [row for row in all_rows if row['reason'] == reason][:12]
            for reason in reasons
        },
    }
    Path('/tmp/keikyu-reverse-diagnostic.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload['summary'], ensure_ascii=False, indent=2))
    if not all_rows:
        raise RuntimeError('No Keikyu -> Toei official candidates were extracted')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
