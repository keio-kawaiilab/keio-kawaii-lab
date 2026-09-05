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
# Seibu Railway's current official site links users to this timetable service.
# The rendered station pages themselves contain the exact one-train parameters
# for every departure in openOneTrainTimetable(...).
SOURCE_PAGES = [
    f'{BASE}/norikae/timetable/station/232-1/d1?dw=0',  # Shin-Sakuradai -> Kotake / Metro
    f'{BASE}/norikae/timetable/station/232-1/d1?dw=1',
    f'{BASE}/norikae/timetable/station/232-1/d2?dw=0',  # Shin-Sakuradai -> Nerima
    f'{BASE}/norikae/timetable/station/232-1/d2?dw=1',
]
KNOWN_SAMPLE = (
    f'{BASE}/norikae/timetable/onetraintimetable/'
    '?date=20260530&dw=1&sf=2836&time=1926&tx=1050110-1809-4702'
)
ONE_TRAIN_CALL_RE = re.compile(
    r"openOneTrainTimetable\(\s*['\"]([^'\"]+)['\"]\s*,\s*"
    r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*"
    r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
    re.I,
)
BOUNDARIES = {
    'seibu-metro-kotake-mukaihara': (
        ('新桜台', '小竹向原', '千川'),
        ('千川', '小竹向原', '新桜台'),
    ),
    'metro-tokyu-shibuya': (
        ('明治神宮前', '渋谷', '代官山'),
        ('代官山', '渋谷', '明治神宮前'),
    ),
    'tokyu-minatomirai-yokohama': (
        ('反町', '横浜', '新高島'),
        ('新高島', '横浜', '反町'),
    ),
}

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/7.0)',
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
    query = urlencode({
        'date': date,
        'dw': dw,
        'sf': sf,
        'time': time,
        'tx': tx,
    })
    return f'{BASE}/norikae/timetable/onetraintimetable/?{query}'


def detail_url_metadata(url: str) -> dict[str, str]:
    q = parse_qs(urlparse(url).query)
    return {
        key: (q.get(key) or [''])[0]
        for key in ('date', 'dw', 'sf', 'time', 'tx')
    }


def discover_detail_urls(source_url: str, text: str) -> tuple[list[str], list[str]]:
    soup = BeautifulSoup(text, 'html.parser')
    urls: list[str] = []

    # Current official-linked station pages publish every departure as a Vue
    # click handler. These five arguments are the site's own exact identifiers;
    # no time/destination similarity is used to manufacture identity.
    for tx, sf, date, time, dw in ONE_TRAIN_CALL_RE.findall(text):
        urls.append(one_train_url(tx, sf, date, time, dw))

    # Retain ordinary-link discovery as a compatibility fallback if the site
    # changes rendering while keeping direct one-train URLs.
    for tag in soup.find_all(['a', 'form']):
        target = tag.get('href') or tag.get('action') or ''
        if 'onetraintimetable' in target:
            urls.append(urljoin(source_url, html.unescape(target)))

    unique: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not url.startswith(BASE + '/norikae/timetable/onetraintimetable'):
            continue
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)

    snippets: list[str] = []
    if not unique:
        for needle in ('openOneTrainTimetable', 'onetraintimetable', 'tx=', 'oneTrain', 'trainDetail'):
            pos = text.find(needle)
            if pos >= 0:
                snippets.append(clean(text[max(0, pos - 350):pos + 650]))
    return unique, snippets[:8]


def parse_detail(url: str, text: str) -> dict[str, Any]:
    soup = BeautifulSoup(text, 'html.parser')
    headings = [clean(node.get_text(' ', strip=True)) for node in soup.find_all(['h1', 'h2', 'h3'])]
    stops: list[dict[str, str]] = []
    for tr in soup.find_all('tr'):
        cells = [clean(cell.get_text(' ', strip=True)) for cell in tr.find_all(['th', 'td'])]
        if len(cells) < 3:
            continue
        if cells[0] in {'駅', '駅名'}:
            continue
        station = cells[0]
        if not station or station in {'着時刻', '発時刻'}:
            continue
        if not (re.search(r'\d{1,2}:\d{2}', ' '.join(cells[1:])) or any(c == '' for c in cells[1:3])):
            continue
        stops.append({
            'station': station,
            'arrival': cells[1] if len(cells) > 1 else '',
            'departure': cells[2] if len(cells) > 2 else '',
        })

    names = [row['station'] for row in stops]
    boundaries: list[str] = []
    for boundary_id, patterns in BOUNDARIES.items():
        for pattern in patterns:
            n = len(pattern)
            if any(tuple(names[i:i+n]) == pattern for i in range(max(0, len(names) - n + 1))):
                boundaries.append(boundary_id)
                break

    return {
        'url': url,
        'sourceParameters': detail_url_metadata(url),
        'title': clean(soup.title.get_text(' ', strip=True) if soup.title else ''),
        'headings': headings[:8],
        'stops': stops,
        'stationCount': len(stops),
        'boundaries': boundaries,
        'identityEvidence': 'single-published-one-train-page',
    }


def build_report() -> dict[str, Any]:
    source_rows: list[dict[str, Any]] = []
    detail_urls: list[str] = []
    seen: set[str] = set()
    calendar_keys: set[tuple[str, str]] = set()
    for source_url in SOURCE_PAGES:
        try:
            text = fetch(source_url)
            urls, snippets = discover_detail_urls(source_url, text)
            metas = [detail_url_metadata(url) for url in urls]
            for meta in metas:
                if meta.get('date') or meta.get('dw'):
                    calendar_keys.add((meta.get('date', ''), meta.get('dw', '')))
            source_rows.append({
                'url': source_url,
                'fetched': True,
                'bytes': len(text.encode('utf-8')),
                'detailUrlCount': len(urls),
                'calendarKeys': sorted({(m.get('date', ''), m.get('dw', '')) for m in metas}),
                'diagnosticSnippets': snippets,
            })
            for url in urls:
                if url not in seen:
                    seen.add(url)
                    detail_urls.append(url)
        except Exception as exc:
            source_rows.append({'url': source_url, 'fetched': False, 'error': f'{type(exc).__name__}: {exc}'})

    discovered_count = len(detail_urls)
    used_known_sample_fallback = False
    if not detail_urls:
        used_known_sample_fallback = True
        detail_urls.append(KNOWN_SAMPLE)

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
    boundary_counts = {
        boundary_id: sum(boundary_id in (row.get('boundaries') or []) for row in exact_rows)
        for boundary_id in BOUNDARIES
    }
    triple = [row for row in exact_rows if len(row.get('boundaries') or []) == 3]
    exact_calendar_counts: dict[str, int] = {}
    for row in exact_rows:
        meta = row.get('sourceParameters') or {}
        key = f"{meta.get('date','')}|dw={meta.get('dw','')}"
        exact_calendar_counts[key] = exact_calendar_counts.get(key, 0) + 1

    return {
        'version': 7,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'source': 'Seibu Railway official-linked timetable service / one-train timetable pages',
        'officialEntryEvidence': 'https://www.seiburailway.jp/railway/station/shin-sakuradai/timetable/',
        'sourcePages': source_rows,
        'identityPolicy': {
            'singlePublishedOneTrainPageMayEstablishIdentity': True,
            'stationListingAloneMayEstablishIdentity': False,
            'timeProximityMayEstablishIdentity': False,
            'trainNumberAloneMayEstablishIdentity': False,
            'destinationAloneMayEstablishIdentity': False,
            'boundaryRequiresAdjacentPublishedStopsOnSameTrainPage': True,
            'sitePublishedDetailParametersMayConstructDetailUrl': True,
        },
        'summary': {
            'sourcePagesFetched': sum(bool(row.get('fetched')) for row in source_rows),
            'discoveredTrainDetailUrls': discovered_count,
            'usedKnownSampleFallback': used_known_sample_fallback,
            'calendarKeys': [f'{date}|dw={dw}' for date, dw in sorted(calendar_keys)],
            'trainDetailPagesFetched': len(detail_rows),
            'exactThroughTrainPages': len(exact_rows),
            'allThreeBoundaryPages': len(triple),
            'boundaryCounts': boundary_counts,
            'exactCalendarCounts': exact_calendar_counts,
            'errors': len(errors),
        },
        'authoritativeThroughTrains': exact_rows,
        'detailErrors': errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default='data/transit/fukutoshin/seibu-official-linked-through-trains.json')
    args = ap.parse_args()
    report = build_report()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('SUMMARY', json.dumps(report['summary'], ensure_ascii=False, indent=2))
    for row in (report.get('authoritativeThroughTrains') or [])[:12]:
        print('THROUGH_SAMPLE', json.dumps({
            'url': row.get('url'),
            'sourceParameters': row.get('sourceParameters'),
            'stationCount': row.get('stationCount'),
            'boundaries': row.get('boundaries'),
            'headings': row.get('headings'),
        }, ensure_ascii=False))
    for source in report.get('sourcePages') or []:
        if source.get('diagnosticSnippets'):
            print('SOURCE_DIAGNOSTIC', json.dumps(source, ensure_ascii=False))
    summary = report['summary']
    if int(summary['discoveredTrainDetailUrls']) == 0:
        raise RuntimeError('No current one-train URL was discovered from the official-linked station timetable')
    if summary['usedKnownSampleFallback']:
        raise RuntimeError('Current collection fell back to a retained sample instead of station-published train parameters')
    if int(summary['trainDetailPagesFetched']) == 0:
        raise RuntimeError('No Seibu one-train timetable page was fetched')
    if int(summary['exactThroughTrainPages']) == 0:
        raise RuntimeError('No exact Line 13 through train was proven by one published train page')
    if int((summary['boundaryCounts'] or {}).get('seibu-metro-kotake-mukaihara') or 0) == 0:
        raise RuntimeError('No exact Seibu-Metro Kotake-Mukaihara crossing was proven')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
