#!/usr/bin/env python3
"""Materialize retained JR official continuations; account for every fragment.

This is a snapshot assembly, NOT proof of an independently complete timetable.
Missing external legs, omitted identity-only rows and split/merge boundaries
remain explicit. Numbers, destinations and clock proximity never join trains.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
from pathlib import Path

from transit_network_db import read_json, load_network_journeys
from import_western_train_db import write_json, digest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = 'jr-official'
SOURCE = 'jr-official-continuations'


def station_key(sid):
    # JR-East's line-scoped identifiers share the physical station suffix.
    # This only compares already-authoritatively-linked rows, never finds links.
    if sid.startswith('odpt.Station:JR-East.'):
        return 'JR-East.' + sid.rsplit('.', 1)[-1]
    return sid


def minute(value):
    if value is None:
        return None
    n = int(value)
    if not 0 <= n < 1620:
        raise ValueError('Invalid source minute')
    return n + 1440 if n < 180 else n


def assemble_stops(chain):
    stops, projection = [], []
    for fragment in chain:
        indices = []
        for sid, arrival, departure in fragment['stops']:
            stop = [sid, minute(arrival), minute(departure)]
            if stops and station_key(stops[-1][0]) == station_key(sid):
                previous = stops[-1]
                if any(previous[i] is not None and stop[i] is not None and previous[i] != stop[i] for i in (1, 2)):
                    raise ValueError('Conflicting duplicate boundary event')
                stops[-1] = [previous[0], *[previous[i] if previous[i] is not None else stop[i] for i in (1, 2)]]
            else:
                stops.append(stop)
            indices.append(len(stops) - 1)
        projection.append({'fragmentId': fragment['id'], 'stopIndices': indices})
    times = [t for s in stops for t in s[1:] if t is not None]
    if times != sorted(times):
        raise ValueError('Non-monotonic source sequence')
    return stops, projection


def prove_edges(fragments, records, edges):
    by_tt = {f['timetableId']: f for f in fragments}
    by_id = {f['id']: f for f in fragments}
    adjacency = defaultdict(set)
    for r in records:
        tt = r['timetableId']
        for nxt in r.get('nextTrainTimetables', []):
            adjacency[tt].add(nxt)
        for prev in r.get('previousTrainTimetables', []):
            adjacency[prev].add(tt)
    proved = []
    for edge in edges:
        a, b = edge['fromFragment'], edge['toFragment']
        if a not in by_id or b not in by_id:
            continue
        chain = [by_id[a]['timetableId'], *edge.get('viaTimetables', []), by_id[b]['timetableId']]
        if not all(y in adjacency[x] for x, y in zip(chain, chain[1:])):
            raise ValueError('Edge lacks the stated ODPT continuation chain')
        if by_id[a]['calendar'] != by_id[b]['calendar']:
            raise ValueError('Calendar mismatch in authoritative continuation')
        proved.append({'fromFragment': a, 'toFragment': b,
                       'viaTimetables': chain[1:-1], 'sourceTimetableChain': chain,
                       'fromRailway': by_id[a]['railway'], 'toRailway': by_id[b]['railway'],
                       'evidence': 'odpt:next/previousTrainTimetable'})
    return proved, adjacency


def build(root):
    root = Path(root)
    v2 = root / 'data/transit-v2'
    fragments = read_json(v2 / 'fragments/jr-east.json')['fragments']
    sidecar = read_json(root / 'data/transit/odpt-train-identities.json')
    records = sidecar['records']
    record_by_tt = {r['timetableId']: r for r in records}
    registry = read_json(v2 / 'same-train-edges.json')['edges']
    if len({f['id'] for f in fragments}) != len(fragments):
        raise ValueError('Duplicate JR fragment ID')
    by_id = {f['id']: f for f in fragments}
    by_tt = {f['timetableId']: f for f in fragments}
    edges, adjacency = prove_edges(fragments, records, registry)
    outgoing, incoming = defaultdict(list), defaultdict(list)
    for e in edges:
        outgoing[e['fromFragment']].append(e)
        incoming[e['toFragment']].append(e)
    # Materialize unbranched portions only. A split/merge remains an explicit
    # directed edge and never becomes an arbitrary car-to-car combination.
    next_id, prev_id = {}, {}
    for e in edges:
        a, b = e['fromFragment'], e['toFragment']
        if len(outgoing[a]) == 1 and len(incoming[b]) == 1:
            next_id[a], prev_id[b] = b, a
    seen, chains = set(), []
    for fid in sorted(by_id):
        if fid in prev_id:
            continue
        chain, cur = [], fid
        while cur:
            if cur in seen:
                raise ValueError('Cyclic/repeated official fragment chain')
            seen.add(cur)
            chain.append(by_id[cur])
            cur = next_id.get(cur)
        chains.append(chain)
    if seen != by_id.keys():
        raise ValueError('Official JR continuation cycle')
    journeys, quarantine, ledger = [], [], []
    edge_by_pair = {(e['fromFragment'], e['toFragment']): e for e in edges}
    for chain in chains:
        ids = [f['id'] for f in chain]
        jid = 'jr.OfficialChain:' + digest(ids)[:24]
        try:
            stops, projections = assemble_stops(chain)
        except ValueError as error:
            quarantine.append({'id': jid, 'fragmentIds': ids, 'reason': str(error)})
            ledger.extend({'fragmentId': fid, 'journeyId': None, 'quarantineId': jid} for fid in ids)
            continue
        rails = []
        for f in chain:
            if not rails or rails[-1] != f['railway']:
                rails.append(f['railway'])
        via = [tt for a, b in zip(ids, ids[1:]) for tt in edge_by_pair[a, b]['viaTimetables']]
        head, tail = chain[0], chain[-1]
        # A builder's fallback first stop is not a published origin.
        published_origins = record_by_tt.get(head['timetableId'], {}).get('origin', [])
        origin_matches = bool(stops) and any(station_key(s) == station_key(stops[0][0]) for s in published_origins)
        destination_matches = bool(stops) and any(station_key(s) == station_key(stops[-1][0]) for s in tail.get('destination', []))
        branch = bool(incoming[head['id']] or outgoing[tail['id']])
        complete_endpoints = origin_matches and destination_matches and not branch and not via
        journeys.append({'id': jid, 'sourceKind': 'official-linked-fragments', 'sourceOperator': SOURCE,
                         'operator': 'odpt.Operator:JR-East', 'calendar': head['calendar'],
                         'railwayPath': rails, 'stops': stops, 'sourceFragmentIds': ids,
                         'sourceStopProjection': projections, 'omittedIdentityTimetables': via,
                         'publishedOrigins': published_origins, 'publishedDestinations': tail.get('destination', []),
                         'observedOrigin': stops[0][0] if stops else None,
                         'observedDestination': stops[-1][0] if stops else None,
                         'originMatchesPublished': origin_matches, 'destinationMatchesPublished': destination_matches,
                         'classification': 'through' if len(rails) > 1 else 'single-railway-segment',
                         'identityLevel': 'official-linked-fragments',
                         'hasSplitMergeBoundary': branch,
                         'publishedEndpointsCovered': complete_endpoints,
                         'inventoryCompleteness': 'not-independently-verified',
                         'runtimeActivated': False,
                         'sourceTrainNumbers': [f['trainNumber'] for f in chain],
                         'sectionTrainTypes': [f['trainType'] for f in chain]})
        ledger.extend({'fragmentId': fid, 'journeyId': jid} for fid in ids)
    external, missing_links = [], []
    for r in records:
        if r.get('sourceOperator') != 'jr-east':
            continue
        for direction, field in [('origin', 'origin'), ('destination', 'destination')]:
            for endpoint in r.get(field, []):
                if endpoint.startswith('odpt.Station:') and not endpoint.startswith('odpt.Station:JR-East.'):
                    external.append({'timetableId': r['timetableId'], 'railway': r['railway'],
                                     'calendar': r['calendars'], 'endpointRole': direction,
                                     'endpoint': endpoint, 'targetRailway': 'odpt.Railway:' + '.'.join(endpoint.split(':')[1].split('.')[:-1]),
                                     'status': 'external-full-journey-not-reconciled'})
        for field in ['previousTrainTimetables', 'nextTrainTimetables']:
            for linked in r.get(field, []):
                if linked not in by_tt:
                    missing_links.append({'timetableId': r['timetableId'], 'field': field, 'linkedTimetable': linked,
                                          'identityRecordRetained': linked in record_by_tt})
    per_line = []
    names = {r['owl:sameAs']: r.get('dc:title', '') for r in read_json(root / 'data/transit/jr-east/entities.json')['Railway']}
    for railway in sorted({f['railway'] for f in fragments}):
        rows = [f for f in fragments if f['railway'] == railway]
        per_line.append({'railway': railway, 'name': names.get(railway, ''), 'fragments': len(rows),
                         'calendars': dict(Counter(f['calendar'] for f in rows)),
                         'independentMotherSetComplete': False})
    west = read_json(v2 / 'western/network-journeys.json.gz')['journeys']
    west_jr = [j['id'] for j in west if any('JR-East.' in r for r in j['railwayPath'])]
    yahoo_checks_path = v2 / 'jr-official/yahoo-external-spot-checks.json'
    yahoo_checks = read_json(yahoo_checks_path)['checks'] if yahoo_checks_path.exists() else []
    inputs = ['data/transit-v2/fragments/jr-east.json', 'data/transit-v2/same-train-edges.json',
              'data/transit/odpt-train-identities.json', 'data/transit/jr-east/entities.json',
              'data/transit-v2/western/network-journeys.json.gz']
    audit = {'version': 1, 'scope': 'retained JR-East 40-line snapshot; not nationwide JR',
             'inputHashes': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in inputs},
             'summary': {'railways': len(per_line), 'fragments': len(fragments), 'officialEdges': len(edges),
                         'assembledJourneys': len(journeys), 'internalThroughJourneys': sum(j['classification'] == 'through' for j in journeys),
                         'sourceStopRows': sum(len(f['stops']) for f in fragments),
                         'assembledStopRows': sum(len(j['stops']) for j in journeys),
                         'quarantinedChains': len(quarantine),
                         'quarantinedFragments': sum(len(q['fragmentIds']) for q in quarantine),
                         'splitMergeEdges': sum(e['toFragment'] != next_id.get(e['fromFragment']) for e in edges),
                         'externalEndpointEvidenceRows': len(external),
                         'missingFragmentLinkReferences': len(missing_links),
                         'existingWesternJRJourneyReferences': len(west_jr),
                         'yahooExternalSpotChecks': len(yahoo_checks)},
             'snapshotAccounted': len(ledger) == len(fragments),
             'allJRComplete': False, 'independentMotherSetComplete': False,
             'runtimeActivated': False, 'lines': per_line,
             'externalTargets': dict(Counter(e['targetRailway'] for e in external)),
             'existingWesternJRJourneyIds': west_jr,
             'yahooExternalSpotCheckFile': str(yahoo_checks_path.relative_to(root)) if yahoo_checks_path.exists() else None,
             'remaining': ['independent all-station weekday/holiday inventory',
                           'external one-train full-journey collection/reconciliation',
                           'quarantined event conflicts and omitted identity-row stop coverage',
                           'split/merge car restrictions, operating-date rules and runtime validation']}
    return ({'version': 1, 'source': SOURCE, 'journeys': journeys,
             'policy': {'timeProximityMayJoin': False, 'trainNumberMayJoin': False, 'destinationMayJoin': False}},
            {'version': 1, 'fragments': sorted(ledger, key=lambda x: x['fragmentId']), 'edges': edges,
             'quarantine': quarantine, 'externalEndpoints': external, 'missingLinkedFragments': missing_links}, audit)


def install(root=ROOT):
    root = Path(root)
    if not (root / 'data/transit-v2/fragments/jr-east.json').exists():
        return None
    network, ledger, audit = build(root)
    directory = root / 'data/transit-v2' / DIRECTORY
    for name, value in [('network-journeys.json.gz', network), ('source-accounting.json.gz', ledger), ('audit.json', audit)]:
        write_json(directory / name, value)
    index_path = root / 'data/transit-v2/index.json'
    index = read_json(index_path)
    index.setdefault('networkJourneyFiles', {})[SOURCE] = DIRECTORY + '/network-journeys.json.gz'
    index.setdefault('sourceCatalogs', {})[SOURCE] = {'audit': DIRECTORY + '/audit.json', 'sourceAccounting': DIRECTORY + '/source-accounting.json.gz'}
    write_json(index_path, index)
    all_journeys = load_network_journeys(index_path.parent)
    coverage_path = index_path.parent / 'coverage.json'
    coverage = read_json(coverage_path)
    coverage.setdefault('summary', {})['networkJourneys'] = len(all_journeys)
    coverage['summary']['jrOfficialAssembledJourneys'] = len(network['journeys'])
    write_json(coverage_path, coverage)
    return audit


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(install(args.root)['summary'], ensure_ascii=False, indent=2))
