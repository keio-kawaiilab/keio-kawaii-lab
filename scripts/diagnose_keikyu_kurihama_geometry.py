#!/usr/bin/env python3
from __future__ import annotations

import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pdfplumber

import keikyu_internal_official_evidence as internal
import keikyu_official_train_evidence as parser

MAIN = 'odpt.Railway:Keikyu.Main'
KURIHAMA = 'odpt.Railway:Keikyu.Kurihama'
SHINAGAWA_SUFFIX = '.Shinagawa'
ENDPOINT_SUFFIX = {
    '三崎口': '.Misakiguchi',
    '三浦海岸': '.Miurakaigan',
    '京急久里浜': '.KeikyuKurihama',
}


def rail_direction_matches(fragment: dict[str, Any], outbound: bool) -> bool:
    direction = str(fragment.get('direction') or '')
    wanted = 'Outbound' if outbound else 'Inbound'
    return direction.endswith(':' + wanted) or direction == wanted


def exact_matches(
    fragments: list[dict[str, Any]],
    railway: str,
    service: str,
    suffix: str,
    minute: int,
    *,
    outbound: bool,
) -> list[dict[str, Any]]:
    return [
        fragment
        for fragment in fragments
        if internal.fragment_has_exact(fragment, railway, service, suffix, minute)
        and rail_direction_matches(fragment, outbound)
    ]


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


def explicit_endpoint(words: list[dict[str, Any]], row: dict[str, Any] | None, x: float) -> dict[str, Any] | None:
    if not row:
        return None
    all_cells = parser.cells(words, float(row['y']))
    time_cells = parser.time_cells(words, float(row['y']))
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
        'x': round(tx, 2),
        'rowY': round(float(row['y']), 2),
    }


def columns(service: str, url: str) -> tuple[list[dict[str, Any]], Counter]:
    content = parser.fetch_pdf(url)
    found: list[dict[str, Any]] = []
    reasons: Counter = Counter()
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False, use_text_flow=False)
            page_rows = parser.rows(words)
            for candidate in parser.extract_page_candidates(
                words,
                page_number=page_number,
                calendar=service,
                source_url=url,
            ):
                geometry = candidate.get('rowGeometry') or {}
                sy = float(geometry.get('sourceBoundaryY') or 0)
                ty = float(geometry.get('targetBoundaryY') or 0)
                x = float(candidate.get('columnX') or 0)
                direction = str(candidate.get('direction') or '')
                if not sy or not ty or not x:
                    reasons['invalid-candidate-geometry'] += 1
                    continue
                shinagawa_row = (
                    internal.nearest_row(page_rows, '品川', max(sy, ty), above=False)
                    if direction == 'toei-to-keikyu'
                    else internal.nearest_row(page_rows, '品川', min(sy, ty), above=True)
                )
                shinagawa = internal.exact_column_time(words, shinagawa_row, x)
                if shinagawa is None:
                    reasons['missing-shinagawa-time'] += 1
                    continue
                endpoint = explicit_endpoint(words, endpoint_row(page_rows, sy, ty, direction), x)
                if endpoint is None:
                    reasons['no-explicit-kurihama-endpoint-in-column'] += 1
                    continue
                found.append({
                    'calendar': service,
                    'direction': direction,
                    'pdfPage': page_number,
                    'columnX': round(x, 2),
                    'shinagawaMinute': shinagawa,
                    **endpoint,
                })
                reasons['explicit-kurihama-endpoint-column'] += 1
    return found, reasons


def diagnose() -> dict[str, Any]:
    fragments = internal.load_keikyu_fragments(Path('data/transit-v2/fragments'))
    all_columns: list[dict[str, Any]] = []
    extraction_reasons: Counter = Counter()
    for service, url in (
        ('weekday', parser.DEFAULT_WEEKDAY_URL),
        ('holiday', parser.DEFAULT_HOLIDAY_URL),
    ):
        extracted, reasons = columns(service, url)
        all_columns.extend(extracted)
        extraction_reasons.update(reasons)

    match_reasons: Counter = Counter()
    matched: list[dict[str, Any]] = []
    for row in all_columns:
        service = str(row['calendar'])
        direction = str(row['direction'])
        outbound = direction == 'toei-to-keikyu'
        main_matches = exact_matches(
            fragments, MAIN, service, SHINAGAWA_SUFFIX,
            int(row['shinagawaMinute']), outbound=outbound,
        )
        branch_matches = exact_matches(
            fragments, KURIHAMA, service, str(row['stationSuffix']),
            int(row['minute']), outbound=outbound,
        )
        if len(main_matches) == 1 and len(branch_matches) == 1:
            match_reasons['matched-singleton-two-point'] += 1
            matched.append({
                **row,
                'mainFragment': str(main_matches[0]['id']),
                'kurihamaFragment': str(branch_matches[0]['id']),
            })
            continue
        if not main_matches:
            match_reasons['missing-main-exact'] += 1
        if not branch_matches:
            match_reasons['missing-kurihama-exact'] += 1
        if len(main_matches) > 1:
            match_reasons['ambiguous-main-exact'] += 1
        if len(branch_matches) > 1:
            match_reasons['ambiguous-kurihama-exact'] += 1

    summary = {
        'officialColumnsWithExplicitKurihamaEndpoint': len(all_columns),
        'columnsByService': dict(Counter(str(row['calendar']) for row in all_columns)),
        'columnsByDirection': dict(Counter(str(row['direction']) for row in all_columns)),
        'matchedSingleton': len(matched),
        'matchedByService': dict(Counter(str(row['calendar']) for row in matched)),
        'matchedByDirection': dict(Counter(str(row['direction']) for row in matched)),
        'matchedByEndpoint': dict(Counter(str(row['stationName']) for row in matched)),
        'extractionReasons': dict(extraction_reasons),
        'matchReasons': dict(match_reasons),
    }
    print('SUMMARY', json.dumps(summary, ensure_ascii=False, indent=2))
    for row in matched[:30]:
        print('MATCH', json.dumps(row, ensure_ascii=False))
    return summary


def main() -> int:
    summary = diagnose()
    if summary['officialColumnsWithExplicitKurihamaEndpoint'] <= 0:
        raise RuntimeError('No explicit Kurihama-line endpoint columns were extracted')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
