#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import keikyu_internal_generated_evidence as target


def fragment(fid: str, railway: str, calendar: str = 'odpt.Calendar:Weekday') -> dict:
    return {'id': fid, 'railway': railway, 'calendar': calendar, 'stops': []}


def row(**changes) -> dict:
    value = {
        'id': 'section-local:test',
        'matchStatus': 'matched-singleton',
        'boundaryId': target.ZUSHI_BOUNDARY_ID,
        'fromRailway': target.ZUSHI,
        'toRailway': target.MAIN,
        'fromFragment': 'z1',
        'toFragment': 'm1',
        'sourceMatches': ['z1'],
        'targetMatches': ['m1'],
        'calendar': 'weekday',
        'officialPrintedCalendar': 'weekday',
        'officialAnchors': [
            {'station': '六浦', 'suffix': '.Mutsuura', 'minute': 600},
            {'station': '金沢文庫', 'suffix': '.KanazawaBunko', 'minute': 608},
        ],
        'officialPageSectionLocalFragment': 'keikyu-official-pdf:p067:s02:c04',
        'pdfPage': 67,
        'pdfSection': 2,
        'pdfColumn': 4,
        'evidence': ['operator-official-full-timetable', target.MARKER, target.SECTION_LOCAL_MARKER],
        'sourceUrl': 'https://www.keikyu.co.jp/ride/kakueki/pdf/schedule_all.pdf',
        'matchPolicy': {
            'officialSamePrintedColumnRequired': True,
            'twoExactPublishedStationTimesRequired': True,
            'singletonFragmentMatchRequiredAtBothPoints': True,
            'officialPageSectionColumnIsExactLocalIdentity': True,
            'officialSectionIdentityRequired': True,
            'literalPrintedCalendarRequired': True,
            'runtimeCalendarMustMatchOfficialPrintedCalendar': True,
            'calendarMayBeInferredFromPageNumber': False,
            'crossPageIdentityUsed': False,
            'sharedPublishedDestinationUsedOnlyForSearch': True,
            'candidateFragmentGapUsedOnlyForSearch': True,
            'trainNumberAloneMayEstablishIdentity': False,
            'timeProximityAloneMayEstablishIdentity': False,
        },
    }
    value.update(changes)
    return value


def payload(entry: dict) -> dict:
    return {
        'policy': {
            'officialSamePrintedColumnRequired': True,
            'twoExactPublishedStationTimesRequired': True,
            'singletonFragmentMatchRequiredAtBothPoints': True,
            'trainNumberAloneMayEstablishIdentity': False,
            'timeProximityAloneMayEstablishIdentity': False,
        },
        'entries': [entry],
    }


def graph() -> dict:
    return {
        'graph': {
            target.ZUSHI: [{
                'toRailway': target.MAIN,
                'boundaryId': target.ZUSHI_BOUNDARY_ID,
            }],
        },
    }


class SectionLocalConsumerTests(unittest.TestCase):
    def apply(self, entry: dict, *, source_calendar='odpt.Calendar:Weekday', target_calendar='odpt.Calendar:Weekday'):
        unresolved: list[dict] = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'evidence.json'
            path.write_text(json.dumps(payload(entry)), encoding='utf-8')
            edges = target.apply_generated_evidence(
                [fragment('z1', target.ZUSHI, source_calendar), fragment('m1', target.MAIN, target_calendar)],
                [],
                unresolved,
                graph(),
                path,
            )
        return edges, unresolved

    def test_valid_section_calendar_local_v2_adds_edge(self) -> None:
        edges, unresolved = self.apply(row())
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        self.assertEqual('keikyu-official-internal-same-section-calendar-column-two-point', edges[0]['evidence'][0])

    def test_fragment_metadata_mismatch_fails_closed(self) -> None:
        edges, unresolved = self.apply(row(pdfColumn=5))
        self.assertEqual([], edges)
        self.assertEqual('section-local-fragment-metadata-mismatch', unresolved[0]['reason'])

    def test_missing_section_policy_fails_closed(self) -> None:
        entry = row()
        entry['matchPolicy'].pop('officialSectionIdentityRequired')
        edges, unresolved = self.apply(entry)
        self.assertEqual([], edges)
        self.assertEqual('unsafe-section-local-entry-policy', unresolved[0]['reason'])

    def test_unbanded_official_fragment_fails_closed(self) -> None:
        edges, unresolved = self.apply(row(officialPageSectionLocalFragment='keikyu-official-pdf:p067:c04'))
        self.assertEqual([], edges)
        self.assertEqual('missing-section-aware-official-fragment-id', unresolved[0]['reason'])

    def test_evidence_and_official_calendar_mismatch_fails_closed(self) -> None:
        edges, unresolved = self.apply(row(calendar='holiday'))
        self.assertEqual([], edges)
        self.assertEqual('evidence-calendar-official-calendar-mismatch', unresolved[0]['reason'])

    def test_runtime_and_official_calendar_mismatch_fails_closed(self) -> None:
        edges, unresolved = self.apply(row(), target_calendar='odpt.Calendar:SaturdayHoliday')
        self.assertEqual([], edges)
        self.assertEqual('runtime-calendar-official-calendar-mismatch', unresolved[0]['reason'])


if __name__ == '__main__':
    unittest.main()
