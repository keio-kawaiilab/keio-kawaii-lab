#!/usr/bin/env python3
"""Check every operator-published Hokuso departure against whole train pages."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from build_asakusa_boundary_network import minute, validate_chronology
from build_keisei_extended_network import HOKUSO_STATIONS
from audit_keisei_asakusa_gap import normalize_station_name


def direction_for(seq, train, names):
    if len(seq) >= 2:
        return 1 if names.index(seq[0][0]) > names.index(seq[-1][0]) else 2
    # The shared-corridor board also publishes Skyliners at Shin-Kamagaya.
    # Keep these accounted; their full official pages run airport <-> Ueno.
    if train.get('trainType') == 'スカイライナー' and seq[0][0] == '新鎌ヶ谷':
        if train['stops'][0]['station'] == '京成上野':
            return 2
        if train['stops'][-1]['station'] == '京成上野':
            return 1
    raise ValueError('Cannot establish published corridor direction: ' + train['key'])


def audit(data):
    names = [s[0] for s in HOKUSO_STATIONS]
    groups = defaultdict(list)
    for t in data['trains']:
        seq = [[normalize_station_name(s['station']), minute(s['arrival']), minute(s['departure'])] for s in t['stops'] if normalize_station_name(s['station']) in names]
        if not seq:
            raise ValueError('Hokuso source page lacks a local sequence: ' + t['key'])
        validate_chronology(seq)
        direction = direction_for(seq, t, names)
        if any((names.index(b[0]) - names.index(a[0])) * (1 if direction == 2 else -1) <= 0 for a, b in zip(seq, seq[1:])):
            raise ValueError('Source crosses the same Hokuso line more than once')
        key = json.dumps([t['calendar'], seq], ensure_ascii=False, separators=(',', ':'))
        groups[key].append(t)
    by_departure = defaultdict(set)
    physical = []
    for key, trains in groups.items():
        calendar, seq = json.loads(key)
        direction = direction_for(seq, trains[0], names)
        gid = 'hokuso-independent:' + hashlib.sha256(key.encode()).hexdigest()[:24]
        physical.append({'id': gid, 'calendar': calendar, 'direction': direction, 'stops': seq,
                         'sourceKeys': [t['key'] for t in trains]})
        for s in seq:
            if s[2] is not None:
                by_departure[(calendar, s[0], direction, s[2])].add(gid)
    boards = [b for b in data['boardsAndReferences'] if b['kind'] == 'operator-board']
    expected_inventory = {(i,d,c) for i in range(15) for d in (1,2) for c in (0,1) if (i,d) not in {(0,1),(14,2)}}
    assert {(b['stationIndex'], b['travelDirection'], b['calendar']) for b in boards} == expected_inventory
    by_group = {x['id']: x for x in physical}
    seen, missing, ambiguous = set(), [], []
    evidence = []
    for b in boards:
        station = names[b['stationIndex']]
        calendar = 'weekday' if b['calendar'] == 0 else 'holiday'
        for row in b['departures']:
            key = (calendar, station, b['travelDirection'], row['minute'])
            if key in seen:
                raise ValueError('Duplicate independent board departure')
            seen.add(key)
            candidates = sorted(by_departure.get(key, []))
            if not candidates:
                missing.append(list(key))
            if len(candidates) > 1:
                ambiguous.append({'departure': list(key), 'candidates': candidates})
            evidence.append({'departure': list(key), 'journeys': candidates, 'sourceUrl': b['url'],
                             'literalMarker': row['literalMarker']})
    # A westbound departure from Takasago is on Keisei, and an eastbound
    # departure from Nihon-Idai is on Sky Access beyond this corridor.
    # Both remain in their complete train pages, not in a Hokuso station board.
    outside = sorted(k for k in set(by_departure)-seen if (k[1], k[2]) in {('京成高砂', 1), ('印旛日本医大', 2)})
    extra = sorted(set(by_departure)-seen-set(outside))
    return {'version': 1, 'coverageComplete': not(missing or ambiguous or extra),
            'summary': {'independentStationBoards': len(boards), 'publishedDepartures': len(seen),
                        'physicalTrains': len(physical), 'sourcePublications': len(data['trains']),
                        'newSourcePublications': len(data['newSourceKeys']), 'missingDepartures': len(missing),
                        'ambiguousDepartures': len(ambiguous), 'extraDepartures': len(extra),
                        'outboundBeyondCorridorDepartures': len(outside)},
            'missingDepartures': missing, 'ambiguousDepartures': ambiguous,
            'extraDepartures': [list(k) for k in extra], 'outboundBeyondCorridorDepartures': [list(k) for k in outside],
            'journeys': physical, 'departureEvidence': evidence}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = audit(json.loads(args.input.read_bytes()))
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['coverageComplete'] else 1)
