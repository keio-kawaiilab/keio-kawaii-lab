#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import fitz

import keikyu_internal_official_evidence as target

MAIN = target.MAIN
AIRPORT = target.AIRPORT
KURIHAMA = target.KURIHAMA
ZUSHI = target.ZUSHI
SUPPORTED_PAIRS = {
    (MAIN, AIRPORT),
    (AIRPORT, MAIN),
    (KURIHAMA, MAIN),
    (MAIN, KURIHAMA),
    (ZUSHI, MAIN),
    (MAIN, ZUSHI),
}


def load_context(
    coverage_path: Path = Path('data/transit-v2/coverage.json'),
    fragments_path: Path = Path('data/transit-v2/fragments/keikyu.json'),
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    coverage = json.loads(coverage_path.read_text(encoding='utf-8'))
    payload = json.loads(fragments_path.read_text(encoding='utf-8'))
    fragments = [row for row in payload.get('fragments') or [] if isinstance(row, dict) and row.get('id')]
    by_id = {str(row['id']): row for row in fragments}
    return coverage, fragments, by_id


def relevant_rows(
    coverage: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    output: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for row in coverage.get('unresolved') or []:
        if not isinstance(row, dict) or row.get('kind') != 'ambiguous-boundary-fragment-alignment':
            continue
        source = by_id.get(str(row.get('fragment') or ''))
        if not source:
            continue
        pair = (str(source.get('railway') or ''), str(row.get('nextRailway') or ''))
        if pair not in SUPPORTED_PAIRS:
            continue
        candidates = [
            by_id[fid]
            for fid in (str(value) for value in row.get('candidateFragments') or [])
            if fid in by_id
        ]
        if candidates:
            output.append((source, candidates))
    return output


def needed_services(rows: list[tuple[dict[str, Any], list[dict[str, Any]]]]) -> set[str]:
    return {service for source, _ in rows if (service := target.service_of(source))}


def needed_station_times(
    rows: list[tuple[dict[str, Any], list[dict[str, Any]]]],
) -> dict[str, set[tuple[str, int]]]:
    """Exact station/minute keys that can participate in current ambiguities.

    This is only a performance filter. Identity still requires two exact points
    from one official printed column and singleton fragment matches on both sides.
    """
    output: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for source, candidates in rows:
        service = target.service_of(source)
        if not service:
            continue
        for fragment in [source, *candidates]:
            for anchor in target.fragment_anchors(fragment):
                suffix = str(anchor.get('suffix') or '')
                minute = anchor.get('minute')
                if suffix and isinstance(minute, int):
                    output[service].add((suffix, minute % 1440))
    return output


def fitz_words(page: fitz.Page) -> list[dict[str, Any]]:
    """Adapt PyMuPDF word coordinates to the existing strict parser geometry.

    Only the extraction engine changes. The row grouping, exact HHMM parsing,
    column tolerance and same-column proof remain the existing production rules.
    """
    out: list[dict[str, Any]] = []
    for item in page.get_text('words', sort=False):
        if len(item) < 5:
            continue
        x0, y0, x1, y1, text = item[:5]
        if not str(text or '').strip():
            continue
        out.append({
            'x0': float(x0),
            'x1': float(x1),
            'top': float(y0),
            'bottom': float(y1),
            'text': str(text),
        })
    return out


def focused_official_station_time_index(
    service: str,
    url: str,
    needed: dict[str, set[tuple[str, int]]],
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    required = needed.get(service) or set()
    if not required:
        print('SKIP_UNUSED_KEIKYU_MAINLINE_CALENDAR', service)
        return {}

    suffix_minutes: dict[str, set[int]] = defaultdict(set)
    for suffix, minute in required:
        suffix_minutes[suffix].add(minute)
    label_suffixes: list[tuple[str, str]] = []
    for suffix in suffix_minutes:
        for label in target.STATION_LABELS.get(suffix) or ():
            label_suffixes.append((target.parser.norm(label), suffix))

    content = target.parser.fetch_pdf(url)
    index: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    scanned_rows = 0
    kept_cells = 0
    document = fitz.open(stream=content, filetype='pdf')
    try:
        print('KEIKYU_PYMUPDF_PAGES', service, document.page_count)
        for page_index in range(document.page_count):
            words = fitz_words(document.load_page(page_index))
            if not words:
                continue
            for row in target.parser.rows(words):
                text = target.parser.norm(row.get('text'))
                suffixes = {suffix for label, suffix in label_suffixes if label and label in text}
                if not suffixes:
                    continue
                scanned_rows += 1
                cells = target.parser.time_cells(words, float(row['y']))
                for cell in cells:
                    minute = int(cell['minute']) % 1440
                    for suffix in suffixes:
                        if minute not in suffix_minutes[suffix]:
                            continue
                        index[(suffix, minute)].append({
                            'page': page_index + 1,
                            'x': round(float(cell['x']), 2),
                            'rowText': text,
                            'sourceUrl': url,
                        })
                        kept_cells += 1
    finally:
        document.close()

    print('KEIKYU_FOCUSED_OFFICIAL_INDEX', json.dumps({
        'engine': 'PyMuPDF',
        'service': service,
        'requiredStationTimes': len(required),
        'matchedStationRows': scanned_rows,
        'keptOfficialCells': kept_cells,
        'indexKeys': len(index),
    }, ensure_ascii=False))
    return dict(index)


def main() -> int:
    try:
        coverage, _, by_id = load_context()
        rows = relevant_rows(coverage, by_id)
    except (FileNotFoundError, json.JSONDecodeError):
        print('KEIKYU_FOCUSED_INDEX_FALLBACK', 'missing-or-invalid-context')
        return target.main()

    services = needed_services(rows)
    needed = needed_station_times(rows)
    print('KEIKYU_MAINLINE_CALENDARS_NEEDED', sorted(services))
    print('KEIKYU_MAINLINE_EXACT_KEYS_NEEDED', {service: len(keys) for service, keys in sorted(needed.items())})

    def selective(service: str, url: str) -> dict[tuple[str, int], list[dict[str, Any]]]:
        return focused_official_station_time_index(service, url, needed)

    target.official_station_time_index = selective
    return target.main()


if __name__ == '__main__':
    raise SystemExit(main())
