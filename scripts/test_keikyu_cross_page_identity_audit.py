#!/usr/bin/env python3
from __future__ import annotations

import unittest

from build_keikyu_cross_page_identity_audit import build_audit
from verify_keikyu_cross_page_identity_audit import verify


def stop_payload(numbers: dict[tuple[int, int], str | None]) -> dict:
    fragments = []
    for (page, column), number in sorted(numbers.items()):
        fragments.append({
            "id": f"keikyu-official-pdf:p{page:03d}:c{column:02d}",
            "page": page,
            "column": column,
            "printedTrainNumber": number,
            "stopTimes": [],
        })
    return {
        "identityPolicy": {
            "pageColumnIsExactLocalIdentity": True,
            "runtimeSameTrainPromotions": 0,
        },
        "fragments": fragments,
    }


def refs(rows: list[dict]) -> dict:
    return {
        "source": {"sha256": "abc"},
        "uniqueExplicitReferenceCandidateCount": len(rows),
        "identityPolicy": {
            "officialPreviousPublicationMetadataExtracted": True,
            "runtimeSameTrainPromotions": 0,
        },
        "fragments": rows,
    }


def ref(current_page: int, current_col: int, current_no: str | None,
        previous_page: int, previous_col: int, previous_no: str) -> dict:
    return {
        "pdfPage": current_page,
        "printedPage": current_page,
        "column": current_col,
        "currentTrainNumber": current_no,
        "previousPrintedPage": previous_page,
        "previousTrainNumber": previous_no,
        "targetStatus": "unique-explicit-reference-candidate",
        "targetPdfPage": previous_page,
        "targetColumn": previous_col,
    }


class KeikyuCrossPageIdentityAuditTest(unittest.TestCase):
    def test_linear_exact_reference_chain_verifies(self):
        stops = stop_payload({(7, 0): "100A", (8, 0): "200A", (9, 0): "300A"})
        references = refs([
            ref(8, 0, "200A", 7, 0, "100A"),
            ref(9, 0, "300A", 8, 0, "200A"),
        ])
        payload = build_audit(stops, references)
        result = verify(payload)
        self.assertTrue(result["verified"])
        self.assertEqual(payload["materializedCandidateEdgeCount"], 2)
        self.assertEqual(payload["identityComponentCount"], 1)
        self.assertEqual(payload["runtimeSameTrainPromotions"], 0 if "runtimeSameTrainPromotions" in payload else 0)

    def test_previous_train_number_mismatch_is_rejected(self):
        stops = stop_payload({(7, 0): "100A", (8, 0): "200A"})
        payload = build_audit(stops, refs([ref(8, 0, "200A", 7, 0, "999A")]))
        self.assertEqual(payload["materializedCandidateEdgeCount"], 0)
        self.assertEqual(payload["issues"][0]["kind"], "previous-train-number-mismatch")
        with self.assertRaises(RuntimeError):
            verify(payload)

    def test_stale_target_fragment_is_rejected(self):
        stops = stop_payload({(8, 0): "200A"})
        payload = build_audit(stops, refs([ref(8, 0, "200A", 7, 0, "100A")]))
        self.assertEqual(payload["issues"][0]["kind"], "stale-fragment-reference")
        with self.assertRaises(RuntimeError):
            verify(payload)

    def test_branching_reference_graph_fails_closed(self):
        stops = stop_payload({(7, 0): "100A", (8, 0): "200A", (9, 0): "300A"})
        payload = build_audit(stops, refs([
            ref(8, 0, "200A", 7, 0, "100A"),
            ref(9, 0, "300A", 7, 0, "100A"),
        ]))
        self.assertIn("keikyu-official-pdf:p007:c00", payload["branchingTargets"])
        with self.assertRaises(RuntimeError):
            verify(payload)

    def test_cycle_fails_closed(self):
        stops = stop_payload({(7, 0): "100A", (8, 0): "200A"})
        payload = build_audit(stops, refs([
            ref(8, 0, "200A", 7, 0, "100A"),
            ref(7, 0, "100A", 8, 0, "200A"),
        ]))
        self.assertTrue(payload["cycles"])
        with self.assertRaises(RuntimeError):
            verify(payload)


if __name__ == "__main__":
    unittest.main()
