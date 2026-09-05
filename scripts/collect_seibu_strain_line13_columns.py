#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

PDF_URL = 'https://www.seiburailway.jp/railway/reservedtrain/file/20260314_S-TRAIN_timetable.pdf'
REVIEWED_SHA256 = 'd04ba82847797557e5ca22e5bc3a7f70eff18204f02a2fc017eaa3a131d8c66d'
REVIEWED_BYTES = 252008
REVIEWED_REVISION = '2026-03-14 partial change'

# The official PDF is an image/outline PDF with no machine-readable text layer.
# These two weekend columns were reviewed directly from the official one-page
# timetable. Automation may reuse the reviewed transcription only while the
# downloaded official PDF is byte-for-byte identical to the reviewed snapshot.
# If Seibu changes the file, generation fails closed and requires a fresh review.
REVIEWED_COLUMNS: list[dict[str, Any]] = [
    {
        'label': 'S-TRAIN 4',
        'direction': 'chichibu-to-fukutoshin',
        'publishedTimes': {
            '西武秩父': '17:07', '飯能': '17:50', '入間市': '17:58',
            '所沢': '18:12', '石神井公園': '18:27', '池袋': '18:42',
            '新宿三丁目': '18:50', '渋谷': '18:56', '自由が丘': '19:09',
            '横浜': '19:31', 'みなとみらい': '19:35', '元町・中華街': '19:40',
        },
    },
    {
        'label': 'S-TRAIN 1',
        'direction': 'fukutoshin-to-chichibu',
        'publishedTimes': {
            '元町・中華街': '07:46', 'みなとみらい': '07:50', '横浜': '07:54',
            '自由が丘': '08:17', '渋谷': '08:27', '新宿三丁目': '08:33',
            '池袋': '08:39', '石神井公園': '08:54', '所沢': '09:06',
            '入間市': '09:17', '飯能': '09:25', '西武秩父': '10:03',
        },
    },
]


def digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:24]


def download_reviewed_source() -> bytes:
    response = requests.get(
        PDF_URL,
        timeout=(20, 90),
        headers={'User-Agent': 'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/10.0)'},
    )
    response.raise_for_status()
    body = response.content
    if not body.startswith(b'%PDF'):
        raise RuntimeError('S-TRAIN source is no longer a PDF')
    sha = hashlib.sha256(body).hexdigest()
    if sha != REVIEWED_SHA256 or len(body) != REVIEWED_BYTES:
        raise RuntimeError(
            'Official S-TRAIN PDF changed since manual review; refusing to reuse '
            f'reviewed columns (sha={sha}, bytes={len(body)})'
        )
    return body


def boundaries_for(direction: str) -> list[dict[str, str]]:
    if direction == 'chichibu-to-fukutoshin':
        return [
            {'canonicalBoundaryId': 'seibu-ikebukuro-seibuchichibu-agano', 'fromRailway': 'odpt.Railway:Seibu.SeibuChichibu', 'toRailway': 'odpt.Railway:Seibu.Ikebukuro', 'boundaryStation': '吾野'},
            {'canonicalBoundaryId': 'seibuyurakucho-ikebukuro-nerima', 'fromRailway': 'odpt.Railway:Seibu.Ikebukuro', 'toRailway': 'odpt.Railway:Seibu.SeibuYurakucho', 'boundaryStation': '練馬'},
            {'canonicalBoundaryId': 'fukutoshin-seibuyurakucho-kotakemukaihara', 'fromRailway': 'odpt.Railway:Seibu.SeibuYurakucho', 'toRailway': 'odpt.Railway:TokyoMetro.Fukutoshin', 'boundaryStation': '小竹向原'},
            {'canonicalBoundaryId': 'toyoko-fukutoshin-shibuya', 'fromRailway': 'odpt.Railway:TokyoMetro.Fukutoshin', 'toRailway': 'odpt.Railway:Tokyu.Toyoko', 'boundaryStation': '渋谷'},
            {'canonicalBoundaryId': 'minatomirai-toyoko-yokohama', 'fromRailway': 'odpt.Railway:Tokyu.Toyoko', 'toRailway': 'manual.Railway:YokohamaMinatomirai.Minatomirai', 'boundaryStation': '横浜'},
        ]
    if direction == 'fukutoshin-to-chichibu':
        return [
            {'canonicalBoundaryId': 'minatomirai-toyoko-yokohama', 'fromRailway': 'manual.Railway:YokohamaMinatomirai.Minatomirai', 'toRailway': 'odpt.Railway:Tokyu.Toyoko', 'boundaryStation': '横浜'},
            {'canonicalBoundaryId': 'toyoko-fukutoshin-shibuya', 'fromRailway': 'odpt.Railway:Tokyu.Toyoko', 'toRailway': 'odpt.Railway:TokyoMetro.Fukutoshin', 'boundaryStation': '渋谷'},
            {'canonicalBoundaryId': 'fukutoshin-seibuyurakucho-kotakemukaihara', 'fromRailway': 'odpt.Railway:TokyoMetro.Fukutoshin', 'toRailway': 'odpt.Railway:Seibu.SeibuYurakucho', 'boundaryStation': '小竹向原'},
            {'canonicalBoundaryId': 'seibuyurakucho-ikebukuro-nerima', 'fromRailway': 'odpt.Railway:Seibu.SeibuYurakucho', 'toRailway': 'odpt.Railway:Seibu.Ikebukuro', 'boundaryStation': '練馬'},
            {'canonicalBoundaryId': 'seibu-ikebukuro-seibuchichibu-agano', 'fromRailway': 'odpt.Railway:Seibu.Ikebukuro', 'toRailway': 'odpt.Railway:Seibu.SeibuChichibu', 'boundaryStation': '吾野'},
        ]
    raise RuntimeError(f'Unexpected reviewed direction: {direction}')


def build_report() -> dict[str, Any]:
    pdf_bytes = download_reviewed_source()
    evidence: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}

    for column_index, column in enumerate(REVIEWED_COLUMNS):
        direction = str(column['direction'])
        times = dict(column['publishedTimes'])
        required = {'西武秩父', '飯能', '所沢', '石神井公園', '池袋', '新宿三丁目', '渋谷', '横浜', '元町・中華街'}
        if not required.issubset(times):
            raise RuntimeError(f'Reviewed S-TRAIN column is incomplete: {column["label"]}')
        for boundary in boundaries_for(direction):
            bid = boundary['canonicalBoundaryId']
            key = digest([REVIEWED_SHA256, column['label'], direction, bid, times])
            evidence.append({
                'id': f'strain-official-column:{key}',
                'identityEvidence': 'official-same-printed-column-route-span',
                'status': 'verified',
                'corridor': 'line13',
                'service': 'S-TRAIN',
                'direction': direction,
                'sourceUrl': PDF_URL,
                'sourceSha256': REVIEWED_SHA256,
                'sourceRevision': REVIEWED_REVISION,
                'reviewMode': 'manual-visual-review-hash-guarded',
                'pdfPage': 1,
                'columnIndex': column_index,
                'publishedColumnLabel': column['label'],
                'publishedTimes': times,
                'publishedRouteMarkers': list(times),
                **boundary,
                'matchPolicy': {
                    'sameOfficialPrintedColumnRequired': True,
                    'reviewedSourceHashRequired': True,
                    'publishedFukutoshinSpecificStationRequired': True,
                    'publishedSeibuChichibuStationRequired': True,
                    'verifiedUniqueFamilyPathRequired': True,
                    'timeProximityAloneMayEstablishIdentity': False,
                    'trainNumberAloneMayEstablishIdentity': False,
                    'destinationAloneMayEstablishIdentity': False,
                },
            })
            counts.setdefault(bid, {'chichibu-to-fukutoshin': 0, 'fukutoshin-to-chichibu': 0})
            counts[bid][direction] += 1

    required_boundaries = {
        'seibu-ikebukuro-seibuchichibu-agano',
        'seibuyurakucho-ikebukuro-nerima',
        'fukutoshin-seibuyurakucho-kotakemukaihara',
        'toyoko-fukutoshin-shibuya',
        'minatomirai-toyoko-yokohama',
    }
    for bid in required_boundaries:
        c = counts.get(bid) or {}
        if c.get('chichibu-to-fukutoshin', 0) != 1 or c.get('fukutoshin-to-chichibu', 0) != 1:
            raise RuntimeError(f'Reviewed S-TRAIN evidence is not bidirectional for {bid}: {c}')

    return {
        'version': 2,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'source': 'Seibu Railway official S-TRAIN timetable PDF',
        'sourceUrl': PDF_URL,
        'sourceSha256': hashlib.sha256(pdf_bytes).hexdigest(),
        'sourceBytes': len(pdf_bytes),
        'sourceRevision': REVIEWED_REVISION,
        'identityPolicy': {
            'sameOfficialPrintedColumnMayEstablishIdentity': True,
            'reviewedSourceHashRequired': True,
            'verifiedUniqueFamilyPathMayProjectInternalBoundaries': True,
            'timeProximityMayEstablishIdentity': False,
            'trainNumberAloneMayEstablishIdentity': False,
            'destinationAloneMayEstablishIdentity': False,
        },
        'summary': {
            'reviewedColumns': len(REVIEWED_COLUMNS),
            'evidenceRecords': len(evidence),
            'boundaryDirectionCounts': counts,
        },
        'reviewedColumns': REVIEWED_COLUMNS,
        'evidence': evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='data/transit/line8-line13/seibu-strain-line13-columns.json')
    args = parser.parse_args()
    report = build_report()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('SUMMARY', json.dumps(report['summary'], ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
