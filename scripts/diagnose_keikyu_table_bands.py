#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from audit_keikyu_official_columns import FIRST_POSSIBLE_TIMETABLE_PAGE, page_scope_reason
from audit_keikyu_station_time_resolution import resolve_page
from keikyu_connected_station_catalog import station_titles
from keikyu_official_pdf import (
    PRINTED_HEADER_Y_LIMIT,
    TRAIN_NUMBER_RE,
    Word,
    _label_span,
    bbox_words,
    cluster_by_y,
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


def header_gate(y: float, xs: list[float]) -> tuple[str, float | None]:
    if y > PRINTED_HEADER_Y_LIMIT:
        return 'below-current-header-y-limit', None
    if len(xs) < 3:
        return 'fewer-than-three-explicit-train-numbers', None
    adjacent = [b - a for a, b in zip(xs, xs[1:]) if 10.0 <= b - a <= 22.0]
    if not adjacent:
        return 'no-valid-10-to-22pt-adjacent-pitch', None
    pitch = float(statistics.median(adjacent))
    if not (10.0 <= pitch <= 22.0):
        return 'median-pitch-out-of-range', pitch
    return 'passes-header-preconditions', pitch


def train_number_rows(words: list[Word]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in cluster_by_y(words):
        span = _label_span(row, '列車番号')
        if span is None:
            continue
        label_right = span[1]
        tokens = [w for w in row if w.x > label_right and TRAIN_NUMBER_RE.fullmatch(w.text)]
        xs = sorted(w.x for w in tokens)
        candidate_gaps = [round(b - a, 3) for a, b in zip(xs, xs[1:]) if 8 <= b - a <= 25]
        exact_gaps = [round(b - a, 3) for a, b in zip(xs, xs[1:]) if 10 <= b - a <= 22]
        y = float(statistics.median(w.y for w in row))
        gate, pitch = header_gate(y, xs)
        out.append({
            'y': round(y, 3),
            'labelRight': round(float(label_right), 3),
            'explicitTokenCount': len(tokens),
            'tokens': [w.text for w in tokens[:16]],
            'candidateGaps': candidate_gaps[:24],
            'exactPitchGaps': exact_gaps[:24],
            'inferredPitch': round(pitch, 3) if pitch is not None else None,
            'gate': gate,
        })
    return out


def diagnose(pdf_path: Path) -> dict[str, Any]:
    titles = station_titles()
    total_pages = page_count(pdf_path)
    pages: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    missing: list[dict[str, Any]] = []
    lower_gate_counts: Counter[str] = Counter()
    lower_header_samples: list[dict[str, Any]] = []

    for page_number in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total_pages + 1):
        _width, height, words = bbox_words(pdf_path, page_number)
        page_text = compact(''.join(w.text for w in words))
        excluded = page_scope_reason(page_text)
        if excluded:
            continue
        page_row: dict[str, Any] = {'page': page_number, 'height': height, 'bands': {}}
        for band in BANDS:
            bw = band_words(words, height, band)
            headers = train_number_rows(bw)
            totals[f'{band}TrainNumberRows'] += len(headers)
            if band == 'lower':
                for header in headers:
                    lower_gate_counts[str(header['gate'])] += 1
                    if len(lower_header_samples) < 30:
                        lower_header_samples.append({'page': page_number, **header})
            grid = detect_train_column_grid(bw)
            if grid is None:
                page_row['bands'][band] = {'grid': False, 'trainNumberRows': headers}
                missing.append({
                    'page': page_number,
                    'band': band,
                    'reason': 'no-grid',
                    'trainNumberRows': headers,
                })
                totals[f'{band}BandsWithoutGrid'] += 1
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
                'trainNumberRows': headers,
            }
            page_row['bands'][band] = row
            totals['bandsWithGrid'] += 1
            totals[f'{band}BandsWithGrid'] += 1
            totals[f'{band}Columns'] += row['columns']
            totals[f'{band}TimeCells'] += row['timeCells']
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
    sample_missing = [row for row in missing if row.get('reason') == 'no-grid'][:12]
    return {
        'kind': 'keikyu-two-table-band-diagnosis',
        'splitPolicy': {
            'pageSplit': 'exact-height-midpoint',
            'upperAndLowerWordsDisjoint': True,
            'eachBandRequiresIndependentPrintedTrainNumberGrid': True,
            'identityPromotions': 0,
        },
        'totals': dict(totals),
        'lowerHeaderGateCounts': dict(lower_gate_counts.most_common()),
        'lowerHeaderSamples': lower_header_samples,
        'sampleMissingHeaders': sample_missing,
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
        'lowerHeaderGateCounts': payload['lowerHeaderGateCounts'],
        'lowerHeaderSamples': payload['lowerHeaderSamples'],
        'missingOrInvalidBands': len(payload['missingOrInvalidBands']),
        'identityPromotions': 0,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
