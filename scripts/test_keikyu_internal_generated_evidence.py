#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import keikyu_internal_generated_evidence as target


def fragment(fid: str, railway: str, calendar: str = 'odpt.Calendar:Weekday') -> dict:
    return {'id': fid, 'railway': railway, 'calendar': calendar, 'stops': []}


def entry(**changes) -> dict:
    base = {
        'id': 'internal:test', 'matchStatus': 'matched-singleton',
        'boundaryId': target.BOUNDARY_ID, 'fromRailway': target.MAIN, 'toRailway': target.AIRPORT,
        'fromFragment': 'm1', 'toFragment': 'a1', 'sourceMatches': ['m1'], 'targetMatches': ['a1'],
        'evidence': ['operator-official-mainline-timetable', target.MARKER],
        'sourceUrl': 'https://www.keikyu.co.jp/example.pdf',
    }
    base.update(changes)
    return base


def cross_page_entry(**changes) -> dict:
    base = {
        'id': 'internal:cross-v2', 'matchStatus': 'matched-singleton',
        'boundaryId': target.ZUSHI_BOUNDARY_ID,
        'fromRailway': target.ZUSHI, 'toRailway': target.MAIN,
        'fromFragment': 'z1', 'toFragment': 'm1',
        'sourceMatches': ['z1'], 'targetMatches': ['m1'],
        'calendar': 'weekday',
        'officialPrintedCalendar': 'weekday',
        'sourceOfficialFragment': 'keikyu-official-pdf:p010:s01:c01',
        'targetOfficialFragment': 'keikyu-official-pdf:p011:s00:c01',
        'officialPhysicalComponentRoot': 'keikyu-official-pdf:p010:s01:c01',
        'officialAnchors': [
            {'station': '六浦', 'suffix': '.Mutsuura', 'minute': 600},
            {'station': '金沢文庫', 'suffix': '.KanazawaBunko', 'minute': 608},
        ],
        'officialPreviousPublicationPath': [{
            'fromFragment': 'keikyu-official-pdf:p010:s01:c01',
            'toFragment': 'keikyu-official-pdf:p011:s00:c01',
            'previousPrintedPage': 10,
            'previousTrainNumber': '1234',
            'currentPrintedPage': 11,
            'currentTrainNumber': '1234',
            'calendar': 'weekday',
            'evidence': target.CROSS_PAGE_REFERENCE_EVIDENCE,
        }],
        'evidence': ['operator-official-full-timetable-section-aware', target.CROSS_PAGE_MARKER],
        'sourceUrl': 'https://www.keikyu.co.jp/ride/kakueki/pdf/schedule_all.pdf',
        'matchPolicy': {
            'crossPageIdentityUsed': True,
            'officialPreviousPublicationPageAndTrainNumberRequired': True,
            'uniquePreviousPublicationTargetRequired': True,
            'pageSectionLocalFragmentMetadataMustMatch': True,
            'crossPageGraphMustBeNonBranchingAcyclic': True,
            'directedOfficialContinuationPathRequired': True,
            'officialSectionIdentityRequired': True,
            'twoExactPublishedStationTimesRequired': True,
            'singletonFragmentMatchRequiredAtBothPoints': True,
            'literalPrintedCalendarRequired': True,
            'runtimeCalendarMustMatchOfficialPrintedCalendar': True,
            'unclassifiedCalendarPagesExcludedFromIdentity': True,
            'officialContinuationPathMustStayWithinPrintedCalendar': True,
            'calendarMayBeInferredFromPageNumber': False,
            'calendarMayBeInferredFromNeighboringPages': False,
            'sharedPublishedDestinationUsedOnlyForSearch': True,
            'candidateFragmentGapUsedOnlyForSearch': True,
            'trainNumberAloneMayEstablishIdentity': False,
            'timeProximityAloneMayEstablishIdentity': False,
        },
    }
    base.update(changes)
    return base


def payload(row: dict, *, safe: bool = True, cross_page: bool = False) -> dict:
    policy = {
        'officialSamePrintedColumnRequired': True,
        'twoExactPublishedStationTimesRequired': True,
        'singletonFragmentMatchRequiredAtBothPoints': True,
        'trainNumberAloneMayEstablishIdentity': False if safe else True,
        'timeProximityAloneMayEstablishIdentity': False,
    }
    if cross_page:
        policy.update({
            'officialPreviousPublicationPageAndTrainNumberRequiredForCrossPage': True,
            'uniquePreviousPublicationTargetRequiredForCrossPage': True,
            'pageSectionLocalFragmentMetadataMustMatchForCrossPage': True,
            'crossPageGraphMustBeNonBranchingAcyclic': True,
            'directedOfficialContinuationPathRequired': True,
            'officialSectionIdentityRequiredForCrossPage': True,
            'literalPrintedCalendarRequiredForCrossPage': True,
            'runtimeCalendarMustMatchOfficialPrintedCalendarForCrossPage': True,
            'unclassifiedCalendarPagesExcludedFromCrossPageIdentity': True,
            'crossPageEdgesStayWithinPrintedCalendar': True,
            'calendarMayBeInferredFromPageNumberForCrossPage': False,
            'calendarMayBeInferredFromNeighboringPagesForCrossPage': False,
        })
    return {'policy': policy, 'entries': [row]}


def graph(pair=None, boundary_id=None, *, verified: bool = True) -> dict:
    pair = pair or (target.MAIN, target.AIRPORT)
    boundary_id = boundary_id or target.BOUNDARY_ID
    rows = [{'toRailway': pair[1], 'boundaryId': boundary_id}] if verified else []
    return {'graph': {pair[0]: rows}}


class ConsumerTests(unittest.TestCase):
    def apply(self, data: dict, *, fragments=None, indexes=None, initial_unresolved=None):
        fragments = fragments or [fragment('m1', target.MAIN), fragment('a1', target.AIRPORT)]
        unresolved: list[dict] = list(initial_unresolved or [])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'evidence.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            edges = target.apply_generated_evidence(fragments, [], unresolved, indexes or graph(), path)
        return edges, unresolved

    def test_valid_two_point_singleton_adds_edge(self) -> None:
        edges, unresolved = self.apply(payload(entry()))
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        self.assertEqual('evidence-backed', edges[0]['identityLevel'])
        self.assertEqual('京急蒲田', edges[0]['boundary']['station'])

    def test_valid_kurihama_main_two_point_singleton_adds_edge(self) -> None:
        row = entry(boundaryId=target.KURIHAMA_BOUNDARY_ID, fromRailway=target.KURIHAMA,
                    toRailway=target.MAIN, fromFragment='k1', toFragment='m1',
                    sourceMatches=['k1'], targetMatches=['m1'])
        fragments = [fragment('k1', target.KURIHAMA), fragment('m1', target.MAIN)]
        indexes = graph((target.KURIHAMA, target.MAIN), target.KURIHAMA_BOUNDARY_ID)
        edges, unresolved = self.apply(payload(row), fragments=fragments, indexes=indexes)
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        self.assertEqual('堀ノ内', edges[0]['boundary']['station'])

    def test_valid_zushi_main_two_point_singleton_adds_edge(self) -> None:
        row = entry(boundaryId=target.ZUSHI_BOUNDARY_ID, fromRailway=target.ZUSHI,
                    toRailway=target.MAIN, fromFragment='z1', toFragment='m1',
                    sourceMatches=['z1'], targetMatches=['m1'])
        fragments = [fragment('z1', target.ZUSHI), fragment('m1', target.MAIN)]
        indexes = graph((target.ZUSHI, target.MAIN), target.ZUSHI_BOUNDARY_ID)
        edges, unresolved = self.apply(payload(row), fragments=fragments, indexes=indexes)
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        self.assertEqual('金沢八景', edges[0]['boundary']['station'])

    def test_current_missing_boundary_row_is_cleared_after_proof(self) -> None:
        unresolved = [
            {'kind': 'missing-boundary-train-identity-evidence', 'fragment': 'm1', 'nextRailway': target.AIRPORT},
            {'kind': 'missing-boundary-train-identity-evidence', 'fragment': 'other', 'nextRailway': target.AIRPORT},
        ]
        edges, remaining = self.apply(payload(entry()), initial_unresolved=unresolved)
        self.assertEqual(1, len(edges))
        self.assertEqual(1, len(remaining))
        self.assertEqual('other', remaining[0]['fragment'])

    def test_legacy_non_schedule_all_marker_remains_accepted(self) -> None:
        row = entry(evidence=['operator-official-connection-timetable', target.LEGACY_MARKER])
        edges, unresolved = self.apply(payload(row))
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))

    def test_deprecated_unbanded_schedule_all_marker_is_rejected(self) -> None:
        row = entry(evidence=['operator-official-full-timetable', target.MARKER, 'schedule-all-page-column-v1'])
        edges, unresolved = self.apply(payload(row))
        self.assertEqual([], edges)
        self.assertEqual('deprecated-unbanded-official-identity', unresolved[0]['reason'])

    def test_deprecated_unbanded_cross_page_marker_is_rejected(self) -> None:
        row = entry(evidence=['operator-official-full-timetable', 'official-previous-publication-chain-two-exact-station-times-v1'])
        edges, unresolved = self.apply(payload(row))
        self.assertEqual([], edges)
        self.assertEqual('deprecated-unbanded-official-identity', unresolved[0]['reason'])

    def test_non_singleton_record_fails_closed(self) -> None:
        edges, unresolved = self.apply(payload(entry(sourceMatches=['m1', 'm2'])))
        self.assertEqual([], edges)
        self.assertEqual('non-singleton-recorded-match', unresolved[0]['reason'])

    def test_stale_fragment_fails_closed(self) -> None:
        edges, unresolved = self.apply(payload(entry()), fragments=[fragment('m1', target.MAIN)])
        self.assertEqual([], edges)
        self.assertEqual('stale-fragment-reference', unresolved[0]['reason'])

    def test_unverified_boundary_fails_closed(self) -> None:
        edges, unresolved = self.apply(payload(entry()), indexes=graph(verified=False))
        self.assertEqual([], edges)
        self.assertEqual('unverified-operational-boundary', unresolved[0]['reason'])

    def test_unsafe_policy_fails_closed(self) -> None:
        edges, unresolved = self.apply(payload(entry(), safe=False))
        self.assertEqual([], edges)
        self.assertEqual('keikyu-internal-generated-evidence-unsafe-policy', unresolved[0]['kind'])

    def test_wrong_pair_fails_closed(self) -> None:
        edges, unresolved = self.apply(payload(entry(toRailway=target.ZUSHI)))
        self.assertEqual([], edges)
        self.assertEqual('unexpected-railway-pair', unresolved[0]['reason'])

    def test_valid_section_aware_explicit_cross_page_path_adds_edge(self) -> None:
        row = cross_page_entry()
        fragments = [fragment('z1', target.ZUSHI), fragment('m1', target.MAIN)]
        indexes = graph((target.ZUSHI, target.MAIN), target.ZUSHI_BOUNDARY_ID)
        edges, unresolved = self.apply(payload(row, cross_page=True), fragments=fragments, indexes=indexes)
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        self.assertEqual('keikyu-official-internal-explicit-section-cross-page-two-point', edges[0]['evidence'][0])

    def test_cross_page_without_global_policy_fails_closed(self) -> None:
        row = cross_page_entry()
        fragments = [fragment('z1', target.ZUSHI), fragment('m1', target.MAIN)]
        indexes = graph((target.ZUSHI, target.MAIN), target.ZUSHI_BOUNDARY_ID)
        edges, unresolved = self.apply(payload(row), fragments=fragments, indexes=indexes)
        self.assertEqual([], edges)
        self.assertEqual('unsafe-cross-page-global-policy', unresolved[0]['reason'])

    def test_cross_page_path_calendar_mismatch_fails_closed(self) -> None:
        row = cross_page_entry(officialPreviousPublicationPath=[{
            'fromFragment': 'keikyu-official-pdf:p010:s01:c01',
            'toFragment': 'keikyu-official-pdf:p011:s00:c01',
            'previousPrintedPage': 10, 'previousTrainNumber': '1234',
            'calendar': 'holiday',
            'evidence': target.CROSS_PAGE_REFERENCE_EVIDENCE,
        }])
        fragments = [fragment('z1', target.ZUSHI), fragment('m1', target.MAIN)]
        indexes = graph((target.ZUSHI, target.MAIN), target.ZUSHI_BOUNDARY_ID)
        edges, unresolved = self.apply(payload(row, cross_page=True), fragments=fragments, indexes=indexes)
        self.assertEqual([], edges)
        self.assertEqual('cross-page-reference-edge-calendar-mismatch', unresolved[0]['reason'])

    def test_cross_page_runtime_calendar_mismatch_fails_closed(self) -> None:
        row = cross_page_entry()
        fragments = [
            fragment('z1', target.ZUSHI),
            fragment('m1', target.MAIN, 'odpt.Calendar:SaturdayHoliday'),
        ]
        indexes = graph((target.ZUSHI, target.MAIN), target.ZUSHI_BOUNDARY_ID)
        edges, unresolved = self.apply(payload(row, cross_page=True), fragments=fragments, indexes=indexes)
        self.assertEqual([], edges)
        self.assertEqual('runtime-calendar-official-calendar-mismatch', unresolved[0]['reason'])

    def test_unbanded_fragment_id_in_v2_cross_page_path_fails_closed(self) -> None:
        row = cross_page_entry(
            sourceOfficialFragment='official:p1:c1',
            officialPreviousPublicationPath=[{
                'fromFragment': 'official:p1:c1',
                'toFragment': 'keikyu-official-pdf:p011:s00:c01',
                'previousPrintedPage': 10, 'previousTrainNumber': '1234',
                'calendar': 'weekday',
                'evidence': target.CROSS_PAGE_REFERENCE_EVIDENCE,
            }],
        )
        fragments = [fragment('z1', target.ZUSHI), fragment('m1', target.MAIN)]
        indexes = graph((target.ZUSHI, target.MAIN), target.ZUSHI_BOUNDARY_ID)
        edges, unresolved = self.apply(payload(row, cross_page=True), fragments=fragments, indexes=indexes)
        self.assertEqual([], edges)
        self.assertEqual('missing-section-aware-official-fragment-id', unresolved[0]['reason'])

    def test_discontinuous_cross_page_path_fails_closed(self) -> None:
        row = cross_page_entry(officialPreviousPublicationPath=[{
            'fromFragment': 'keikyu-official-pdf:p999:s00:c01',
            'toFragment': 'keikyu-official-pdf:p011:s00:c01',
            'previousPrintedPage': 10, 'previousTrainNumber': '1234',
            'calendar': 'weekday',
            'evidence': target.CROSS_PAGE_REFERENCE_EVIDENCE,
        }])
        fragments = [fragment('z1', target.ZUSHI), fragment('m1', target.MAIN)]
        indexes = graph((target.ZUSHI, target.MAIN), target.ZUSHI_BOUNDARY_ID)
        edges, unresolved = self.apply(payload(row, cross_page=True), fragments=fragments, indexes=indexes)
        self.assertEqual([], edges)
        self.assertEqual('discontinuous-cross-page-reference-path', unresolved[0]['reason'])

    def test_cross_page_path_missing_explicit_metadata_fails_closed(self) -> None:
        row = cross_page_entry(officialPreviousPublicationPath=[{
            'fromFragment': 'keikyu-official-pdf:p010:s01:c01',
            'toFragment': 'keikyu-official-pdf:p011:s00:c01',
            'previousPrintedPage': None, 'previousTrainNumber': '',
            'calendar': 'weekday',
            'evidence': target.CROSS_PAGE_REFERENCE_EVIDENCE,
        }])
        fragments = [fragment('z1', target.ZUSHI), fragment('m1', target.MAIN)]
        indexes = graph((target.ZUSHI, target.MAIN), target.ZUSHI_BOUNDARY_ID)
        edges, unresolved = self.apply(payload(row, cross_page=True), fragments=fragments, indexes=indexes)
        self.assertEqual([], edges)
        self.assertEqual('missing-explicit-previous-publication-metadata', unresolved[0]['reason'])


if __name__ == '__main__':
    unittest.main()
