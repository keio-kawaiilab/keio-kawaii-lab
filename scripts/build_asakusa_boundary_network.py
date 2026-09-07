#!/usr/bin/env python3
"""Join independent Asakusa trains only at independently proven operator boundaries.

Oshiage identity requires an official one-train page crossing the boundary and
the entire ordered Asakusa sequence, with every observed arrival/departure exact.
Repeated one-train publications are alternatives, never extra physical trains;
all alternatives must give the identical northern continuation or the join fails.
Sengakuji uses the separate 577-continuation / 4-transfer source audit.
"""
import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from audit_keisei_asakusa_gap import calendar_key, normalize_station_name, station_name_map
from keikyu_internal_runtime import NETWORK

TOEI = Path('data/transit/toei/timetables/899209dea5fc3a.json')
DETAILS = Path('data/transit/keisei/official-train-details.json')
KEISEI = Path('data/transit/keisei/timetables/official-network.json')
IDENTITIES = Path('data/transit/odpt-train-identities.json')
ORIGINS = Path('docs/transit/oshiage-official-origin-markers.json')
ASAKUSA = 'odpt.Railway:Toei.Asakusa'


def read(path):
    return json.loads(Path(path).read_bytes())


def minute(value):
    if value is None:
        return None
    if isinstance(value, str):
        h, m = value.split(':')
        value = int(h) * 60 + int(m)
    return value + 1440 if value < 180 else value


def exact_local_sequence(local, published):
    if [s[0] for s in local] != [s[0] for s in published]:
        return False
    for a, b in zip(local, published):
        for event in (1, 2):
            if a[event] is not None and a[event] != b[event]:
                return False
    return True


def join(a, b):
    """Merge one explicitly proven common boundary; never manufacture a dwell."""
    if a['stops'][-1][0] != b['stops'][0][0]:
        raise ValueError('Proven journeys do not share a physical boundary')
    left, right = a['stops'][-1], b['stops'][0]
    merged = [left[0]]
    for event in (1, 2):
        if left[event] is not None and right[event] is not None and left[event] != right[event]:
            raise ValueError('Conflicting published boundary event')
        merged.append(left[event] if left[event] is not None else right[event])
    return {'stops': a['stops'][:-1] + [merged] + b['stops'][1:], 'links': a['links'] + b['links']}


def validate_chronology(stops):
    previous = None
    for stop in stops:
        for t in stop[1:]:
            if t is not None:
                if previous is not None and t < previous:
                    raise ValueError('Published joined sequence has a time regression')
                previous = t


def build():
    toei, details, keisei = map(read, [TOEI, DETAILS, KEISEI])
    keikyu = read(NETWORK)
    boundary = read('docs/transit/sengakuji-published-sequence-audit.json')
    from save_keikyu_recovery_checkpoint import verify_boundary
    verify_boundary(boundary, read('docs/transit/sengakuji-unfiltered-column-audit.json'))
    if hashlib.sha256(TOEI.read_bytes()).hexdigest() != boundary['toeiSourceSha256']:
        raise ValueError('Asakusa source changed since Sengakuji reconciliation')
    names = station_name_map()
    for path in ['data/transit/hokuso/entities.json', 'data/transit/shibayama/entities.json']:
        for station in read(path)['Station']:
            names[station['owl:sameAs']] = normalize_station_name(station['dc:title'])
    origins = {s['calendar']: s for s in read(ORIGINS)['sources']}
    # Add the canonical Keikyu full-network names, which include physical aliases.
    for station in keikyu['stations']:
        if station not in names:
            raise ValueError('Unknown Keikyu station identity')
    id_by_name = {name: sid for sid, name in names.items()}
    for sid in keisei['stations'] + keikyu['stations'] + toei['stations']:
        id_by_name[names[sid]] = sid
    toei_names = {names[s] for s in toei['stations']}
    local = {}
    by_shape = defaultdict(list)
    for t in toei['trips']:
        tid = t[6]
        seq = [[names[toei['stations'][s[0]]], minute(s[1]), minute(s[2])] for s in t[3]]
        cal = calendar_key(toei['calendars'][t[0]])
        local[tid] = {'calendar': cal, 'stops': seq, 'links': [[ASAKUSA] for _ in seq[1:]], 'trip': t}
        by_shape[(cal, tuple(s[0] for s in seq))].append(tid)
    if len(local) != 1260 or len(details['trains']) != len(keisei['trips']):
        raise ValueError('Independent source inventory changed')

    alternatives = defaultdict(list)
    source_matches = []
    for index, (source, t) in enumerate(zip(details['trains'], keisei['trips'])):
        raw = [[normalize_station_name(s['station']), minute(s['arrival']), minute(s['departure'])] for s in source['stops']]
        projected = [[names[keisei['stations'][s[0]]], minute(s[1]), minute(s[2])] for s in t[3]]
        if raw != projected or source['calendar'] != calendar_key(keisei['calendars'][t[0]]):
            raise ValueError('Keisei network no longer exactly projects source page: ' + source['key'])
        if not any(s[0] == '押上' for s in raw):
            continue
        oi = next(i for i, s in enumerate(raw) if s[0] == '押上')
        before = oi > 0 and raw[oi-1][0] in toei_names
        after = oi+1 < len(raw) and raw[oi+1][0] in toei_names
        if not ((before and oi+1 < len(raw)) or (after and oi > 0)):
            continue  # Keisei-only origins/termini at Oshiage are not through proof.
        published = [s for s in raw if s[0] in toei_names]
        candidates = [tid for tid in by_shape[(source['calendar'], tuple(s[0] for s in published))]
                      if exact_local_sequence(local[tid]['stops'], published)]
        if len(candidates) != 1:
            raise ValueError('Official cross-Oshiage source lacks a unique complete Toei sequence: ' + source['key'])
        tid = candidates[0]
        all_links = [[keisei['railways'][r] for r in rails] for rails in t[4]]
        north = {'stops': raw[oi:] if before else raw[:oi+1],
                 'links': all_links[oi:] if before else all_links[:oi]}
        direction = 'toei-to-keisei' if before else 'keisei-to-toei'
        alternatives[tid].append({'segment': north, 'direction': direction,
                                  'sourceKey': source['key'], 'sourceUrl': source['url'], 'sourceIndex': index})
        source_matches.append(source['key'])

    oshiage = []
    osh_join = {}
    for tid, row in local.items():
        starts = row['stops'][0][0] == '押上'
        ends = row['stops'][-1][0] == '押上'
        if not starts and not ends:
            continue
        candidates = alternatives[tid]
        if candidates:
            first = candidates[0]
            if any(c['segment'] != first['segment'] or c['direction'] != first['direction'] for c in candidates):
                raise ValueError('Different northern continuations claim the same independent Toei train: ' + tid)
            osh_join[tid] = first
            oshiage.append({'toeiTimetableId': tid, 'calendar': row['calendar'], 'status': 'verified-continuation',
                            'direction': first['direction'], 'sourcePublications': [{k: c[k] for k in ['sourceKey', 'sourceUrl', 'sourceIndex']} for c in candidates],
                            'matchedAsakusaStops': len(row['stops'])})
        else:
            side = 'origin' if starts else 'destination'
            if starts:
                board = origins[row['calendar']]
                departure = row['stops'][0][2]
                peers = [x for x in local.values() if x['calendar'] == row['calendar']
                         and x['stops'][0][0] == '押上' and x['stops'][0][2] == departure]
                if departure not in board['explicitOriginDepartureMinutes'] or len(peers) != 1:
                    raise ValueError('Missing explicit singleton station-origin marker: ' + tid)
                evidence = {'sourceUrl': board['url'], 'marker': '▲', 'departureMinute': departure}
            else:
                if row['trip'][4] != 'odpt.Station:Toei.Asakusa.Oshiage':
                    raise ValueError('Unresolved boundary is not a published Oshiage terminus: ' + tid)
                evidence = {'sourceFile': str(TOEI), 'destination': row['trip'][4]}
            oshiage.append({'toeiTimetableId': tid, 'calendar': row['calendar'],
                            'status': 'explicit-oshiage-origin' if starts else 'explicit-oshiage-terminus',
                            'originOrDestinationEvidence': evidence})
    if len(oshiage) != 932 or len(osh_join) != 902:
        raise ValueError('Oshiage inventory changed; review all positive and negative cases')

    member = {f: row['id'] for row in keikyu['journeyEvidence'] for f in row['members']}
    ky_trips = {t[5]: t for t in keikyu['trips']}
    sg_join = {}
    for row in boundary['results']:
        if row['publishedSequenceStatus'] != 'both-local-published-sequence-singleton':
            continue
        tid = row['toeiSequenceMatches'][0]
        columns = row['supportingOfficialColumns'][row['keikyuSequenceMatches'][0]]
        groups = {member[f] for f in columns}
        if len(groups) != 1 or tid in sg_join:
            raise ValueError('Ambiguous Sengakuji physical train')
        jid = next(iter(groups))
        t = ky_trips[jid]
        segment = {'stops': [[names[keikyu['stations'][s[0]]], minute(s[1]), minute(s[2])] for s in t[3]],
                   'links': [[keikyu['railways'][r] for r in rs] for rs in t[4]]}
        sg_join[tid] = {'segment': segment, 'direction': row['direction'], 'journeyId': jid, 'candidateId': row['candidateId']}

    trips, reports = [], []
    rails = sorted(set(keisei['railways']) | set(keikyu['railways']) | {ASAKUSA})
    station_ids = sorted(set(id_by_name.values()))
    station_index = {sid: i for i, sid in enumerate(station_ids)}
    for tid, row in local.items():
        combined = {'stops': row['stops'], 'links': row['links']}
        osh, sg = osh_join.get(tid), sg_join.get(tid)
        if osh:
            combined = join(combined, osh['segment']) if osh['direction'] == 'toei-to-keisei' else join(osh['segment'], combined)
        if sg:
            combined = join(combined, sg['segment']) if sg['direction'] == 'toei-to-keikyu' else join(sg['segment'], combined)
        validate_chronology(combined['stops'])
        stops = [[station_index[id_by_name[s[0]]], s[1], s[2]] for s in combined['stops']]
        links = [[rails.index(r) for r in rs] for rs in combined['links']]
        trips.append([0 if row['calendar'] == 'weekday' else 1, 0, row['trip'][2], stops, links, 'asakusa-verified:' + tid])
        reports.append({'toeiTimetableId': tid, 'oshiage': osh is not None, 'sengakuji': sg is not None,
                        'keikyuJourneyId': sg['journeyId'] if sg else None, 'stopCount': len(stops)})
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [TOEI, DETAILS, KEISEI, IDENTITIES, NETWORK, ORIGINS]}
    network = {'version': 1, 'timeBasis': 'train-timetable-network', 'source': 'Independent Toei/Keikyu timetables + Keisei official one-train pages',
               'identityBasis': 'whole-local-sequence-and-explicit-published-boundary-proof',
               'calendars': ['odpt.Calendar:Weekday', 'odpt.Calendar:SaturdayHoliday'], 'trainTypes': [''],
               'stations': station_ids, 'railways': rails, 'trips': trips, 'sourceFilesSha256': hashes}
    report = {'version': 1, 'scope': 'All 1260 independent Asakusa trains and their proven Oshiage/Sengakuji continuations; not independent Hokuso/Shibayama completeness',
              'sourceFilesSha256': hashes, 'summary': {'asakusaTrains': len(trips), 'oshiageContinuations': len(osh_join),
              'oshiageOriginsOrTermini': len(oshiage)-len(osh_join), 'sengakujiContinuations': len(sg_join),
              'matchedKeiseiSourcePublications': len(source_matches), 'unresolvedOshiageColumns': 0},
              'oshiage': oshiage, 'journeys': reports,
              'policy': {'trainNumberAloneProvesIdentity': False, 'timeProximityProvesIdentity': False,
                         'entireOrderedAsakusaSequenceRequired': True, 'allObservedArrivalDepartureEventsRequired': True,
                         'conflictingContinuationAlternativesRejected': True}}
    return network, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--network-output', required=True)
    parser.add_argument('--report-output', required=True)
    args = parser.parse_args()
    network, report = build()
    Path(args.network_output).write_text(json.dumps(network, ensure_ascii=False, separators=(',', ':')) + '\n')
    raw = json.dumps(report, ensure_ascii=False, indent=2).encode()
    Path(args.report_output).write_bytes(gzip.compress(raw, mtime=0) if args.report_output.endswith('.gz') else raw)
    print(json.dumps(report['summary'], ensure_ascii=False))
