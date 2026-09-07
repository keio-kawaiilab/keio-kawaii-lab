import copy
import unittest
from build_asakusa_boundary_network import exact_local_sequence, join, minute, validate_chronology


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.local = [['押上', None, 400], ['本所吾妻橋', 402, 403], ['浅草', 405, None]]

    def test_all_events_match(self):
        self.assertTrue(exact_local_sequence(self.local, self.local))

    def test_every_observed_event_is_required(self):
        for i, stop in enumerate(self.local):
            for event in (1, 2):
                if stop[event] is None:
                    continue
                for replacement in (None, stop[event] + 1):
                    changed = copy.deepcopy(self.local)
                    changed[i][event] = replacement
                    self.assertFalse(exact_local_sequence(self.local, changed))

    def test_whole_ordered_sequence_required(self):
        self.assertFalse(exact_local_sequence(self.local, self.local[1:]))
        self.assertFalse(exact_local_sequence(self.local, self.local[::-1]))

    def test_no_synthetic_dwell(self):
        a = {'stops': [['A', None, 390], ['押上', 399, None]], 'links': [['north']]}
        b = {'stops': [['押上', None, 400], ['B', 402, None]], 'links': [['south']]}
        self.assertEqual(join(a, b)['stops'][1], ['押上', 399, 400])
        b['stops'][0][2] = None
        self.assertEqual(join(a, b)['stops'][1], ['押上', 399, None])

    def test_conflicting_event_rejected(self):
        a = {'stops': [['押上', 399, 400]], 'links': []}
        b = {'stops': [['押上', 399, 401]], 'links': []}
        with self.assertRaises(ValueError):
            join(a, b)

    def test_different_boundary_rejected(self):
        with self.assertRaises(ValueError):
            join({'stops': [['A', None, 400]], 'links': []}, {'stops': [['B', 400, None]], 'links': []})

    def test_service_day_and_chronology(self):
        self.assertEqual(minute('00:12'), 1452)
        self.assertEqual(minute(1452), 1452)
        validate_chronology([['A', None, 1439], ['B', 1452, None]])
        with self.assertRaises(ValueError):
            validate_chronology([['A', None, 400], ['B', 399, None]])


if __name__ == '__main__':
    unittest.main()
