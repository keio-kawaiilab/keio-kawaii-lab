#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import reviewed_train_evidence as reviewed


def main() -> int:
    fragments = [
        {
            'id': 'source', 'railway': 'r1', 'calendar': 'weekday', 'trainType': 'express',
            'destination': ['dest'], 'stops': [['s1', None, 100], ['s2', 104, 104]],
        },
        {
            'id': 'wrong-target', 'railway': 'r2', 'calendar': 'weekday', 'trainType': 'local',
            'destination': ['dest'], 'stops': [['b', None, 106], ['x', 110, 110]],
        },
        {
            'id': 'target', 'railway': 'r2', 'calendar': 'weekday', 'trainType': 'express',
            'destination': ['dest'], 'stops': [['b', None, 108], ['x', 112, 112]],
        },
    ]
    registry = {
        'entries': [{
            'id': 'test-evidence', 'status': 'verified-current', 'boundaryId': 'junction',
            'from': {
                'railway': 'r1', 'calendar': 'weekday', 'trainType': 'express', 'destination': 'dest',
                'containsStop': {'station': 's2', 'departure': 104},
            },
            'to': {
                'railway': 'r2', 'calendar': 'weekday', 'trainType': 'express', 'destination': 'dest',
                'firstStop': {'station': 'b', 'departure': 108},
            },
            'sourceUrls': ['https://example.invalid/official'],
        }]
    }
    indexes = {'graph': {'r1': [{
        'fromRailway': 'r1', 'toRailway': 'r2', 'station': 'Boundary',
        'boundaryId': 'junction', 'kind': 'verified-operational-junction',
    }]}}
    unresolved = [{
        'kind': 'ambiguous-boundary-fragment-alignment', 'fragment': 'source',
        'nextRailway': 'r2', 'candidateFragments': ['wrong-target', 'target'],
    }]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'registry.json'
        path.write_text(json.dumps(registry), encoding='utf-8')
        edges = reviewed.apply_reviewed_train_evidence(fragments, [], unresolved, indexes, path)
    assert len(edges) == 1, edges
    assert edges[0]['fromFragment'] == 'source' and edges[0]['toFragment'] == 'target', edges
    assert edges[0]['identityLevel'] == 'evidence-backed', edges
    assert edges[0]['evidence'][0] == 'operator-official-per-train-timetable', edges
    custom_registry = json.loads(json.dumps(registry))
    custom_registry['entries'][0]['id'] = 'test-yahoo-evidence'
    custom_registry['entries'][0]['evidenceType'] = 'third-party-route-result:yahoo-transit-zero-transfer'
    custom_registry['entries'][0]['sourceUrls'] = ['https://transit.yahoo.co.jp/example']
    custom_unresolved = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'registry.json'
        path.write_text(json.dumps(custom_registry), encoding='utf-8')
        custom_edges = reviewed.apply_reviewed_train_evidence(fragments, [], custom_unresolved, indexes, path)
    assert len(custom_edges) == 1, custom_edges
    assert custom_edges[0]['evidence'] == ['third-party-route-result:yahoo-transit-zero-transfer', 'test-yahoo-evidence'], custom_edges
    assert not unresolved, unresolved
    print('reviewed train evidence tests passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
