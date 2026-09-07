import copy
import json
import unittest
from pathlib import Path

from keikyu_exact_terminal import verify_exact_terminal


class ExactTerminalTest(unittest.TestCase):
    def setUp(self):
        self.table = json.loads(Path('data/transit/keikyu/timetables/official-internal-main.json').read_text())

    def test_exact_terminal_needs_no_synthetic_board(self):
        result = verify_exact_terminal(self.table)
        self.assertEqual(result['patch']['syntheticRows'], 0)
        for calendar in ['weekday', 'holiday']:
            self.assertGreater(result['exactTerminalCounts'][calendar]['ends'], 0)

    def test_legacy_tables_still_use_the_existing_repair(self):
        self.assertIsNone(verify_exact_terminal({'timeBasis': 'station-departure-only'}))

    def test_deleted_exact_terminal_is_rejected(self):
        for trip in self.table['trips']:
            if self.table['stations'][trip[3][-1][0]].endswith('.Sengakuji'):
                trip[3].pop()
                break
        with self.assertRaises(ValueError):
            verify_exact_terminal(self.table)

    def test_changed_event_does_not_pass_as_already_repaired(self):
        self.table['trips'][0][3][0][2] = 123
        with self.assertRaises(ValueError):
            verify_exact_terminal(self.table)


if __name__ == '__main__':
    unittest.main()
