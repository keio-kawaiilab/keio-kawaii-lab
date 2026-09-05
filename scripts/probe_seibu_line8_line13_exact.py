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

# The two Metro routes share Kotake-mukaihara through Ikebukuro. A published
# one-train page is assigned to Line 8 or Line 13 only when it contains at least
# one station unique to that Metro route beyond the shared section.
YURAKUCHO_MARKERS = {
    '東池袋', '護国寺', '江戸川橋', '飯田橋', '市ケ谷', '市ヶ谷', '麹町',
    '永田町', '桜田門', '有楽町', '銀座一丁目', '新富町', '月島', '豊洲',
    '辰巳', '新木場',
}
FUKUTOSHIN_MARKERS = {
    '雑司が谷', '西早稲田', '東新宿', '新宿三丁目', '北参道',
    '明治神宮前', '明治神宮前〈原宿〉', '渋谷',
}
SEIBU_YURAKUCHO_SIDE = {'新桜台', '練馬'}
SEIBU_IKEBUKURO_WEST = {
    '中村橋', '富士見台', '練馬高野台', '石神井公園', '大泉学園', '保谷',
    'ひばりヶ丘', '東久留米', '清瀬', '秋津', '所沢', '西所沢', '小手指',
    '狭山ヶ丘', '武蔵藤沢', '稲荷山公園', '入間市', '仏子', '元加治', '飯能',
}
SEIBU_CHICHIBU_SIDE = {'西吾野', '正丸', '芦ヶ久保', '横瀬', '西武秩父'}

BOUNDARY_ADJACENT_PATTERNS = {
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
    'User-Agent': 'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/9.0)',
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


def first_index(names: list[str], candidates: set[str]) -> tuple[int, str] | None:
    hits = [(i, name) for i, name in enumerate(names) if name in candidates]
    return min(hits) if hits else None


def last_index(names: list[str], candidates: set[str]) -> tuple[int, str] | None:
    hits = [(i, name) for i, name in enumerate(names) if name in candidates]
    return max(hits) if hits else None


def route_span_proof(names: list[str], left: set[str], right: set[str], boundary_station: str,
                     forward_from: str, forward_to: str) -> dict[str, Any] | None:
    left_hits = [(i, name) for i, name in enumerate(names) if name in left]
    right_hits = [(i, name) for i, name in enumerate(names) if name in right]
    if not left_hits or not right_hits:
        return None
    # Every station in each marker set belongs to a fixed side of the verified
    # boundary. Compare the closest published markers across the boundary.
    pairs = sorted((abs(li - ri), li, ln, ri, rn) for li, ln in left_hits for ri, rn in right_hits)
    _, li, ln, ri, rn = pairs[0]
    if li == ri:
        return None
    forward = li < ri
    return {
        'proofType': 'same-published-one-train-page+verified-unique-route-span',
        'boundaryStation': boundary_station,
        'fromRailway': forward_from if forward else forward_to,
        'toRailway': forward_to if forward else forward_from,
        'publishedSideMarkers': [ln, rn] if forward else [rn, ln],
        'publishedMarkerIndexes': [li, ri] if forward else [ri, li],
        'adjacentPublishedBoundaryStopsRequired': False,
        'verifiedUniqueRouteSpanRequired': True,
    }


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
    name_set = set(names)
    branch, markers = metro_branch(names)
    boundaries: list[str] = []
    proofs: dict[str, dict[str, Any]] = {}

    # Metro <-> Seibu at Kotake-mukaihara. The exact route is identified by a
    # route-specific Metro station and a published Seibu-side station on this
    # same one-train page. Intermediate stop-skipping is irrelevant.
    if branch in {'yurakucho', 'fukutoshin'} and '小竹向原' in name_set:
        metro_set = YURAKUCHO_MARKERS if branch == 'yurakucho' else FUKUTOSHIN_MARKERS
        proof = route_span_proof(
            names, metro_set, SEIBU_YURAKUCHO_SIDE, '小竹向原',
            f'odpt.Railway:TokyoMetro.{"Yurakucho" if branch == "yurakucho" else "Fukutoshin"}',
            'odpt.Railway:Seibu.SeibuYurakucho',
        )
        if proof:
            bid = f'{branch}-seibu-kotake-mukaihara'
            boundaries.append(bid)
            proofs[bid] = proof

    # Seibu Yurakucho <-> Ikebukuro at Nerima. Require a route-specific Metro
    # station plus a published Ikebukuro-line station west of Nerima, all on the
    # same one-train page. This captures express trains that skip intermediate
    # stations without guessing from clock times.
    if branch in {'yurakucho', 'fukutoshin'}:
        metro_set = YURAKUCHO_MARKERS if branch == 'yurakucho' else FUKUTOSHIN_MARKERS
        east = metro_set | {'小竹向原', '新桜台'}
        proof = route_span_proof(
            names, east, SEIBU_IKEBUKURO_WEST, '練馬',
            'odpt.Railway:Seibu.SeibuYurakucho', 'odpt.Railway:Seibu.Ikebukuro',
        )
        if proof:
            # route_span_proof's left side here is east-of-Nerima. For a train
            # east -> west, the operational transition is SeibuYurakucho ->
            # Ikebukuro, regardless of whether the left marker itself is Metro.
            east_index = proof['publishedMarkerIndexes'][0]
            west_index = proof['publishedMarkerIndexes'][1]
            if east_index < west_index:
                proof['fromRailway'] = 'odpt.Railway:Seibu.SeibuYurakucho'
                proof['toRailway'] = 'odpt.Railway:Seibu.Ikebukuro'
            else:
                proof['fromRailway'] = 'odpt.Railway:Seibu.Ikebukuro'
                proof['toRailway'] = 'odpt.Railway:Seibu.SeibuYurakucho'
            bid = 'seibuyurakucho-ikebukuro-nerima'
            boundaries.append(bid)
            proofs[bid] = proof

    # Ordinary station pages usually do not discover S-TRAIN because it passes
    # Shin-Sakuradai. If a current page does contain a Fukutoshin-specific and a
    # Chichibu-line station, retain it as exact route-span evidence; the separate
    # official S-TRAIN PDF collector provides the exhaustive special-train proof.
    if branch == 'fukutoshin':
        proof = route_span_proof(
            names, FUKUTOSHIN_MARKERS, SEIBU_CHICHIBU_SIDE, '吾野',
            'odpt.Railway:Seibu.Ikebukuro', 'odpt.Railway:Seibu.SeibuChichibu',
        )
        if proof:
            # Metro is east of the boundary; normalize the operational direction.
            f_idx = first_index(names, FUKUTOSHIN_MARKERS)
            c_idx = first_index(names, SEIBU_CHICHIBU_SIDE)
            if f_idx and c_idx and f_idx[0] < c_idx[0]:
                proof['fromRailway'] = 'odpt.Railway:Seibu.Ikebukuro'
                proof['toRailway'] = 'odpt.Railway:Seibu.SeibuChichibu'
            else:
                proof['fromRailway'] = 'odpt.Railway:Seibu.SeibuChichibu'
                proof['toRailway'] = 'odpt.Railway:Seibu.Ikebukuro'
            bid = 'seibu-ikebukuro-seibuchichibu-agano'
            boundaries.append(bid)
            proofs[bid] = proof

    # South-side operator boundaries remain proven by adjacent published stops
    # on the same one-train page.
    for boundary_id, patterns in BOUNDARY_ADJACENT_PATTERNS.items():
        matched = next((p for p in patterns if includes_adjacent(names, p)), None)
        if not matched:
            continue
        if branch != 'fukutoshin':
            raise RuntimeError(f'Line 13-only boundary found without exact Fukutoshin marker: {url}')
        boundaries.append(boundary_id)
        proofs[boundary_id] = {
            'proofType': 'same-published-one-train-page+adjacent-published-boundary-stops',
            'publishedSideMarkers': list(matched),
            'adjacentPublishedBoundaryStopsRequired': True,
            'verifiedUniqueRouteSpanRequired': False,
        }

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
        'boundaryProofs': proofs,
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
        'yurakucho-seibu-kotake-mukaihara', 'fukutoshin-seibu-kotake-mukaihara',
        'seibuyurakucho-ikebukuro-nerima', 'seibu-ikebukuro-seibuchichibu-agano',
        'metro-tokyu-shibuya', 'tokyu-minatomirai-yokohama',
    ]
    boundary_counts = {bid: sum(bid in (row.get('boundaries') or []) for row in exact_rows) for bid in all_boundary_ids}
    branch_counts = {key: sum(row.get('metroBranch') == key for row in detail_rows) for key in ('yurakucho', 'fukutoshin', 'ambiguous', 'conflict')}
    exact_branch_counts = {key: sum(row.get('metroBranch') == key for row in exact_rows) for key in ('yurakucho', 'fukutoshin', 'ambiguous', 'conflict')}
    branch_kotake_counts = {
        'yurakucho': sum(row.get('metroBranch') == 'yurakucho' and 'yurakucho-seibu-kotake-mukaihara' in (row.get('boundaries') or []) for row in detail_rows),
        'fukutoshin': sum(row.get('metroBranch') == 'fukutoshin' and 'fukutoshin-seibu-kotake-mukaihara' in (row.get('boundaries') or []) for row in detail_rows),
    }

    return {
        'version': 9,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'source': 'Seibu Railway official-linked timetable service / one-train timetable pages',
        'officialEntryEvidence': 'https://www.seiburailway.jp/railway/station/shin-sakuradai/timetable/',
        'identityPolicy': {
            'singlePublishedOneTrainPageMayEstablishIdentity': True,
            'samePublishedTrainPageWithVerifiedUniqueRouteSpanMayEstablishInternalBoundary': True,
            'metroLineRequiresPublishedRouteSpecificStation': True,
            'ambiguousMetroBranchMayEstablishLineIdentity': False,
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
            'branchKotakeCounts': branch_kotake_counts,
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
        print('THROUGH_SAMPLE', json.dumps({k: row.get(k) for k in ('url', 'metroBranch', 'metroBranchPublishedMarkers', 'boundaries', 'boundaryProofs', 'headings')}, ensure_ascii=False))
    s = report['summary']
    if s['discoveredTrainDetailUrls'] <= 0 or s['trainDetailPagesFetched'] <= 0:
        raise RuntimeError('No current Seibu one-train timetable pages were collected')
    if s['errors']:
        raise RuntimeError(f"One-train page collection had {s['errors']} errors")
    if s['metroBranchCounts']['conflict']:
        raise RuntimeError('A one-train page contained conflicting Yurakucho and Fukutoshin route markers')
    # Every branch-specific train discovered at Shin-Sakuradai must be classified
    # across Kotake. If not, fail closed rather than silently dropping trains.
    for branch in ('yurakucho', 'fukutoshin'):
        if int(s['branchKotakeCounts'][branch]) != int(s['metroBranchCounts'][branch]):
            raise RuntimeError(f'Not every {branch} one-train page was exactly classified at Kotake: {s["branchKotakeCounts"][branch]}/{s["metroBranchCounts"][branch]}')
    if int(s['boundaryCounts'].get('seibuyurakucho-ikebukuro-nerima', 0)) <= 0:
        raise RuntimeError('No exact current Seibu Yurakucho-Ikebukuro route-span evidence found')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
