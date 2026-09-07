#!/usr/bin/env python3
"""Verify every published Sengakuji continuation, and reject the four transfers."""
import argparse
import hashlib
import json
import urllib.request
from collections import Counter
from pathlib import Path

from verify_keikyu_internal_network import verify as verify_internal, read
from keikyu_internal_runtime import NETWORK


def verify(current_source=False):
    internal = verify_internal()
    audit = read('docs/transit/sengakuji-published-sequence-audit.json')
    network = read(NETWORK)
    fragments = read('data/transit-v2/fragments/keikyu.json')['fragments']
    fragments += read('data/transit-v2/fragments/toei.json')['fragments']
    by_id = {f['id']: f for f in fragments}
    edges = read('data/transit-v2/same-train-edges.json')['edges']
    member = {f: row['id'] for row in network['journeyEvidence'] for f in row['members']}
    verified = [e for e in edges if 'keikyu-official-sengakuji-exact-sequence' in e.get('evidence', [])]
    assert len(verified) == 577
    by_candidate = {e['evidence'][1]: e for e in verified}
    directions = Counter()
    transfers = []
    for row in audit['results']:
        if row['publishedSequenceStatus'] == 'both-local-published-sequence-singleton':
            assert row['candidateId'] in by_candidate
            directions[(row['calendar'], row['direction'])] += 1
        else:
            assert row['publishedSequenceStatus'] == 'official-transfer-via-nishimagome'
            assert row['candidateId'] not in by_candidate
            columns = row['supportingOfficialColumns'][row['keikyuSequenceMatches'][0]]
            journeys = {member[x] for x in columns}
            assert len(journeys) == 1
            jid = next(iter(journeys))
            source_ids = {f['id'] for f in fragments if f.get('trainId') == jid}
            for edge in edges:
                if edge['fromFragment'] in source_ids:
                    target = by_id.get(edge['toFragment'], {})
                    assert target.get('railway') != 'odpt.Railway:Toei.Asakusa', 'terminating train falsely continued'
            transfers.append(row['candidateId'])
    assert len(transfers) == 4 and len(directions) == 4
    if current_source:
        sources = audit['connectionSources'] + [{'url': 'https://www.keikyu.co.jp/ride/kakueki/pdf/schedule_all.pdf',
                                                'sha256': network['sourceSha256']}]
        for source in sources:
            request = urllib.request.Request(source['url'], headers={'User-Agent': 'Mozilla/5.0 transit-source-verification'})
            with urllib.request.urlopen(request, timeout=60) as response:
                digest = hashlib.sha256(response.read()).hexdigest()
            if digest != source['sha256']:
                raise ValueError('Official source revision changed: ' + source['url'])
    return {'continuations': len(verified), 'explicitTransfers': len(transfers), 'unresolvedPublishedColumns': 0,
            'calendarDirections': [{'calendar': k[0], 'direction': k[1], 'count': v} for k, v in sorted(directions.items())],
            'internal': internal, 'currentOfficialSourcesChecked': current_source}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-current-source', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.verify_current_source), ensure_ascii=False, indent=2))
