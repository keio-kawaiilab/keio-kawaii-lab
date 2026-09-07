import unittest

from diagnose_keikyu_official_calendars import printed_calendar
from audit_keikyu_station_time_resolution import recover_nearby_operation_markers
from keikyu_audit_test_fixtures import fragment, stop_payload
from verify_keikyu_official_stop_times import verify
from keikyu_official_pdf import Word, TrainColumnGrid, _extend_right_edge_columns, split_multiline_word


def word(text, x, y):
    return Word(text, x-2, y-3, x+2, y+3)


class CalendarGeometryTest(unittest.TestCase):
    def label(self, text, x=480, start=100):
        return [word(c, x, start+i*10) for i,c in enumerate(text)]

    def test_interleaved_note_does_not_destroy_literal_vertical_label(self):
        w=self.label('平日用')+[word('%',460,115)]
        self.assertEqual(printed_calendar('平日%用',w),'weekday')

    def test_vertical_holiday(self):
        self.assertEqual(printed_calendar('',self.label('土休日用')),'holiday')

    def test_input_extraction_order_is_irrelevant(self):
        self.assertEqual(printed_calendar('',list(reversed(self.label('平日用')))),'weekday')

    def test_different_columns_cannot_form_a_label(self):
        self.assertIsNone(printed_calendar('',[word('平',480,100),word('日',460,110),word('用',480,120)]))

    def test_large_gap_cannot_form_a_label(self):
        self.assertIsNone(printed_calendar('',[word('平',480,100),word('日',480,110),word('用',480,200)]))

    def test_both_calendars_fail_closed(self):
        self.assertIsNone(printed_calendar('平日用',self.label('土休日用')))

    def test_unrecognized_char_between_label_letters_is_not_removed(self):
        self.assertIsNone(printed_calendar('',self.label('平日?用')))

    def test_no_calendar_is_inferred(self):
        self.assertIsNone(printed_calendar('第51ページ 平日',[]))


class SplitGlyphTest(unittest.TestCase):
    def test_actual_different_rows_are_restored(self):
        merged=Word('塚発',75,218,89,232)
        chars=[word('塚',79,229),word('発',85,222),word('〃',85,229)]
        self.assertEqual(split_multiline_word(merged,chars),chars[:2])

    def test_missing_or_duplicate_glyph_rejected(self):
        merged=Word('塚発',75,218,89,232)
        chars=[word('塚',79,229),word('発',85,222)]
        self.assertEqual(split_multiline_word(merged,chars[:1]),[merged])
        self.assertEqual(split_multiline_word(merged,chars+[chars[1]]),[merged])

    def test_single_row_label_not_split(self):
        merged=Word('泉岳寺',50,100,80,114)
        self.assertEqual(split_multiline_word(merged,[word(c,55+i*10,107) for i,c in enumerate('泉岳寺')]),[merged])


class MarkerBaselineTest(unittest.TestCase):
    def test_verifier_rejects_missing_or_distant_marker_proof(self):
        f=fragment(7,0,'100A',3)
        s=f['stopTimes'][0]
        s['resolution']='exact-nearby-printed-marker-and-same-row-station-title'
        s['markerEvidenceY']=s['rowY']+1.6
        self.assertTrue(verify(stop_payload([f]))['verified'])
        for bad in (None, float('nan'), s['rowY']+6):
            s['markerEvidenceY']=bad
            with self.assertRaises(RuntimeError):verify(stop_payload([f]))

    def row(self,y,marker=None):
        return dict(y=y,marker=marker,stationMatches=[],cells=[] if marker else ['639'])

    def test_font_baseline_offset_requires_unique_explicit_marker(self):
        rows=[self.row(100),self.row(101.6,'arrival')]
        recover_nearby_operation_markers(rows)
        self.assertEqual(rows[0]['marker'],'arrival')
        self.assertEqual(rows[0]['markerEvidenceY'],101.6)

    def test_adjacent_timetable_row_is_not_used(self):
        rows=[self.row(100),self.row(106.4,'arrival')]
        recover_nearby_operation_markers(rows)
        self.assertIsNone(rows[0]['marker'])

    def test_two_competing_markers_fail_closed(self):
        rows=[self.row(100),self.row(101.6,'arrival'),self.row(98.5,'departure')]
        recover_nearby_operation_markers(rows)
        self.assertIsNone(rows[0]['marker'])


class TrailingArrowTest(unittest.TestCase):
    def recover(self, arrow=True, times=2, dy=0, dx=0):
        grid=TrainColumnGrid(20,(100,115,130),15,('100A','102A','104A'))
        w=[word('020',160,50+i*10) for i in range(times)]
        if arrow:
            w.append(word('↓',160+dx,20+dy))
        return _extend_right_edge_columns(w,grid)

    def test_two_stops_plus_own_header_arrow_extend_column_without_identity(self):
        result=self.recover()
        self.assertEqual(result.centers,(100,115,130,145,160))
        self.assertEqual(result.explicit_numbers[-2:],(None,None))

    def test_two_times_alone_are_not_sufficient(self):
        self.assertEqual(len(self.recover(arrow=False).centers),3)

    def test_arrow_without_two_stops_is_not_sufficient(self):
        self.assertEqual(len(self.recover(times=1).centers),3)

    def test_arrow_from_another_row_is_not_used(self):
        self.assertEqual(len(self.recover(dy=20).centers),3)

    def test_off_grid_arrow_is_not_used(self):
        self.assertEqual(len(self.recover(dx=7).centers),3)


if __name__=='__main__':
    unittest.main()
