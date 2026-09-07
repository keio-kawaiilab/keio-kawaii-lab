#!/usr/bin/env python3
import copy
import unittest

from keikyu_audit_test_fixtures import fragment, stop_payload, graph
from verify_keikyu_official_stop_times import verify as verify_stops
from verify_keikyu_cross_page_identity_audit import verify as verify_graph
from build_keikyu_independent_mother_set_audit import build_audit
from verify_keikyu_independent_mother_set_audit import verify as verify_mother


class CalendarAuditSafetyTest(unittest.TestCase):
    def setUp(self):
        self.a = fragment(7, 0, "100A", 3)
        self.b = fragment(8, 0, "200A", 3, 1)
        self.rows = [self.a, self.b]
        self.stops = stop_payload(self.rows)
        self.graph = graph([(self.a["id"], self.b["id"])], self.rows)

    def test_current_schema_passes_end_to_end(self):
        self.assertTrue(verify_stops(self.stops)["verified"])
        self.assertTrue(verify_graph(self.graph)["verified"])
        result = build_audit(self.stops, self.graph)
        self.assertTrue(verify_mother(result)["verified"])
        self.assertFalse(result["coverageComplete"])

    def test_stop_mutations_fail_closed(self):
        mutations = [
            lambda p: p.update(version=1),
            lambda p: p["source"].update(sha256=""),
            lambda p: p["fragments"][0].update(section=1),
            lambda p: p["fragments"][0].update(calendar="holiday"),
            lambda p: p["fragments"][0].update(calendar="unknown"),
            lambda p: p["fragments"][0]["stopTimes"][0].update(rowY=650),
            lambda p: p["fragments"][1]["unresolvedCells"][0].update(rowY=float("nan")),
            lambda p: p["pages"].pop(),
            lambda p: p["pages"].append(copy.deepcopy(p["pages"][0])),
            lambda p: p["pages"][0]["sections"].append(copy.deepcopy(p["pages"][0]["sections"][0])),
            lambda p: p["pages"][0]["sections"][0].update(resolvedTimeCells=0),
            lambda p: p["calendarCounts"]["fragments"].update(weekday=1),
            lambda p: p["calendarExcludedPages"].append(7),
            lambda p: p["identityPolicy"].update(calendarMayBeInferredFromPageNumber=True),
            lambda p: p["identityPolicy"].update(clockTimeProximityMayJoinFragments=True),
        ]
        for i, mutate in enumerate(mutations):
            with self.subTest(mutation=i):
                payload = copy.deepcopy(self.stops)
                mutate(payload)
                with self.assertRaises(RuntimeError):
                    verify_stops(payload)

    def test_cross_calendar_edge_never_unions(self):
        self.b["calendar"] = "holiday"
        payload = build_audit(stop_payload(self.rows), self.graph)
        self.assertEqual(payload["officialCrossPageEdgeCount"], 0)
        with self.assertRaises(RuntimeError):
            verify_mother(payload)

    def test_stale_number_never_unions(self):
        self.graph["edges"][0]["previousTrainNumber"] = "999A"
        payload = build_audit(self.stops, self.graph)
        self.assertEqual(payload["officialCrossPageEdgeCount"], 0)
        with self.assertRaises(RuntimeError):
            verify_mother(payload)

    def test_mismatched_pdf_hash_rejected(self):
        self.graph["sourceSha256"] = "b" * 64
        with self.assertRaises(RuntimeError):
            build_audit(self.stops, self.graph)

    def test_calendar_free_graph_cannot_build_mother_set(self):
        self.graph["version"] = 2
        with self.assertRaises(RuntimeError):
            build_audit(self.stops, self.graph)

    def test_forged_clean_graph_summary_cannot_hide_branch_cycle_or_join(self):
        c = fragment(9, 0, "300A", 3)
        a, b, c_id = self.a["id"], self.b["id"], c["id"]
        for edges in ([(a, b), (a, c_id)], [(a, b), (b, a)], [(a, c_id), (b, c_id)]):
            with self.subTest(edges=edges), self.assertRaises(RuntimeError):
                verify_graph(graph(edges, self.rows + [c]))

    def test_graph_metadata_and_calendar_mutations_rejected(self):
        for key, value in (("calendar", "holiday"), ("previousPdfPage", 999), ("currentSection", 2)):
            p = copy.deepcopy(self.graph)
            p["edges"][0][key] = value
            with self.subTest(field=key), self.assertRaises(RuntimeError):
                verify_graph(p)

    def test_same_number_different_section_stays_separate_without_reference(self):
        second = fragment(7, 0, "100A", 3, section=1)
        p = build_audit(stop_payload([self.a, second]), graph([]))
        self.assertEqual(p["candidatePhysicalTrainCount"], 2)
        self.assertTrue(verify_mother(p)["verified"])


if __name__ == "__main__":
    unittest.main()
