#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path('.')
SCRIPT = ROOT / 'scripts/build_keisei_network_timetable.py'
REPORT = ROOT / 'data/transit/keisei/official-network-report.json'
NETWORK = ROOT / 'data/transit/keisei/timetables/official-network.json'


def load_builder():
    spec = importlib.util.spec_from_file_location('keisei_network_builder', SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError('could not import Keisei network builder')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_boundary_gate() -> None:
    module = load_builder()
    lines = {
        'odpt.Railway:Keisei.Oshiage': {'names': ['青砥', '押上']},
        'odpt.Railway:Toei.Asakusa': {'names': ['押上', '泉岳寺']},
        'odpt.Railway:Keikyu.Main': {'names': ['泉岳寺', '品川']},
    }
    graph, common = module.build_graph(lines)
    allowed = {
        ('odpt.Railway:Keisei.Oshiage', 'odpt.Railway:Toei.Asakusa', '押上'),
        ('odpt.Railway:Toei.Asakusa', 'odpt.Railway:Keisei.Oshiage', '押上'),
        ('odpt.Railway:Toei.Asakusa', 'odpt.Railway:Keikyu.Main', '泉岳寺'),
        ('odpt.Railway:Keikyu.Main', 'odpt.Railway:Toei.Asakusa', '泉岳寺'),
    }
    paths = module.shortest_line_paths('青砥', '品川', graph, common, allowed)
    assert ['odpt.Railway:Keisei.Oshiage', 'odpt.Railway:Toei.Asakusa', 'odpt.Railway:Keikyu.Main'] in paths, paths

    # Time proximity / topology alone must never jump an unverified operator boundary.
    without_oshiage = {row for row in allowed if row[2] != '押上'}
    assert module.shortest_line_paths('青砥', '品川', graph, common, without_oshiage) == []


def test_materialized_snapshot() -> None:
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    network = json.loads(NETWORK.read_text(encoding='utf-8'))
    assert report['version'] >= 2, report
    assert report['sourceTrainCount'] >= 3000, report['sourceTrainCount']
    assert report['networkTripCount'] > 0
    assert report['unresolvedPairCount'] == 0, report.get('unresolvedPairs')

    policy = report['identityPolicy']
    assert policy['officialTrainPageEstablishesIdentity'] is True
    assert policy['trainNumberAloneMayEstablishIdentity'] is False
    assert policy['timeProximityAloneMayEstablishIdentity'] is False
    assert policy['crossOperatorTransitionRequiresVerifiedBoundary'] is True

    crossings = {
        (row['fromRailway'], row['toRailway']): int(row['trains'])
        for row in report.get('crossOperatorTransitions') or []
    }
    keisei_toei = crossings.get(('odpt.Railway:Keisei.Oshiage', 'odpt.Railway:Toei.Asakusa'), 0) + crossings.get(('odpt.Railway:Toei.Asakusa', 'odpt.Railway:Keisei.Oshiage'), 0)
    toei_keikyu = crossings.get(('odpt.Railway:Toei.Asakusa', 'odpt.Railway:Keikyu.Main'), 0) + crossings.get(('odpt.Railway:Keikyu.Main', 'odpt.Railway:Toei.Asakusa'), 0)
    assert keisei_toei > 0, crossings
    assert toei_keikyu > 0, crossings

    assert network['timeBasis'] == 'train-timetable-network'
    assert network['identityBasis'] == 'Keisei official one-train timetable page'
    railways = set(network['railways'])
    assert 'odpt.Railway:Keisei.Oshiage' in railways
    assert 'odpt.Railway:Toei.Asakusa' in railways
    assert 'odpt.Railway:Keikyu.Main' in railways


def main() -> int:
    test_boundary_gate()
    test_materialized_snapshot()
    print('Keisei exact through-network tests passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
