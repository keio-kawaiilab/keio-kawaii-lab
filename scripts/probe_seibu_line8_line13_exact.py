#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = 'https://seibu.ekitan.com'
SOURCE_PAGES = [
    f'{BASE}/norikae/timetable/station/232-1/d1?dw=0',
    f'{BASE}/norikae/timetable/station/232-1/d1?dw=1',
    f'{BASE}/norikae/timetable/station/232-1/d2?dw=0',
    f'{BASE}/norikae/timetable/station/232-1/d2?dw=1',
]
ONE_TRAIN_CALL_RE = re.compile(
    r"openOneTrainTimetable\(\s*['\"]([^'\"]+)['\"]\s*,\s*"
    r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*"
    r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
    re.I,
)

# The two Metro routes share Kotake-mukaihara-Senkawa-Kanamecho-Ikebukuro.
# A train is assigned to a Metro line only when its published one-train page
# contains at least one station unique to that line beyond the shared section.
YURAKUCHO_MARKERS = {
    '東池袋', '護国寺', '江戸川橋', '飯田橋', '市ケ谷', '市ヶ谷', '麹町',
    '永田町', '桜田門', '有楽町', '銀座一丁目', '新富町', '月島', '豊洲',
    '辰巳', '新木場',
}
FUKUTOSHIN_MARKERS = {
    '雑司が谷', '西早稲田', '東新宿', '新宿三丁目', '北参道',
    '明治神宮前', '明治神宮前〈原宿〉', '渋谷',
}

COMMON_KOTAKE_PATTERNS = (
    ('新桜台', '小竹向原', '千川'),
    ('千川', '小竹向原', '新桜台'),
)
BOUNDARY_PATTERNS = {
    'seibuyurakucho-ikebukuro-nerima': (
        ('新桜台', '練馬', '中村橋'),
        ('中村橋', '練馬', '新桜台'),
    ),
    'seibu-ikebukuro-seibuchichibu-agano': (
        ('東吾野', '吾野', '西吾野'),
        ('西吾野', '吾野', '東吾野'),
    ),
    'metro-tokyu-shibuya': (
        ('明治神宮前', '渋谷', '代官山'),
        ('明治神宮前〈原宿〉', '渋谷', '代官山'),
        ('代官山', '渋谷', '明治神宮前'),
        ('代官山', '渋谷', '明治神宮前〈原宿〉'),
    ),
    'tokyu-minatomirai-yokohama': (
        ('反町', '横浜', '新高島'),
        ('新高島', '横浜', '反町'),
    ),
}

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/8.0)',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
})


def clean(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def fetch(url: str) -> str:
    response = SESSION.get(url, timeout=(20, 60))
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding or 'utf-8'
    return response.text


def one_train_url(tx: str, sf: str, date: str, time: str, dw: str) -> str:
    return f"{BASE}/norikae/timetable/onetraintimetable/?{urlencode({'date': date, 'dw': dw, 'sf': sf, 'time': time, 'tx': tx})}"


def detail_url_metadata(url: str) -> dict[str, str]:
    q = parse_qs(urlparse(url).query)
    return {key: (q.get(key) or [''])[0] for key in ('date', 'dw', 'sf', 'time', 'tx')}


def discover_detail_urls(source_url: str, text: str) -> list[str]:
    soup = BeautifulSoup(text, 'html.parser')
    urls: list[str] = []
    for tx, sf, date, time, dw in ONE_TRAIN_CALL_RE.findall(text):
        urls.append(one_train_url(tx, sf, date, time, dw))
    for tag in soup.find_all(['a', 'form']):
        target = tag.get('href') or tag.get('action') or ''
        if 'onetraintimetable' in target:
            urls.append(urljoin(source_url, html.unescape(target)))
    unique: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not url.startswith(BASE + '/norikae/timetable/onetraintimetable') or url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique


def includes_adjacent(names: list[str], pattern: tuple[str, ...]) -> bool:
    return any(tuple(names[i:i + len(pattern)]) == pattern for i in range(max(0, len(names) - len(pattern) + 1)))


def metro_branch(names: list[str]) -> tuple[str, list[str]]:
    name_set = set(names)
    y = sorted(name_set & YURAKUCHO_MARKERS)
    f = sorted(name_set & FUKUTOSHIN_MARKERS)
    if y and not f:
        return 'yurakucho', y
    if f and not y:
        return 'fukutoshin', f
    if y and f:
        return 'conflict', sorted(set(y + f))
    return 'ambiguous', []


def parse_detail(url: str, text: str) -> dict[str, Any]:
    soup = BeautifulSoup(text, 'html.parser')
    headings = [clean(node.get_text(' ', strip=True)) for node in soup.find_all(['h1', 'h2', 'h3'])]
    stops: list[dict[str, str]] = []
    for tr in soup.find_all('tr'):
        cells = [clean(cell.get_text(' ', strip=True)) for cell in tr.find_all(['th', 'td'])]
        if len(cells) < 3 or cells[0] in {'駅', '駅名'}:
            continue
        station = cells[0]
        if not station or station in {'着時刻', '発時刻'}:
            continue
        joined = ' '.join(cells[1:])
        if not (re.search(r'\d{1,2}:\d{2}', joined) or any(c == '' for c in cells[1:3]) or 'レ' in joined):
            continue
        stops.append({'station': station, 'arrival': cells[1], 'departure': cells[2]})

    names = [row['station'] for row in stops]
    branch, markers = metro_branch(names)
    boundaries: list[str] = []

    if any(includes_adjacent(names, p) for p in COMMON_KOTAKE_PATTERNS):
        if branch == 'yurakucho':
            boundaries.append('yurakucho-seibu-kotake-mukaihara')
        elif branch == 'fukutoshin':
            boundaries.append('fukutoshin-seibu-kotake-mukaihara')

    for boundary_id, patterns in BOUNDARY_PATTERNS.items():
        if any(includes_adjacent(names, p) for p in patterns):
            boundaries.append(boundary_id)

    # Shibuya/Yokohama and the Chichibu S-TRAIN path are Line 13-only in the
    # current operating pattern. A contradictory Metro branch is rejected.
    line13_only = {'metro-tokyu-shibuya', 'tokyu-minatomirai-yokohama', 'seibu-ikebukuro-seibuchichibu-agano'}
    if any(x in boundaries for x in line13_only) and branch != 'fukutoshin':
        raise RuntimeError(f'Line 13-only boundary found without exact Fukutoshin branch marker: {url}')

    return {
        'url': url,
        'sourceParameters': detail_url_metadata(url),
        'title': clean(soup.title.get_text(' ', strip=True) if soup.title else ''),
        'headings': headings[:8],
        'stops': stops,
        'stationCount': len(stops),
        'metroBranch': branch,
        'metroBranchPublishedMarkers': markers,
        'boundaries': boundaries,
        'identityEvidence': 'single-published-one-train-page',
    }


def build_report() -> dict[str, Any]:
    source_rows: list[dict[str, Any]] = []
    detail_urls: list[str] = []
    seen: set[str] = set()
    for source_url in SOURCE_PAGES:
        try:
            text = fetch(source_url)
            urls = discover_detail_urls(source_url, text)
            source_rows.append({'url': source_url, 'fetched': True, 'bytes': len(text.encode('utf-8')), 'detailUrlCount': len(urls)})
            for url in urls:
                if url not in seen:
                    seen.add(url)
                    detail_urls.append(url)
        except Exception as exc:
            source_rows.append({'url': source_url, 'fetched': False, 'error': f'{type(exc).__name__}: {exc}'})

    detail_rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(fetch, url): url for url in detail_urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                detail_rows.append(parse_detail(url, future.result()))
            except Exception as exc:
                errors.append({'url': url, 'error': f'{type(exc).__name__}: {exc}'})
    detail_rows.sort(key=lambda row: row['url'])

    exact_rows = [row for row in detail_rows if row.get('boundaries')]
    all_boundary_ids = [
        'yurakucho-seibu-kotake-mukaihara',
        'fukutoshin-seibu-kotake-mukaihara',
        'seibuyurakucho-ikebukuro-nerima',
        'seibu-ikebukuro-seibuchichibu-agano',
        'metro-tokyu-shibuya',
        'tokyu-minatomirai-yokohama',
    ]
    boundary_counts = {bid: sum(bid in (row.get('boundaries') or []) for row in exact_rows) for bid in all_boundary_ids}
    branch_counts = {key: sum(row.get('metroBranch') == key for row in detail_rows) for key in ('yurakucho', 'fukutoshin', 'ambiguous', 'conflict')}
    exact_branch_counts = {key: sum(row.get('metroBranch') == key for row in exact_rows) for key in ('yurakucho', 'fukutoshin', 'ambiguous', 'conflict')}

    return {
        'version': 8,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'source': 'Seibu Railway official-linked timetable service / one-train timetable pages',
        'officialEntryEvidence': 'https://www.seiburailway.jp/railway/station/shin-sakuradai/timetable/',
        'identityPolicy': {
            'singlePublishedOneTrainPageMayEstablishIdentity': True,
            'boundaryRequiresAdjacentPublishedStopsOnSameTrainPage': True,
            'metroLineRequiresPublishedRouteSpecificStation': True,
            'ambiguousMetroBranchMayEstablishLineIdentity': False,
            'stationListingAloneMayEstablishIdentity': False,
            'timeProximityMayEstablishIdentity': False,
            'trainNumberAloneMayEstablishIdentity': False,
            'destinationAloneMayEstablishIdentity': False,
        },
        'summary': {
            'sourcePagesFetched': sum(bool(row.get('fetched')) for row in source_rows),
            'discoveredTrainDetailUrls': len(detail_urls),
            'trainDetailPagesFetched': len(detail_rows),
            'exactThroughTrainPages': len(exact_rows),
            'metroBranchCounts': branch_counts,
            'exactMetroBranchCounts': exact_branch_counts,
            'boundaryCounts': boundary_counts,
            'errors': len(errors),
        },
        'sourcePages': source_rows,
        'authoritativeThroughTrains': exact_rows,
        'detailErrors': errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default='data/transit/line8-line13/seibu-official-exact-through-trains.json')
    args = ap.parse_args()
    report = build_report()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('SUMMARY', json.dumps(report['summary'], ensure_ascii=False, indent=2))
    for row in (report.get('authoritativeThroughTrains') or [])[:16]:
        print('THROUGH_SAMPLE', json.dumps({k: row.get(k) for k in ('url', 'metroBranch', 'metroBranchPublishedMarkers', 'boundaries', 'headings')}, ensure_ascii=False))
    s = report['summary']
    if s['discoveredTrainDetailUrls'] <= 0 or s['trainDetailPagesFetched'] <= 0:
        raise RuntimeError('No current Seibu one-train timetable pages were collected')
    if s['errors']:
        raise RuntimeError(f"One-train page collection had {s['errors']} errors")
    if s['metroBranchCounts']['conflict']:
        raise RuntimeError('A one-train page contained conflicting Yurakucho and Fukutoshin route markers')
    for bid in ('yurakucho-seibu-kotake-mukaihara', 'fukutoshin-seibu-kotake-mukaihara', 'seibuyurakucho-ikebukuro-nerima'):
        if int(s['boundaryCounts'].get(bid, 0)) <= 0:
            raise RuntimeError(f'No exact current evidence found for {bid}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
