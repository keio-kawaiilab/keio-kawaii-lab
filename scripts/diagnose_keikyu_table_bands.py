#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from audit_keikyu_official_columns import FIRST_POSSIBLE_TIMETABLE_PAGE, page_scope_reason
from audit_keikyu_station_time_resolution import resolve_page
from keikyu_connected_station_catalog import station_titles
from keikyu_official_pdf import (
    Word,
    bbox_words,
    compact,
    detect_train_column_grid,
    download_official_pdf,
    page_count,
    time_cells,
)

BANDS = ('upper', 'lower')


def band_words(words: list[Word], height: float, band: str) -> list[Word]:
    split = height / 2.0
    if band == 'upper':
        selected = [w for w in words if w.y < split]
        offset = 0.0
    elif band == 'lower':
        selected = [w for w in words if w.y >= split]
        offset = split
    else:
        raise ValueError(band)
    return [
        Word(
            text=w.text,
            x_min=w.x_min,
            y_min=w.y_min - offset,
            x_max=w.x_max,
            y_max=w.y_max - offset,
        )
        for w in selected
    ]


def diagnose(pdf_path: Path) -> dict[str, Any]:
    titles = station_titles()
    total_pages = page_count(pdf_path)
    pages: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    missing: list[dict[str, Any]] = []

    for page_number in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total_pages + 1):
        _width, height, words = bbox_words(pdf_path, page_number)
        page_text = compact(''.join(w.text for w in words))
        excluded = page_scope_reason(page_text)
        if excluded:
            continue
        page_row: dict[str, Any] = {'page': page_number, 'bands': {}}
        for band in BANDS:
            bw = band_words(words, height, band)
            grid = detect_train_column_grid(bw)
            if grid is None:
                page_row['bands'][band] = {'grid': False}
                missing.append({'page': page_number, 'band': band, 'reason': 'no-grid'})
                continue
            resolution = resolve_page(bw, grid, titles, include_records=False)
            cells = len(time_cells(bw, grid))
            accounted = int(resolution.get('resolvedTimeCells') or 0) + int(resolution.get('unresolvedTimeCells') or 0)
            row = {
                'grid': True,
                'headerY': round(float(grid.header_y), 3),
                'columns': len(grid.centers),
                'explicitColumns': sum(1 for n in grid.explicit_numbers if n is not None),
                'anonymousColumns': sum(1 for n in grid.explicit_numbers if n is None),
                'timeCells': cells,
                'resolverTimeCells': int(resolution.get('timeCells') or 0),
                'resolvedTimeCells': int(resolution.get('resolvedTimeCells') or 0),
                'unresolvedTimeCells': int(resolution.get('unresolvedTimeCells') or 0),
                'recordAccountingGap': int(resolution.get('recordAccountingGap') or 0),
                'accountingMatches': accounted == int(resolution.get('timeCells') or 0),
            }
            page_row['bands'][band] = row
            totals['bandsWithGrid'] += 1
            totals['columns'] += row['columns']
            totals['explicitColumns'] += row['explicitColumns']
            totals['anonymousColumns'] += row['anonymousColumns']
            totals['timeCells'] += row['timeCells']
            totals['resolverTimeCells'] += row['resolverTimeCells']
            totals['resolvedTimeCells'] += row['resolvedTimeCells']
            totals['unresolvedTimeCells'] += row['unresolvedTimeCells']
            if row['recordAccountingGap'] != 0 or not row['accountingMatches']:
                missing.append({'page': page_number, 'band': band, 'reason': 'semantic-accounting-gap', 'detail': row})
        pages.append(page_row)
        totals['pagesAudited'] += 1

    totals['expectedBands'] = totals['pagesAudited'] * 2
    return {
        'kind': 'keikyu-two-table-band-diagnosis',
        'splitPolicy': {
            'pageSplit': 'exact-height-midpoint',
            'upperAndLowerWordsDisjoint': True,
            'eachBandRequiresIndependentPrintedTrainNumberGrid': True,
            'identityPromotions': 0,
        },
        'totals': dict(totals),
        'missingOrInvalidBands': missing,
        'pages': pages,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if args.pdf:
        payload = diagnose(args.pdf)
    else:
        with tempfile.TemporaryDirectory(prefix='keikyu-band-diagnosis-') as td:
            pdf = Path(td) / 'schedule_all.pdf'
            download_official_pdf(pdf)
            payload = diagnose(pdf)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = {
        'output': str(args.output),
        **payload['totals'],
        'missingOrInvalidBands': len(payload['missingOrInvalidBands']),
        'identityPromotions': 0,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
