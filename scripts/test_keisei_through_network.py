#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path('.')
SCRIPT = ROOT / 'scripts/build_keisei_network_timetable.py'
REPORT = ROOT / 'data/transit/keisei/official-network-report.json'
NETWORK = ROOT / 'data/transit/keisei/timetables/official-network.json'

KEISEI_TOEI_FLOOR = 1900
TOEI_KEIKYU_FLOOR = 1150
NARITA_HANEDA_SIGNATURE_FLOOR = 200
KNOWN_EXTERNAL_UNSUPPORTED = {
    '印西牧の原', '西白井', '白井', '小室', '矢切', '北国分',
    '秋山', '松飛台', '大町', '新柴又', '芝山千代田', '井土ケ谷',
}


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
    assert keisei_toei >= KEISEI_TOEI_FLOOR, (keisei_toei, crossings)
    assert toei_keikyu >= TOEI_KEIKYU_FLOOR, (toei_keikyu, crossings)

    # Protect the longest high-value exact chain in both directions. A future
    # parser bug must not silently turn hundreds of airport through trains into
    # transfers while leaving a single token example that makes a >0 test pass.
    signatures = {
        tuple(row.get('railways') or []): int(row.get('trains') or 0)
        for row in report.get('routeSignatures') or []
    }
    narita_to_haneda = (
        'odpt.Railway:Keisei.NaritaSkyAccess',
        'odpt.Railway:Keisei.Main',
        'odpt.Railway:Keisei.Oshiage',
        'odpt.Railway:Toei.Asakusa',
        'odpt.Railway:Keikyu.Main',
        'odpt.Railway:Keikyu.Airport',
    )
    haneda_to_narita = tuple(reversed(narita_to_haneda))
    assert signatures.get(narita_to_haneda, 0) >= NARITA_HANEDA_SIGNATURE_FLOOR, signatures.get(narita_to_haneda, 0)
    assert signatures.get(haneda_to_narita, 0) >= NARITA_HANEDA_SIGNATURE_FLOOR, signatures.get(haneda_to_narita, 0)

    unsupported = set((report.get('unsupportedStations') or {}).keys())
    unexpected = unsupported - KNOWN_EXTERNAL_UNSUPPORTED
    assert not unexpected, f'new unsupported official stations appeared: {sorted(unexpected)}'

    assert network['timeBasis'] == 'train-timetable-network'
    assert network['identityBasis'] == 'Keisei official one-train timetable page'
    railways = set(network['railways'])
    assert 'odpt.Railway:Keisei.Oshiage' in railways
    assert 'odpt.Railway:Toei.Asakusa' in railways
    assert 'odpt.Railway:Keikyu.Main' in railways
    assert 'odpt.Railway:Keikyu.Airport' in railways


def main() -> int:
    test_boundary_gate()
    test_materialized_snapshot()
    print('Keisei exact through-network tests passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
