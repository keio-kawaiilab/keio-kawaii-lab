"""Validate exact published terminal events instead of fabricating a station board."""
import json
from collections import Counter
from pathlib import Path

from keikyu_internal_runtime import NETWORK, projections


def verify_exact_terminal(table):
    if table.get('identityBasis') != 'official-keikyu-network-projection':
        return None
    network = json.loads(NETWORK.read_text())
    if network.get('internalCoverageComplete') is not True:
        raise ValueError('Incomplete official network cannot bypass terminal repair')
    tables, _ = projections(network)
    if table != tables['odpt.Railway:Keikyu.Main']:
        raise ValueError('Official Main projection changed or lost a terminal event')
    counts = Counter()
    for trip in table['trips']:
        service = 'weekday' if trip[0] == 0 else 'holiday'
        stops = trip[3]
        for side, stop in [('starts', stops[0]), ('ends', stops[-1])]:
            if table['stations'][stop[0]].endswith('.Sengakuji'):
                if (stop[2] if side == 'starts' else stop[1]) is None:
                    raise ValueError('Missing exact Sengakuji departure/arrival event')
                counts[(service, side)] += 1
    if any(counts[(service, side)] <= 0 for service in ['weekday', 'holiday'] for side in ['starts', 'ends']):
        raise ValueError('A service calendar/direction lost its exact terminal trains')
    ends = {service: counts[(service, 'ends')] for service in ['weekday', 'holiday']}
    return {'repairMode': 'verified-exact-network-no-repair-needed',
            'sourceSha256': network['sourceSha256'], 'beforeSengakujiEnds': ends,
            'afterSengakujiEnds': ends, 'patch': {'syntheticRows': 0},
            'exactTerminalCounts': {service: {side: counts[(service, side)] for side in ['starts', 'ends']}
                                    for service in ['weekday', 'holiday']}}
