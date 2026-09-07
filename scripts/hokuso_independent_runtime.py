#!/usr/bin/env python3
"""Preserve the Keisei-led baseline and add independently discovered local trains."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from build_asakusa_boundary_network import minute
from build_keisei_extended_network import HOKUSO, HOKUSO_STATIONS

INVENTORY = Path('data/transit/hokuso/official-independent-inventory.json.gz')
ARCHIVE = Path('docs/transit/hokuso-independent-source-pages.json.gz')
REPORT = Path('docs/transit/hokuso-independent-inventory-audit.json.gz')
NETWORK = Path('data/transit/hokuso/timetables/official-local-supplement.json')
BASE = Path('data/transit/hokuso/timetables/official-hokuso.json')
LINE = Path('data/transit/hokuso/timetables/official-complete-hokuso.json')
INDEX = Path('data/transit/hokuso/timetable-index.json')
DETAILS = Path('data/transit/keisei/official-train-details.json')


def read(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith('.gz') else raw)


def write(path, payload):
    raw = (json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    Path(path).write_bytes(gzip.compress(raw, mtime=0) if str(path).endswith('.gz') else raw)


def package(input_path, cache):
    data = read(input_path)
    from audit_hokuso_independent_inventory import audit
    report = audit(data)
    if not report['coverageComplete']:
        raise ValueError('Independent corridor inventory is incomplete')
    urls = {r['url']: r['sourceSha256'] for r in data['boardsAndReferences']}
    urls.update({t['url']: t['sourceSha256'] for t in data['trains'] if t['key'] in data['newSourceKeys']})
    archive = {}
    for url, expected in urls.items():
        raw = gzip.decompress((cache / (hashlib.sha256(url.encode()).hexdigest() + '.html.gz')).read_bytes())
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Source cache differs from parsed evidence')
        archive[url] = raw.decode()
    data['keiseiDetailsSha256'] = hashlib.sha256(DETAILS.read_bytes()).hexdigest()
    write(INVENTORY, data)
    write(ARCHIVE, archive)
    write(REPORT, report)


def supplement(data):
    stations = [s[1] for s in HOKUSO_STATIONS]
    names = [s[0] for s in HOKUSO_STATIONS]
    trips = []
    for t in data['trains']:
        if t['key'] not in data['newSourceKeys']:
            continue
        if [s['station'] for s in t['stops']] != ['印西牧の原', '印旛日本医大']:
            raise ValueError('Unreviewed new northern train; not an internal two-stop supplement')
        stops = [[names.index(s['station']), minute(s['arrival']), minute(s['departure'])] for s in t['stops']]
        trips.append([0 if t['calendar'] == 'weekday' else 1, 0, t['sourceTrainId'].rsplit('-', 1)[-1],
                      stops, [[0]], 'hokuso-official:' + t['key']])
    if len(trips) != 3:
        raise ValueError('New-train inventory changed')
    return {'version': 1, 'timeBasis': 'train-timetable-network', 'identityBasis': 'official-one-train-page',
            'railways': [HOKUSO], 'stations': stations, 'calendars': ['weekday', 'holiday'],
            'trainTypes': ['普通'], 'trips': trips,
            'inventorySha256': hashlib.sha256(INVENTORY.read_bytes()).hexdigest()}


def complete_line(base, network):
    line = json.loads(json.dumps(base))
    if line['stations'] != network['stations']:
        raise ValueError('Hokuso physical station inventory changed')
    for t in network['trips']:
        cal, typ = network['calendars'][t[0]], network['trainTypes'][t[1]]
        if typ not in line['trainTypes']:
            line['trainTypes'].append(typ)
        line['trips'].append([line['calendars'].index(cal), line['trainTypes'].index(typ), t[2], t[3],
                              line['stations'][t[3][-1][0]], t[5], t[5]])
    line['source'] = 'Exact Keisei-led baseline plus independently audited official Hokuso local train pages'
    return line


def install():
    if not INVENTORY.exists():
        return
    data = read(INVENTORY)
    if data['keiseiDetailsSha256'] != hashlib.sha256(DETAILS.read_bytes()).hexdigest():
        raise ValueError('Keisei source changed since independent Hokuso audit')
    network = supplement(data)
    line = complete_line(read(BASE), network)
    write(NETWORK, network)
    write(LINE, line)
    index = read(INDEX)
    index['lines'][HOKUSO] = {'file': 'timetables/' + LINE.name, 'timeBasis': 'train-timetable',
                              'status': 'official-independent-inventory', 'identityBasis': 'official-one-train-page',
                              'trips': len(line['trips']), 'connections': sum(len(t[3])-1 for t in line['trips'])}
    index['network'] = {'id': 'hokuso-official-local-supplement', 'file': 'timetables/' + NETWORK.name,
                        'timeBasis': 'train-timetable-network', 'trips': 3, 'railways': [HOKUSO],
                        'identityBasis': 'official-one-train-page'}
    write(INDEX, index)
    manifest_path = Path('data/transit/manifest.json')
    manifest = read(manifest_path)
    manifest['operators']['hokuso'].update({'timetableStatus': 'complete', 'trainTimetables': len(line['trips']),
                                           'independentStationBoards': 56, 'independentSourcePublications': 490,
                                           'localSupplementTrips': 3})
    manifest['operators']['shibayama'].update({'timetableStatus': 'complete', 'independentPhysicalDepartures': 122})
    write(manifest_path, manifest)
    for slug, count, evidence in [('hokuso', len(line['trips']), str(REPORT)),
                                  ('shibayama', 185, 'docs/transit/shibayama-independent-inventory.json')]:
        path = Path('data/transit') / slug / 'coverage-report.json'
        coverage = read(path)
        coverage.update({'overall': 'complete', 'trips': count, 'independentInventoryAudit': evidence,
                         'note': 'All independent operator station departures accounted; full official train pages establish identity.'})
        if slug == 'hokuso':
            coverage['connections'] = sum(len(t[3])-1 for t in line['trips'])
        write(path, coverage)


def materialize():
    install()
    from build_transit_v2 import load_all_fragments
    fragments, networks = load_all_fragments({'operators': {'hokuso': {'operator': 'manual.Operator:Hokuso'}}}, {})
    fragment_path = Path('data/transit-v2/fragments/hokuso.json')
    payload = read(fragment_path)
    old = payload['fragments']
    if old != fragments[:len(old)]:
        raise ValueError('Independent supplement would alter existing Hokuso fragments')
    payload['fragments'] = fragments
    write(fragment_path, payload)
    path = Path('data/transit-v2/network-journeys.json')
    payload = read(path)
    payload['journeys'] = [j for j in payload['journeys'] if j['sourceOperator'] != 'hokuso'] + networks
    write(path, payload)
    print(json.dumps({'hokusoFragments': len(fragments), 'localSupplementJourneys': len(networks)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--package-input', type=Path)
    p.add_argument('--cache', type=Path)
    args = p.parse_args()
    if args.package_input:
        package(args.package_input, args.cache)
    materialize()
