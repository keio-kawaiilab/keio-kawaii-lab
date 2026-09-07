#!/usr/bin/env python3
from __future__ import annotations

import unittest

import keikyu_schedule_all_zushi_evidence as target

CAL = 'odpt.Calendar:Weekday'
DEST = 'odpt.Station:Keikyu.Main.Shinagawa'


def current_fragment(fid: str, railway: str, stops: list[list]) -> dict:
    return {
        'id': fid,
        'railway': railway,
        'calendar': CAL,
        'destination': [DEST],
        'stops': stops,
    }


def official_payload(extra_fragments: list[dict] | None = None) -> dict:
    base_fragment = {
        'id': 'keikyu-official-pdf:p010:c03',
        'page': 10,
        'column': 3,
        'stopTimes': [
            {'station': '逗子・葉山', 'event': 'departure', 'time': '1000'},
            {'station': '神武寺', 'event': 'departure', 'time': '1005'},
            {'station': '六浦', 'event': 'departure', 'time': '1010'},
            {'station': '金沢八景', 'event': 'departure', 'time': '1012'},
            {'station': '横浜', 'event': 'departure', 'time': '1020'},
            {'station': '品川', 'event': 'arrival', 'time': '1040'},
        ],
    }
    return {
        'kind': 'keikyu-official-page-local-stop-times',
        'source': {'url': target.OFFICIAL_PDF_URL},
        'identityPolicy': {
            'pageColumnIsExactLocalIdentity': True,
            'printedTrainNumberMayJoinPages': False,
            'anonymousColumnMayJoinPages': False,
            'clockTimeProximityMayJoinFragments': False,
            'destinationMayJoinFragments': False,
            'crossPageIdentityEstablished': False,
            'runtimeSameTrainPromotions': 0,
        },
        'fragments': [base_fragment, *(extra_fragments or [])],
    }


class ScheduleAllZushiEvidenceTests(unittest.TestCase):
    def source_and_target(self):
        source = current_fragment('z1', target.base.ZUSHI, [
            ['odpt.Station:Keikyu.Zushi.ZushiHayama', 600, 600],
            ['odpt.Station:Keikyu.Zushi.Jinmuji', 605, 605],
            ['odpt.Station:Keikyu.Zushi.Mutsuura', 610, 610],
        ])
        dest = current_fragment('m1', target.base.MAIN, [
            ['odpt.Station:Keikyu.Main.KanazawaHakkei', 612, 612],
            ['odpt.Station:Keikyu.Main.Yokohama', 620, 620],
            ['odpt.Station:Keikyu.Main.Shinagawa', 640, 640],
        ])
        return source, dest

    def test_same_exact_official_page_column_proves_pair(self):
        source, dest = self.source_and_target()
        fragments = [source, dest]
        owners = target.current.anchor_owner_index(fragments)
        anchors = target.current.singleton_anchor_cache(fragments, owners)
        index = target.official_anchor_index(official_payload())
        proof = target.same_page_column_proof(source, dest, anchors, index)
        self.assertIsNotNone(proof)
        self.assertEqual('keikyu-official-pdf:p010:c03', proof['officialFragment'])
        self.assertGreaterEqual(proof['corroboratingAnchorPairs'], 1)

    def test_duplicate_official_columns_fail_closed(self):
        source, dest = self.source_and_target()
        duplicate = {
            'id': 'keikyu-official-pdf:p011:c04',
            'page': 11,
            'column': 4,
            'stopTimes': official_payload()['fragments'][0]['stopTimes'],
        }
        fragments = [source, dest]
        owners = target.current.anchor_owner_index(fragments)
        anchors = target.current.singleton_anchor_cache(fragments, owners)
        index = target.official_anchor_index(official_payload([duplicate]))
        self.assertIsNone(target.same_page_column_proof(source, dest, anchors, index))

    def test_build_entries_uses_search_filters_only_then_official_proof(self):
        source, dest = self.source_and_target()
        coverage = {'unresolved': [{
            'kind': target.current.CURRENT_KIND,
            'fragment': 'z1',
            'nextRailway': target.base.MAIN,
        }]}
        entries, summary = target.build_entries(coverage, [source, dest], official_payload())
        self.assertEqual(1, len(entries))
        self.assertEqual('z1', entries[0]['fromFragment'])
        self.assertEqual('m1', entries[0]['toFragment'])
        self.assertIn(target.base.MARKER, entries[0]['evidence'])
        self.assertIs(entries[0]['matchPolicy']['crossPageIdentityUsed'], False)
        self.assertEqual(1, summary['matchedSingleton'])

    def test_unsafe_official_dataset_policy_is_rejected(self):
        payload = official_payload()
        payload['identityPolicy']['clockTimeProximityMayJoinFragments'] = True
        with self.assertRaises(RuntimeError):
            target.official_anchor_index(payload)


if __name__ == '__main__':
    unittest.main()
