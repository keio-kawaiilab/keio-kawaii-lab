#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber
import requests

PDF_URL = 'https://www.seiburailway.jp/railway/reservedtrain/file/20260314_S-TRAIN_timetable.pdf'

# A published S-TRAIN column that contains both the Seibu-Chichibu side and a
# Fukutoshin-specific station proves one physical train spans the unique,
# officially verified route Seibu Chichibu -> Ikebukuro -> Seibu Yurakucho ->
# Fukutoshin. No time, train number, or destination matching across sources is
# used. The train name only labels a column already proven within one PDF.
SEIBU_CHICHIBU_MARKERS = {'西武秩父', '横瀬', '芦ヶ久保', '正丸', '西吾野'}
SEIBU_IKEBUKURO_MARKERS = {'飯能', '入間市', '所沢', '石神井公園'}
FUKUTOSHIN_MARKERS = {'池袋', '新宿三丁目', '渋谷'}
SOUTH_MARKERS = {'自由が丘', '横浜', 'みなとみらい', '元町・中華街'}


def clean(value: Any) -> str:
    return re.sub(r'\s+', '', str(value or '')).strip()


def normalized_time(value: Any) -> str:
    text = clean(value)
    m = re.search(r'(\d{1,2})[:：](\d{2})', text)
    return f'{int(m.group(1)):02d}:{m.group(2)}' if m else ''


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def download() -> bytes:
    r = requests.get(PDF_URL, timeout=(20, 90), headers={'User-Agent': 'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/8.0)'})
    r.raise_for_status()
    if not r.content.startswith(b'%PDF'):
        raise RuntimeError('S-TRAIN source is not a PDF')
    return r.content


def extract_tables(pdf_bytes: bytes) -> list[list[list[str | None]]]:
    out: list[list[list[str | None]]] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if len(pdf.pages) != 1:
            raise RuntimeError(f'Unexpected S-TRAIN PDF page count: {len(pdf.pages)}')
        page = pdf.pages[0]
        tables = page.extract_tables() or []
        for table in tables:
            if table:
                out.append(table)
    return out


def parse_columns(tables: list[list[list[str | None]]]) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    for table_index, table in enumerate(tables):
        if len(table) < 3:
            continue
        # Find a row containing one or more S-TRAIN column labels.
        header_index = -1
        header: list[str] = []
        for idx, raw_row in enumerate(table[:5]):
            row = [clean(x) for x in raw_row]
            if sum('S-TRAIN' in x.upper() for x in row) >= 1:
                header_index = idx
                header = row
                break
        if header_index < 0:
            continue

        station_col = None
        # The station-name column is the leftmost column that contains several
        # known station labels in subsequent rows.
        for col in range(max(len(r) for r in table)):
            vals = [clean(r[col]) if col < len(r) else '' for r in table[header_index + 1:]]
            known = sum(v in (SEIBU_CHICHIBU_MARKERS | SEIBU_IKEBUKURO_MARKERS | FUKUTOSHIN_MARKERS | SOUTH_MARKERS | {'豊洲','有楽町','飯田橋','保谷','小手指','西所沢','練馬'}) for v in vals)
            if known >= 3:
                station_col = col
                break
        if station_col is None:
            continue

        for col, label in enumerate(header):
            if 'S-TRAIN' not in label.upper():
                continue
            times: dict[str, str] = {}
            for raw_row in table[header_index + 1:]:
                station = clean(raw_row[station_col]) if station_col < len(raw_row) else ''
                if not station or col >= len(raw_row):
                    continue
                time = normalized_time(raw_row[col])
                if time:
                    times[station] = time
            if times:
                columns.append({'tableIndex': table_index, 'columnIndex': col, 'label': label, 'times': times})
    return columns


def build_report() -> dict[str, Any]:
    pdf_bytes = download()
    tables = extract_tables(pdf_bytes)
    columns = parse_columns(tables)
    evidence: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for col in columns:
        stations = set(col['times'])
        is_line13 = bool(stations & FUKUTOSHIN_MARKERS) and bool(stations & SOUTH_MARKERS)
        has_chichibu = bool(stations & SEIBU_CHICHIBU_MARKERS)
        has_ikebukuro = bool(stations & SEIBU_IKEBUKURO_MARKERS)
        if not is_line13:
            continue
        diagnostics.append({'label': col['label'], 'stations': list(col['times']), 'hasChichibu': has_chichibu, 'hasIkebukuro': has_ikebukuro})
        if not has_chichibu:
            continue
        # One current published printed column spans the Chichibu branch,
        # Ikebukuro-line branch, Fukutoshin and the south side. This proves the
        # same train traverses both internal Seibu boundaries in the unique
        # verified through-service family path.
        direction = 'chichibu-to-fukutoshin' if col['times'].get('西武秩父','') and list(col['times']).index('西武秩父') < min((list(col['times']).index(x) for x in FUKUTOSHIN_MARKERS if x in col['times']), default=999) else 'fukutoshin-to-chichibu'
        boundaries = [
            {
                'canonicalBoundaryId': 'seibu-ikebukuro-seibuchichibu-agano',
                'fromRailway': 'odpt.Railway:Seibu.SeibuChichibu' if direction == 'chichibu-to-fukutoshin' else 'odpt.Railway:Seibu.Ikebukuro',
                'toRailway': 'odpt.Railway:Seibu.Ikebukuro' if direction == 'chichibu-to-fukutoshin' else 'odpt.Railway:Seibu.SeibuChichibu',
                'boundaryStation': '吾野',
            },
            {
                'canonicalBoundaryId': 'seibuyurakucho-ikebukuro-nerima',
                'fromRailway': 'odpt.Railway:Seibu.Ikebukuro' if direction == 'chichibu-to-fukutoshin' else 'odpt.Railway:Seibu.SeibuYurakucho',
                'toRailway': 'odpt.Railway:Seibu.SeibuYurakucho' if direction == 'chichibu-to-fukutoshin' else 'odpt.Railway:Seibu.Ikebukuro',
                'boundaryStation': '練馬',
            },
        ]
        for boundary in boundaries:
            key = digest([PDF_URL, col['tableIndex'], col['columnIndex'], col['label'], boundary['canonicalBoundaryId'], direction, col['times']])
            evidence.append({
                'id': f'strain-official-column:{key}',
                'identityEvidence': 'official-same-printed-column-route-span',
                'status': 'verified',
                'corridor': 'line13',
                'service': 'S-TRAIN',
                'direction': direction,
                'sourceUrl': PDF_URL,
                'pdfPage': 1,
                'tableIndex': col['tableIndex'],
                'columnIndex': col['columnIndex'],
                'publishedColumnLabel': col['label'],
                'publishedTimes': col['times'],
                'publishedRouteMarkers': sorted(stations),
                **boundary,
                'matchPolicy': {
                    'sameOfficialPrintedColumnRequired': True,
                    'publishedFukutoshinSpecificStationRequired': True,
                    'publishedSeibuChichibuStationRequired': True,
                    'verifiedUniqueFamilyPathRequired': True,
                    'timeProximityAloneMayEstablishIdentity': False,
                    'trainNumberAloneMayEstablishIdentity': False,
                    'destinationAloneMayEstablishIdentity': False,
                },
            })

    counts: dict[str, dict[str, int]] = {}
    for row in evidence:
        bid = row['canonicalBoundaryId']
        counts.setdefault(bid, {'chichibu-to-fukutoshin': 0, 'fukutoshin-to-chichibu': 0})
        counts[bid][row['direction']] += 1

    return {
        'version': 1,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'source': 'Seibu Railway official S-TRAIN timetable PDF',
        'sourceUrl': PDF_URL,
        'sourceSha256': hashlib.sha256(pdf_bytes).hexdigest(),
        'identityPolicy': {
            'sameOfficialPrintedColumnMayEstablishIdentity': True,
            'verifiedUniqueFamilyPathMayProjectInternalBoundaries': True,
            'timeProximityMayEstablishIdentity': False,
            'trainNumberAloneMayEstablishIdentity': False,
            'destinationAloneMayEstablishIdentity': False,
        },
        'summary': {
            'pdfBytes': len(pdf_bytes),
            'tablesExtracted': len(tables),
            'columnsParsed': len(columns),
            'evidenceRecords': len(evidence),
            'boundaryDirectionCounts': counts,
        },
        'evidence': evidence,
        'diagnostics': diagnostics,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default='data/transit/line8-line13/seibu-strain-line13-columns.json')
    args = ap.parse_args()
    report = build_report()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('SUMMARY', json.dumps(report['summary'], ensure_ascii=False, indent=2))
    for row in report['evidence'][:12]:
        print('EVIDENCE', json.dumps(row, ensure_ascii=False))
    counts = report['summary']['boundaryDirectionCounts']
    for bid in ('seibu-ikebukuro-seibuchichibu-agano', 'seibuyurakucho-ikebukuro-nerima'):
        c = counts.get(bid) or {}
        if not (int(c.get('chichibu-to-fukutoshin', 0)) > 0 and int(c.get('fukutoshin-to-chichibu', 0)) > 0):
            raise RuntimeError(f'Bidirectional current S-TRAIN exact evidence missing for {bid}: {c}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
