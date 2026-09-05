#!/usr/bin/env python3
from __future__ import annotations

import io
import json

import pdfplumber

import keikyu_official_train_evidence as parser

KEYWORDS = ('始発', '終着', '品川', '泉岳寺', '列車番号')


def compact_cells(words, y):
    return [
        {'x': round(float(row['x']), 2), 'text': str(row['text'])}
        for row in parser.cells(words, y)
    ]


def inspect_page(content: bytes, page_number: int = 1) -> None:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        page = pdf.pages[page_number - 1]
        words = page.extract_words(
            x_tolerance=1,
            y_tolerance=1,
            keep_blank_chars=False,
            use_text_flow=False,
        )
        rows = parser.rows(words, 4.0)
        print('PAGE', page_number, 'ROWS', len(rows))
        anchors = [row for row in rows if any(key in parser.norm(row.get('text')) for key in KEYWORDS)]
        for anchor in anchors:
            ay = float(anchor['y'])
            print('ANCHOR', json.dumps({'y': round(ay, 2), 'text': anchor['text']}, ensure_ascii=False))
            nearby = [row for row in rows if abs(float(row['y']) - ay) <= 24]
            for row in nearby:
                payload = {
                    'dy': round(float(row['y']) - ay, 2),
                    'y': round(float(row['y']), 2),
                    'text': row['text'],
                    'cells': compact_cells(words, float(row['y'])),
                }
                print('ROW', json.dumps(payload, ensure_ascii=False))


def main() -> int:
    content = parser.fetch_pdf(parser.DEFAULT_WEEKDAY_URL)
    inspect_page(content, 1)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
