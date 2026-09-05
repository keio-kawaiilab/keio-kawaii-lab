#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import keisei_generated_evidence as generated

KEISEI = "odpt.Railway:Keisei.Oshiage"
TOEI = "odpt.Railway:Toei.Asakusa"


def strict_policy(*, safe: bool = True) -> dict:
    return {
        "trainNumberAloneMayEstablishIdentity": False if safe else True,
        "timeProximityAloneMayEstablishIdentity": False,
        "exactBoundaryAnchorRequired": True,
        "ambiguousBoundaryEndpointRequiresExactAdjacentOfficialAnchor": True,
        "officialTrainNumberMayDisambiguateOnlyAfterExactBoundaryAndAdjacentAnchor": True,
        "boundaryMinuteTolerance": 0,
        "adjacentMinuteTolerance": 0,
    }


def fragment(fragment_id: str, railway: str, *, train_number: str = "", exact: bool = False) -> dict:
    station = "odpt.Station:Keisei.Oshiage.Oshiage" if railway == KEISEI else "odpt.Station:Toei.Asakusa.Oshiage"
    return {
        "id": fragment_id,
        "railway": railway,
        "calendar": "odpt.Calendar:Weekday",
        "stops": [[station, 600, 600]],
        "sourceKind": "exact-train-timetable" if exact else "station-timetable-reconstruction",
        "trainNumber": train_number,
    }


def payload(item: dict, *, safe: bool = True) -> dict:
    return {"version": 3, "policy": strict_policy(safe=safe), "entries": [item]}


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
        "sourceMatchMethod": "boundary-singleton",
        "targetMatchMethod": "boundary-singleton",
        "resolvedByOfficialTrainNumberAfterExactAnchors": False,
        "matchPolicy": strict_policy(),
        "evidence": ["operator-official-per-train-timetable", generated.MARKER],
        "sourceUrl": "https://keisei.ekitan.com/example",
    }
    base.update(changes)
    return base


def indexes(*, verified: bool = True) -> dict:
    graph = {KEISEI: []}
    if verified:
        graph[KEISEI].append({"toRailway": TOEI, "boundaryId": generated.BOUNDARY_ID})
    return {"graph": graph}


class GeneratedEvidenceTest(unittest.TestCase):
    def apply(self, data: dict, *, fragments=None, graph=None):
        fragments = fragments if fragments is not None else [fragment("k1", KEISEI), fragment("t1", TOEI)]
        unresolved: list[dict] = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            edges = generated.apply_generated_evidence(fragments, [], unresolved, graph if graph is not None else indexes(), path)
        return edges, unresolved

    def test_valid_singleton_adds_evidence_backed_edge(self):
        edges, unresolved = self.apply(payload(entry()))
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))
        self.assertEqual("same-train", edges[0]["classification"])
        self.assertEqual("evidence-backed", edges[0]["identityLevel"])

    def test_valid_post_anchor_train_number_resolution(self):
        item = entry(
            officialTrainNumber="official:E04205",
            sourceMatchMethod=generated.TRAIN_NUMBER_METHOD,
            sourceAdjacentAnchor={"station": "odpt.Station:Keisei.Oshiage.Yotsugi", "minutes": [598]},
            resolvedByOfficialTrainNumberAfterExactAnchors=True,
        )
        fragments = [fragment("k1", KEISEI, train_number="official:E04205", exact=True), fragment("t1", TOEI)]
        edges, unresolved = self.apply(payload(item), fragments=fragments)
        self.assertEqual([], unresolved)
        self.assertEqual(1, len(edges))

    def test_train_number_resolution_rejects_mismatched_exact_fragment(self):
        item = entry(
            officialTrainNumber="official:E04205",
            sourceMatchMethod=generated.TRAIN_NUMBER_METHOD,
            sourceAdjacentAnchor={"station": "odpt.Station:Keisei.Oshiage.Yotsugi", "minutes": [598]},
            resolvedByOfficialTrainNumberAfterExactAnchors=True,
        )
        fragments = [fragment("k1", KEISEI, train_number="other", exact=True), fragment("t1", TOEI)]
        edges, unresolved = self.apply(payload(item), fragments=fragments)
        self.assertEqual([], edges)
        self.assertEqual("invalid-post-anchor-train-number-resolution", unresolved[0]["reason"])

    def test_train_number_resolution_requires_exact_adjacent_anchor_method(self):
        item = entry(
            officialTrainNumber="official:E04205",
            sourceMatchMethod="boundary-singleton",
            sourceAdjacentAnchor={"station": "odpt.Station:Keisei.Oshiage.Yotsugi", "minutes": [598]},
            resolvedByOfficialTrainNumberAfterExactAnchors=True,
        )
        fragments = [fragment("k1", KEISEI, train_number="official:E04205", exact=True), fragment("t1", TOEI)]
        edges, unresolved = self.apply(payload(item), fragments=fragments)
        self.assertEqual([], edges)
        self.assertEqual("invalid-post-anchor-train-number-resolution", unresolved[0]["reason"])

    def test_unsafe_policy_fails_closed(self):
        edges, unresolved = self.apply(payload(entry(), safe=False))
        self.assertEqual([], edges)
        self.assertEqual("keisei-oshiage-generated-evidence-unsafe-policy", unresolved[0]["kind"])

    def test_unsafe_entry_policy_fails_closed(self):
        edges, unresolved = self.apply(payload(entry(matchPolicy=strict_policy(safe=False))))
        self.assertEqual([], edges)
        self.assertEqual("unsafe-entry-match-policy", unresolved[0]["reason"])

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
