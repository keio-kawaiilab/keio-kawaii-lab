#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

from audit_keikyu_official_columns import FIRST_POSSIBLE_TIMETABLE_PAGE, page_scope_reason
from keikyu_official_pdf import bbox_words, cluster_by_y, compact, detect_train_column_sections, page_count


def row_y(row) -> float:
    return float(statistics.median(word.y for word in row))


def marker_kind(text: str) -> str | None:
    value = compact(text)
    if '土休日用' in value or '土休日' in value:
        return 'holiday'
    if '平日用' in value or '平日' in value:
        return 'weekday'
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()

    counts = Counter()
    pages = []
    total = page_count(args.pdf)
    for page_number in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total + 1):
        _width, _height, words = bbox_words(args.pdf, page_number)
        page_text = compact(''.join(word.text for word in words))
        if page_scope_reason(page_text):
            continue
        sections = detect_train_column_sections(words)
        if not sections:
            continue
        markers = []
        for row in cluster_by_y(words):
            text = ''.join(word.text for word in row)
            kind = marker_kind(text)
            if kind:
                markers.append({'kind': kind, 'y': row_y(row), 'text': compact(text)})
        page_kinds = sorted({item['kind'] for item in markers})
        section_rows = []
        for section in sections:
            preceding = [item for item in markers if item['y'] <= section.grid.header_y + 1.0]
            nearest = max(preceding, key=lambda item: item['y']) if preceding else None
            if nearest and section.grid.header_y - nearest['y'] <= 180.0:
                calendar = nearest['kind']
                method = 'nearest-preceding-printed-label'
            elif len(page_kinds) == 1:
                calendar = page_kinds[0]
                method = 'single-printed-label-on-page'
            else:
                calendar = 'unknown'
                method = 'unresolved'
            counts[calendar] += 1
            counts[f'method:{method}'] += 1
            section_rows.append({
                'section': section.section_index,
                'headerOrdinal': section.header_ordinal,
                'headerY': round(section.grid.header_y, 2),
                'calendar': calendar,
                'method': method,
                'nearestMarker': nearest,
            })
        pages.append({
            'page': page_number,
            'pageMarkerKinds': page_kinds,
            'markers': markers,
            'sections': section_rows,
        })

    payload = {'counts': dict(counts), 'pages': pages}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'counts': dict(counts), 'pages': len(pages)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
