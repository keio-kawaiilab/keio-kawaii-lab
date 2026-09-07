#!/usr/bin/env python3
"""Reproduce every saved Asakusa journey and both boundary inventories."""
import gzip
import json
from collections import Counter
from pathlib import Path

from asakusa_boundary_runtime import NETWORK, INDEX, descriptor
from build_asakusa_boundary_network import build, TOEI
from build_transit_v2 import load_all_fragments


def verify():
    network, report = build()
    assert network == json.loads(NETWORK.read_bytes()), 'saved Asakusa network differs from primary-source reconstruction'
    assert report == json.loads(gzip.decompress(Path('docs/transit/asakusa-boundary-network-audit.json.gz').read_bytes()))
    assert json.loads(INDEX.read_bytes())['network'] == descriptor(network)
    _, expected = load_all_fragments({'operators': {'toei': {'operator': 'odpt.Operator:Toei'}}}, {})
    actual = json.loads(Path('data/transit-v2/network-journeys.json').read_bytes())['journeys']
    assert [j for j in actual if j['sourceOperator'] == 'toei'] == expected
    assert len(expected) == 1260
    assert Counter(t[0] for t in network['trips']) == {0: 651, 1: 609}
    source = json.loads(TOEI.read_bytes())
    assert {t[5].removeprefix('asakusa-verified:') for t in network['trips']} == {t[6] for t in source['trips']}
    counts = Counter(r['status'] for r in report['oshiage'])
    assert counts == {'verified-continuation': 902, 'explicit-oshiage-origin': 15, 'explicit-oshiage-terminus': 15}
    # Negatives remain genuine endpoints, never silently upgraded to through trains.
    journeys = {t[5].removeprefix('asakusa-verified:'): t for t in network['trips']}
    for row in report['oshiage']:
        if row['status'] == 'explicit-oshiage-origin':
            assert network['stations'][journeys[row['toeiTimetableId']][3][0][0]].endswith('.Oshiage')
        if row['status'] == 'explicit-oshiage-terminus':
            assert network['stations'][journeys[row['toeiTimetableId']][3][-1][0]].endswith('.Oshiage')
    assert sum(r['oshiage'] and r['sengakuji'] for r in report['journeys']) == 573
    return report['summary']


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
