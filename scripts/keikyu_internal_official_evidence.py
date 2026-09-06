#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber

import keikyu_official_train_evidence as parser

MAIN = 'odpt.Railway:Keikyu.Main'
AIRPORT = 'odpt.Railway:Keikyu.Airport'
KURIHAMA = 'odpt.Railway:Keikyu.Kurihama'
ZUSHI = 'odpt.Railway:Keikyu.Zushi'
BOUNDARY_ID = 'keikyu-main-airport-kamata'
KURIHAMA_BOUNDARY_ID = 'keikyu-main-kurihama-horinouchi'
ZUSHI_BOUNDARY_ID = 'keikyu-main-zushi-kanazawahakkei'
LEGACY_MARKER = 'same-printed-column-includes-shinagawa-and-haneda'
MARKER = 'same-printed-column-two-exact-station-times'
SHINAGAWA_SUFFIX = '.Shinagawa'
HANEDA_T3_SUFFIX = '.HanedaAirportTerminal3'
HANEDA_T12_SUFFIX = '.HanedaAirportTerminal1and2'
MAINLINE_WEEKDAY_URL = 'https://www.keikyu.co.jp/ride/kakueki/pdf/mainline_weekday.pdf'
MAINLINE_HOLIDAY_URL = 'https://www.keikyu.co.jp/ride/kakueki/pdf/mainline_holiday.pdf'

BOUNDARIES: dict[tuple[str, str], dict[str, str]] = {
    (MAIN, AIRPORT): {'id': BOUNDARY_ID, 'station': '京急蒲田'},
    (AIRPORT, MAIN): {'id': BOUNDARY_ID, 'station': '京急蒲田'},
    (KURIHAMA, MAIN): {'id': KURIHAMA_BOUNDARY_ID, 'station': '堀ノ内'},
    (MAIN, KURIHAMA): {'id': KURIHAMA_BOUNDARY_ID, 'station': '堀ノ内'},
    (ZUSHI, MAIN): {'id': ZUSHI_BOUNDARY_ID, 'station': '金沢八景'},
    (MAIN, ZUSHI): {'id': ZUSHI_BOUNDARY_ID, 'station': '金沢八景'},
}

STATION_LABELS: dict[str, tuple[str, ...]] = {
    '.Sengakuji': ('泉岳寺',), '.Shinagawa': ('品川',), '.Kitashinagawa': ('北品川',),
    '.Shimbamba': ('新馬場',), '.AomonoYokocho': ('青物横丁',), '.Samezu': ('鮫洲',),
    '.Tachiaigawa': ('立会川',), '.Omorikaigan': ('大森海岸',), '.Heiwajima': ('平和島',),
    '.Omorimachi': ('大森町',), '.Umeyashiki': ('梅屋敷',), '.KeikyuKamata': ('京急蒲田',),
    '.Zoshiki': ('雑色',), '.Rokugodote': ('六郷土手',), '.KeikyuKawasaki': ('京急川崎',),
    '.HatchoNawate': ('八丁畷',), '.TsurumiIchiba': ('鶴見市場',), '.KeikyuTsurumi': ('京急鶴見',),
    '.Kagetsusojiji': ('花月総持寺',), '.Namamugi': ('生麦',), '.KeikyuShinkoyasu': ('京急新子安',),
    '.Koyasu': ('子安',), '.KanagawaShimmachi': ('神奈川新町',),
    '.KeikyuHigashikanagawa': ('京急東神奈川',), '.Kanagawa': ('神奈川',), '.Yokohama': ('横浜',),
    '.Tobe': ('戸部',), '.Hinodecho': ('日ノ出町',), '.Koganecho': ('黄金町',),
    '.Minamiota': ('南太田',), '.Idogaya': ('井土ヶ谷',), '.Gumyoji': ('弘明寺',),
    '.Kamiooka': ('上大岡',), '.Byobugaura': ('屛風浦', '屏風浦'), '.Sugita': ('杉田',),
    '.KeikyuTomioka': ('京急富岡',), '.Nokendai': ('能見台',), '.KanazawaBunko': ('金沢文庫',),
    '.KanazawaHakkei': ('金沢八景',), '.Oppama': ('追浜',), '.KeikyuTaura': ('京急田浦',),
    '.Anjinzuka': ('安針塚',), '.Hemi': ('逸見',), '.Shioiri': ('汐入',),
    '.YokosukaChuo': ('横須賀中央',), '.Kenritsudaigaku': ('県立大学',), '.Horinouchi': ('堀ノ内',),
    '.KeikyuOtsu': ('京急大津',), '.Maborikaigan': ('馬堀海岸',), '.Uraga': ('浦賀',),
    '.Kojiya': ('糀谷',), '.Otorii': ('大鳥居',), '.AnamoriInari': ('穴守稲荷',),
    '.Tenkubashi': ('天空橋',), '.HanedaAirportTerminal3': ('羽田空港第3ターミナル', '羽田空港第３ターミナル'),
    '.HanedaAirportTerminal1and2': ('羽田空港第1・第2ターミナル', '羽田空港第１・第２ターミナル'),
    '.Shinotsu': ('新大津',), '.Kitakurihama': ('北久里浜',), '.KeikyuKurihama': ('京急久里浜',),
    '.YrpNobi': ('YRP野比', 'ＹＲＰ野比'), '.KeikyuNagasawa': ('京急長沢',),
    '.Tsukuihama': ('津久井浜',), '.Miurakaigan': ('三浦海岸',), '.Misakiguchi': ('三崎口',),
    '.Mutsuura': ('六浦',), '.Jinmuji': ('神武寺',), '.ZushiHayama': ('逗子・葉山',),
}


def stable_id(*parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return 'keikyu-internal-pdf:' + hashlib.sha256(raw.encode()).hexdigest()[:24]


def stop_minutes(fragment: dict[str, Any], suffix: str) -> set[int]:
    out: set[int] = set()
    for stop in fragment.get('stops') or []:
        if not isinstance(stop, list) or len(stop) < 3 or not str(stop[0] or '').endswith(suffix):
            continue
        for value in stop[1:3]:
            if isinstance(value, (int, float)):
                out.add(int(value) % 1440)
    return out


def fragment_has_exact(fragment: dict[str, Any], railway: str, service: str, suffix: str, minute: int) -> bool:
    return (
        str(fragment.get('railway') or '') == railway
        and parser.calendar_matches(fragment.get('calendar'), service)
        and minute % 1440 in stop_minutes(fragment, suffix)
    )


def load_keikyu_fragments(folder: Path) -> list[dict[str, Any]]:
    payload = json.loads((folder / 'keikyu.json').read_text(encoding='utf-8'))
    return [row for row in payload.get('fragments') or [] if isinstance(row, dict) and row.get('id')]


def nearest_row(page_rows: list[dict[str, Any]], needle: str, y: float, *, above: bool, max_distance: float = 100.0) -> dict[str, Any] | None:
    rows = [row for row in page_rows if needle in parser.norm(row.get('text'))]
    rows = [row for row in rows if (float(row['y']) < y if above else float(row['y']) > y)]
    rows = [row for row in rows if abs(float(row['y']) - y) <= max_distance]
    return min(rows, key=lambda row: abs(float(row['y']) - y)) if rows else None


def exact_column_time(words: list[dict[str, Any]], row: dict[str, Any] | None, x: float) -> int | None:
    if not row:
        return None
    times = parser.time_cells(words, float(row['y']))
    if not times:
        return None
    cell = parser.nearest(times, x, parser.column_tolerance(times))
    return int(cell['minute']) if cell else None


def airport_time(words: list[dict[str, Any]], page_rows: list[dict[str, Any]], source_y: float, target_y: float, x: float, direction: str) -> tuple[int | None, str, str]:
    low, high = sorted((source_y, target_y))

    def is_haneda(row: dict[str, Any]) -> bool:
        text = parser.norm(row.get('text'))
        return '羽田空港第1・第2ターミナル' in text or '羽田空港第3ターミナル' in text

    if direction == 'toei-to-keikyu':
        candidates = [row for row in page_rows if float(row['y']) > high and float(row['y']) - high <= 120 and is_haneda(row)]
        anchor = high
    else:
        candidates = [row for row in page_rows if float(row['y']) < low and low - float(row['y']) <= 120 and is_haneda(row)]
        anchor = low

    candidates.sort(key=lambda row: (0 if '第1・第2' in parser.norm(row.get('text')) else 1, abs(float(row['y']) - anchor)))
    for row in candidates:
        minute = exact_column_time(words, row, x)
        if minute is None:
            continue
        text = parser.norm(row.get('text'))
        suffix = HANEDA_T12_SUFFIX if '第1・第2' in text else HANEDA_T3_SUFFIX
        return minute, suffix, text
    return None, '', ''


def official_columns(service: str, url: str) -> list[dict[str, Any]]:
    content = parser.fetch_pdf(url)
    out: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False, use_text_flow=False)
            page_rows = parser.rows(words)
            for candidate in parser.extract_page_candidates(words, page_number=page_number, calendar=service, source_url=url):
                geometry = candidate.get('rowGeometry') or {}
                sy = float(geometry.get('sourceBoundaryY') or 0)
                ty = float(geometry.get('targetBoundaryY') or 0)
                x = float(candidate.get('columnX') or 0)
                direction = str(candidate.get('direction') or '')
                if not sy or not ty or not x or direction not in ('toei-to-keikyu', 'keikyu-to-toei'):
                    continue
                shinagawa_row = nearest_row(page_rows, '品川', max(sy, ty), above=False) if direction == 'toei-to-keikyu' else nearest_row(page_rows, '品川', min(sy, ty), above=True)
                shinagawa = exact_column_time(words, shinagawa_row, x)
                haneda, haneda_suffix, haneda_text = airport_time(words, page_rows, sy, ty, x, direction)
                if shinagawa is None or haneda is None or not haneda_suffix:
                    continue
                out.append({
                    'calendar': service,
                    'pdfPage': page_number,
                    'columnX': round(x, 2),
                    'direction': direction,
                    'shinagawaMinute': shinagawa,
                    'hanedaMinute': haneda,
                    'hanedaStationSuffix': haneda_suffix,
                    'hanedaRowText': haneda_text,
                    'sourceUrl': url,
                })
    return out


def match_columns(columns: list[dict[str, Any]], fragments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    reasons = Counter()
    for row in columns:
        service = str(row['calendar'])
        direction = str(row['direction'])
        shinagawa = int(row['shinagawaMinute'])
        haneda = int(row['hanedaMinute'])
        suffix = str(row['hanedaStationSuffix'])
        main_matches = [f for f in fragments if fragment_has_exact(f, MAIN, service, SHINAGAWA_SUFFIX, shinagawa)]
        airport_matches = [f for f in fragments if fragment_has_exact(f, AIRPORT, service, suffix, haneda)]
        if len(main_matches) != 1 or len(airport_matches) != 1:
            if not main_matches:
                reasons['missing-main-exact'] += 1
            elif not airport_matches:
                reasons['missing-airport-exact'] += 1
            else:
                reasons['ambiguous-exact'] += 1
            continue

        if direction == 'toei-to-keikyu':
            source, target = main_matches[0], airport_matches[0]
        else:
            source, target = airport_matches[0], main_matches[0]
        entry = {
            'status': 'official-column-evidence',
            'matchStatus': 'matched-singleton',
            'id': stable_id(service, direction, row['pdfPage'], row['columnX'], shinagawa, haneda, source['id'], target['id']),
            'operator': 'keikyu',
            'calendar': service,
            'direction': 'main-to-airport' if direction == 'toei-to-keikyu' else 'airport-to-main',
            'boundaryId': BOUNDARY_ID,
            'boundaryStation': '京急蒲田',
            'fromRailway': str(source.get('railway') or ''),
            'toRailway': str(target.get('railway') or ''),
            'fromFragment': source['id'],
            'toFragment': target['id'],
            'sourceMatches': [str(source['id'])],
            'targetMatches': [str(target['id'])],
            'shinagawaMinute': shinagawa,
            'hanedaMinute': haneda,
            'hanedaStationSuffix': suffix,
            'pdfPage': row['pdfPage'],
            'columnX': row['columnX'],
            'evidence': ['operator-official-connection-timetable', LEGACY_MARKER],
            'sourceUrl': row['sourceUrl'],
            'matchPolicy': {
                'officialSamePrintedColumnRequired': True,
                'exactShinagawaMinuteRequired': True,
                'exactHanedaMinuteRequired': True,
                'singletonFragmentMatchRequiredAtBothPoints': True,
                'trainNumberAloneMayEstablishIdentity': False,
                'timeProximityAloneMayEstablishIdentity': False,
            },
        }
        entries.append(entry)
        reasons['matched-singleton-two-point'] += 1

    return entries, {
        'matchedSingleton': len(entries),
        'directions': dict(Counter(str(row['direction']) for row in entries)),
        'reasons': dict(reasons),
    }


def suffix_of(station: Any) -> str:
    text = str(station or '')
    return '.' + text.rsplit('.', 1)[-1] if '.' in text else ''


def service_of(fragment: dict[str, Any]) -> str:
    raw = fragment.get('calendar')
    if parser.calendar_matches(raw, 'weekday'):
        return 'weekday'
    if parser.calendar_matches(raw, 'holiday'):
        return 'holiday'
    return ''


def fragment_anchors(fragment: dict[str, Any]) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for stop in fragment.get('stops') or []:
        if not isinstance(stop, list) or len(stop) < 3:
            continue
        suffix = suffix_of(stop[0])
        if suffix not in STATION_LABELS:
            continue
        for minute in sorted({int(v) % 1440 for v in stop[1:3] if isinstance(v, (int, float))}):
            anchors.append({'station': str(stop[0]), 'suffix': suffix, 'minute': minute})
    return anchors


def singleton_anchors(fragment: dict[str, Any], fragments: list[dict[str, Any]], service: str) -> list[dict[str, Any]]:
    railway = str(fragment.get('railway') or '')
    fid = str(fragment.get('id') or '')
    out: list[dict[str, Any]] = []
    for anchor in fragment_anchors(fragment):
        matches = [
            str(row.get('id') or '') for row in fragments
            if fragment_has_exact(row, railway, service, str(anchor['suffix']), int(anchor['minute']))
        ]
        if matches == [fid]:
            out.append(anchor)
    return out


def official_station_time_index(service: str, url: str) -> dict[tuple[str, int], list[dict[str, Any]]]:
    content = parser.fetch_pdf(url)
    index: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False, use_text_flow=False)
            page_rows = parser.rows(words, 4.0)
            for row in page_rows:
                text = parser.norm(row.get('text'))
                suffixes = [
                    suffix for suffix, labels in STATION_LABELS.items()
                    if any(parser.norm(label) in text for label in labels)
                ]
                if not suffixes:
                    continue
                for cell in parser.time_cells(words, float(row['y'])):
                    minute = int(cell['minute']) % 1440
                    for suffix in suffixes:
                        index[(suffix, minute)].append({
                            'page': page_number,
                            'x': round(float(cell['x']), 2),
                            'rowText': text,
                            'sourceUrl': url,
                        })
    return index


def same_column_proof(
    source: dict[str, Any],
    target: dict[str, Any],
    fragments: list[dict[str, Any]],
    service: str,
    official_index: dict[tuple[str, int], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    source_anchors = singleton_anchors(source, fragments, service)
    target_anchors = singleton_anchors(target, fragments, service)
    proofs: list[dict[str, Any]] = []
    for left in source_anchors:
        left_positions = official_index.get((str(left['suffix']), int(left['minute'])), [])
        if not left_positions:
            continue
        for right in target_anchors:
            if left['station'] == right['station']:
                continue
            right_positions = official_index.get((str(right['suffix']), int(right['minute'])), [])
            for a in left_positions:
                for b in right_positions:
                    if int(a['page']) != int(b['page']) or abs(float(a['x']) - float(b['x'])) > 3.0:
                        continue
                    proofs.append({
                        'page': int(a['page']),
                        'x': round((float(a['x']) + float(b['x'])) / 2, 2),
                        'sourceAnchor': left,
                        'targetAnchor': right,
                        'sourceRowText': a['rowText'],
                        'targetRowText': b['rowText'],
                        'sourceUrl': a['sourceUrl'],
                    })
    if not proofs:
        return None
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for proof in proofs:
        buckets[(int(proof['page']), int(round(float(proof['x']) * 2)))].append(proof)
    best = sorted(buckets.values(), key=lambda rows: (-len(rows), rows[0]['page'], rows[0]['x']))[0]
    chosen = best[0]
    chosen['corroboratingAnchorPairs'] = len(best)
    return chosen


def resolve_ambiguous_cases(
    coverage: dict[str, Any],
    fragments: list[dict[str, Any]],
    indexes: dict[str, dict[tuple[str, int], list[dict[str, Any]]]],
) -> tuple[list[dict[str, Any]], Counter]:
    by_id = {str(row['id']): row for row in fragments}
    entries: list[dict[str, Any]] = []
    reasons: Counter = Counter()
    for unresolved in coverage.get('unresolved') or []:
        if not isinstance(unresolved, dict) or unresolved.get('kind') != 'ambiguous-boundary-fragment-alignment':
            continue
        source = by_id.get(str(unresolved.get('fragment') or ''))
        if not source:
            reasons['missing-source-fragment'] += 1
            continue
        pair = (str(source.get('railway') or ''), str(unresolved.get('nextRailway') or ''))
        boundary = BOUNDARIES.get(pair)
        if not boundary:
            continue
        service = service_of(source)
        official_index = indexes.get(service)
        if not service or official_index is None:
            reasons['unsupported-calendar'] += 1
            continue
        proven: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for candidate_id in unresolved.get('candidateFragments') or []:
            candidate = by_id.get(str(candidate_id or ''))
            if not candidate or str(candidate.get('railway') or '') != pair[1] or service_of(candidate) != service:
                continue
            proof = same_column_proof(source, candidate, fragments, service, official_index)
            if proof:
                proven.append((candidate, proof))
        if len(proven) != 1:
            reasons['no-single-official-column-candidate' if not proven else 'multiple-official-column-candidates'] += 1
            continue
        target, proof = proven[0]
        source_id, target_id = str(source['id']), str(target['id'])
        source_anchor, target_anchor = proof['sourceAnchor'], proof['targetAnchor']
        entry = {
            'status': 'official-column-evidence',
            'matchStatus': 'matched-singleton',
            'id': stable_id(
                service, boundary['id'], proof['page'], proof['x'], source_id, target_id,
                source_anchor['station'], source_anchor['minute'], target_anchor['station'], target_anchor['minute'],
            ),
            'operator': 'keikyu',
            'calendar': service,
            'direction': f"{pair[0].rsplit('.', 1)[-1].lower()}-to-{pair[1].rsplit('.', 1)[-1].lower()}",
            'boundaryId': boundary['id'],
            'boundaryStation': boundary['station'],
            'fromRailway': pair[0],
            'toRailway': pair[1],
            'fromFragment': source_id,
            'toFragment': target_id,
            'sourceMatches': [source_id],
            'targetMatches': [target_id],
            'officialAnchors': [source_anchor, target_anchor],
            'pdfPage': proof['page'],
            'columnX': proof['x'],
            'corroboratingAnchorPairs': proof['corroboratingAnchorPairs'],
            'evidence': ['operator-official-mainline-timetable', MARKER],
            'sourceUrl': proof['sourceUrl'],
            'matchPolicy': {
                'officialSamePrintedColumnRequired': True,
                'twoExactPublishedStationTimesRequired': True,
                'singletonFragmentMatchRequiredAtBothPoints': True,
                'trainNumberAloneMayEstablishIdentity': False,
                'timeProximityAloneMayEstablishIdentity': False,
            },
        }
        entries.append(entry)
        reasons['matched-singleton-two-point-mainline'] += 1
    return entries, reasons


def build_payload(fragment_folder: Path, coverage_path: Path) -> dict[str, Any]:
    fragments = load_keikyu_fragments(fragment_folder)

    legacy_columns: list[dict[str, Any]] = []
    legacy_columns.extend(official_columns('weekday', parser.DEFAULT_WEEKDAY_URL))
    legacy_columns.extend(official_columns('holiday', parser.DEFAULT_HOLIDAY_URL))
    legacy_entries, legacy_summary = match_columns(legacy_columns, fragments)

    coverage = json.loads(coverage_path.read_text(encoding='utf-8')) if coverage_path.exists() else {}
    mainline_indexes = {
        'weekday': official_station_time_index('weekday', MAINLINE_WEEKDAY_URL),
        'holiday': official_station_time_index('holiday', MAINLINE_HOLIDAY_URL),
    }
    generic_entries, generic_reasons = resolve_ambiguous_cases(coverage, fragments, mainline_indexes)

    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in legacy_entries + generic_entries:
        by_pair[(str(entry['fromFragment']), str(entry['toFragment']))] = entry
    entries = list(by_pair.values())
    directions = Counter(str(row.get('direction') or '') for row in entries)
    boundary_counts = Counter(str(row.get('boundaryId') or '') for row in entries)
    return {
        'version': 2,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'operator': 'keikyu',
        'boundaryIds': sorted(set(boundary_counts)),
        'policy': {
            'officialSamePrintedColumnRequired': True,
            'twoExactPublishedStationTimesRequired': True,
            'singletonFragmentMatchRequiredAtBothPoints': True,
            'trainNumberAloneMayEstablishIdentity': False,
            'timeProximityAloneMayEstablishIdentity': False,
        },
        'summary': {
            'officialLegacyTwoPointColumns': len(legacy_columns),
            'legacy': legacy_summary,
            'genericReasons': dict(generic_reasons),
            'matchedSingleton': len(entries),
            'directions': dict(directions),
            'boundaries': dict(boundary_counts),
        },
        'entries': entries,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--fragments', default='data/transit-v2/fragments')
    ap.add_argument('--coverage', default='data/transit-v2/coverage.json')
    ap.add_argument('--output', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    args = ap.parse_args()
    payload = build_payload(Path(args.fragments), Path(args.coverage))
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload['summary'], ensure_ascii=False, indent=2))
    if not payload['entries']:
        raise RuntimeError('No strict Keikyu internal official same-column evidence matched')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
