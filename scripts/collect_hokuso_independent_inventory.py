#!/usr/bin/env python3
"""Discover all Hokuso station departures, including internal-only trains.

The operator-linked Hokuso Ekitan station boards establish the independent
inventory. Keisei's public one-train pages provide ordered arrival/departure
sequences. Station clocks never establish a cross-train identity.
"""
import argparse
import concurrent.futures
import gzip
import hashlib
import html
import json
import re
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from build_keisei_extended_network import HOKUSO_STATIONS

REF = re.compile(r"openOneTrainTimetable\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")
CACHE = Path(tempfile.gettempdir()) / 'hokuso-source-cache'


def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]*>', ' ', s))).strip()


def fetch(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.html.gz')
    if path.exists():
        return gzip.decompress(path.read_bytes()).decode('utf-8')
    request = urllib.request.Request(url, headers={'User-Agent': 'Keio-Kawaii-Lab timetable verification/1.0'})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()
    text = raw.decode('utf-8')
    if '<html' not in text.lower() or len(raw) < 2000:
        raise ValueError('Not a timetable HTML response: ' + url)
    path.write_bytes(gzip.compress(raw, mtime=0))
    return text


def parse_board(source):
    rows = []
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', source, re.S):
        hour = re.search(r'<th class="side0[12]">(\d+)</th>', row)
        if not hour:
            continue
        h = int(hour[1])
        h = h + 24 if h < 3 else h
        boxes = re.findall(r'<div class="syasyubox[^\"]*">(.*?)</div>', row, re.S)
        for box in boxes:
            pieces = re.split(r'<br\s*/?>', box)
            if len(pieces) != 2:
                raise ValueError('Unknown Hokuso board cell')
            label = clean(pieces[0])
            annotations = re.findall(r'<span class="cntmark"[^>]*>(.*?)</span>', pieces[1], re.S)
            event = clean(re.sub(r'<span class="cntmark"[^>]*>.*?</span>', '', pieces[1], flags=re.S))
            m = re.fullmatch(r'(\d{1,2})', event)
            if not m or int(m[1]) > 59:
                raise ValueError('Unclassified Hokuso departure cell: ' + event)
            # Symbols are station-specific: Takasago ▲ means an overtaking
            # wait at Yagiri, not an origin. Never turn a glyph into identity.
            rows.append({'minute': h * 60 + int(m[1]), 'label': label,
                         'literalMarker': ' '.join(clean(a) for a in annotations)})
    if not rows:
        raise ValueError('No independent Hokuso departures parsed')
    return rows


def parse_detail(source, url, ref):
    headings = [clean(x) for x in re.findall(r'<h[1-4]\b[^>]*>(.*?)</h[1-4]>', source, re.S)]
    stops = []
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', source, re.S):
        cells = [clean(x) for x in re.findall(r'<t[hd]\b[^>]*>(.*?)</t[hd]>', row, re.S)]
        if len(cells) < 3:
            continue
        station, arrival, departure = cells[:3]
        times = [v if re.fullmatch(r'[0-2]?\d:[0-5]\d', v) else None for v in [arrival, departure]]
        if any(times):
            stops.append({'station': station, 'arrival': times[0], 'departure': times[1]})
    if len(stops) < 2:
        raise ValueError('No complete official one-train sequence: ' + url)
    return {'key': ref['dw'] + ':' + ref['tx'], 'sourceTrainId': ref['tx'],
            'calendar': 'weekday' if ref['dw'] == '0' else 'holiday',
            'url': url, 'reference': ref, 'headings': headings,
            'sourceSha256': hashlib.sha256(source.encode()).hexdigest(), 'stops': stops}


def collect(output):
    # The official T2 selector labels Takasago's sole Hokuso direction d=1.
    # At intermediate stations d=1 is westbound and d=2 is eastbound.
    pairs = [(0, 1)] + [(i, d) for i in range(1, 15) for d in (1, 2) if (i, d) != (14, 2)]
    jobs = []
    for i, d in pairs:
        for dw in (0, 1):
            jobs.append({'kind': 'operator-board', 'stationIndex': i, 'direction': d, 'calendar': dw,
                         'url': f'https://hokuso.ekitan.com/jp/pc/T5?USR=PC&dw={dw}&slCode=200-{i}&d={d}'})
        jobs.append({'kind': 'train-page-references', 'stationIndex': i, 'direction': d,
                     'url': f'https://keisei.ekitan.com/search/timetable/station/200-{i}/d{d}?dw=0'})
    refs = {}
    def one(job):
        s = fetch(job['url'])
        item = dict(job, sourceSha256=hashlib.sha256(s.encode()).hexdigest(),
                    travelDirection=2 if job['stationIndex'] == 0 else job['direction'])
        if job['kind'] == 'operator-board':
            try:
                item['departures'] = parse_board(s)
            except ValueError as error:
                raise ValueError(str(error) + ': ' + job['url']) from error
        else:
            item['references'] = [dict(zip(['tx', 'sf', 'date', 'time', 'dw'], m)) for m in REF.findall(s)]
            if not item['references']:
                raise ValueError('Missing official train-page references: ' + job['url'])
        return item
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, jobs))
    for row in results:
        for ref in row.get('references', []):
            refs.setdefault(ref['dw'] + ':' + ref['tx'], ref)
    old = {t['key']: t for t in json.loads(Path('data/transit/keisei/official-train-details.json').read_bytes())['trains']}
    missing = [r for key, r in refs.items() if key not in old]
    print(json.dumps({'boards': len(pairs) * 2, 'uniqueTrainPublications': len(refs), 'newPublicationsToCollect': len(missing)}), flush=True)
    def detail(ref):
        url = 'https://keisei.ekitan.com/search/timetable/onetraintimetable/?' + urllib.parse.urlencode(ref)
        return parse_detail(fetch(url), url, ref)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        new = list(pool.map(detail, missing))
    trains = [old[key] for key in refs if key in old] + new
    payload = {'version': 1, 'operatorSource': 'https://www.hokuso-railway.co.jp/',
               'stationNames': [s[0] for s in HOKUSO_STATIONS], 'boardsAndReferences': results,
               'trains': trains, 'newSourceKeys': [t['key'] for t in new]}
    output.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(json.dumps({'trains': len(trains), 'newPublications': len(new), 'output': str(output)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cache', type=Path)
    args = p.parse_args()
    if args.cache:
        CACHE = args.cache
    collect(args.output)
