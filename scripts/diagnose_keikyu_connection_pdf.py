#!/usr/bin/env python3
import io
import json
import pdfplumber
import keikyu_official_train_evidence as parser

content = parser.fetch_pdf(parser.DEFAULT_WEEKDAY_URL)
with pdfplumber.open(io.BytesIO(content)) as pdf:
    page = pdf.pages[0]
    words = page.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False, use_text_flow=False)
    for row in parser.rows(words, 4.0):
        if '泉岳寺' not in row['text'] and '列車番号' not in row['text']:
            continue
        y = float(row['y'])
        raw = []
        for word in words:
            if abs(parser.cy(word) - y) <= 4.5:
                raw.append({
                    'text': parser.norm(word.get('text')),
                    'x0': round(float(word.get('x0', 0)), 2),
                    'x1': round(float(word.get('x1', 0)), 2),
                    'y': round(parser.cy(word), 2),
                })
        print('ROW', json.dumps(row, ensure_ascii=False))
        print('CELLS', json.dumps(parser.cells(words, y, 4.5), ensure_ascii=False))
        print('RAW', json.dumps(raw, ensure_ascii=False))
