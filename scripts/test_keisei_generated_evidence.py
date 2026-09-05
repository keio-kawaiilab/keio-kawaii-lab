#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import keisei_generated_evidence as generated

KEISEI = "odpt.Railway:Keisei.Oshiage"
TOEI = "odpt.Railway:Toei.Asakusa"


def fragment(fragment_id: str, railway: str) -> dict:
    station = "odpt.Station:Keisei.Oshiage.Oshiage" if railway == KEISEI else "odpt.Station:Toei.Asakusa.Oshiage"
    return {
        "id": fragment_id,
        "railway": railway,
        "calendar": "odpt.Calendar:Weekday",
        "stops": [[station, 600, 600]],
    }


def payload(entry: dict, *, safe: bool = True) -> dict:
    return {
        "version": 1,
        "policy": {
            "trainNumberAloneMayEstablishIdentity": False if safe else True,
            "timeProximityAloneMayEstablishIdentity": False,
        },
        "entries": [entry],
    }


def entry(**changes) -> dict:
    base = {
        "id": "official:test",
        "matchStatus": "matched-singleton",
        "boundaryId": generated.BOUNDARY_ID,
        "fromRailway": KEISEI,
        "toRailway": TOEI,
        "fromFragment": "k1",
        "toFragment": "t1",
        "sourceMatches": ["k1"],
        "targetMatches": ["t1"],
        "evidence": [
            "operator-official-per-train-timetable",
            generated.MARKER,
        ],
        "sourceUrl": "https://keisei.ekitan.com/example",
    }
    base.update(changes)
    return base


def indexes(*, verified: bool = True) -> dict:
    graph = {KEISEI: []}
    if verified:
        graph[KEISEI].append({
            "toRailway": TOEI,
            "boundaryId": generated.BOUNDARY_ID,
        })
    return {"graph": graph}


class GeneratedEvidenceTest(unittest.TestCase):
    def apply(self, data: dict, *, fragments=None, graph=None):
        fragments = fragments if fragments is not None else [fragment("k1", KEISEI), fragment("t1", TOEI)]
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

    def test_valid_singleton_adds_evidence_backed_edge(self):
        edges, unresolved = self.apply(payload(entry()))
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        edge = edges[0]
        self.assertEqual("same-train", edge["classification"])
        self.assertEqual("evidence-backed", edge["identityLevel"])
        self.assertEqual(KEISEI, edge["boundary"]["fromRailway"])
        self.assertEqual(TOEI, edge["boundary"]["toRailway"])
        self.assertIn("keisei-official-per-train-timetable-spans-oshiage", edge["evidence"])

    def test_unsafe_policy_fails_closed(self):
        edges, unresolved = self.apply(payload(entry(), safe=False))
        self.assertEqual([], edges)
        self.assertEqual("keisei-oshiage-generated-evidence-unsafe-policy", unresolved[0]["kind"])

    def test_stale_fragment_reference_fails_closed(self):
        edges, unresolved = self.apply(payload(entry()), fragments=[fragment("k1", KEISEI)])
        self.assertEqual([], edges)
        self.assertEqual("stale-fragment-reference", unresolved[0]["reason"])

    def test_non_singleton_recorded_match_fails_closed(self):
        edges, unresolved = self.apply(payload(entry(sourceMatches=["k1", "k2"])))
        self.assertEqual([], edges)
        self.assertEqual("non-singleton-recorded-match", unresolved[0]["reason"])

    def test_wrong_boundary_marker_fails_closed(self):
        edges, unresolved = self.apply(payload(entry(boundaryId="wrong-boundary")))
        self.assertEqual([], edges)
        self.assertEqual("missing-official-train-page-marker", unresolved[0]["reason"])

    def test_unverified_boundary_fails_closed(self):
        edges, unresolved = self.apply(payload(entry()), graph=indexes(verified=False))
        self.assertEqual([], edges)
        self.assertEqual("unverified-operational-boundary", unresolved[0]["reason"])


if __name__ == "__main__":
    unittest.main()
