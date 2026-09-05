#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE = 'https://www.seiburailway.jp/railways/2026digitaltimetable/'
BOOK_XML = BASE + 'book.xml'
KEYWORDS = (
    '小竹向原', '新桜台', '練馬', '池袋', '西武有楽町線', '副都心線',
    '元町・中華街', '横浜', '渋谷', '新木場', '和光市',
)


def norm(value: Any) -> str:
    return re.sub(r'[\s\u3000]+', '', unicodedata.normalize('NFKC', str(value or '')))


def local_name(tag: str) -> str:
    return str(tag).split('}', 1)[-1]


def get(url: str, *, timeout: tuple[int, int] = (20, 60)) -> bytes:
    response = requests.get(
        url,
        headers={'User-Agent': 'keio-kawaiilab-transit-evidence/4.0'},
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
    if total < 200 or len(folders) < 200:
        raise RuntimeError(f'unexpected Seibu book structure: total={total}, folders={len(folders)}')
    if total != len(folders):
        raise RuntimeError(f'page/folder mismatch: total={total}, folders={len(folders)}')
    return publish_date, folders


def xml_diagnostics(content: bytes) -> tuple[str, dict[str, int], list[dict[str, Any]], str]:
    root = ET.fromstring(content)
    tags: Counter[str] = Counter()
    sample: list[dict[str, Any]] = []
    pieces: list[str] = []
    for elem in root.iter():
        name = local_name(elem.tag)
        tags[name] += 1
        text = (elem.text or '').strip()
        if text:
            pieces.append(text)
        for value in elem.attrib.values():
            if value and str(value).strip():
                pieces.append(str(value).strip())
        if len(sample) < 40:
            sample.append({
                'tag': name,
                'attrs': dict(elem.attrib),
                'text': text[:120],
            })
    return local_name(root.tag), dict(tags), sample, norm(''.join(pieces))


def probe_page(page: int, folder: str) -> dict[str, Any]:
    candidates = [
        BASE + f'page{folder}/textpoint.xml',
        BASE + f'page{page}/textpoint.xml',
    ]
    errors: list[str] = []
    for url in candidates:
        try:
            content = get(url)
            root_tag, tag_counts, element_sample, flat = xml_diagnostics(content)
            hits = [keyword for keyword in KEYWORDS if norm(keyword) in flat]
            return {
                'page': page,
                'folder': folder,
                'reachable': True,
                'url': url,
                'bytes': len(content),
                'rootTag': root_tag,
                'tagCounts': tag_counts,
                'elementSample': element_sample,
                'keywordHits': hits,
                'flattenedLength': len(flat),
                'flattenedSample': flat[:800],
            }
        except Exception as exc:
            errors.append(f'{url}: {type(exc).__name__}: {exc}')
    return {
        'page': page,
        'folder': folder,
        'reachable': False,
        'errors': errors,
        'keywordHits': [],
    }


def build_report() -> dict[str, Any]:
    book = get(BOOK_XML)
    publish_date, folders = parse_book(book)
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(probe_page, page, folder): page
            for page, folder in enumerate(folders, start=1)
        }
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: int(row.get('page') or 0))
    matched = [row for row in rows if row.get('keywordHits')]
    counts = Counter(hit for row in matched for hit in row.get('keywordHits') or [])
    schema_samples = [
        {
            'page': row.get('page'),
            'folder': row.get('folder'),
            'url': row.get('url'),
            'rootTag': row.get('rootTag'),
            'tagCounts': row.get('tagCounts'),
            'elementSample': row.get('elementSample'),
            'flattenedSample': row.get('flattenedSample'),
        }
        for row in rows[:3]
        if row.get('reachable')
    ]
    return {
        'version': 2,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'source': 'Seibu Railway official Digital Seibu Timetable 2026',
        'sourceBase': BASE,
        'bookPublishDate': publish_date,
        'identityPolicy': {
            'pageDiscoveryMayEstablishTrainIdentity': False,
            'glyphStructureMayEstablishTrainIdentity': False,
            'keywordPresenceMayEstablishTrainIdentity': False,
            'singlePublishedTrainColumnRequired': True,
            'timeProximityMayEstablishTrainIdentity': False,
            'trainNumberAloneMayEstablishTrainIdentity': False,
            'destinationAloneMayEstablishTrainIdentity': False,
        },
        'summary': {
            'pages': len(rows),
            'reachableTextpointPages': sum(bool(row.get('reachable')) for row in rows),
            'matchedPages': len(matched),
            'keywordCounts': dict(counts),
        },
        'schemaSamples': schema_samples,
        'matchedPages': matched,
        'unreachablePages': [row for row in rows if not row.get('reachable')],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default='data/transit/fukutoshin/seibu-2026-fukutoshin-page-probe.json')
    args = ap.parse_args()
    report = build_report()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))
    print('SCHEMA_SAMPLES', json.dumps(report.get('schemaSamples') or [], ensure_ascii=False))
    if int(report['summary']['reachableTextpointPages']) == 0:
        raise RuntimeError('No official Seibu textpoint pages were reachable')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
