#!/usr/bin/env python3
"""Fail closed on incomplete source accounting or stale runtime materialization."""
import gzip
import json
from collections import Counter
from pathlib import Path

from keikyu_internal_runtime import NETWORK, CORE, apply, projections


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def verify():
    network = read(NETWORK)
    audit = read('docs/transit/keikyu-internal-network-audit.json.gz')
    stops = read('docs/transit/keikyu-internal-source-stop-times.json.gz')
    assert network['internalCoverageComplete'] is True
    assert audit['coverageComplete'] is True
    assert network['sourceSha256'] == audit['sourceSha256'] == stops['source']['sha256']
    assert audit['summary']['unclassifiedCells'] == audit['summary']['unassembledGroups'] == 0
    assert not audit['unmatchedInlineNotes']
    assert network['journeyEvidence'] == audit['trips']
    assert len(network['trips']) == audit['summary']['routeTrips'] == 2011
    assert {t[5] for t in network['trips']} == {r['id'] for r in audit['trips']}
    assert audit['summary']['throughTrips'] == 1368
    members = {m for g in audit['groups'] for m in g['members']}
    assert len(members) == 3140
    for fragment in stops['fragments']:
        if fragment['id'] not in members:
            assert not fragment['stopTimes'] and not fragment['unresolvedCells'] and not fragment['printedTrainNumber']
    tables, _ = projections(network)
    index = read('data/transit/keikyu/timetable-index.json')
    assert index['network']['file'] == 'timetables/' + NETWORK.name
    for railway, table in tables.items():
        assert table == read(Path('data/transit/keikyu') / index['lines'][railway]['file'])
    fragments = []
    for file in Path('data/transit-v2/fragments').glob('*.json'):
        fragments.extend(read(file)['fragments'])
    for f in fragments:
        if f['railway'] in CORE:
            assert f['sourceKind'] == 'exact-train-timetable'
    expected = apply(fragments, [])  # also checks every stop and retained external fingerprint
    internal = [e for e in expected if 'keikyu-official-complete-internal-network' in e['evidence']]
    external = [e for e in expected if 'keikyu-official-sengakuji-exact-sequence' in e['evidence']]
    assert len(internal) == 1590 and len(external) == 577
    by_id = {f['id']: f for f in fragments}
    actual = read('data/transit-v2/same-train-edges.json')['edges']
    pairs = {(e['fromFragment'], e['toFragment']) for e in actual}
    runtime = {tuple(e) for e in read('data/transit-v2/runtime-same-train.json')['edges']}
    for e in expected:
        assert (e['fromFragment'], e['toFragment']) in pairs
        a, b = by_id[e['fromFragment']], by_id[e['toFragment']]
        assert ('tt:' + a['timetableId'], 'tt:' + b['timetableId'], a['railway'], b['railway']) in runtime
    directions = Counter()
    for row in audit['trips']:
        for a, b in zip(row['railwayPath'], row['railwayPath'][1:]):
            directions[(row['calendar'], a, b)] += 1
    assert len(directions) == 12  # all six directed boundaries on each service calendar
    journeys = [j for j in read('data/transit-v2/network-journeys.json')['journeys'] if j['sourceOperator'] == 'keikyu']
    assert len(journeys) == len(network['trips'])
    from build_transit_v2 import load_all_fragments
    _, regenerated = load_all_fragments({'operators': {'keikyu': {'operator': 'odpt.Operator:Keikyu'}}}, {})
    assert journeys == regenerated, 'saved network journeys differ from official input'
    return {'routeJourneys': len(journeys), 'internalThroughJourneys': 1368,
            'internalRuntimeLinks': len(internal), 'verifiedExternalLinks': len(external),
            'unassembledGroups': 0, 'unclassifiedNumericCells': 0, 'calendarDirections': len(directions)}


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
