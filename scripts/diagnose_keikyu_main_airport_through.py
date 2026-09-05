#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pdfplumber

import keikyu_official_train_evidence as parser

MAIN = 'odpt.Railway:Keikyu.Main'
AIRPORT = 'odpt.Railway:Keikyu.Airport'
SHINAGAWA_SUFFIX = '.Shinagawa'
HANEDA_T3_SUFFIX = '.HanedaAirportTerminal3'
HANEDA_T12_SUFFIX = '.HanedaAirportTerminal1and2'


def calendar_matches(raw: Any, service: str) -> bool:
    return parser.calendar_matches(raw, service)


def stop_minutes(fragment: dict[str, Any], suffix: str) -> set[int]:
    out: set[int] = set()
    for stop in fragment.get('stops') or []:
        if not isinstance(stop, list) or len(stop) < 3 or not str(stop[0] or '').endswith(suffix):
            continue
        for value in stop[1:3]:
            if isinstance(value, (int, float)):
                out.add(int(value) % 1440)
    return out


def fragment_has_exact(fragment: dict[str, Any], railway: str, service: str, suffix: str, minute: int) -> bool:
    return (
        str(fragment.get('railway') or '') == railway
        and calendar_matches(fragment.get('calendar'), service)
        and minute % 1440 in stop_minutes(fragment, suffix)
    )


def load_keikyu_fragments(folder: Path) -> list[dict[str, Any]]:
    payload = json.loads((folder / 'keikyu.json').read_text(encoding='utf-8'))
    return [row for row in payload.get('fragments') or [] if isinstance(row, dict) and row.get('id')]


def nearest_row(page_rows: list[dict[str, Any]], needle: str, y: float, *, above: bool | None = None, max_distance: float = 220.0) -> dict[str, Any] | None:
    candidates = [row for row in page_rows if needle in parser.norm(row.get('text'))]
    if above is True:
        candidates = [row for row in candidates if float(row['y']) < y]
    elif above is False:
        candidates = [row for row in candidates if float(row['y']) > y]
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


def airport_minute(words: list[dict[str, Any]], page_rows: list[dict[str, Any]], source_y: float, target_y: float, x: float, direction: str) -> tuple[int | None, str]:
    # Both panels contain Haneda Terminal 3 and Terminal 1/2 rows. Restrict the
    # search to the same panel around the Sengakuji rows used by the trusted
    # existing parser, then read the exact same printed x-column.
    low, high = sorted((source_y, target_y))
    if direction == 'toei-to-keikyu':
        candidates = [row for row in page_rows if float(row['y']) > high and float(row['y']) - high <= 120 and ('羽田空港第１・第２ターミナル' in parser.norm(row.get('text')) or '羽田空港第3ターミナル' in parser.norm(row.get('text')) or '羽田空港第３ターミナル' in parser.norm(row.get('text')))]
    else:
        candidates = [row for row in page_rows if float(row['y']) < low and low - float(row['y']) <= 120 and ('羽田空港第１・第２ターミナル' in parser.norm(row.get('text')) or '羽田空港第3ターミナル' in parser.norm(row.get('text')) or '羽田空港第３ターミナル' in parser.norm(row.get('text')))]
    # Prefer Terminal 1/2 because it is the Airport-line endpoint in the PDF.
    candidates.sort(key=lambda row: (0 if '第１・第２' in parser.norm(row.get('text')) else 1, abs(float(row['y']) - (high if direction == 'toei-to-keikyu' else low))))
    for row in candidates:
        minute = exact_column_time(words, row, x)
        if minute is not None:
            text = parser.norm(row.get('text'))
            suffix = HANEDA_T12_SUFFIX if '第１・第２' in text else HANEDA_T3_SUFFIX
            return minute, suffix
    return None, ''


def extract_columns(service: str, url: str) -> list[dict[str, Any]]:
    content = parser.fetch_pdf(url)
    output: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False, use_text_flow=False)
            page_rows = parser.rows(words)
            candidates = parser.extract_page_candidates(words, page_number=page_number, calendar=service, source_url=url)
            for candidate in candidates:
                geometry = candidate.get('rowGeometry') or {}
                sy = float(geometry.get('sourceBoundaryY') or 0)
                ty = float(geometry.get('targetBoundaryY') or 0)
                x = float(candidate.get('columnX') or 0)
                direction = str(candidate.get('direction') or '')
                if not sy or not ty or not x or direction not in ('toei-to-keikyu', 'keikyu-to-toei'):
                    continue
                if direction == 'toei-to-keikyu':
                    shinagawa_row = nearest_row(page_rows, '品川', max(sy, ty), above=False, max_distance=100)
                else:
                    shinagawa_row = nearest_row(page_rows, '品川', min(sy, ty), above=True, max_distance=100)
                shinagawa = exact_column_time(words, shinagawa_row, x)
                haneda, haneda_suffix = airport_minute(words, page_rows, sy, ty, x, direction)
                output.append({
                    'calendar': service,
                    'pdfPage': page_number,
                    'columnX': x,
                    'direction': direction,
                    'boundaryTrainNumber': candidate.get('boundaryTrainNumber') or '',
                    'shinagawaMinute': shinagawa,
                    'hanedaMinute': haneda,
                    'hanedaSuffix': haneda_suffix,
                    'sourceUrl': url,
                    'evidence': ['operator-official-connection-timetable', 'same-printed-column-includes-shinagawa-and-haneda'],
                })
    return output


def diagnose(columns: list[dict[str, Any]], fragments: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter()
    examples: dict[str, list[dict[str, Any]]] = {}
    matched: list[dict[str, Any]] = []
    for row in columns:
        service = row['calendar']
        direction = row['direction']
        shinagawa = row.get('shinagawaMinute')
        haneda = row.get('hanedaMinute')
        suffix = row.get('hanedaSuffix') or ''
        if not isinstance(shinagawa, int) or not isinstance(haneda, int) or not suffix:
            reason = 'missing-official-two-point-time'
            main_matches = []
            airport_matches = []
        else:
            main_matches = [f for f in fragments if fragment_has_exact(f, MAIN, service, SHINAGAWA_SUFFIX, shinagawa)]
            airport_matches = [f for f in fragments if fragment_has_exact(f, AIRPORT, service, suffix, haneda)]
            if len(main_matches) == 1 and len(airport_matches) == 1:
                reason = 'matched-singleton-two-point'
                if direction == 'toei-to-keikyu':
                    from_fragment, to_fragment = main_matches[0], airport_matches[0]
                else:
                    from_fragment, to_fragment = airport_matches[0], main_matches[0]
                matched.append({
                    **row,
                    'boundaryId': 'keikyu-main-airport-kamata',
                    'fromRailway': str(from_fragment.get('railway') or ''),
                    'toRailway': str(to_fragment.get('railway') or ''),
                    'fromFragment': from_fragment.get('id'),
                    'toFragment': to_fragment.get('id'),
                    'matchStatus': 'matched-singleton',
                    'matchPolicy': {
                        'officialSamePrintedColumnRequired': True,
                        'exactShinagawaMinuteRequired': True,
                        'exactHanedaMinuteRequired': True,
                        'singletonFragmentMatchRequiredAtBothPoints': True,
                        'trainNumberAloneMayEstablishIdentity': False,
                        'timeProximityAloneMayEstablishIdentity': False,
                    },
                })
            elif not main_matches:
                reason = 'missing-main-exact'
            elif not airport_matches:
                reason = 'missing-airport-exact'
            else:
                reason = 'ambiguous-exact'
        counts[reason] += 1
        if len(examples.setdefault(reason, [])) < 8:
            examples[reason].append({
                **row,
                'mainMatches': [f.get('id') for f in main_matches],
                'airportMatches': [f.get('id') for f in airport_matches],
            })

    by_direction = Counter(row['direction'] for row in matched)
    return {
        'officialColumns': len(columns),
        'matchedSingletonTwoPoint': len(matched),
        'matchedDirections': dict(by_direction),
        'reasons': dict(counts),
        'examples': examples,
        'matched': matched,
        'policy': {
            'purpose': 'diagnostic only; does not modify production same-train DB',
            'officialSamePrintedColumnRequired': True,
            'twoExactPublishedStationTimesRequired': True,
            'singletonAtBothFragmentsRequired': True,
            'trainNumberAloneMayEstablishIdentity': False,
            'timeProximityAloneMayEstablishIdentity': False,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--fragments', default='data/transit-v2/fragments')
    ap.add_argument('--output', default='/tmp/keikyu-main-airport-diagnostic.json')
    args = ap.parse_args()
    fragments = load_keikyu_fragments(Path(args.fragments))
    columns = []
    columns.extend(extract_columns('weekday', parser.DEFAULT_WEEKDAY_URL))
    columns.extend(extract_columns('holiday', parser.DEFAULT_HOLIDAY_URL))
    report = diagnose(columns, fragments)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('matched', 'examples')}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
