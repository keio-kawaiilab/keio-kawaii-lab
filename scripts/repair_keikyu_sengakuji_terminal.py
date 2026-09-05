#!/usr/bin/env python3
from __future__ import annotations

import copy
import io
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
SENGAKUJI = 'odpt.Station:Keikyu.Main.Sengakuji'
SHINAGAWA = 'odpt.Station:Keikyu.Main.Shinagawa'


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


def clock_text(value: int) -> str:
    hour, minute = divmod(int(value), 60)
    return f'{hour:02d}:{minute:02d}'


def first_destination(row: dict[str, Any]) -> str:
    values = as_list(row.get('odpt:destinationStation'))
    return str(next((value for value in values if value), '') or '')


def calendars_of(item: dict[str, Any]) -> list[str]:
    return [str(value or '') for value in as_list(item.get('odpt:calendar')) if value]


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


def adjacent_minutes(table: dict[str, Any]) -> tuple[int, int]:
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
    return minutes, support


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


def enrich_reverse_candidate_with_shinagawa(
    words: list[dict[str, Any]], candidate: dict[str, Any]
) -> dict[str, Any]:
    if candidate.get('direction') != 'keikyu-to-toei':
        return candidate
    source_y = float((candidate.get('rowGeometry') or {}).get('sourceBoundaryY') or 0)
    if not source_y:
        return {**candidate, 'officialShinagawaMatchStatus': 'missing-source-boundary-geometry'}
    page_rows = parser.rows(words)
    shinagawa_rows = [
        row for row in page_rows
        if '品川' in parser.norm(row.get('text')) and float(row.get('y', 0)) < source_y
    ]
    # The northbound Keikyu panel places 品川 immediately above 泉岳寺着.
    nearby = [row for row in shinagawa_rows if 0 < source_y - float(row['y']) <= 45]
    if not nearby:
        return {**candidate, 'officialShinagawaMatchStatus': 'missing-shinagawa-row'}
    row = max(nearby, key=lambda value: float(value['y']))
    times = parser.time_cells(words, float(row['y']))
    if not times:
        return {**candidate, 'officialShinagawaMatchStatus': 'missing-shinagawa-times'}
    tolerance = parser.column_tolerance(times)
    cell = parser.nearest(times, float(candidate['columnX']), tolerance)
    if not cell:
        return {**candidate, 'officialShinagawaMatchStatus': 'missing-shinagawa-column-time'}
    source_minute = int(candidate['sourceBoundaryMinute'])
    shinagawa_minute = int(cell['minute'])
    gap = (source_minute - shinagawa_minute) % 1440
    if not 1 <= gap <= 6:
        return {
            **candidate,
            'officialShinagawaMatchStatus': 'invalid-shinagawa-sengakuji-gap',
            'officialShinagawaMinute': shinagawa_minute,
            'officialShinagawaGapMinutes': gap,
        }
    return {
        **candidate,
        'officialShinagawaMatchStatus': 'matched-same-printed-column',
        'officialShinagawaStation': '品川',
        'officialShinagawaMinute': shinagawa_minute,
        'officialShinagawaGapMinutes': gap,
        'rowGeometry': {
            **(candidate.get('rowGeometry') or {}),
            'officialShinagawaText': row['text'],
            'officialShinagawaY': round(float(row['y']), 2),
        },
        'evidence': list(dict.fromkeys([
            *(candidate.get('evidence') or []),
            'same-printed-column-includes-shinagawa-and-sengakuji',
        ])),
    }


def official_reverse_candidates() -> list[dict[str, Any]]:
    import pdfplumber

    output: list[dict[str, Any]] = []
    for service, url in (
        ('weekday', parser.DEFAULT_WEEKDAY_URL),
        ('holiday', parser.DEFAULT_HOLIDAY_URL),
    ):
        content = parser.fetch_pdf(url)
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                words = page.extract_words(
                    x_tolerance=1,
                    y_tolerance=1,
                    keep_blank_chars=False,
                    use_text_flow=False,
                )
                candidates = parser.extract_page_candidates(
                    words,
                    page_number=page_number,
                    calendar=service,
                    source_url=url,
                )
                output.extend(
                    enrich_reverse_candidate_with_shinagawa(words, row)
                    for row in candidates
                    if row.get('direction') == 'keikyu-to-toei'
                )
    return output


def destination_is_beyond_sengakuji(destination: str) -> bool:
    if not destination or destination == SENGAKUJI:
        return False
    return not destination.startswith('odpt.Station:Keikyu.')


def build_official_inbound_sengakuji_boards(
    station_raw: list[dict[str, Any]],
    official: list[dict[str, Any]],
    operator: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    shinagawa_items: dict[str, dict[str, Any]] = {}
    for item in station_raw:
        if str(item.get('odpt:railway') or '') != MAIN:
            continue
        if str(item.get('odpt:station') or '') != SHINAGAWA:
            continue
        direction = str(item.get('odpt:railDirection') or '')
        if not direction.endswith(':Inbound'):
            continue
        for calendar in calendars_of(item):
            service = service_for_calendar(calendar)
            if service:
                if service in shinagawa_items:
                    raise RuntimeError(f'Multiple Shinagawa inbound boards for {service}')
                shinagawa_items[service] = item

    official_by_key: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    for candidate in official:
        service = str(candidate.get('calendar') or '')
        source_minute = int(candidate.get('sourceBoundaryMinute'))
        shinagawa_minute = candidate.get('officialShinagawaMinute')
        if not isinstance(shinagawa_minute, int):
            continue
        official_by_key[(service, source_minute % 1440, shinagawa_minute % 1440)].append(candidate)

    rows_by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    report_rows = []
    reasons = Counter()
    used_shinagawa_rows = Counter()

    missing_preboundary = Counter(
        str(row.get('officialShinagawaMatchStatus') or 'missing')
        for row in official
        if row.get('officialShinagawaMatchStatus') != 'matched-same-printed-column'
    )

    for (service, source_mod, official_shinagawa_mod), candidates in sorted(official_by_key.items()):
        board = shinagawa_items.get(service)
        matches = []
        raw_source = int(candidates[0].get('sourceBoundaryMinute')) if candidates else source_mod
        if board:
            for row_index, row in enumerate(board.get('odpt:stationTimetableObject') or []):
                if not isinstance(row, dict):
                    continue
                departure = minute_of(row.get('odpt:departureTime'))
                destination = first_destination(row)
                if departure is None or departure % 1440 != official_shinagawa_mod:
                    continue
                if not destination_is_beyond_sengakuji(destination):
                    continue
                matches.append((row_index, row))

        if len(candidates) != 1:
            reason = 'ambiguous-official-columns'
        elif not board:
            reason = 'missing-shinagawa-inbound-board'
        elif not matches:
            reason = 'no-exact-official-shinagawa-through-match'
        elif len(matches) > 1:
            reason = 'ambiguous-official-shinagawa-through-match'
        else:
            row_index, source_row = matches[0]
            claim_key = (service, row_index)
            used_shinagawa_rows[claim_key] += 1
            synthetic = {
                'odpt:departureTime': clock_text(raw_source),
                'odpt:destinationStation': copy.deepcopy(source_row.get('odpt:destinationStation')),
                'odpt:trainType': source_row.get('odpt:trainType'),
            }
            rows_by_service[service].append(synthetic)
            reason = 'strict-singleton-synthetic-board-row'
        reasons[reason] += 1
        report_rows.append({
            'service': service,
            'sourceBoundaryMinute': raw_source,
            'officialShinagawaMinute': official_shinagawa_mod,
            'officialColumns': len(candidates),
            'shinagawaMatches': len(matches),
            'reason': reason,
            'destination': first_destination(matches[0][1]) if len(matches) == 1 else '',
            'trainType': str(matches[0][1].get('odpt:trainType') or '') if len(matches) == 1 else '',
        })

    duplicated_claims = [key for key, count in used_shinagawa_rows.items() if count != 1]
    if duplicated_claims:
        raise RuntimeError(f'One Shinagawa departure was claimed by multiple official columns: {duplicated_claims[:8]}')

    synthetic_items = []
    for service in ('weekday', 'holiday'):
        source_board = shinagawa_items.get(service)
        rows = rows_by_service.get(service, [])
        if not source_board or not rows:
            continue
        calendar_values = calendars_of(source_board)
        if len(calendar_values) != 1:
            raise RuntimeError(f'Unexpected Shinagawa calendar cardinality for {service}: {calendar_values}')
        synthetic_items.append({
            '@type': 'odpt:StationTimetable',
            'owl:sameAs': f'manual.StationTimetable:Keikyu.Main.Sengakuji.Inbound.{service}',
            'odpt:operator': operator,
            'odpt:railway': MAIN,
            'odpt:station': SENGAKUJI,
            'odpt:railDirection': str(source_board.get('odpt:railDirection') or ''),
            'odpt:calendar': calendar_values[0],
            'odpt:stationTimetableObject': rows,
            'x-officialSupplement': {
                'source': 'Keikyu official connection timetable',
                'policy': 'same printed column Shinagawa+Sengakuji + exact singleton ODPT Shinagawa departure',
            },
        })

    return synthetic_items, {
        'officialCandidatesWithShinagawaTime': sum(
            1 for row in official if row.get('officialShinagawaMatchStatus') == 'matched-same-printed-column'
        ),
        'missingOfficialShinagawaTime': dict(missing_preboundary),
        'syntheticRows': sum(len(item.get('odpt:stationTimetableObject') or []) for item in synthetic_items),
        'syntheticItems': len(synthetic_items),
        'reasons': dict(reasons),
        'byService': {service: len(rows_by_service.get(service, [])) for service in ('weekday', 'holiday')},
        'examples': {
            reason: [row for row in report_rows if row['reason'] == reason][:12]
            for reason in reasons
        },
    }


def write_report(report: dict[str, Any]) -> None:
    Path('/tmp/keikyu-sengakuji-repair.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> int:
    challenge_key = os.environ.get('ODPT_CHALLENGE_API_KEY', '').strip() or os.environ.get('ODPT_API_KEY', '').strip()
    if not challenge_key:
        raise RuntimeError('ODPT_CHALLENGE_API_KEY is required for Keikyu repair')

    current_table, table_path, index = load_main_table()
    before_ends = count_sengakuji_ends(current_table)
    modal_minutes, modal_support = adjacent_minutes(current_table)
    official = official_reverse_candidates()
    if not official:
        raise RuntimeError('No official Keikyu -> Toei candidates found')

    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    operator = str(((manifest.get('operators') or {}).get('keikyu') or {}).get('operator') or importer.TARGETS['keikyu']['fallback'])
    session = requests.Session()
    session.headers.update({'User-Agent': 'keio-kawaii-lab-keikyu-terminal-repair/3.0'})

    station_raw = importer.api_get(session, 'odpt:StationTimetable', challenge_key, operator, base_url=importer.CHALLENGE_BASE_URL)
    railway_raw = importer.api_get(session, 'odpt:Railway', challenge_key, operator, base_url=importer.CHALLENGE_BASE_URL)
    station_entities_raw = importer.api_get(session, 'odpt:Station', challenge_key, operator, base_url=importer.CHALLENGE_BASE_URL)
    if not station_raw or not railway_raw or not station_entities_raw:
        raise RuntimeError('Keikyu ODPT source data is incomplete')

    synthetic_items, patch_report = build_official_inbound_sengakuji_boards(station_raw, official, operator)
    preliminary = {
        'officialReverseCandidates': len(official),
        'existingModalShinagawaToSengakujiMinutes': modal_minutes,
        'existingModalSupport': modal_support,
        'patch': patch_report,
        'beforeSengakujiEnds': dict(before_ends),
    }
    if patch_report['syntheticRows'] <= 0:
        write_report(preliminary)
        raise RuntimeError('No strict synthetic Sengakuji inbound rows were generated')

    augmented_raw = list(station_raw) + synthetic_items
    compact_stations = [importer.compact_entity(row) for row in station_entities_raw]
    aliases = importer.canonical_station_aliases(station_entities_raw, compact_stations)
    rebuilt = importer.compact_station_timetables(augmented_raw, aliases, railway_raw)
    if MAIN not in rebuilt:
        write_report(preliminary)
        raise RuntimeError('Rebuilt Keikyu Main timetable is missing')
    table, connection_count, departure_count = rebuilt[MAIN]
    after_ends = count_sengakuji_ends(table)

    report = {
        **preliminary,
        'afterSengakujiEnds': dict(after_ends),
        'inferredTrips': len(table.get('inferredTrips') or []),
        'inferredConnections': int(table.get('inferredConnections') or 0),
    }
    write_report(report)
    if sum(after_ends.values()) <= sum(before_ends.values()):
        raise RuntimeError(f'Sengakuji terminal coverage did not improve: before={before_ends}, after={after_ends}')

    table['officialTerminalRepair'] = {
        'boundary': 'Sengakuji',
        'source': 'Keikyu official connection timetable + ODPT Shinagawa inbound station timetable',
        'policy': {
            'officialThroughColumnRequired': True,
            'officialSameColumnShinagawaTimeRequired': True,
            'syntheticInboundBoundaryBoardOnly': True,
            'exactShinagawaPublishedMinuteRequired': True,
            'shinagawaDepartureSingletonRequired': True,
            'publishedDestinationBeyondSengakujiRequired': True,
            'trainNumberAloneMayResolve': False,
            'timeProximityAloneMayResolve': False,
        },
        'syntheticRows': patch_report['syntheticRows'],
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
    meta['source'] = 'station-timetable+official-sengakuji-inbound-board'
    importer.dump_json(INDEX_PATH, index)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
