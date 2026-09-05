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
HOKUSO_PROJECTED_FLOOR = 820
SHIBAYAMA_PROJECTED_FLOOR = 180
NARITA_TO_HANEDA_ENDPOINT_FLOOR = 170
HANEDA_TO_NARITA_ENDPOINT_FLOOR = 195
HOKUSO_HANEDA_SIGNATURE_FLOOR = 120
SHIBAYAMA_TO_HANEDA_SIGNATURE_FLOOR = 2
HANEDA_TO_SHIBAYAMA_SIGNATURE_FLOOR = 7
OSHIAGE_KURIHAMA_SIGNATURE_FLOOR = 70
OSHIAGE_ZUSHI_SIGNATURE_FLOOR = 1
MATSUDO_CHIBA_SIGNATURE_FLOOR = 100
CHIHARA_CHIBA_SIGNATURE_FLOOR = 140

HOKUSO = 'manual.Railway:Hokuso.Hokuso'
SHIBAYAMA = 'manual.Railway:Shibayama.Shibayama'
KEISEI_MAIN = 'odpt.Railway:Keisei.Main'
KEISEI_OSHIAGE = 'odpt.Railway:Keisei.Oshiage'
KEISEI_HIGASHI_NARITA = 'odpt.Railway:Keisei.HigashiNarita'
KEISEI_MATSUDO = 'odpt.Railway:Keisei.Matsudo'
KEISEI_CHIBA = 'odpt.Railway:Keisei.Chiba'
KEISEI_CHIHARA = 'odpt.Railway:Keisei.Chihara'
TOEI_ASAKUSA = 'odpt.Railway:Toei.Asakusa'
KEIKYU_MAIN = 'odpt.Railway:Keikyu.Main'
KEIKYU_AIRPORT = 'odpt.Railway:Keikyu.Airport'
KEIKYU_KURIHAMA = 'odpt.Railway:Keikyu.Kurihama'
KEIKYU_ZUSHI = 'odpt.Railway:Keikyu.Zushi'


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

    lines = {
        KEISEI_OSHIAGE: {'names': ['青砥', '押上']},
        TOEI_ASAKUSA: {'names': ['押上', '泉岳寺']},
        KEIKYU_MAIN: {'names': ['泉岳寺', '品川']},
    }
    graph, common = module.build_graph(lines)
    allowed = {
        (KEISEI_OSHIAGE, TOEI_ASAKUSA, '押上'),
        (TOEI_ASAKUSA, KEISEI_OSHIAGE, '押上'),
        (TOEI_ASAKUSA, KEIKYU_MAIN, '泉岳寺'),
        (KEIKYU_MAIN, TOEI_ASAKUSA, '泉岳寺'),
    }
    paths = module.shortest_line_paths('青砥', '品川', graph, common, allowed)
    assert [KEISEI_OSHIAGE, TOEI_ASAKUSA, KEIKYU_MAIN] in paths, paths
    without_oshiage = {row for row in allowed if row[2] != '押上'}
    assert module.shortest_line_paths('青砥', '品川', graph, common, without_oshiage) == []

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

    assert crossing_total(KEISEI_OSHIAGE, TOEI_ASAKUSA) >= KEISEI_TOEI_FLOOR, crossings
    assert crossing_total(TOEI_ASAKUSA, KEIKYU_MAIN) >= TOEI_KEIKYU_FLOOR, crossings
    assert crossing_total(KEISEI_MAIN, HOKUSO) >= HOKUSO_KEISEI_FLOOR, crossings
    assert crossing_total(KEISEI_HIGASHI_NARITA, SHIBAYAMA) >= SHIBAYAMA_KEISEI_FLOOR, crossings

    projection = report.get('externalLineProjection') or {}
    assert int(projection.get('hokusoTrips') or 0) >= HOKUSO_PROJECTED_FLOOR, projection
    assert int(projection.get('shibayamaTrips') or 0) >= SHIBAYAMA_PROJECTED_FLOOR, projection
    assert projection.get('unsupportedStopRowsAfterExtension') == 0, projection
    assert projection.get('unsupportedStationsAfterExtension') == {}, projection

    endpoints = report.get('endpointThroughCounts') or {}
    assert int(endpoints.get('naritaToHaneda') or 0) >= NARITA_TO_HANEDA_ENDPOINT_FLOOR, endpoints
    assert int(endpoints.get('hanedaToNarita') or 0) >= HANEDA_TO_NARITA_ENDPOINT_FLOOR, endpoints

    signatures = {
        tuple(row.get('railways') or []): int(row.get('trains') or 0)
        for row in report.get('routeSignatures') or []
    }

    def require_signature(signature: tuple[str, ...], minimum: int) -> None:
        actual = signatures.get(signature, 0)
        assert actual >= minimum, {'signature': signature, 'actual': actual, 'minimum': minimum}

    hokuso_to_haneda = (
        HOKUSO, KEISEI_MAIN, KEISEI_OSHIAGE, TOEI_ASAKUSA, KEIKYU_MAIN, KEIKYU_AIRPORT,
    )
    require_signature(hokuso_to_haneda, HOKUSO_HANEDA_SIGNATURE_FLOOR)
    require_signature(tuple(reversed(hokuso_to_haneda)), HOKUSO_HANEDA_SIGNATURE_FLOOR)

    shibayama_to_haneda = (
        SHIBAYAMA, KEISEI_HIGASHI_NARITA, KEISEI_MAIN, KEISEI_OSHIAGE,
        TOEI_ASAKUSA, KEIKYU_MAIN, KEIKYU_AIRPORT,
    )
    require_signature(shibayama_to_haneda, SHIBAYAMA_TO_HANEDA_SIGNATURE_FLOOR)
    require_signature(tuple(reversed(shibayama_to_haneda)), HANEDA_TO_SHIBAYAMA_SIGNATURE_FLOOR)

    oshiage_to_kurihama = (KEISEI_OSHIAGE, TOEI_ASAKUSA, KEIKYU_MAIN, KEIKYU_KURIHAMA)
    require_signature(oshiage_to_kurihama, OSHIAGE_KURIHAMA_SIGNATURE_FLOOR)
    require_signature(tuple(reversed(oshiage_to_kurihama)), OSHIAGE_KURIHAMA_SIGNATURE_FLOOR)

    oshiage_to_zushi = (KEISEI_MAIN, KEISEI_OSHIAGE, TOEI_ASAKUSA, KEIKYU_MAIN, KEIKYU_ZUSHI)
    zushi_to_oshiage = (KEIKYU_ZUSHI, KEIKYU_MAIN, TOEI_ASAKUSA, KEISEI_OSHIAGE)
    require_signature(oshiage_to_zushi, OSHIAGE_ZUSHI_SIGNATURE_FLOOR)
    require_signature(zushi_to_oshiage, OSHIAGE_ZUSHI_SIGNATURE_FLOOR)

    require_signature((KEISEI_MATSUDO, KEISEI_CHIBA), MATSUDO_CHIBA_SIGNATURE_FLOOR)
    require_signature((KEISEI_CHIBA, KEISEI_MATSUDO), MATSUDO_CHIBA_SIGNATURE_FLOOR)
    require_signature((KEISEI_CHIHARA, KEISEI_CHIBA), CHIHARA_CHIBA_SIGNATURE_FLOOR)
    require_signature((KEISEI_CHIBA, KEISEI_CHIHARA), CHIHARA_CHIBA_SIGNATURE_FLOOR)

    assert network['timeBasis'] == 'train-timetable-network'
    assert network['identityBasis'] == 'Keisei official one-train timetable page'
    railways = set(network['railways'])
    for railway in (
        'odpt.Railway:Keisei.Main',
        KEISEI_OSHIAGE,
        'odpt.Railway:Keisei.Kanamachi',
        KEISEI_CHIBA,
        KEISEI_CHIHARA,
        KEISEI_HIGASHI_NARITA,
        'odpt.Railway:Keisei.NaritaSkyAccess',
        KEISEI_MATSUDO,
        TOEI_ASAKUSA,
        KEIKYU_MAIN,
        KEIKYU_AIRPORT,
        'odpt.Railway:Keikyu.Daishi',
        KEIKYU_KURIHAMA,
        KEIKYU_ZUSHI,
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
