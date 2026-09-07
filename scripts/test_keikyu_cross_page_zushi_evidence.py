#!/usr/bin/env python3
from __future__ import annotations

import unittest

import keikyu_cross_page_zushi_evidence as target
from keikyu_official_pdf import OFFICIAL_PDF_URL


def official_dataset() -> dict:
    return {
        'kind': 'keikyu-official-section-local-stop-times',
        'source': {'url': OFFICIAL_PDF_URL, 'sha256': 'abc'},
        'identityPolicy': {
            'pageSectionColumnIsExactLocalIdentity': True,
            'literalTrainNumberRowsAreHardSectionBoundaries': True,
            'literalPrintedCalendarRequired': True,
            'calendarMayBeInferredFromPageNumber': False,
            'printedTrainNumberMayJoinSectionsOrPages': False,
            'anonymousColumnMayJoinSectionsOrPages': False,
            'clockTimeProximityMayJoinFragments': False,
            'destinationMayJoinFragments': False,
            'crossPageIdentityEstablished': False,
            'runtimeSameTrainPromotions': 0,
        },
        'fragments': [],
    }


def audit() -> dict:
    return {
        'kind': 'keikyu-official-cross-page-identity-audit',
        'sourceSha256': 'abc',
        'issues': [],
        'branchingTargets': {},
        'multiplePreviousSources': {},
        'cycles': [],
        'identityPolicy': {
            'officialPreviousPublicationPageRequired': True,
            'officialPreviousTrainNumberRequired': True,
            'uniqueTargetFragmentRequired': True,
            'pageLocalFragmentMetadataMustMatch': True,
            'clockTimeUsedForIdentity': False,
            'destinationUsedForIdentity': False,
            'branchingAllowedForPromotion': False,
            'cyclesAllowedForPromotion': False,
            'runtimeSameTrainPromotions': 0,
        },
        'edges': [],
    }


def edge(a: str, b: str) -> dict:
    return {
        'fromFragment': a,
        'toFragment': b,
        'evidence': target.REFERENCE_EVIDENCE,
        'previousPrintedPage': 10,
        'previousTrainNumber': '1234',
        'currentPrintedPage': 11,
        'currentTrainNumber': '1234',
    }


class CrossPageZushiEvidenceTests(unittest.TestCase):
    def test_valid_sources_pass(self) -> None:
        target.validate_cross_page_sources(official_dataset(), audit())

    def test_source_sha_mismatch_fails_closed(self) -> None:
        value = audit()
        value['sourceSha256'] = 'different'
        with self.assertRaises(RuntimeError):
            target.validate_cross_page_sources(official_dataset(), value)

    def test_graph_rejects_branching_source(self) -> None:
        value = audit()
        value['edges'] = [edge('a', 'b'), edge('a', 'c')]
        with self.assertRaises(RuntimeError):
            target.build_graph(value, {'a', 'b', 'c'})

    def test_directed_path_only_follows_official_direction(self) -> None:
        value = audit()
        value['edges'] = [edge('a', 'b'), edge('b', 'c')]
        outgoing, _incoming = target.build_graph(value, {'a', 'b', 'c'})
        self.assertEqual(2, len(target.directed_path('a', 'c', outgoing) or []))
        self.assertIsNone(target.directed_path('c', 'a', outgoing))

    def test_two_point_proof_requires_same_component_and_direction(self) -> None:
        value = audit()
        value['edges'] = [edge('a', 'b')]
        outgoing, incoming = target.build_graph(value, {'a', 'b', 'c'})
        roots = target.component_roots({'a', 'b', 'c'}, incoming)
        source = {'id': 'source', 'calendar': 'odpt.Calendar:Weekday'}
        dest = {'id': 'target', 'calendar': 'odpt.Calendar:Weekday'}
        anchors = {
            'source': [{'station': '六浦', 'suffix': '.Mutsuura', 'minute': 600}],
            'target': [{'station': '金沢文庫', 'suffix': '.KanazawaBunko', 'minute': 608}],
        }
        index = {
            ('weekday', '.Mutsuura', 600): [{'calendar': 'weekday', 'officialFragment': 'a'}],
            ('weekday', '.KanazawaBunko', 608): [{'calendar': 'weekday', 'officialFragment': 'b'}],
        }
        proof = target.cross_page_proof(source, dest, 'weekday', anchors, index, outgoing, roots)
        self.assertIsNotNone(proof)
        self.assertEqual('a', proof['sourceOfficialFragment'])
        self.assertEqual('b', proof['targetOfficialFragment'])

        reverse = target.cross_page_proof(dest, source, 'weekday', {
            'target': anchors['target'], 'source': anchors['source']
        }, index, outgoing, roots)
        self.assertIsNone(reverse)

    def test_different_components_never_prove_identity(self) -> None:
        value = audit()
        value['edges'] = [edge('a', 'b')]
        outgoing, incoming = target.build_graph(value, {'a', 'b', 'c'})
        roots = target.component_roots({'a', 'b', 'c'}, incoming)
        anchors = {
            'source': [{'station': '六浦', 'suffix': '.Mutsuura', 'minute': 600}],
            'target': [{'station': '金沢文庫', 'suffix': '.KanazawaBunko', 'minute': 608}],
        }
        index = {
            ('weekday', '.Mutsuura', 600): [{'calendar': 'weekday', 'officialFragment': 'a'}],
            ('weekday', '.KanazawaBunko', 608): [{'calendar': 'weekday', 'officialFragment': 'c'}],
        }
        self.assertIsNone(target.cross_page_proof({'id': 'source', 'calendar': 'odpt.Calendar:Weekday'}, {'id': 'target', 'calendar': 'odpt.Calendar:Weekday'}, 'weekday', anchors, index, outgoing, roots))


if __name__ == '__main__':
    unittest.main()
