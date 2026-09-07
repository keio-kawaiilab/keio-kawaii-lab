#!/usr/bin/env python3
"""Reproduce independent station inventories and verify every served train."""
import hashlib
import json
import re
from pathlib import Path

from audit_hokuso_independent_inventory import audit
from collect_hokuso_independent_inventory import parse_board, parse_detail, REF, clean
from hokuso_independent_runtime import INVENTORY, ARCHIVE, REPORT, NETWORK, LINE, BASE, INDEX, DETAILS, read, supplement, complete_line
from build_asakusa_boundary_network import minute
from audit_keisei_asakusa_gap import normalize_station_name
import build_keisei_extended_network as extension


def verify():
    data, archive = read(INVENTORY), read(ARCHIVE)
    assert data['keiseiDetailsSha256'] == hashlib.sha256(DETAILS.read_bytes()).hexdigest()
    old_trains = read(DETAILS)['trains']
    old = {t['key']: t for t in old_trains}
    trains = {t['key']: t for t in data['trains']}
    assert len(trains) == len(data['trains']) == 490
    refs = set()
    for row in data['boardsAndReferences']:
        source = archive[row['url']]
        assert hashlib.sha256(source.encode()).hexdigest() == row['sourceSha256']
        station = data['stationNames'][row['stationIndex']]
        if row['kind'] == 'operator-board':
            assert parse_board(source) == row['departures']
            header = re.search(r'<div class="name">(.*?)</div>', source, re.S)
            station_label = re.search(r'■北総線\s+(.+?)\s+◇', clean(header[1])) if header else None
            assert station_label and station == normalize_station_name(station_label[1]), row['url']
            assert ('土休日' in clean(header[1])) == (row['calendar'] == 1)
        else:
            actual = [dict(zip(['tx', 'sf', 'date', 'time', 'dw'], m)) for m in REF.findall(source)]
            assert actual == row['references']
            for ref in actual:
                key = ref['dw'] + ':' + ref['tx']
                refs.add(key)
                clock = ref['time'].zfill(4)
                departure = minute(clock[:-2] + ':' + clock[-2:])
                assert any(normalize_station_name(s['station']) == station and minute(s['departure']) == departure for s in trains[key]['stops']), (key, station, departure)
    assert refs == set(trains)
    for key, t in trains.items():
        if key in data['newSourceKeys']:
            source = archive[t['url']]
            assert parse_detail(source, t['url'], t['reference']) == t
        else:
            assert t == old[key]
    report = audit(data)
    assert report == read(REPORT) and report['coverageComplete']
    assert report['summary']['publishedDepartures'] == 4572
    module = extension.load_base()
    extension.install_extensions(module)
    names = extension.station_names_by_id(module, extension.load_lines(module))
    keisei = read(extension.NETWORK_PATH)
    indices = {t['key']: i for i, t in enumerate(old_trains)}
    for key in refs-set(data['newSourceKeys']):
        t = keisei['trips'][indices[key]]
        actual = [[names[keisei['stations'][s[0]]], minute(s[1]), minute(s[2])] for s in t[3]]
        expected = [[normalize_station_name(s['station']), minute(s['arrival']), minute(s['departure'])] for s in trains[key]['stops']]
        assert actual == expected, key
        assert keisei['calendars'][t[0]] == trains[key]['calendar']
    baseline = extension.project_line(keisei, extension.HOKUSO, extension.HOKUSO_STATIONS, names)
    assert baseline == read(BASE)
    network = supplement(data)
    assert network == read(NETWORK)
    assert complete_line(baseline, network) == read(LINE)
    index = read(INDEX)
    assert index['lines'][extension.HOKUSO]['file'] == 'timetables/' + LINE.name
    assert index['lines'][extension.HOKUSO]['trips'] == 873
    assert index['network']['file'] == 'timetables/' + NETWORK.name and index['network']['trips'] == 3
    from build_transit_v2 import load_all_fragments
    fragments, networks = load_all_fragments({'operators': {'hokuso': {'operator': 'manual.Operator:Hokuso'}}}, {})
    assert fragments == read('data/transit-v2/fragments/hokuso.json')['fragments']
    assert [j for j in read('data/transit-v2/network-journeys.json')['journeys'] if j['sourceOperator'] == 'hokuso'] == networks
    assert len(networks) == 3
    return report['summary']


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
