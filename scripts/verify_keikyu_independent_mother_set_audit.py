#!/usr/bin/env python3
"""Fail-closed verifier for the independent Keikyu mother-set audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify(payload: dict) -> dict:
    errors: list[str] = []
    if payload.get("version") != 1:
        errors.append("version must be 1")
    if payload.get("kind") != "keikyu-independent-mother-set-audit":
        errors.append("unexpected dataset kind")

    policy = payload.get("identityPolicy") or {}
    required_true = (
        "allOfficialPageLocalColumnsRetained",
        "onlyVerifiedOfficialCrossPageEdgesMayUnion",
        "crossPageIdentityCandidateOnly",
    )
    required_false = (
        "clockTimeMayEstablishIdentity",
        "destinationMayEstablishIdentity",
    )
    for key in required_true:
        if policy.get(key) is not True:
            errors.append(f"{key} must be true")
    for key in required_false:
        if policy.get(key) is not False:
            errors.append(f"{key} must be false")
    if policy.get("runtimeSameTrainPromotions") != 0:
        errors.append("runtimeSameTrainPromotions must remain zero")

    fragments = int(payload.get("localFragmentCount") or 0)
    edges = int(payload.get("officialCrossPageEdgeCount") or 0)
    trains = int(payload.get("candidatePhysicalTrainCount") or 0)
    joined = int(payload.get("joinedPhysicalTrainCandidateCount") or 0)
    singleton = int(payload.get("singletonPhysicalTrainCandidateCount") or 0)
    components = payload.get("components") or []
    if fragments <= 0:
        errors.append("no official fragments retained")
    if trains != len(components):
        errors.append("candidate train/component count mismatch")
    if trains != fragments - edges:
        errors.append(f"forest accounting mismatch: trains={trains}, fragments={fragments}, edges={edges}")
    if joined + singleton != trains:
        errors.append("joined + singleton candidate count mismatch")

    seen: set[str] = set()
    fragment_sum = 0
    component_cell_sum = 0
    for component in components:
        members = [str(x) for x in component.get("fragments") or []]
        count = int(component.get("fragmentCount") or 0)
        if not members or count != len(members):
            errors.append(f"invalid component membership: {component.get('id')}")
            continue
        fragment_sum += count
        for member in members:
            if member in seen:
                errors.append(f"fragment assigned twice: {member}")
            seen.add(member)
        resolved = int(component.get("resolvedTimeCells") or 0)
        unresolved = int(component.get("unresolvedTimeCells") or 0)
        source = int(component.get("sourceTimeCells") or 0)
        if resolved + unresolved != source:
            errors.append(f"component cell accounting mismatch: {component.get('id')}")
        component_cell_sum += source
        basis = component.get("identityBasis")
        if count == 1 and basis != "page-local-column":
            errors.append(f"singleton has wrong identity basis: {component.get('id')}")
        if count > 1 and basis != "official-previous-publication-reference":
            errors.append(f"joined component has wrong identity basis: {component.get('id')}")

    if fragment_sum != fragments or len(seen) != fragments:
        errors.append("not every retained fragment belongs to exactly one component")

    resolved = int(payload.get("resolvedTimeCells") or 0)
    unresolved = int(payload.get("unresolvedTimeCells") or 0)
    source = int(payload.get("sourceTimeCells") or 0)
    if resolved + unresolved != source:
        errors.append("mother-set cell accounting mismatch")
    if component_cell_sum != source:
        errors.append("component cells do not sum to mother-set source cells")
    if source <= 0:
        errors.append("mother set has no source time cells")

    histogram = payload.get("componentSizeHistogram") or {}
    histogram_components = sum(int(v) for v in histogram.values())
    histogram_fragments = sum(int(k) * int(v) for k, v in histogram.items())
    if histogram_components != trains:
        errors.append("component histogram count mismatch")
    if histogram_fragments != fragments:
        errors.append("component histogram fragment mismatch")

    if payload.get("issues"):
        errors.append(f"mother-set audit has {len(payload['issues'])} issue(s)")

    if errors:
        raise RuntimeError("Keikyu independent mother-set verification failed:\n- " + "\n- ".join(errors[:100]))
    return {
        "verified": True,
        "localFragments": fragments,
        "officialCrossPageEdges": edges,
        "candidatePhysicalTrains": trains,
        "joinedCandidates": joined,
        "singletons": singleton,
        "sourceTimeCells": source,
        "resolvedTimeCells": resolved,
        "unresolvedTimeCells": unresolved,
        "emptyLocalFragments": int(payload.get("emptyLocalFragmentCount") or 0),
        "emptyComponents": int(payload.get("emptyComponentCount") or 0),
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
