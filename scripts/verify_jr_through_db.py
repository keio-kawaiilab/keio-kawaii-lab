#!/usr/bin/env python3
"""Independently compare each retained JR stop event and continuation proof."""
from collections import Counter
import hashlib
from pathlib import Path

from transit_network_db import read_json, load_network_journeys
from build_jr_through_db import station_key, minute, prove_edges, ROOT, SOURCE


def verify(root=ROOT, network_override=None):
    root = Path(root)
    directory = root / 'data/transit-v2'
    audit = read_json(directory / 'jr-official/audit.json')
    for name, expected in audit['inputHashes'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
    fs = read_json(directory / 'fragments/jr-east.json')['fragments']
    fragments = {f['id']: f for f in fs}
    net = network_override if network_override is not None else read_json(directory / 'jr-official/network-journeys.json.gz')
    ledger = read_json(directory / 'jr-official/source-accounting.json.gz')
    records = read_json(root / 'data/transit/odpt-train-identities.json')['records']
    edges = read_json(directory / 'same-train-edges.json')['edges']
    proven, adjacency = prove_edges(fs, records, edges)
    assert proven == ledger['edges']
    pairs = {(e['fromFragment'], e['toFragment']) for e in proven}
    available_pairs = {(fragments[a]['timetableId'], fragments[b]['timetableId']) for a, b in pairs}
    retained_tt = {f['timetableId'] for f in fs}
    for a, successors in adjacency.items():
        for b in successors:
            if a in retained_tt and b in retained_tt:
                assert (a, b) in available_pairs, 'Unaccounted available official link'
    counts = Counter()
    journey_ids, represented_edges = set(), set()
    for j in net['journeys']:
        assert j['id'] not in journey_ids
        journey_ids.add(j['id'])
        assert j['runtimeActivated'] is False
        ids = j['sourceFragmentIds']
        assert [p['fragmentId'] for p in j['sourceStopProjection']] == ids
        assert len({fragments[f]['calendar'] for f in ids}) == 1
        assert j['calendar'] == fragments[ids[0]]['calendar']
        path = []
        for fid in ids:
            rail = fragments[fid]['railway']
            if not path or path[-1] != rail:
                path.append(rail)
        assert path == j['railwayPath']
        for pair in zip(ids, ids[1:]):
            assert pair in pairs
            represented_edges.add(pair)
        used = set()
        for fid, projection in zip(ids, j['sourceStopProjection']):
            counts[fid] += 1
            original = fragments[fid]['stops']
            positions = projection['stopIndices']
            assert len(original) == len(positions)
            assert positions == sorted(positions)
            for source, position in zip(original, positions):
                target = j['stops'][position]
                used.add(position)
                assert station_key(source[0]) == station_key(target[0])
                for column in (1, 2):
                    if source[column] is not None:
                        assert minute(source[column]) == target[column], 'Altered source event'
        assert used == set(range(len(j['stops']))), 'Invented stop'
        # Each available output event must be backed by at least one source
        # event; a null source arrival must not be filled by interpolation.
        support = set()
        for p in j['sourceStopProjection']:
            for stop, pos in zip(fragments[p['fragmentId']]['stops'], p['stopIndices']):
                for column in (1, 2):
                    if stop[column] is not None:
                        support.add((pos, column, minute(stop[column])))
        for pos, stop in enumerate(j['stops']):
            for column in (1, 2):
                if stop[column] is not None:
                    assert (pos, column, stop[column]) in support, 'Invented time'
    for q in ledger['quarantine']:
        counts.update(q['fragmentIds'])
    assert counts == Counter(fragments.keys()), 'Missing/duplicated source fragment'
    assert len(ledger['fragments']) == len(fragments)
    assert set(x['fragmentId'] for x in ledger['fragments']) == set(fragments)
    for row in ledger['fragments']:
        if row['journeyId'] is not None:
            assert row['journeyId'] in journey_ids
    assert audit['allJRComplete'] is False
    assert audit['summary']['assembledJourneys'] == len(net['journeys'])
    assert len(pairs - represented_edges) == audit['summary']['splitMergeEdges']
    if network_override is None:
        loaded = load_network_journeys(directory)
        assert sum(j.get('sourceOperator') == SOURCE for j in loaded) == len(net['journeys'])
    return audit['summary']


if __name__ == '__main__':
    import json
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
