#!/usr/bin/env python3
"""Fail-closed verifier for the section-aware Keikyu cross-page identity graph."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from build_keikyu_cross_page_identity_audit import _components, _find_cycles

ID_RE = re.compile(r"^keikyu-official-pdf:p(\d{3}):s(\d{2}):c(\d{2})$")


def verify(payload: dict) -> dict:
    errors: list[str] = []
    version = payload.get("version")
    if version not in (2, 3):
        errors.append("version must be 2 or 3")
    if payload.get("kind") != "keikyu-official-section-cross-page-identity-audit":
        errors.append("unexpected dataset kind")

    policy = payload.get("identityPolicy") or {}
    required_true = (
        "officialPreviousPublicationPageRequired",
        "officialPreviousTrainNumberRequired",
        "uniqueTargetFragmentRequired",
        "pageSectionLocalFragmentMetadataMustMatch",
        "officialSectionIdentityRequired",
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
    if version == 3:
        for key in ("literalPrintedCalendarRequired", "unclassifiedCalendarPagesExcludedFromIdentity",
                    "crossPageEdgesStayWithinPrintedCalendar"):
            if policy.get(key) is not True:
                errors.append(f"{key} must be true")
        for key in ("calendarMayBeInferredFromPageNumber", "calendarMayBeInferredFromNeighboringPages"):
            if policy.get(key) is not False:
                errors.append(f"{key} must be false")

    candidate_count = int(payload.get("candidateReferenceCount") or 0)
    edge_count = int(payload.get("materializedCandidateEdgeCount") or 0)
    edges = payload.get("edges") or []
    if edge_count != len(edges):
        errors.append("edge count mismatch")
    if candidate_count != edge_count:
        errors.append(f"not every unique official reference materialized: {edge_count}/{candidate_count}")

    pairs: set[tuple[str, str]] = set()
    incoming, outgoing = defaultdict(list), defaultdict(list)
    nodes = set()
    node_calendars = defaultdict(set)
    calendars = Counter()
    for edge in edges:
        source = str(edge.get("fromFragment") or "")
        target = str(edge.get("toFragment") or "")
        if not source or not target:
            errors.append("edge missing fragment id")
            continue
        for node, prefix in ((source, "previous"), (target, "current")):
            match = ID_RE.fullmatch(node)
            if not match:
                errors.append(f"edge uses invalid section fragment id: {node}")
            elif (int(match[1]), int(match[2])) != (edge.get(prefix + "PdfPage"), edge.get(prefix + "Section")):
                errors.append(f"edge page/section metadata mismatch: {node}")
        nodes.update((source, target))
        outgoing[source].append(target)
        incoming[target].append(source)
        if version == 3:
            calendar = edge.get("calendar")
            if calendar not in ("weekday", "holiday"):
                errors.append("edge missing literal calendar")
            calendars[calendar] += 1
            node_calendars[source].add(calendar)
            node_calendars[target].add(calendar)
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
        if edge.get("previousSection") is None or edge.get("currentSection") is None:
            errors.append(f"edge missing section metadata: {source}->{target}")

    if payload.get("issues"):
        errors.append(f"identity audit has {len(payload['issues'])} structural/reference issue(s)")
    if payload.get("branchingTargets"):
        errors.append("reference graph branches")
    if payload.get("multiplePreviousSources"):
        errors.append("reference graph has multiple predecessors")
    if payload.get("cycles"):
        errors.append("reference graph contains cycles")
    # Recompute rather than trusting the producer's empty issue arrays.
    if any(len(v) > 1 for v in outgoing.values()):
        errors.append("actual reference graph branches")
    if any(len(v) > 1 for v in incoming.values()):
        errors.append("actual reference graph has multiple predecessors")
    if _find_cycles(nodes, outgoing):
        errors.append("actual reference graph contains cycles")
    groups = _components(nodes, list(pairs)) if nodes else []
    if payload.get("nodeCount") != len(nodes) or payload.get("identityComponentCount") != len(groups):
        errors.append("graph node/component accounting mismatch")
    if payload.get("componentSizeHistogram") != dict(Counter(str(len(g)) for g in groups)):
        errors.append("graph component histogram mismatch")
    if any(len(values) != 1 for values in node_calendars.values()):
        errors.append("component crosses printed calendars")
    if version == 3 and payload.get("calendarEdgeCounts") != {c: calendars[c] for c in ("weekday", "holiday")}:
        errors.append("calendar edge accounting mismatch")

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
