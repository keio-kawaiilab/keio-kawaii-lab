#!/usr/bin/env python3
"""Install only hash-bound, independently reconciled Asakusa network data."""
import hashlib
import json
from pathlib import Path

NETWORK = Path('data/transit/toei/timetables/official-through-network.json')
INDEX = Path('data/transit/toei/timetable-index.json')


def descriptor(network):
    return {'id': 'asakusa-verified-boundary-network', 'file': 'timetables/' + NETWORK.name,
            'railways': network['railways'], 'trips': len(network['trips']),
            'timeBasis': 'train-timetable-network', 'identityBasis': network['identityBasis']}


def install():
    if not NETWORK.exists():
        return
    network = json.loads(NETWORK.read_bytes())
    if len(network['trips']) != 1260 or not network.get('sourceFilesSha256'):
        raise ValueError('Unverified Asakusa source inventory')
    for filename, expected in network['sourceFilesSha256'].items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
            raise ValueError('Asakusa boundary source changed; reconcile before installing: ' + filename)
    index = json.loads(INDEX.read_bytes())
    index['network'] = descriptor(network)
    index['version'] = max(2, index.get('version', 1))
    INDEX.write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')) + '\n')


def materialize():
    """Refresh this operator's journeys without rebuilding unrelated fragments."""
    install()
    from build_transit_v2 import load_all_fragments
    _, journeys = load_all_fragments({'operators': {'toei': {'operator': 'odpt.Operator:Toei'}}}, {})
    path = Path('data/transit-v2/network-journeys.json')
    payload = json.loads(path.read_bytes())
    payload['journeys'] = [j for j in payload['journeys'] if j['sourceOperator'] != 'toei'] + journeys
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(json.dumps({'asakusaNetworkJourneys': len(journeys)}))


if __name__ == '__main__':
    materialize()
