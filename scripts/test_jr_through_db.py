#!/usr/bin/env python3
import copy
import unittest

from build_jr_through_db import assemble_stops, prove_edges, ROOT, install
from transit_network_db import read_json
from verify_jr_through_db import verify


def fragment(fid, stops, calendar='weekday'):
    return {'id': fid, 'timetableId': 'tt:' + fid, 'stops': stops,
            'calendar': calendar, 'railway': 'rail:' + fid}


class BoundaryTests(unittest.TestCase):
    def test_exact_arrival_departure_boundary_preserved(self):
        a = fragment('a', [['odpt.Station:JR-East.Tokaido.Tokyo', 600, None]])
        b = fragment('b', [['odpt.Station:JR-East.Utsunomiya.Tokyo', None, 605]])
        stops, projection = assemble_stops([a, b])
        self.assertEqual(stops, [['odpt.Station:JR-East.Tokaido.Tokyo', 600, 605]])
        self.assertEqual([p['stopIndices'] for p in projection], [[0], [0]])

    def test_conflicting_boundary_cannot_be_silently_overwritten(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            assemble_stops([fragment('a', [['station', 600, 601]]),
                            fragment('b', [['station', 600, 602]])])

    def test_long_dwell_is_allowed_when_identity_is_proved(self):
        stops, _ = assemble_stops([fragment('a', [['a', None, 600]]),
                                  fragment('b', [['b', 720, None]])])
        self.assertEqual(stops, [['a', None, 600], ['b', 720, None]])

    def test_chronology_conflict_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'monotonic'):
            assemble_stops([fragment('a', [['a', None, 600], ['b', 599, None]])])

    def test_similar_number_and_time_cannot_prove_an_edge(self):
        fs = [fragment('a', [['a', None, 600]]), fragment('b', [['b', 601, None]])]
        with self.assertRaisesRegex(ValueError, 'lacks'):
            prove_edges(fs, [], [{'fromFragment': 'a', 'toFragment': 'b'}])

    def test_official_edge_with_wrong_calendar_rejected(self):
        fs = [fragment('a', []), fragment('b', [], 'holiday')]
        records = [{'timetableId': 'tt:a', 'nextTrainTimetables': ['tt:b']}]
        with self.assertRaisesRegex(ValueError, 'Calendar'):
            prove_edges(fs, records, [{'fromFragment': 'a', 'toFragment': 'b'}])

    def test_omitted_chain_requires_every_official_link(self):
        fs = [fragment('a', []), fragment('b', [])]
        records = [{'timetableId': 'tt:a', 'nextTrainTimetables': ['tt:omitted']}]
        edge = {'fromFragment': 'a', 'toFragment': 'b', 'viaTimetables': ['tt:omitted']}
        with self.assertRaisesRegex(ValueError, 'lacks'):
            prove_edges(fs, records, [edge])
        records.append({'timetableId': 'tt:omitted', 'nextTrainTimetables': ['tt:b']})
        self.assertEqual(len(prove_edges(fs, records, [edge])[0]), 1)


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network = read_json(ROOT / 'data/transit-v2/jr-official/network-journeys.json.gz')

    def test_all_saved_source_events(self):
        summary = verify()
        self.assertEqual(summary['fragments'], 18731)
        self.assertEqual(summary['officialEdges'], 5633)
        self.assertEqual(summary['quarantinedChains'], 0)

    def test_missing_journey_detected(self):
        bad = dict(self.network, journeys=self.network['journeys'][1:])
        with self.assertRaises(AssertionError):
            verify(network_override=bad)

    def test_changed_source_time_detected(self):
        bad = copy.deepcopy(self.network)
        stop = next(s for s in bad['journeys'][0]['stops'] if s[2] is not None)
        stop[2] += 1
        with self.assertRaisesRegex(AssertionError, 'Altered'):
            verify(network_override=bad)

    def test_install_deterministic_and_registers_after_index_reset(self):
        import tempfile
        import shutil
        from pathlib import Path
        from import_western_train_db import write_json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = read_json(ROOT / 'data/transit-v2/jr-official/audit.json')
            names = set(audit['inputHashes']) | {'data/transit-v2/index.json', 'data/transit-v2/coverage.json', 'data/transit-v2/network-journeys.json'}
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, path)
            index_path = root / 'data/transit-v2/index.json'
            index = read_json(index_path)
            del index['networkJourneyFiles']['jr-official-continuations']
            del index['sourceCatalogs']['jr-official-continuations']
            write_json(index_path, index)
            install(root)
            before = {p.name: p.read_bytes() for p in (root / 'data/transit-v2/jr-official').iterdir()}
            install(root)
            after = {p.name: p.read_bytes() for p in (root / 'data/transit-v2/jr-official').iterdir()}
            self.assertEqual(before, after)
            verify(root)


if __name__ == '__main__':
    unittest.main()
