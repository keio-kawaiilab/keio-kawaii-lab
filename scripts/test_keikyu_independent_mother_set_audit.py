#!/usr/bin/env python3
from __future__ import annotations

import unittest

from build_keikyu_independent_mother_set_audit import build_audit
from verify_keikyu_independent_mother_set_audit import verify


def fragment(page: int, col: int, number: str | None, resolved: int, unresolved: int = 0) -> dict:
    return {
        "id": f"keikyu-official-pdf:p{page:03d}:c{col:02d}",
        "page": page,
        "column": col,
        "printedTrainNumber": number,
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
    def test_every_fragment_and_cell_is_preserved_exactly_once(self):
        a = fragment(7, 0, "100A", 2)
        b = fragment(8, 0, "200A", 3, 1)
        c = fragment(9, 0, "300A", 4)
        d = fragment(10, 0, None, 1, 2)
        payload = build_audit(stop_payload([a, b, c, d]), graph([(a["id"], b["id"]), (b["id"], c["id"])]))
        result = verify(payload)
        self.assertTrue(result["verified"])
        self.assertEqual(payload["localFragmentCount"], 4)
        self.assertEqual(payload["officialCrossPageEdgeCount"], 2)
        self.assertEqual(payload["candidatePhysicalTrainCount"], 2)
        self.assertEqual(payload["joinedPhysicalTrainCandidateCount"], 1)
        self.assertEqual(payload["singletonPhysicalTrainCandidateCount"], 1)
        self.assertEqual(payload["componentSizeHistogram"], {"1": 1, "3": 1})
        self.assertEqual(payload["sourceTimeCells"], 13)
        self.assertEqual(payload["identityPolicy"]["runtimeSameTrainPromotions"], 0)

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

    def test_empty_fragment_is_retained_not_silently_dropped(self):
        a = fragment(7, 0, None, 0)
        payload = build_audit(stop_payload([a]), graph([]))
        result = verify(payload)
        self.assertTrue(result["verified"])
        self.assertEqual(payload["emptyLocalFragmentCount"], 1)
        self.assertEqual(payload["candidatePhysicalTrainCount"], 1)


if __name__ == "__main__":
    unittest.main()
