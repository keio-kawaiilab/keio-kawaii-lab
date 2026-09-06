#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import keikyu_generated_evidence as generated

KEIKYU = "odpt.Railway:Keikyu.Main"
TOEI = "odpt.Railway:Toei.Asakusa"


def fragment(fragment_id: str, railway: str) -> dict:
    return {
        "id": fragment_id,
        "railway": railway,
        "calendar": "odpt.Calendar:Weekday",
        "stops": [["odpt.Station:Keikyu.Main.Sengakuji", 600, 600]],
    }


def payload(entry: dict, *, safe: bool = True) -> dict:
    return {
        "version": 3,
        "policy": {
            "trainNumberAloneMayEstablishIdentity": False if safe else True,
            "timeProximityAloneMayEstablishIdentity": False,
        },
        "entries": [entry],
    }


def entry(*, independently_verified: bool = True, **changes) -> dict:
    base = {
        "id": "official:test",
        "matchStatus": "matched-singleton",
        "boundaryId": generated.BOUNDARY_ID,
        "fromRailway": KEIKYU,
        "toRailway": TOEI,
        "fromFragment": "k1",
        "toFragment": "t1",
        "sourceMatches": ["k1"],
        "targetMatches": ["t1"],
        "evidence": [
            "operator-official-connection-timetable",
            generated.SAFE_CONTINUATION_MARKER if independently_verified else generated.LEGACY_COLUMN_MARKER,
        ],
        "sourceUrl": "https://www.keikyu.co.jp/example.pdf",
    }
    if independently_verified:
        base["verification"] = {"crossBoundaryContinuationVerified": True}
    base.update(changes)
    return base


def indexes(*, verified: bool = True) -> dict:
    graph = {KEIKYU: []}
    if verified:
        graph[KEIKYU].append({
            "toRailway": TOEI,
            "boundaryId": generated.BOUNDARY_ID,
        })
    return {"graph": graph}


class GeneratedEvidenceTest(unittest.TestCase):
    def apply(self, data: dict, *, fragments=None, graph=None):
        fragments = fragments if fragments is not None else [fragment("k1", KEIKYU), fragment("t1", TOEI)]
        unresolved: list[dict] = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            edges = generated.apply_generated_evidence(
                fragments,
                [],
                unresolved,
                graph if graph is not None else indexes(),
                path,
            )
        return edges, unresolved

    def test_independently_verified_singleton_adds_evidence_backed_edge(self):
        edges, unresolved = self.apply(payload(entry()))
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        edge = edges[0]
        self.assertEqual("same-train", edge["classification"])
        self.assertEqual("evidence-backed", edge["identityLevel"])
        self.assertEqual(KEIKYU, edge["boundary"]["fromRailway"])
        self.assertEqual(TOEI, edge["boundary"]["toRailway"])
        self.assertIn("independently-verified-cross-boundary-continuation", edge["evidence"])
        self.assertNotIn(generated.LEGACY_COLUMN_MARKER, edge["evidence"])

    def test_legacy_same_column_candidate_never_promotes(self):
        edges, unresolved = self.apply(payload(entry(independently_verified=False)))
        self.assertEqual([], edges)
        self.assertTrue(any(
            row.get("kind") == "keikyu-generated-evidence-legacy-column-marker-disabled"
            for row in unresolved
        ))

    def test_safe_marker_without_explicit_verification_fails_closed(self):
        candidate = entry()
        candidate.pop("verification", None)
        edges, unresolved = self.apply(payload(candidate))
        self.assertEqual([], edges)
        self.assertTrue(any(
            row.get("reason") == "cross-boundary-continuation-not-verified"
            for row in unresolved
        ))

    def test_unsafe_policy_fails_closed(self):
        edges, unresolved = self.apply(payload(entry(), safe=False))
        self.assertEqual([], edges)
        self.assertEqual("keikyu-generated-evidence-unsafe-policy", unresolved[0]["kind"])

    def test_stale_fragment_reference_fails_closed(self):
        edges, unresolved = self.apply(
            payload(entry()),
            fragments=[fragment("k1", KEIKYU)],
        )
        self.assertEqual([], edges)
        self.assertEqual("stale-fragment-reference", unresolved[0]["reason"])

    def test_non_singleton_recorded_match_fails_closed(self):
        edges, unresolved = self.apply(payload(entry(sourceMatches=["k1", "k2"])))
        self.assertEqual([], edges)
        self.assertEqual("non-singleton-recorded-match", unresolved[0]["reason"])

    def test_wrong_boundary_fails_closed(self):
        edges, unresolved = self.apply(payload(entry(boundaryId="wrong-boundary")))
        self.assertEqual([], edges)
        self.assertEqual("missing-independent-cross-boundary-continuation-marker", unresolved[0]["reason"])

    def test_unverified_operational_boundary_fails_closed(self):
        edges, unresolved = self.apply(payload(entry()), graph=indexes(verified=False))
        self.assertEqual([], edges)
        self.assertEqual("unverified-operational-boundary", unresolved[0]["reason"])


if __name__ == "__main__":
    unittest.main()
