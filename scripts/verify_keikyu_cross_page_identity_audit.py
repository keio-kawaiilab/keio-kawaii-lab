#!/usr/bin/env python3
"""Fail-closed verifier for the Keikyu cross-page identity audit graph."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify(payload: dict) -> dict:
    errors: list[str] = []
    if payload.get("version") != 1:
        errors.append("version must be 1")
    if payload.get("kind") != "keikyu-official-cross-page-identity-audit":
        errors.append("unexpected dataset kind")

    policy = payload.get("identityPolicy") or {}
    required_true = (
        "officialPreviousPublicationPageRequired",
        "officialPreviousTrainNumberRequired",
        "uniqueTargetFragmentRequired",
        "pageLocalFragmentMetadataMustMatch",
    )
    required_false = (
        "clockTimeUsedForIdentity",
        "destinationUsedForIdentity",
        "branchingAllowedForPromotion",
        "cyclesAllowedForPromotion",
        "crossPageIdentityEstablished",
    )
    for key in required_true:
        if policy.get(key) is not True:
            errors.append(f"{key} must be true")
    for key in required_false:
        if policy.get(key) is not False:
            errors.append(f"{key} must be false")
    if policy.get("runtimeSameTrainPromotions") != 0:
        errors.append("runtimeSameTrainPromotions must remain zero")

    candidate_count = int(payload.get("candidateReferenceCount") or 0)
    edge_count = int(payload.get("materializedCandidateEdgeCount") or 0)
    edges = payload.get("edges") or []
    if edge_count != len(edges):
        errors.append("edge count mismatch")
    if candidate_count != edge_count:
        errors.append(f"not every unique official reference materialized: {edge_count}/{candidate_count}")

    pairs: set[tuple[str, str]] = set()
    for edge in edges:
        source = str(edge.get("fromFragment") or "")
        target = str(edge.get("toFragment") or "")
        if not source or not target:
            errors.append("edge missing fragment id")
            continue
        if source == target:
            errors.append(f"self edge: {source}")
        pair = (source, target)
        if pair in pairs:
            errors.append(f"duplicate edge: {source}->{target}")
        pairs.add(pair)
        if edge.get("evidence") != "keikyu-official-previous-publication-page-and-train-number":
            errors.append(f"unexpected evidence marker: {source}->{target}")
        if not edge.get("previousTrainNumber"):
            errors.append(f"edge missing previous train number: {source}->{target}")
        if not edge.get("previousPrintedPage"):
            errors.append(f"edge missing previous printed page: {source}->{target}")

    if payload.get("issues"):
        errors.append(f"identity audit has {len(payload['issues'])} structural/reference issue(s)")
    if payload.get("branchingTargets"):
        errors.append("reference graph branches")
    if payload.get("multiplePreviousSources"):
        errors.append("reference graph has multiple predecessors")
    if payload.get("cycles"):
        errors.append("reference graph contains cycles")

    if errors:
        raise RuntimeError("Keikyu cross-page identity audit verification failed:\n- " + "\n- ".join(errors[:100]))
    return {
        "verified": True,
        "candidateReferences": candidate_count,
        "candidateEdges": edge_count,
        "nodes": int(payload.get("nodeCount") or 0),
        "components": int(payload.get("identityComponentCount") or 0),
        "runtimeSameTrainPromotions": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    print(json.dumps(verify(payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
