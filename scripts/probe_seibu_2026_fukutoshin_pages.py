#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

BASE = 'https://www.seiburailway.jp/railways/2026digitaltimetable/'
INDEX_URL = BASE + 'index.html'
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
        headers={'User-Agent': 'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/4.1)'},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.content


def decode(raw: bytes) -> str:
    for encoding in ('utf-8', 'cp932', 'shift_jis'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


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


def attr_values(text: str, name: str) -> list[str]:
    pattern = re.compile(rf'\b{re.escape(name)}\s*=\s*["\']([^"\']*)["\']', re.I)
    out: list[str] = []
    for value in pattern.findall(text):
        value = html.unescape(value.strip())
        if value not in out:
            out.append(value)
    return out


def viewer_data_bases(index_raw: bytes) -> tuple[list[str], dict[str, Any]]:
    text = decode(index_raw)
    bookpaths = attr_values(text, 'bookpath')
    imagepaths = attr_values(text, 'imagepath')
    candidates: list[str] = []
    # FLIPPER3 itself uses imagepath first, otherwise bookpath. Preserve exactly
    # that precedence, while retaining all literal values for diagnostics.
    for value in [*imagepaths, *bookpaths]:
        absolute = urljoin(INDEX_URL, value or './')
        if not absolute.endswith('/'):
            absolute += '/'
        if absolute not in candidates:
            candidates.append(absolute)
    if not candidates:
        candidates.append(BASE)

    fragments: list[str] = []
    for needle in ('imagepath', 'bookpath', 'flipper-app'):
        start = 0
        while len(fragments) < 12:
            pos = text.lower().find(needle.lower(), start)
            if pos < 0:
                break
            fragments.append(re.sub(r'\s+', ' ', text[max(0, pos - 180):pos + 420]))
            start = pos + len(needle)
    return candidates, {
        'bookpathAttributes': bookpaths,
        'imagepathAttributes': imagepaths,
        'derivedDataBases': candidates,
        'configFragments': fragments,
    }


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
        if len(sample) < 80:
            sample.append({'tag': name, 'attrs': dict(elem.attrib), 'text': text[:120]})
    return local_name(root.tag), dict(tags), sample, norm(''.join(pieces))


def probe_page(page: int, folder: str, data_bases: list[str]) -> dict[str, Any]:
    candidates: list[str] = []
    for data_base in data_bases:
        for token in (folder, str(page)):
            url = urljoin(data_base, f'page{token}/textpoint.xml')
            if url not in candidates:
                candidates.append(url)
    errors: list[str] = []
    shell_urls: list[str] = []
    for url in candidates:
        try:
            content = get(url)
            root_tag, tag_counts, element_sample, flat = xml_diagnostics(content)
            has_payload = any(tag not in ('TET', 'Page') and count > 0 for tag, count in tag_counts.items())
            if not has_payload:
                shell_urls.append(url)
                continue
            hits = [keyword for keyword in KEYWORDS if norm(keyword) in flat]
            return {
                'page': page,
                'folder': folder,
                'reachable': True,
                'hasGlyphPayload': True,
                'url': url,
                'bytes': len(content),
                'rootTag': root_tag,
                'tagCounts': tag_counts,
                'elementSample': element_sample,
                'keywordHits': hits,
                'flattenedLength': len(flat),
                'flattenedSample': flat[:1200],
                'shellUrls': shell_urls,
            }
        except Exception as exc:
            errors.append(f'{url}: {type(exc).__name__}: {exc}')
    return {
        'page': page,
        'folder': folder,
        'reachable': bool(shell_urls),
        'hasGlyphPayload': False,
        'errors': errors,
        'shellUrls': shell_urls,
        'keywordHits': [],
    }


def build_report() -> dict[str, Any]:
    index_raw = get(INDEX_URL)
    data_bases, viewer_config = viewer_data_bases(index_raw)
    publish_date, folders = parse_book(get(BOOK_XML))
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(probe_page, page, folder, data_bases): page
            for page, folder in enumerate(folders, start=1)
        }
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: int(row.get('page') or 0))
    payload_rows = [row for row in rows if row.get('hasGlyphPayload')]
    matched = [row for row in payload_rows if row.get('keywordHits')]
    counts = Counter(hit for row in matched for hit in row.get('keywordHits') or [])
    schema_samples = [
        {
            'page': row.get('page'), 'folder': row.get('folder'), 'url': row.get('url'),
            'rootTag': row.get('rootTag'), 'tagCounts': row.get('tagCounts'),
            'elementSample': row.get('elementSample'), 'flattenedSample': row.get('flattenedSample'),
        }
        for row in payload_rows[:3]
    ]
    return {
        'version': 4,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'source': 'Seibu Railway official Digital Seibu Timetable 2026',
        'viewerUrl': INDEX_URL,
        'bookIndexSource': BOOK_XML,
        'bookPublishDate': publish_date,
        'viewerConfig': viewer_config,
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
            'glyphPayloadPages': len(payload_rows),
            'matchedPages': len(matched),
            'keywordCounts': dict(counts),
        },
        'schemaSamples': schema_samples,
        'matchedPages': matched,
        'unresolvedPages': [row for row in rows if not row.get('hasGlyphPayload')],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default='data/transit/fukutoshin/seibu-2026-fukutoshin-page-probe.json')
    args = ap.parse_args()
    report = build_report()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('VIEWER_CONFIG', json.dumps(report.get('viewerConfig') or {}, ensure_ascii=False))
    print('SUMMARY', json.dumps(report['summary'], ensure_ascii=False, indent=2))
    print('SCHEMA_SAMPLES', json.dumps(report.get('schemaSamples') or [], ensure_ascii=False))
    if int(report['summary']['glyphPayloadPages']) == 0:
        raise RuntimeError('No glyph-bearing Seibu textpoint page was found from the viewer-declared data paths')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
