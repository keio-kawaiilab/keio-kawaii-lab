import unittest
import copy
from collect_hokuso_independent_inventory import parse_board, parse_detail
from audit_shibayama_independent_inventory import boards
from audit_hokuso_independent_inventory import audit
from hokuso_independent_runtime import read, INVENTORY


class NorthernInventoryTests(unittest.TestCase):
    def north(self, content, side='01'):
        return '<tr><th class="side' + side + '">0</th><td><div class="syasyubox syasyu1601">普通&nbsp;日<br />' + content + '</div></td></tr>'

    def test_both_calendar_styles(self):
        for side in ['01', '02']:
            self.assertEqual(parse_board(self.north('12', side))[0]['minute'], 1452)

    def test_annotations_never_prove_origin(self):
        row = parse_board(self.north('<span class="underline">12</span><span class="cntmark" style="color:blue">▲</span>'))[0]
        self.assertEqual(row['minute'], 1452)
        self.assertEqual(row['literalMarker'], '▲')
        self.assertNotIn('originMarker', row)

    def test_unknown_time_fails(self):
        for value in ['12 13', '60', 'xx', '12 ?']:
            with self.assertRaises(ValueError):
                parse_board(self.north(value))

    def test_no_empty_board_is_accepted(self):
        with self.assertRaises(ValueError):
            parse_board('<html>No data</html>')

    def test_full_train_arrival_departure(self):
        html = '<h2>列車時刻表</h2><table><tr><td>矢切</td><td>―</td><td>05:22</td></tr><tr><td>北国分</td><td>05:24</td><td>05:25</td></tr></table>'
        result = parse_detail(html, 'https://example.test/train', {'dw': '1', 'tx': 'source-id'})
        self.assertEqual(result['calendar'], 'holiday')
        self.assertIsNone(result['stops'][0]['arrival'])
        self.assertEqual(result['stops'][1]['arrival'], '05:24')
        self.assertEqual(result['stops'][1]['departure'], '05:25')

    def test_shibayama_requires_both_stations(self):
        with self.assertRaises(ValueError):
            boards('<table></table>')

    def test_shibayama_calendar_columns(self):
        cell = lambda n: '<td><li><div class="schedule-txt">成</div><div class="schedule-number">' + n + '</div></li></td>'
        table = '<table><tr>' + cell('08') + '<td>6</td>' + cell('06') + '</tr></table>'
        rows = boards(table * 2)
        self.assertEqual(len(rows), 4)
        self.assertEqual([r['minute'] for r in rows], [368, 366, 368, 366])
        self.assertEqual([r['calendar'] for r in rows], ['weekday', 'holiday'] * 2)

    def test_missing_internal_train_fails_inventory(self):
        data = read(INVENTORY)
        data['trains'] = [t for t in data['trains'] if t['key'] != data['newSourceKeys'][0]]
        result = audit(data)
        self.assertFalse(result['coverageComplete'])
        self.assertGreater(result['summary']['missingDepartures'], 0)

    def test_missing_station_calendar_fails(self):
        data = read(INVENTORY)
        data['boardsAndReferences'] = data['boardsAndReferences'][1:]
        with self.assertRaises(AssertionError):
            audit(data)

    def test_changed_board_departure_fails(self):
        data = read(INVENTORY)
        data['boardsAndReferences'][0]['departures'][0]['minute'] += 1
        self.assertFalse(audit(data)['coverageComplete'])

    def test_different_arrival_cannot_share_identity(self):
        data = read(INVENTORY)
        t = copy.deepcopy(next(t for t in data['trains'] if t['key'] == data['newSourceKeys'][0]))
        t['key'] += ':conflicting'
        t['stops'][-1]['arrival'] = '06:41'
        data['trains'].append(t)
        result = audit(data)
        self.assertFalse(result['coverageComplete'])
        self.assertGreater(result['summary']['ambiguousDepartures'], 0)


if __name__ == '__main__':
    unittest.main()
