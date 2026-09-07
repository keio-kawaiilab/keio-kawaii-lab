#!/usr/bin/env python3
import copy
import unittest

from audit_toei_sengakuji_official_columns import audit, SENGAKUJI
from audit_sengakuji_independent_reconciliation import reconcile
from keikyu_audit_test_fixtures import fragment, stop_payload, graph
from keikyu_official_train_evidence import DEFAULT_WEEKDAY_URL


def candidate():
    return dict(id="synthetic-column", status="official-column-evidence", operator="keikyu",
                calendar="weekday", direction="toei-to-keikyu", boundaryId="toei-keikyu-sengakuji",
                sourceBoundaryMinute=600, targetBoundaryMinute=601, pdfPage=1, columnX=150,
                sourceUrl=DEFAULT_WEEKDAY_URL, boundaryTrainNumber="100A",
                evidence=["operator-official-connection-timetable", "same-printed-column-spans-both-sides-of-sengakuji"],
                rowGeometry=dict(sourceBoundaryText="泉岳寺着", sourceBoundaryY=100,
                                 boundaryTrainNumberY=110, targetBoundaryY=120, targetBoundaryText="泉岳寺発"))


def timetable():
    return dict(railway="odpt.Railway:Toei.Asakusa", timeBasis="train-timetable",
                tripSchema=["calendarIndex", "trainTypeIndex", "trainNumber", "stops", "destination", "trainId", "timetableId"],
                trainTypes=["odpt.TrainType:Toei.Local"],
                stations=["odpt.Station:Toei.Asakusa.Mita", SENGAKUJI, "odpt.Station:Toei.Asakusa.Oshiage"],
                calendars=["odpt.Calendar:Weekday", "odpt.Calendar:SaturdayHoliday"],
                trips=[[0, 0, "100A", [[0, None, 595], [1, 600, None]], "", "train-1", "timetable-1"]])


class SengakujiReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.candidate = candidate()
        self.timetable = timetable()
        self.fragment = fragment(7, 0, "100A", 1)
        self.fragment["stopTimes"][0].update(station="泉岳寺", event="departure", time="1001")

    def run_audit(self, candidates=None, rows=None):
        return reconcile(candidates or [self.candidate], self.timetable,
                         stop_payload(rows or [self.fragment]), graph([]),
                         {"lines": {"odpt.Railway:Toei.Asakusa": {
                             "trips": len(self.timetable["trips"]),
                             "connections": sum(len(t[3]) - 1 for t in self.timetable["trips"])}}})

    def test_both_singleton_remains_audit_only(self):
        p = self.run_audit()
        self.assertEqual(p["statusCounts"], {"both-local-singleton-candidate": 1})
        self.assertEqual(p["identityPolicy"]["runtimeSameTrainPromotions"], 0)
        self.assertFalse(p["coverageComplete"])

    def test_missing_official_proof_cannot_be_replaced_by_time_or_number(self):
        for field in ("evidence", "rowGeometry", "sourceUrl", "status", "boundaryId"):
            c = candidate()
            del c[field]
            with self.subTest(field=field):
                p = self.run_audit([c])
                self.assertEqual(p["statusCounts"], {"toei-unsupported-official-evidence": 1})

    def test_one_minute_close_is_not_exact(self):
        self.fragment["stopTimes"][0]["time"] = "1002"
        self.assertEqual(self.run_audit()["statusCounts"], {"keikyu-unmatched": 1})

    def test_same_number_other_calendar_cannot_match(self):
        self.fragment["calendar"] = "holiday"
        self.assertEqual(self.run_audit()["statusCounts"], {"keikyu-unmatched": 1})

    def test_wrong_event_cannot_match(self):
        self.fragment["stopTimes"][0]["event"] = "arrival"
        self.assertEqual(self.run_audit()["statusCounts"], {"keikyu-unmatched": 1})

    def test_keikyu_ambiguity_is_not_resolved_by_train_number(self):
        other = copy.deepcopy(self.fragment)
        other.update(id="keikyu-official-pdf:p008:s00:c00", page=8, printedTrainNumber="999X")
        self.assertEqual(self.run_audit(rows=[self.fragment, other])["statusCounts"], {"keikyu-ambiguous": 1})

    def test_toei_ambiguity_is_preserved(self):
        other = copy.deepcopy(self.timetable["trips"][0])
        other[6] = "timetable-2"
        other[5] = "train-2"
        self.timetable["trips"].append(other)
        self.assertEqual(self.run_audit()["statusCounts"], {"toei-ambiguous": 1})

    def test_duplicate_official_ids_are_rejected(self):
        p = self.run_audit([self.candidate, copy.deepcopy(self.candidate)])
        self.assertEqual(p["statusCounts"], {"toei-duplicate-official-column": 2})

    def test_two_columns_targeting_one_toei_trip_are_demoted(self):
        other = copy.deepcopy(self.candidate)
        other.update(id="other-column", columnX=170)
        p = audit([self.candidate, other], self.timetable)
        self.assertEqual(p["statusCounts"], {"conflicting-official-columns": 2})
        self.assertEqual(p["uniqueMatchedToeiTripCount"], 0)

    def test_reverse_direction_uses_keikyu_arrival_and_toei_departure(self):
        self.candidate.update(direction="keikyu-to-toei")
        self.candidate["rowGeometry"]["targetBoundaryText"] = "泉岳寺〃"
        self.timetable["trips"][0][3] = [[1, None, 601], [0, 606, None]]
        self.fragment["stopTimes"][0].update(event="arrival", time="1000")
        self.assertEqual(self.run_audit()["statusCounts"], {"both-local-singleton-candidate": 1})

    def test_duplicate_toei_timetable_identity_is_rejected_upstream(self):
        self.timetable["trips"].append(copy.deepcopy(self.timetable["trips"][0]))
        with self.assertRaises(RuntimeError):
            self.run_audit()

    def test_unsafe_toei_time_regression_is_rejected_upstream(self):
        self.timetable["trips"][0][3][0][2] = 610
        with self.assertRaises(RuntimeError):
            self.run_audit()


if __name__ == "__main__":
    unittest.main()
