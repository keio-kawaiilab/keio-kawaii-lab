#!/usr/bin/env python3
from __future__ import annotations

import unittest

import keikyu_missing_boundary_evidence as target

CAL = 'odpt.Calendar:Weekday'


def fragment(fid: str, railway: str, stops: list[list], destination: str = 'odpt.Station:Keikyu.Main.Shinagawa') -> dict:
    return {
        'id': fid,
        'railway': railway,
        'calendar': CAL,
        'stops': stops,
        'destination': [destination],
    }


class ResolverTests(unittest.TestCase):
    def test_candidate_search_uses_verified_boundary_and_small_gap(self) -> None:
        source = fragment(
            'z1', target.base.ZUSHI,
            [
                ['odpt.Station:Keikyu.Zushi.ZushiHayama', 600, 600],
                ['odpt.Station:Keikyu.Zushi.KanazawaHakkei', 610, 610],
            ],
        )
        good = fragment(
            'm1', target.base.MAIN,
            [
                ['odpt.Station:Keikyu.Main.KanazawaHakkei', 611, 611],
                ['odpt.Station:Keikyu.Main.Yokohama', 620, 620],
            ],
        )
        late = fragment(
            'm2', target.base.MAIN,
            [
                ['odpt.Station:Keikyu.Main.KanazawaHakkei', 616, 616],
                ['odpt.Station:Keikyu.Main.Yokohama', 625, 625],
            ],
        )
        wrong_boundary = fragment(
            'm3', target.base.MAIN,
            [
                ['odpt.Station:Keikyu.Main.Yokohama', 611, 611],
                ['odpt.Station:Keikyu.Main.Shinagawa', 630, 630],
            ],
        )
        rows = target.candidate_targets(source, (target.base.ZUSHI, target.base.MAIN), [source, good, late, wrong_boundary])
        self.assertEqual([('m1', 1)], [(row['id'], gap) for row, gap in rows])

    def test_current_unresolved_row_is_selected(self) -> None:
        source = fragment(
            'z1', target.base.ZUSHI,
            [['odpt.Station:Keikyu.Zushi.KanazawaHakkei', 610, 610]],
        )
        coverage = {'unresolved': [{
            'kind': target.CURRENT_KIND,
            'fragment': 'z1',
            'nextRailway': target.base.MAIN,
        }]}
        rows = target.unresolved_sources(
            coverage,
            {'z1': source},
            boundary_id=target.base.ZUSHI_BOUNDARY_ID,
        )
        self.assertEqual(1, len(rows))
        self.assertEqual((target.base.ZUSHI, target.base.MAIN), rows[0][2])

    def test_same_column_proof_requires_exact_official_column(self) -> None:
        source = fragment(
            'z1', target.base.ZUSHI,
            [
                ['odpt.Station:Keikyu.Zushi.ZushiHayama', 600, 600],
                ['odpt.Station:Keikyu.Zushi.KanazawaHakkei', 610, 610],
            ],
        )
        dest = fragment(
            'm1', target.base.MAIN,
            [
                ['odpt.Station:Keikyu.Main.KanazawaHakkei', 611, 611],
                ['odpt.Station:Keikyu.Main.Yokohama', 620, 620],
            ],
        )
        anchors = {
            'z1': [{'station': 'odpt.Station:Keikyu.Zushi.ZushiHayama', 'suffix': '.ZushiHayama', 'minute': 600}],
            'm1': [{'station': 'odpt.Station:Keikyu.Main.Yokohama', 'suffix': '.Yokohama', 'minute': 620}],
        }
        official = {
            ('.ZushiHayama', 600): [{'page': 10, 'x': 100.0, 'rowText': '逗子・葉山', 'sourceUrl': 'official.pdf'}],
            ('.Yokohama', 620): [{'page': 10, 'x': 101.5, 'rowText': '横浜', 'sourceUrl': 'official.pdf'}],
        }
        proof = target.exact_same_column_proof(source, dest, anchors, official)
        self.assertIsNotNone(proof)
        self.assertEqual(10, proof['page'])

        official[( '.Yokohama', 620)] = [{'page': 10, 'x': 110.0, 'rowText': '横浜', 'sourceUrl': 'official.pdf'}]
        self.assertIsNone(target.exact_same_column_proof(source, dest, anchors, official))

    def test_same_column_proof_rejects_multiple_printed_columns(self) -> None:
        source = fragment('z1', target.base.ZUSHI, [['odpt.Station:Keikyu.Zushi.ZushiHayama', 600, 600]])
        dest = fragment('m1', target.base.MAIN, [['odpt.Station:Keikyu.Main.Yokohama', 620, 620]])
        anchors = {
            'z1': [{'station': 'odpt.Station:Keikyu.Zushi.ZushiHayama', 'suffix': '.ZushiHayama', 'minute': 600}],
            'm1': [{'station': 'odpt.Station:Keikyu.Main.Yokohama', 'suffix': '.Yokohama', 'minute': 620}],
        }
        official = {
            ('.ZushiHayama', 600): [
                {'page': 10, 'x': 100.0, 'rowText': '', 'sourceUrl': 'official.pdf'},
                {'page': 11, 'x': 200.0, 'rowText': '', 'sourceUrl': 'official.pdf'},
            ],
            ('.Yokohama', 620): [
                {'page': 10, 'x': 101.0, 'rowText': '', 'sourceUrl': 'official.pdf'},
                {'page': 11, 'x': 201.0, 'rowText': '', 'sourceUrl': 'official.pdf'},
            ],
        }
        self.assertIsNone(target.exact_same_column_proof(source, dest, anchors, official))

    def test_merge_keeps_fail_closed_policy(self) -> None:
        payload = target.merge_payload({}, [], {'matchedSingleton': 0})
        policy = payload['policy']
        self.assertIs(policy['officialSamePrintedColumnRequired'], True)
        self.assertIs(policy['twoExactPublishedStationTimesRequired'], True)
        self.assertIs(policy['singletonFragmentMatchRequiredAtBothPoints'], True)
        self.assertIs(policy['trainNumberAloneMayEstablishIdentity'], False)
        self.assertIs(policy['timeProximityAloneMayEstablishIdentity'], False)


if __name__ == '__main__':
    unittest.main()
