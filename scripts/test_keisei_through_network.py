#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path('.')
BASE_SCRIPT = ROOT / 'scripts/build_keisei_network_timetable.py'
EXT_SCRIPT = ROOT / 'scripts/build_keisei_extended_network.py'
REPORT = ROOT / 'data/transit/keisei/official-network-report.json'
NETWORK = ROOT / 'data/transit/keisei/timetables/official-network.json'

KEISEI_TOEI_FLOOR = 1900
TOEI_KEIKYU_FLOOR = 1150
HOKUSO_KEISEI_FLOOR = 800
SHIBAYAMA_KEISEI_FLOOR = 170
# Exact-segment projection is 870 trips in the retained snapshot. Keep enough
# headroom for timetable changes while still detecting a major regression.
HOKUSO_PROJECTED_FLOOR = 820
SHIBAYAMA_PROJECTED_FLOOR = 180
# Protect trains that actually serve both airport endpoints. These are
# direction-specific because the retained official timetable is asymmetric.
NARITA_TO_HANEDA_ENDPOINT_FLOOR = 170
HANEDA_TO_NARITA_ENDPOINT_FLOOR = 195
HOKUSO_HANEDA_SIGNATURE_FLOOR = 120

HOKUSO = 'manual.Railway:Hokuso.Hokuso'
SHIBAYAMA = 'manual.Railway:Shibayama.Shibayama'
KEISEI_MAIN = 'odpt.Railway:Keisei.Main'
KEISEI_HIGASHI_NARITA = 'odpt.Railway:Keisei.HigashiNarita'


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'could not import {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_builder():
    base = load_module(BASE_SCRIPT, 'keisei_network_builder_test')
    extension = load_module(EXT_SCRIPT, 'keisei_extended_builder_test')
    extension.install_extensions(base)
    return base


def test_boundary_gate() -> None:
    module = load_builder()

    # Existing cross-operator chain: Keisei -> Toei -> Keikyu.
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
    without_oshiage = {row for row in allowed if row[2] != '押上'}
    assert module.shortest_line_paths('青砥', '品川', graph, common, without_oshiage) == []

    # New Hokusō boundary must require the verified Keisei-Takasago gate.
    hokuso_lines = {
        KEISEI_MAIN: {'names': ['青砥', '京成高砂']},
        HOKUSO: {'names': ['京成高砂', '新柴又']},
    }
    graph, common = module.build_graph(hokuso_lines)
    hokuso_allowed = {
        (KEISEI_MAIN, HOKUSO, '京成高砂'),
        (HOKUSO, KEISEI_MAIN, '京成高砂'),
    }
    assert [KEISEI_MAIN, HOKUSO] in module.shortest_line_paths('青砥', '新柴又', graph, common, hokuso_allowed)
    assert module.shortest_line_paths('青砥', '新柴又', graph, common, set()) == []

    # New Shibayama boundary must likewise require Higashi-Narita evidence.
    shibayama_lines = {
        KEISEI_HIGASHI_NARITA: {'names': ['京成成田', '東成田']},
        SHIBAYAMA: {'names': ['東成田', '芝山千代田']},
    }
    graph, common = module.build_graph(shibayama_lines)
    shibayama_allowed = {
        (KEISEI_HIGASHI_NARITA, SHIBAYAMA, '東成田'),
        (SHIBAYAMA, KEISEI_HIGASHI_NARITA, '東成田'),
    }
    assert [KEISEI_HIGASHI_NARITA, SHIBAYAMA] in module.shortest_line_paths('京成成田', '芝山千代田', graph, common, shibayama_allowed)
    assert module.shortest_line_paths('京成成田', '芝山千代田', graph, common, set()) == []


def test_materialized_snapshot() -> None:
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    network = json.loads(NETWORK.read_text(encoding='utf-8'))
    assert report['version'] >= 2, report
    assert report['sourceTrainCount'] >= 3000, report['sourceTrainCount']
    assert report['networkTripCount'] == report['sourceTrainCount'], (report['networkTripCount'], report['sourceTrainCount'])
    assert report['skippedUnderTwoMappedStops'] == 0, report['skippedUnderTwoMappedStops']
    assert report['unresolvedPairCount'] == 0, report.get('unresolvedPairs')
    assert report.get('unsupportedStopRows') == 0, report.get('unsupportedStations')
    assert report.get('unsupportedStations') == {}, report.get('unsupportedStations')

    policy = report['identityPolicy']
    assert policy['officialTrainPageEstablishesIdentity'] is True
    assert policy['trainNumberAloneMayEstablishIdentity'] is False
    assert policy['timeProximityAloneMayEstablishIdentity'] is False
    assert policy['crossOperatorTransitionRequiresVerifiedBoundary'] is True

    crossings = {
        (row['fromRailway'], row['toRailway']): int(row['trains'])
        for row in report.get('crossOperatorTransitions') or []
    }
    def crossing_total(first: str, second: str) -> int:
        return crossings.get((first, second), 0) + crossings.get((second, first), 0)

    assert crossing_total('odpt.Railway:Keisei.Oshiage', 'odpt.Railway:Toei.Asakusa') >= KEISEI_TOEI_FLOOR, crossings
    assert crossing_total('odpt.Railway:Toei.Asakusa', 'odpt.Railway:Keikyu.Main') >= TOEI_KEIKYU_FLOOR, crossings
    assert crossing_total(KEISEI_MAIN, HOKUSO) >= HOKUSO_KEISEI_FLOOR, crossings
    assert crossing_total(KEISEI_HIGASHI_NARITA, SHIBAYAMA) >= SHIBAYAMA_KEISEI_FLOOR, crossings

    projection = report.get('externalLineProjection') or {}
    assert int(projection.get('hokusoTrips') or 0) >= HOKUSO_PROJECTED_FLOOR, projection
    assert int(projection.get('shibayamaTrips') or 0) >= SHIBAYAMA_PROJECTED_FLOOR, projection
    assert projection.get('unsupportedStopRowsAfterExtension') == 0, projection
    assert projection.get('unsupportedStationsAfterExtension') == {}, projection

    # Count the physical endpoints directly. This intentionally replaces the
    # previous route-signature assertion: before Hokusō existed, Hokusō trains
    # were being mislabelled as Narita Sky Access even when they did not serve
    # Narita Airport.
    endpoints = report.get('endpointThroughCounts') or {}
    assert int(endpoints.get('naritaToHaneda') or 0) >= NARITA_TO_HANEDA_ENDPOINT_FLOOR, endpoints
    assert int(endpoints.get('hanedaToNarita') or 0) >= HANEDA_TO_NARITA_ENDPOINT_FLOOR, endpoints

    # Protect the newly-visible Hokusō <-> Haneda through family as well.
    signatures = {
        tuple(row.get('railways') or []): int(row.get('trains') or 0)
        for row in report.get('routeSignatures') or []
    }
    hokuso_to_haneda = (
        HOKUSO,
        KEISEI_MAIN,
        'odpt.Railway:Keisei.Oshiage',
        'odpt.Railway:Toei.Asakusa',
        'odpt.Railway:Keikyu.Main',
        'odpt.Railway:Keikyu.Airport',
    )
    haneda_to_hokuso = tuple(reversed(hokuso_to_haneda))
    assert signatures.get(hokuso_to_haneda, 0) >= HOKUSO_HANEDA_SIGNATURE_FLOOR, signatures.get(hokuso_to_haneda, 0)
    assert signatures.get(haneda_to_hokuso, 0) >= HOKUSO_HANEDA_SIGNATURE_FLOOR, signatures.get(haneda_to_hokuso, 0)

    assert network['timeBasis'] == 'train-timetable-network'
    assert network['identityBasis'] == 'Keisei official one-train timetable page'
    railways = set(network['railways'])
    for railway in (
        'odpt.Railway:Keisei.Oshiage',
        'odpt.Railway:Toei.Asakusa',
        'odpt.Railway:Keikyu.Main',
        'odpt.Railway:Keikyu.Airport',
        HOKUSO,
        SHIBAYAMA,
    ):
        assert railway in railways, railway


def main() -> int:
    test_boundary_gate()
    test_materialized_snapshot()
    print('Keisei/Hokusō/Shibayama exact through-network tests passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
