#!/usr/bin/env python3
from __future__ import annotations

import unittest

from build_keikyu_independent_mother_set_audit import build_audit
from verify_keikyu_independent_mother_set_audit import verify


def fragment(
    page: int,
    col: int,
    number: str | None,
    resolved: int,
    unresolved: int = 0,
    *,
    anonymous: bool | None = None,
) -> dict:
    if anonymous is None:
        anonymous = number is None
    return {
        "id": f"keikyu-official-pdf:p{page:03d}:c{col:02d}",
        "page": page,
        "column": col,
        "printedTrainNumber": number,
        "anonymousColumn": anonymous,
        "stopTimes": [{"station": f"S{i}", "event": "departure", "time": "1000"} for i in range(resolved)],
        "unresolvedCells": [{"time": "1001"} for _ in range(unresolved)],
    }


def stop_payload(rows: list[dict]) -> dict:
    resolved = sum(len(row["stopTimes"]) for row in rows)
    unresolved = sum(len(row["unresolvedCells"]) for row in rows)
    return {
        "source": {"sha256": "abc"},
        "identityPolicy": {
            "pageColumnIsExactLocalIdentity": True,
            "runtimeSameTrainPromotions": 0,
        },
        "totals": {
            "trainColumnFragments": len(rows),
            "resolvedTimeCells": resolved,
            "unresolvedTimeCells": unresolved,
            "sourceTimeCells": resolved + unresolved,
        },
        "fragments": rows,
    }


def graph(edges: list[tuple[str, str]]) -> dict:
    nodes = sorted({node for edge in edges for node in edge})
    return {
        "version": 1,
        "kind": "keikyu-official-cross-page-identity-audit",
        "candidateReferenceCount": len(edges),
        "materializedCandidateEdgeCount": len(edges),
        "nodeCount": len(nodes),
        "identityComponentCount": 1 if nodes else 0,
        "componentSizeHistogram": {str(len(nodes)): 1} if nodes else {},
        "branchingTargets": {},
        "multiplePreviousSources": {},
        "cycles": [],
        "issues": [],
        "edges": [
            {
                "fromFragment": a,
                "toFragment": b,
                "evidence": "keikyu-official-previous-publication-page-and-train-number",
                "previousPrintedPage": 1,
                "previousTrainNumber": "100A",
            }
            for a, b in edges
        ],
        "identityPolicy": {
            "officialPreviousPublicationPageRequired": True,
            "officialPreviousTrainNumberRequired": True,
            "uniqueTargetFragmentRequired": True,
            "pageLocalFragmentMetadataMustMatch": True,
            "clockTimeUsedForIdentity": False,
            "destinationUsedForIdentity": False,
            "branchingAllowedForPromotion": False,
            "cyclesAllowedForPromotion": False,
            "crossPageIdentityEstablished": False,
            "runtimeSameTrainPromotions": 0,
        },
    }


class KeikyuIndependentMotherSetAuditTest(unittest.TestCase):
    def test_every_train_fragment_and_cell_is_preserved_exactly_once(self):
        a = fragment(7, 0, "100A", 2)
        b = fragment(8, 0, "200A", 3, 1)
        c = fragment(9, 0, "300A", 4)
        d = fragment(10, 0, None, 1, 2)
        payload = build_audit(stop_payload([a, b, c, d]), graph([(a["id"], b["id"]), (b["id"], c["id"])]))
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
        payload = build_audit(stop_payload([previous, referenced_empty]), graph([(previous["id"], referenced_empty["id"])]))
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
        missing = "keikyu-official-pdf:p008:c00"
        payload = build_audit(stop_payload([a]), graph([(a["id"], missing)]))
        self.assertTrue(payload["issues"])
        with self.assertRaises(RuntimeError):
            verify(payload)

    def test_upstream_runtime_promotion_is_rejected(self):
        a = fragment(7, 0, "100A", 1)
        stops = stop_payload([a])
        stops["identityPolicy"]["runtimeSameTrainPromotions"] = 1
        payload = build_audit(stops, graph([]))
        with self.assertRaises(RuntimeError):
            verify(payload)


if __name__ == "__main__":
    unittest.main()
