#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber

import keikyu_official_train_evidence as parser

MAIN = 'odpt.Railway:Keikyu.Main'
KURIHAMA = 'odpt.Railway:Keikyu.Kurihama'
BOUNDARY_ID = 'keikyu-main-kurihama-horinouchi'
BOUNDARY_STATION = '堀ノ内'
MARKER = 'same-printed-column-links-shinagawa-and-explicit-kurihama-origin-or-terminal'
SHINAGAWA_SUFFIX = '.Shinagawa'
ENDPOINT_SUFFIX = {
    '三崎口': '.Misakiguchi',
    '三浦海岸': '.Miurakaigan',
    '京急久里浜': '.KeikyuKurihama',
}


def stable_id(*parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return 'keikyu-kurihama-pdf:' + hashlib.sha256(raw.encode()).hexdigest()[:24]


def stop_minutes(fragment: dict[str, Any], suffix: str) -> set[int]:
    out: set[int] = set()
    for stop in fragment.get('stops') or []:
        if not isinstance(stop, list) or len(stop) < 3 or not str(stop[0] or '').endswith(suffix):
            continue
        for value in stop[1:3]:
            if isinstance(value, (int, float)):
                out.add(int(value) % 1440)
    return out


def direction_matches(fragment: dict[str, Any], outbound: bool) -> bool:
    value = str(fragment.get('direction') or '')
    wanted = 'Outbound' if outbound else 'Inbound'
    return value == wanted or value.endswith(':' + wanted)


def fragment_has_exact(
    fragment: dict[str, Any],
    railway: str,
    service: str,
    suffix: str,
    minute: int,
    *,
    outbound: bool,
) -> bool:
    return (
        str(fragment.get('railway') or '') == railway
        and parser.calendar_matches(fragment.get('calendar'), service)
        and direction_matches(fragment, outbound)
        and minute % 1440 in stop_minutes(fragment, suffix)
    )


def load_fragments(folder: Path) -> list[dict[str, Any]]:
    payload = json.loads((folder / 'keikyu.json').read_text(encoding='utf-8'))
    return [row for row in payload.get('fragments') or [] if isinstance(row, dict) and row.get('id')]


def nearest_row(
    page_rows: list[dict[str, Any]],
    needle: str,
    y: float,
    *,
    above: bool,
    max_distance: float = 100.0,
) -> dict[str, Any] | None:
    candidates = [row for row in page_rows if needle in parser.norm(row.get('text'))]
    candidates = [row for row in candidates if (float(row['y']) < y if above else float(row['y']) > y)]
    candidates = [row for row in candidates if abs(float(row['y']) - y) <= max_distance]
    return min(candidates, key=lambda row: abs(float(row['y']) - y)) if candidates else None


def exact_column_time(words: list[dict[str, Any]], row: dict[str, Any] | None, x: float) -> int | None:
    if not row:
        return None
    times = parser.time_cells(words, float(row['y']))
    if not times:
        return None
    cell = parser.nearest(times, x, parser.column_tolerance(times))
    return int(cell['minute']) if cell else None


def endpoint_row(
    page_rows: list[dict[str, Any]],
    source_y: float,
    target_y: float,
    direction: str,
) -> dict[str, Any] | None:
    low, high = sorted((source_y, target_y))
    if direction == 'toei-to-keikyu':
        candidates = [
            row for row in page_rows
            if '終着' in parser.norm(row.get('text'))
            and float(row['y']) > high
            and float(row['y']) - high <= 70
        ]
        return min(candidates, key=lambda row: float(row['y']) - high) if candidates else None
    if direction == 'keikyu-to-toei':
        candidates = [
            row for row in page_rows
            if '始発' in parser.norm(row.get('text'))
            and float(row['y']) < low
            and low - float(row['y']) <= 70
        ]
        return min(candidates, key=lambda row: low - float(row['y'])) if candidates else None
    return None


def explicit_endpoint(
    words: list[dict[str, Any]],
    row: dict[str, Any] | None,
    x: float,
) -> dict[str, Any] | None:
    if not row:
        return None
    row_y = float(row['y'])
    all_cells = parser.cells(words, row_y)
    time_cells = parser.time_cells(words, row_y)
    if not time_cells:
        return None
    time_cell = parser.nearest(time_cells, x, parser.column_tolerance(time_cells))
    if not time_cell:
        return None
    tx = float(time_cell['x'])
    stations = [
        cell for cell in all_cells
        if parser.norm(cell.get('text')) in ENDPOINT_SUFFIX
        and abs(float(cell['x']) - tx) <= 4.0
    ]
    names = {parser.norm(cell['text']) for cell in stations}
    if len(names) != 1:
        return None
    name = next(iter(names))
    return {
        'stationName': name,
        'stationSuffix': ENDPOINT_SUFFIX[name],
        'minute': int(time_cell['minute']),
        'rowY': round(row_y, 2),
    }


def official_columns(service: str, url: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    content = parser.fetch_pdf(url)
    output: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False, use_text_flow=False)
            page_rows = parser.rows(words)
            candidates = parser.extract_page_candidates(
                words,
                page_number=page_number,
                calendar=service,
                source_url=url,
            )
            for candidate in candidates:
                geometry = candidate.get('rowGeometry') or {}
                source_y = float(geometry.get('sourceBoundaryY') or 0)
                target_y = float(geometry.get('targetBoundaryY') or 0)
                x = float(candidate.get('columnX') or 0)
                direction = str(candidate.get('direction') or '')
                if not source_y or not target_y or not x or direction not in ('toei-to-keikyu', 'keikyu-to-toei'):
                    reasons['invalid-column-geometry'] += 1
                    continue
                shinagawa_row = (
                    nearest_row(page_rows, '品川', max(source_y, target_y), above=False)
                    if direction == 'toei-to-keikyu'
                    else nearest_row(page_rows, '品川', min(source_y, target_y), above=True)
                )
                shinagawa = exact_column_time(words, shinagawa_row, x)
                if shinagawa is None:
                    reasons['missing-shinagawa-time'] += 1
                    continue
                endpoint = explicit_endpoint(words, endpoint_row(page_rows, source_y, target_y, direction), x)
                if not endpoint:
                    reasons['no-explicit-kurihama-endpoint'] += 1
                    continue
                output.append({
                    'calendar': service,
                    'pdfPage': page_number,
                    'columnX': round(x, 2),
                    'direction': direction,
                    'shinagawaMinute': shinagawa,
                    'branchEndpointStationName': endpoint['stationName'],
                    'branchEndpointStationSuffix': endpoint['stationSuffix'],
                    'branchEndpointMinute': endpoint['minute'],
                    'branchEndpointRole': 'terminal' if direction == 'toei-to-keikyu' else 'origin',
                    'sourceUrl': url,
                })
                reasons['explicit-kurihama-endpoint-column'] += 1
    return output, dict(reasons)


def match_columns(
    columns: list[dict[str, Any]],
    fragments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    for row in columns:
        service = str(row['calendar'])
        direction = str(row['direction'])
        outbound = direction == 'toei-to-keikyu'
        shinagawa = int(row['shinagawaMinute'])
        branch_minute = int(row['branchEndpointMinute'])
        branch_suffix = str(row['branchEndpointStationSuffix'])
        main_matches = [
            fragment for fragment in fragments
            if fragment_has_exact(
                fragment, MAIN, service, SHINAGAWA_SUFFIX, shinagawa, outbound=outbound
            )
        ]
        branch_matches = [
            fragment for fragment in fragments
            if fragment_has_exact(
                fragment, KURIHAMA, service, branch_suffix, branch_minute, outbound=outbound
            )
        ]
        if len(main_matches) != 1 or len(branch_matches) != 1:
            if not main_matches:
                reasons['missing-main-exact'] += 1
            if not branch_matches:
                reasons['missing-kurihama-exact'] += 1
            if len(main_matches) > 1:
                reasons['ambiguous-main-exact'] += 1
            if len(branch_matches) > 1:
                reasons['ambiguous-kurihama-exact'] += 1
            continue

        if outbound:
            source, target = main_matches[0], branch_matches[0]
            public_direction = 'main-to-kurihama'
        else:
            source, target = branch_matches[0], main_matches[0]
            public_direction = 'kurihama-to-main'
        entry = {
            'status': 'official-column-evidence',
            'matchStatus': 'matched-singleton',
            'id': stable_id(
                service,
                public_direction,
                row['pdfPage'],
                row['columnX'],
                shinagawa,
                branch_suffix,
                branch_minute,
                source['id'],
                target['id'],
            ),
            'operator': 'keikyu',
            'calendar': service,
            'direction': public_direction,
            'boundaryId': BOUNDARY_ID,
            'boundaryStation': BOUNDARY_STATION,
            'fromRailway': str(source.get('railway') or ''),
            'toRailway': str(target.get('railway') or ''),
            'fromFragment': source['id'],
            'toFragment': target['id'],
            'sourceMatches': [str(source['id'])],
            'targetMatches': [str(target['id'])],
            'shinagawaMinute': shinagawa,
            'branchEndpointStationName': row['branchEndpointStationName'],
            'branchEndpointStationSuffix': branch_suffix,
            'branchEndpointMinute': branch_minute,
            'branchEndpointRole': row['branchEndpointRole'],
            'pdfPage': row['pdfPage'],
            'columnX': row['columnX'],
            'evidence': ['operator-official-connection-timetable', MARKER],
            'sourceUrl': row['sourceUrl'],
            'matchPolicy': {
                'officialSamePrintedColumnRequired': True,
                'explicitBranchOriginOrTerminalRequired': True,
                'exactShinagawaMinuteRequired': True,
                'exactBranchEndpointMinuteRequired': True,
                'singletonFragmentMatchRequiredAtBothPoints': True,
                'stationMinuteTolerance': 0,
                'trainNumberAloneMayEstablishIdentity': False,
                'timeProximityAloneMayEstablishIdentity': False,
                'destinationAloneMayEstablishIdentity': False,
            },
        }
        entries.append(entry)
        reasons['matched-singleton-two-point'] += 1

    return entries, {
        'matchedSingleton': len(entries),
        'directions': dict(Counter(str(row['direction']) for row in entries)),
        'endpoints': dict(Counter(str(row['branchEndpointStationName']) for row in entries)),
        'reasons': dict(reasons),
    }


def generate(fragment_folder: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fragments = load_fragments(fragment_folder)
    columns: list[dict[str, Any]] = []
    extraction: Counter[str] = Counter()
    for service, url in (
        ('weekday', parser.DEFAULT_WEEKDAY_URL),
        ('holiday', parser.DEFAULT_HOLIDAY_URL),
    ):
        service_columns, service_reasons = official_columns(service, url)
        columns.extend(service_columns)
        extraction.update(service_reasons)
    entries, summary = match_columns(columns, fragments)
    return entries, {
        'officialTwoPointColumns': len(columns),
        'columnsByService': dict(Counter(str(row['calendar']) for row in columns)),
        'columnsByDirection': dict(Counter(str(row['direction']) for row in columns)),
        'extractionReasons': dict(extraction),
        **summary,
    }


def append_payload(path: Path, entries: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise RuntimeError('Existing Keikyu internal evidence payload is not an object')
    policy = payload.get('policy') or {}
    if (
        policy.get('officialSamePrintedColumnRequired') is not True
        or policy.get('twoExactPublishedStationTimesRequired') is not True
        or policy.get('singletonFragmentMatchRequiredAtBothPoints') is not True
        or policy.get('trainNumberAloneMayEstablishIdentity') is not False
        or policy.get('timeProximityAloneMayEstablishIdentity') is not False
    ):
        raise RuntimeError('Existing Keikyu internal evidence policy is unsafe')

    existing = [
        row for row in payload.get('entries') or []
        if isinstance(row, dict) and str(row.get('boundaryId') or '') != BOUNDARY_ID
    ]
    payload['version'] = max(int(payload.get('version') or 1), 2)
    payload['generatedAt'] = datetime.now(timezone.utc).isoformat()
    payload['boundaryIds'] = sorted({
        str(row.get('boundaryId') or '')
        for row in existing + entries
        if row.get('boundaryId')
    })
    policy['destinationAloneMayEstablishIdentity'] = False
    policy['stationMinuteTolerance'] = 0
    payload['policy'] = policy
    payload['entries'] = existing + entries
    existing_summary = payload.get('summary') if isinstance(payload.get('summary'), dict) else {}
    existing_summary['kurihama'] = summary
    existing_summary['totalEntries'] = len(payload['entries'])
    payload['summary'] = existing_summary
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--fragments', default='data/transit-v2/fragments')
    ap.add_argument('--evidence', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    args = ap.parse_args()
    entries, summary = generate(Path(args.fragments))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not entries:
        raise RuntimeError('No strict Keikyu Main-Kurihama official same-column evidence matched')
    append_payload(Path(args.evidence), entries, summary)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
