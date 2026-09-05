#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz
import requests

BASE = 'https://www.seiburailway.jp/railways/2026digitaltimetable/'
BOOK_XML = BASE + 'book.xml'
PDF_BASE = BASE + 'pdf/'
KEYWORDS = (
    '小竹向原', '新桜台', '練馬', '池袋', '西武有楽町線', '副都心線',
    '元町・中華街', '横浜', '渋谷', '新木場', '和光市',
)


def norm(value: Any) -> str:
    return re.sub(r'[\s\u3000]+', '', unicodedata.normalize('NFKC', str(value or '')))


def local_name(tag: str) -> str:
    return str(tag).split('}', 1)[-1]


def get(url: str, *, timeout: tuple[int, int] = (20, 90)) -> bytes:
    response = requests.get(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/5.0)',
            'Accept': 'application/pdf,application/xml,text/xml,*/*;q=0.8',
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.content


def parse_book(content: bytes) -> tuple[str, list[str]]:
    root = ET.fromstring(content)
    publish_date = ''
    data_text = ''
    total = 0
    for elem in root.iter():
        name = local_name(elem.tag)
        text = (elem.text or '').strip()
        if name == 'publishDate' and text:
            publish_date = text
        elif name == 'total' and text.isdigit():
            total = max(total, int(text))
        elif name == 'data' and ',' in text and len(text) > len(data_text):
            data_text = text
    folders = [value.strip() for value in data_text.split(',') if value.strip()]
    if total < 200 or len(folders) < 200 or total != len(folders):
        raise RuntimeError(f'unexpected Seibu book structure: total={total}, folders={len(folders)}')
    return publish_date, folders


def pdf_text(raw: bytes) -> tuple[str, int, list[dict[str, Any]]]:
    if not raw.startswith(b'%PDF'):
        raise RuntimeError('response is not a PDF')
    doc = fitz.open(stream=io.BytesIO(raw), filetype='pdf')
    pieces: list[str] = []
    word_count = 0
    word_sample: list[dict[str, Any]] = []
    try:
        for pdf_page in doc:
            text = pdf_page.get_text('text') or ''
            pieces.append(text)
            words = pdf_page.get_text('words') or []
            word_count += len(words)
            if len(word_sample) < 80:
                for word in words[: 80 - len(word_sample)]:
                    x0, y0, x1, y1, value = word[:5]
                    word_sample.append({
                        'text': str(value),
                        'x0': round(float(x0), 2),
                        'y0': round(float(y0), 2),
                        'x1': round(float(x1), 2),
                        'y1': round(float(y1), 2),
                    })
    finally:
        doc.close()
    return ''.join(pieces), word_count, word_sample


def probe_page(page: int, folder: str) -> dict[str, Any]:
    url = PDF_BASE + f'{page}.pdf'
    try:
        raw = get(url)
        text, word_count, word_sample = pdf_text(raw)
        flat = norm(text)
        hits = [keyword for keyword in KEYWORDS if norm(keyword) in flat]
        return {
            'page': page,
            'folder': folder,
            'reachable': True,
            'textBearing': bool(flat),
            'url': url,
            'bytes': len(raw),
            'wordCount': word_count,
            'keywordHits': hits,
            'textSample': re.sub(r'\s+', ' ', text).strip()[:1600],
            'wordSample': word_sample if hits else [],
        }
    except Exception as exc:
        return {
            'page': page,
            'folder': folder,
            'reachable': False,
            'textBearing': False,
            'url': url,
            'keywordHits': [],
            'error': f'{type(exc).__name__}: {exc}',
        }


def build_report() -> dict[str, Any]:
    publish_date, folders = parse_book(get(BOOK_XML))
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {
            pool.submit(probe_page, page, folder): page
            for page, folder in enumerate(folders, start=1)
        }
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: int(row.get('page') or 0))

    text_rows = [row for row in rows if row.get('textBearing')]
    matched = [row for row in text_rows if row.get('keywordHits')]
    counts = Counter(hit for row in matched for hit in row.get('keywordHits') or [])
    return {
        'version': 5,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'source': 'Seibu Railway official Digital Seibu Timetable 2026 per-page PDFs',
        'bookIndexSource': BOOK_XML,
        'pdfSourceTemplate': PDF_BASE + '{page}.pdf',
        'bookPublishDate': publish_date,
        'identityPolicy': {
            'pdfPageDiscoveryMayEstablishTrainIdentity': False,
            'keywordPresenceMayEstablishTrainIdentity': False,
            'singlePublishedTrainColumnRequired': True,
            'timeProximityMayEstablishTrainIdentity': False,
            'trainNumberAloneMayEstablishTrainIdentity': False,
            'destinationAloneMayEstablishTrainIdentity': False,
        },
        'summary': {
            'pages': len(rows),
            'reachablePdfPages': sum(bool(row.get('reachable')) for row in rows),
            'textBearingPdfPages': len(text_rows),
            'matchedPages': len(matched),
            'keywordCounts': dict(counts),
        },
        'matchedPages': matched,
        'unreachablePages': [row for row in rows if not row.get('reachable')],
        'nonTextPages': [
            {'page': row.get('page'), 'folder': row.get('folder'), 'url': row.get('url')}
            for row in rows if row.get('reachable') and not row.get('textBearing')
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default='data/transit/fukutoshin/seibu-2026-fukutoshin-page-probe.json')
    args = ap.parse_args()
    report = build_report()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('SUMMARY', json.dumps(report['summary'], ensure_ascii=False, indent=2))
    for row in report.get('matchedPages') or []:
        print('MATCH', json.dumps({
            'page': row.get('page'),
            'url': row.get('url'),
            'keywordHits': row.get('keywordHits'),
            'wordCount': row.get('wordCount'),
            'textSample': row.get('textSample'),
        }, ensure_ascii=False))
    if int(report['summary']['reachablePdfPages']) == 0:
        raise RuntimeError('No official Seibu per-page PDF was reachable')
    if int(report['summary']['textBearingPdfPages']) == 0:
        raise RuntimeError('Official Seibu per-page PDFs have no extractable text layer')
    if int(report['summary']['matchedPages']) == 0:
        raise RuntimeError('No Line 13 corridor keyword was found in official Seibu PDFs')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
