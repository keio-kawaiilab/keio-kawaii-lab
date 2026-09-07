#!/usr/bin/env python3
from __future__ import annotations

import unittest

from build_keikyu_independent_mother_set_audit import build_audit
from verify_keikyu_independent_mother_set_audit import verify


from keikyu_audit_test_fixtures import fragment, stop_payload, graph


class KeikyuIndependentMotherSetAuditTest(unittest.TestCase):
    def test_every_train_fragment_and_cell_is_preserved_exactly_once(self):
        a = fragment(7, 0, "100A", 2)
        b = fragment(8, 0, "200A", 3, 1)
        c = fragment(9, 0, "300A", 4)
        d = fragment(10, 0, None, 1, 2)
        payload = build_audit(stop_payload([a, b, c, d]), graph([(a["id"], b["id"]), (b["id"], c["id"])], [a,b,c,d]))
        result = verify(payload)
        self.assertTrue(result["verified"])
        self.assertEqual(payload["geometryFragmentCount"], 4)
        self.assertEqual(payload["trainBearingFragmentCount"], 4)
        self.assertEqual(payload["structuralBlankFragmentCount"], 0)
        self.assertEqual(payload["officialCrossPageEdgeCount"], 2)
        self.assertEqual(payload["candidatePhysicalTrainCount"], 2)
        self.assertEqual(payload["joinedPhysicalTrainCandidateCount"], 1)
        self.assertEqual(payload["singletonPhysicalTrainCandidateCount"], 1)
        self.assertEqual(payload["componentSizeHistogram"], {"1": 1, "3": 1})
        self.assertEqual(payload["sourceTimeCells"], 13)
        self.assertEqual(payload["identityPolicy"]["runtimeSameTrainPromotions"], 0)

    def test_anonymous_zero_time_unreferenced_slot_is_audited_but_not_a_train(self):
        normal = fragment(7, 0, "100A", 1)
        blank = fragment(7, 1, None, 0)
        payload = build_audit(stop_payload([normal, blank]), graph([]))
        result = verify(payload)
        self.assertTrue(result["verified"])
        self.assertEqual(payload["geometryFragmentCount"], 2)
        self.assertEqual(payload["trainBearingFragmentCount"], 1)
        self.assertEqual(payload["structuralBlankFragmentCount"], 1)
        self.assertEqual(payload["candidatePhysicalTrainCount"], 1)
        self.assertEqual(payload["structuralBlankFragments"][0]["id"], blank["id"])
        self.assertEqual(payload["sourceTimeCells"], 1)

    def test_explicit_number_zero_time_fragment_is_retained_as_train_evidence(self):
        normal = fragment(7, 0, "100A", 1)
        explicit_empty = fragment(7, 1, "102A", 0)
        payload = build_audit(stop_payload([normal, explicit_empty]), graph([]))
        result = verify(payload)
        self.assertTrue(result["verified"])
        self.assertEqual(payload["trainBearingFragmentCount"], 2)
        self.assertEqual(payload["structuralBlankFragmentCount"], 0)
        self.assertEqual(payload["zeroTimeEvidenceBearingFragmentCount"], 1)
        self.assertIn(explicit_empty["id"], payload["zeroTimeEvidenceBearingFragments"])

    def test_anonymous_zero_time_officially_referenced_fragment_is_retained(self):
        previous = fragment(7, 0, "100A", 1)
        referenced_empty = fragment(8, 0, None, 0)
        payload = build_audit(stop_payload([previous, referenced_empty]), graph([(previous["id"], referenced_empty["id"])], [previous,referenced_empty]))
        result = verify(payload)
        self.assertTrue(result["verified"])
        self.assertEqual(payload["trainBearingFragmentCount"], 2)
        self.assertEqual(payload["candidatePhysicalTrainCount"], 1)
        self.assertEqual(payload["zeroTimeEvidenceBearingFragmentCount"], 1)
        self.assertIn(referenced_empty["id"], payload["zeroTimeEvidenceBearingFragments"])

    def test_nonempty_anonymous_fragment_is_retained(self):
        anonymous = fragment(7, 0, None, 2)
        payload = build_audit(stop_payload([anonymous]), graph([]))
        result = verify(payload)
        self.assertTrue(result["verified"])
        self.assertEqual(payload["trainBearingFragmentCount"], 1)
        self.assertEqual(payload["structuralBlankFragmentCount"], 0)
        self.assertEqual(payload["candidatePhysicalTrainCount"], 1)

    def test_missing_graph_fragment_fails_closed(self):
        a = fragment(7, 0, "100A", 1)
        missing = "keikyu-official-pdf:p008:s00:c00"
        payload = build_audit(stop_payload([a]), graph([(a["id"], missing)]))
        self.assertTrue(payload["issues"])
        with self.assertRaises(RuntimeError):
            verify(payload)

    def test_upstream_runtime_promotion_is_rejected(self):
        a = fragment(7, 0, "100A", 1)
        stops = stop_payload([a])
        stops["identityPolicy"]["runtimeSameTrainPromotions"] = 1
        with self.assertRaises(RuntimeError):
            build_audit(stops, graph([]))


if __name__ == "__main__":
    unittest.main()
