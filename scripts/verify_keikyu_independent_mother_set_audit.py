#!/usr/bin/env python3
"""Fail-closed verifier for the independent Keikyu mother-set audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify(payload: dict) -> dict:
    errors: list[str] = []
    if payload.get("version") != 2:
        errors.append("version must be 2")
    if payload.get("kind") != "keikyu-independent-mother-set-audit":
        errors.append("unexpected dataset kind")

    policy = payload.get("identityPolicy") or {}
    required_true = (
        "allOfficialGeometryFragmentsAudited",
        "trainBearingRequiresTimeOrExplicitNumberOrOfficialReference",
        "anonymousUnreferencedZeroTimeExcludedFromTrainCount",
        "structuralBlankFragmentsRemainAudited",
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

    geometry = int(payload.get("geometryFragmentCount") or 0)
    train_fragments = int(payload.get("trainBearingFragmentCount") or 0)
    structural = int(payload.get("structuralBlankFragmentCount") or 0)
    edges = int(payload.get("officialCrossPageEdgeCount") or 0)
    trains = int(payload.get("candidatePhysicalTrainCount") or 0)
    joined = int(payload.get("joinedPhysicalTrainCandidateCount") or 0)
    singleton = int(payload.get("singletonPhysicalTrainCandidateCount") or 0)
    components = payload.get("components") or []
    structural_rows = payload.get("structuralBlankFragments") or []

    if geometry <= 0:
        errors.append("no official geometry fragments audited")
    if train_fragments <= 0:
        errors.append("no train-bearing fragments retained")
    if geometry != train_fragments + structural:
        errors.append("geometry partition mismatch")
    if structural != len(structural_rows):
        errors.append("structural blank count mismatch")
    if trains != len(components):
        errors.append("candidate train/component count mismatch")
    if trains != train_fragments - edges:
        errors.append(
            f"train-bearing forest accounting mismatch: trains={trains}, "
            f"fragments={train_fragments}, edges={edges}"
        )
    if joined + singleton != trains:
        errors.append("joined + singleton candidate count mismatch")

    structural_ids: set[str] = set()
    for row in structural_rows:
        fragment_id = str(row.get("id") or "")
        if not fragment_id:
            errors.append("structural blank missing id")
            continue
        if fragment_id in structural_ids:
            errors.append(f"duplicate structural blank: {fragment_id}")
        structural_ids.add(fragment_id)
        if row.get("printedTrainNumber"):
            errors.append(f"structural blank has explicit train number: {fragment_id}")
        if row.get("anonymousColumn") is not True:
            errors.append(f"structural blank is not anonymous: {fragment_id}")

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
            if member in structural_ids:
                errors.append(f"structural blank counted as train fragment: {member}")
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

    if fragment_sum != train_fragments or len(seen) != train_fragments:
        errors.append("not every train-bearing fragment belongs to exactly one component")
    if seen.intersection(structural_ids):
        errors.append("train-bearing and structural partitions overlap")
    if len(seen) + len(structural_ids) != geometry:
        errors.append("audited geometry fragments are not fully partitioned")

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
    if histogram_fragments != train_fragments:
        errors.append("component histogram train-fragment mismatch")

    zero_time_evidence = int(payload.get("zeroTimeEvidenceBearingFragmentCount") or 0)
    zero_time_ids = payload.get("zeroTimeEvidenceBearingFragments") or []
    if zero_time_evidence != len(zero_time_ids):
        errors.append("zero-time evidence-bearing count mismatch")
    if structural_ids.intersection(str(x) for x in zero_time_ids):
        errors.append("evidence-bearing zero-time fragment classified as structural blank")

    if payload.get("issues"):
        errors.append(f"mother-set audit has {len(payload['issues'])} issue(s)")

    if errors:
        raise RuntimeError("Keikyu independent mother-set verification failed:\n- " + "\n- ".join(errors[:100]))
    return {
        "verified": True,
        "geometryFragments": geometry,
        "trainBearingFragments": train_fragments,
        "structuralBlankFragments": structural,
        "officialCrossPageEdges": edges,
        "candidatePhysicalTrains": trains,
        "joinedCandidates": joined,
        "singletons": singleton,
        "sourceTimeCells": source,
        "resolvedTimeCells": resolved,
        "unresolvedTimeCells": unresolved,
        "zeroTimeEvidenceBearingFragments": zero_time_evidence,
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
