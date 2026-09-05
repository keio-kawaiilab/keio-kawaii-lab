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

import keikyu_kurihama_official_evidence as kurihama
import keikyu_official_train_evidence as parser

MAIN = 'odpt.Railway:Keikyu.Main'
AIRPORT = 'odpt.Railway:Keikyu.Airport'
BOUNDARY_ID = 'keikyu-main-airport-kamata'
MARKER = 'same-printed-column-includes-shinagawa-and-haneda'
SHINAGAWA_SUFFIX = '.Shinagawa'
HANEDA_T3_SUFFIX = '.HanedaAirportTerminal3'
HANEDA_T12_SUFFIX = '.HanedaAirportTerminal1and2'


def stable_id(*parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return 'keikyu-internal-pdf:' + hashlib.sha256(raw.encode()).hexdigest()[:24]


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
        and parser.calendar_matches(fragment.get('calendar'), service)
        and minute % 1440 in stop_minutes(fragment, suffix)
    )


def load_keikyu_fragments(folder: Path) -> list[dict[str, Any]]:
    payload = json.loads((folder / 'keikyu.json').read_text(encoding='utf-8'))
    return [row for row in payload.get('fragments') or [] if isinstance(row, dict) and row.get('id')]


def nearest_row(page_rows: list[dict[str, Any]], needle: str, y: float, *, above: bool, max_distance: float = 100.0) -> dict[str, Any] | None:
    rows = [row for row in page_rows if needle in parser.norm(row.get('text'))]
    rows = [row for row in rows if (float(row['y']) < y if above else float(row['y']) > y)]
    rows = [row for row in rows if abs(float(row['y']) - y) <= max_distance]
    return min(rows, key=lambda row: abs(float(row['y']) - y)) if rows else None


def exact_column_time(words: list[dict[str, Any]], row: dict[str, Any] | None, x: float) -> int | None:
    if not row:
        return None
    times = parser.time_cells(words, float(row['y']))
    if not times:
        return None
    cell = parser.nearest(times, x, parser.column_tolerance(times))
    return int(cell['minute']) if cell else None


def airport_time(words: list[dict[str, Any]], page_rows: list[dict[str, Any]], source_y: float, target_y: float, x: float, direction: str) -> tuple[int | None, str, str]:
    low, high = sorted((source_y, target_y))

    def is_haneda(row: dict[str, Any]) -> bool:
        text = parser.norm(row.get('text'))
        return '羽田空港第１・第２ターミナル' in text or '羽田空港第3ターミナル' in text or '羽田空港第３ターミナル' in text

    if direction == 'toei-to-keikyu':
        rows = [row for row in page_rows if float(row['y']) > high and float(row['y']) - high <= 120 and is_haneda(row)]
        anchor = high
    else:
        rows = [row for row in page_rows if float(row['y']) < low and low - float(row['y']) <= 120 and is_haneda(row)]
        anchor = low

    rows.sort(key=lambda row: (0 if '第１・第２' in parser.norm(row.get('text')) else 1, abs(float(row['y']) - anchor)))
    for row in rows:
        minute = exact_column_time(words, row, x)
        if minute is None:
            continue
        text = parser.norm(row.get('text'))
        suffix = HANEDA_T12_SUFFIX if '第１・第２' in text else HANEDA_T3_SUFFIX
        return minute, suffix, text
    return None, '', ''


def official_columns(service: str, url: str) -> list[dict[str, Any]]:
    content = parser.fetch_pdf(url)
    out: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False, use_text_flow=False)
            page_rows = parser.rows(words)
            for candidate in parser.extract_page_candidates(words, page_number=page_number, calendar=service, source_url=url):
                geometry = candidate.get('rowGeometry') or {}
                sy = float(geometry.get('sourceBoundaryY') or 0)
                ty = float(geometry.get('targetBoundaryY') or 0)
                x = float(candidate.get('columnX') or 0)
                direction = str(candidate.get('direction') or '')
                if not sy or not ty or not x or direction not in ('toei-to-keikyu', 'keikyu-to-toei'):
                    continue
                shinagawa_row = nearest_row(page_rows, '品川', max(sy, ty), above=False) if direction == 'toei-to-keikyu' else nearest_row(page_rows, '品川', min(sy, ty), above=True)
                shinagawa = exact_column_time(words, shinagawa_row, x)
                haneda, haneda_suffix, haneda_text = airport_time(words, page_rows, sy, ty, x, direction)
                if shinagawa is None or haneda is None or not haneda_suffix:
                    continue
                out.append({
                    'calendar': service,
                    'pdfPage': page_number,
                    'columnX': round(x, 2),
                    'direction': direction,
                    'shinagawaMinute': shinagawa,
                    'hanedaMinute': haneda,
                    'hanedaStationSuffix': haneda_suffix,
                    'hanedaRowText': haneda_text,
                    'sourceUrl': url,
                })
    return out


def match_columns(columns: list[dict[str, Any]], fragments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    reasons = Counter()
    for row in columns:
        service = str(row['calendar'])
        direction = str(row['direction'])
        shinagawa = int(row['shinagawaMinute'])
        haneda = int(row['hanedaMinute'])
        suffix = str(row['hanedaStationSuffix'])
        main_matches = [f for f in fragments if fragment_has_exact(f, MAIN, service, SHINAGAWA_SUFFIX, shinagawa)]
        airport_matches = [f for f in fragments if fragment_has_exact(f, AIRPORT, service, suffix, haneda)]
        if len(main_matches) != 1 or len(airport_matches) != 1:
            if not main_matches:
                reasons['missing-main-exact'] += 1
            elif not airport_matches:
                reasons['missing-airport-exact'] += 1
            else:
                reasons['ambiguous-exact'] += 1
            continue

        if direction == 'toei-to-keikyu':
            source, target = main_matches[0], airport_matches[0]
        else:
            source, target = airport_matches[0], main_matches[0]
        source_matches = [str(source['id'])]
        target_matches = [str(target['id'])]
        entry = {
            'status': 'official-column-evidence',
            'matchStatus': 'matched-singleton',
            'id': stable_id(service, direction, row['pdfPage'], row['columnX'], shinagawa, haneda, source['id'], target['id']),
            'operator': 'keikyu',
            'calendar': service,
            'direction': 'main-to-airport' if direction == 'toei-to-keikyu' else 'airport-to-main',
            'boundaryId': BOUNDARY_ID,
            'boundaryStation': '京急蒲田',
            'fromRailway': str(source.get('railway') or ''),
            'toRailway': str(target.get('railway') or ''),
            'fromFragment': source['id'],
            'toFragment': target['id'],
            'sourceMatches': source_matches,
            'targetMatches': target_matches,
            'shinagawaMinute': shinagawa,
            'hanedaMinute': haneda,
            'hanedaStationSuffix': suffix,
            'pdfPage': row['pdfPage'],
            'columnX': row['columnX'],
            'evidence': ['operator-official-connection-timetable', MARKER],
            'sourceUrl': row['sourceUrl'],
            'matchPolicy': {
                'officialSamePrintedColumnRequired': True,
                'exactShinagawaMinuteRequired': True,
                'exactHanedaMinuteRequired': True,
                'singletonFragmentMatchRequiredAtBothPoints': True,
                'trainNumberAloneMayEstablishIdentity': False,
                'timeProximityAloneMayEstablishIdentity': False,
            },
        }
        entries.append(entry)
        reasons['matched-singleton-two-point'] += 1

    return entries, {
        'matchedSingleton': len(entries),
        'directions': dict(Counter(str(row['direction']) for row in entries)),
        'reasons': dict(reasons),
    }


def build_payload(fragment_folder: Path) -> dict[str, Any]:
    fragments = load_keikyu_fragments(fragment_folder)
    columns = []
    columns.extend(official_columns('weekday', parser.DEFAULT_WEEKDAY_URL))
    columns.extend(official_columns('holiday', parser.DEFAULT_HOLIDAY_URL))
    entries, summary = match_columns(columns, fragments)
    return {
        'version': 1,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'operator': 'keikyu',
        'boundaryId': BOUNDARY_ID,
        'policy': {
            'officialSamePrintedColumnRequired': True,
            'twoExactPublishedStationTimesRequired': True,
            'singletonFragmentMatchRequiredAtBothPoints': True,
            'trainNumberAloneMayEstablishIdentity': False,
            'timeProximityAloneMayEstablishIdentity': False,
        },
        'summary': {'officialTwoPointColumns': len(columns), **summary},
        'entries': entries,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--fragments', default='data/transit-v2/fragments')
    ap.add_argument('--output', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    args = ap.parse_args()
    fragment_folder = Path(args.fragments)
    output_path = Path(args.output)

    payload = build_payload(fragment_folder)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'airport': payload['summary']}, ensure_ascii=False, indent=2))
    if not payload['entries']:
        raise RuntimeError('No strict Keikyu Main-Airport official same-column evidence matched')

    kurihama_entries, kurihama_summary = kurihama.generate(fragment_folder)
    if not kurihama_entries:
        raise RuntimeError('No strict Keikyu Main-Kurihama official same-column evidence matched')
    combined = kurihama.append_payload(output_path, kurihama_entries, kurihama_summary)
    print(json.dumps({
        'airportEntries': len(payload['entries']),
        'kurihamaEntries': len(kurihama_entries),
        'totalEntries': len(combined.get('entries') or []),
        'kurihama': kurihama_summary,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
