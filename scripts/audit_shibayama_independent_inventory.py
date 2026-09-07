#!/usr/bin/env python3
"""Account for every departure on both stations/calendars against exact train pages.

Station-board clocks are inventory checks, never cross-train identity proof.
All through identities remain those of the retained official one-train pages.
"""
import argparse
import gzip
import hashlib
import html
import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

URL = 'https://www.sibatetu.co.jp/schedule.html'
SOURCE = Path('docs/transit/shibayama-official-station-boards.html.gz')
REPORT = Path('docs/transit/shibayama-independent-inventory.json')
DETAILS = Path('data/transit/keisei/official-train-details.json')


def clean(s):
    return html.unescape(re.sub('<[^>]*>', '', s)).strip()


def boards(source):
    tables = re.findall(r'<table\b[^>]*>(.*?)</table>', source, re.S)
    tables = [t for t in tables if 'schedule-number' in t]
    if len(tables) != 2:
        raise ValueError('Expected exactly both official station boards')
    rows = []
    for station, table in zip(['芝山千代田', '東成田'], tables):
        for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', table, re.S):
            cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S)
            if not cells:
                continue
            if len(cells) == 1 and 'class="note"' in cells[0] and 'schedule-number' not in cells[0]:
                continue  # Explicit legend, not a departure row.
            if len(cells) != 3 or not clean(cells[1]).isdigit():
                raise ValueError('Unknown official station-board row')
            hour = int(clean(cells[1]))
            for calendar, cell in zip(['weekday', 'holiday'], [cells[0], cells[2]]):
                for item in re.findall(r'<li\b[^>]*>(.*?)</li>', cell, re.S):
                    number = re.findall(r'<div class="schedule-number">(.*?)</div>', item, re.S)
                    label = re.findall(r'<div class="schedule-txt">(.*?)</div>', item, re.S)
                    if len(number) != 1 or len(label) != 1 or not clean(number[0]).isdigit():
                        raise ValueError('Unparsed official departure cell')
                    minute = int(clean(number[0]))
                    if minute >= 60:
                        raise ValueError('Invalid departure minute')
                    rows.append({'station': station, 'calendar': calendar, 'minute': hour * 60 + minute,
                                 'literalLabel': clean(label[0])})
    return rows


def audit(raw):
    rows = boards(raw.decode('utf-8'))
    trains = json.loads(DETAILS.read_bytes())['trains']
    candidates = defaultdict(list)
    for t in trains:
        local = [s for s in t['stops'] if s['station'] in {'東成田', '芝山千代田'}]
        if len(local) != 2:
            continue
        first = local[0]
        h, m = map(int, first['departure'].split(':'))
        candidates[(t['calendar'], first['station'], h * 60 + m)].append(t)
    seen = set()
    for row in rows:
        key = (row['calendar'], row['station'], row['minute'])
        if key in seen:
            raise ValueError('Duplicate physical departure in independent inventory')
        seen.add(key)
        matches = candidates.get(key, [])
        if not matches:
            raise ValueError('Missing independent Shibayama train: ' + str(key))
        local_shapes = {json.dumps([s for s in t['stops'] if s['station'] in {'東成田', '芝山千代田'}], sort_keys=True) for t in matches}
        if len(local_shapes) != 1:
            raise ValueError('Conflicting local published arrival/departure sequence')
        dest = {'成': '京成成田', '西': '西馬込', '上': '京成上野', '宗': '宗吾参道',
                '羽': '羽田空港第１・第２ターミナル', '高': '京成高砂', '芝': '芝山千代田'}[row['literalLabel'][-1]]
        if any(t['destination'] != dest for t in matches):
            raise ValueError('Official station destination differs from source service label: ' + str(key))
        row['publishedServiceDestination'] = dest
        row['completeJourneyDestinations'] = sorted({t['journeyDestination'] for t in matches})
        row['sourceKeys'] = [t['key'] for t in matches]
    if seen != set(candidates):
        raise ValueError('Source train pages contain departures absent from independent boards: ' + str(set(candidates)-seen))
    counts = defaultdict(int)
    for r in rows:
        counts[r['calendar'] + ':' + r['station']] += 1
    return {'version': 1, 'sourceUrl': URL, 'sourceSha256': hashlib.sha256(raw).hexdigest(),
            'detailsSha256': hashlib.sha256(DETAILS.read_bytes()).hexdigest(), 'coverageComplete': True,
            'summary': {'physicalDepartures': len(rows), 'sourcePublications': sum(len(v) for v in candidates.values()),
                        'missingDepartures': 0, 'unaccountedSourceDepartures': 0, 'counts': dict(counts)},
            'identityPolicy': 'Clocks account inventory only; no new identity joins; official one-train pages prove continuations',
            'departures': rows}


def verify():
    result = audit(gzip.decompress(SOURCE.read_bytes()))
    assert result == json.loads(REPORT.read_bytes())
    from collections import Counter
    from build_asakusa_boundary_network import minute
    table = json.loads(Path('data/transit/shibayama/timetables/official-shibayama.json').read_bytes())
    expected = []
    for t in json.loads(DETAILS.read_bytes())['trains']:
        local = [s for s in t['stops'] if s['station'] in {'東成田', '芝山千代田'}]
        if len(local) == 2:
            expected.append((t['calendar'], tuple((s['station'], minute(s['arrival']), minute(s['departure'])) for s in local)))
    actual = []
    for t in table['trips']:
        seq = tuple(('芝山千代田' if '芝山千代田' in table['stations'][s[0]] else '東成田', minute(s[1]), minute(s[2])) for s in t[3])
        cal = table['calendars'][t[0]]
        actual.append(('weekday' if cal in {'weekday', 'odpt.Calendar:Weekday'} else 'holiday', seq))
    assert Counter(expected) == Counter(actual), 'saved Shibayama table differs from exact published source events'
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--collect', action='store_true')
    p.add_argument('--verify', action='store_true')
    args = p.parse_args()
    if args.collect:
        with urllib.request.urlopen(URL, timeout=45) as response:
            raw = response.read()
        result = audit(raw)
        SOURCE.write_bytes(gzip.compress(raw, mtime=0))
        REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    else:
        result = verify()
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
