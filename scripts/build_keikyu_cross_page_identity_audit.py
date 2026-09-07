#!/usr/bin/env python3
"""Build an audit-only identity graph from Keikyu explicit printed page references.

Both stop-time fragments and references must use page+section+column local identity.
No runtime same-train edge is produced here.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from build_keikyu_official_stop_times import fragment_id


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _find_cycles(nodes: set[str], outgoing: dict[str, list[str]]) -> list[list[str]]:
    state: dict[str, int] = {}
    stack: list[str] = []
    stack_index: dict[str, int] = {}
    cycles: list[list[str]] = []

    def visit(node: str) -> None:
        status = state.get(node, 0)
        if status == 2:
            return
        if status == 1:
            start = stack_index[node]
            cycles.append(stack[start:] + [node])
            return
        state[node] = 1
        stack_index[node] = len(stack)
        stack.append(node)
        for target in outgoing.get(node, []):
            visit(target)
        stack.pop()
        stack_index.pop(node, None)
        state[node] = 2

    for node in sorted(nodes):
        if state.get(node, 0) == 0:
            visit(node)
    return cycles


def _components(nodes: set[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    parent = {node: node for node in nodes}

    def find(node: str) -> str:
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != node:
            nxt = parent[node]
            parent[node] = root
            node = nxt
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in edges:
        union(a, b)

    groups: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        groups[find(node)].append(node)
    return sorted((sorted(group) for group in groups.values()), key=lambda g: (-len(g), g))


def build_audit(stop_times: dict[str, Any], references: dict[str, Any]) -> dict[str, Any]:
    stop_policy = stop_times.get("identityPolicy") or {}
    ref_policy = references.get("identityPolicy") or {}
    issues: list[dict[str, Any]] = []

    if stop_times.get("kind") != "keikyu-official-section-local-stop-times":
        issues.append({"kind": "unsafe-stop-time-kind"})
    if references.get("kind") != "keikyu-official-section-previous-publication-reference-audit":
        issues.append({"kind": "unsafe-reference-kind"})
    if stop_policy.get("pageSectionColumnIsExactLocalIdentity") is not True:
        issues.append({"kind": "unsafe-stop-time-policy", "field": "pageSectionColumnIsExactLocalIdentity"})
    if stop_policy.get("literalTrainNumberRowsAreHardSectionBoundaries") is not True:
        issues.append({"kind": "unsafe-stop-time-policy", "field": "literalTrainNumberRowsAreHardSectionBoundaries"})
    if stop_policy.get("runtimeSameTrainPromotions") != 0:
        issues.append({"kind": "unexpected-upstream-runtime-promotion"})
    if ref_policy.get("officialPreviousPublicationMetadataExtracted") is not True:
        issues.append({"kind": "unsafe-reference-policy", "field": "officialPreviousPublicationMetadataExtracted"})
    if ref_policy.get("sectionLocalCurrentGridRequired") is not True:
        issues.append({"kind": "unsafe-reference-policy", "field": "sectionLocalCurrentGridRequired"})
    if ref_policy.get("runtimeSameTrainPromotions") != 0:
        issues.append({"kind": "unexpected-reference-runtime-promotion"})

    source_sha = str((stop_times.get("source") or {}).get("sha256") or "")
    reference_sha = str((references.get("source") or {}).get("sha256") or "")
    if not source_sha or source_sha != reference_sha:
        issues.append({"kind": "source-sha-mismatch"})

    stop_fragments = stop_times.get("fragments") or []
    by_id = {str(row.get("id")): row for row in stop_fragments if row.get("id")}
    if len(by_id) != len(stop_fragments):
        issues.append({"kind": "duplicate-or-missing-stop-fragment-id"})

    edges: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for ref in references.get("fragments") or []:
        if ref.get("targetStatus") != "unique-explicit-reference-candidate":
            continue
        current_page = int(ref["pdfPage"])
        current_section = int(ref["section"])
        current_column = int(ref["column"])
        target_page = int(ref["targetPdfPage"])
        target_section = int(ref["targetSection"])
        target_column = int(ref["targetColumn"])
        current_id = fragment_id(current_page, current_section, current_column)
        target_id = fragment_id(target_page, target_section, target_column)
        current = by_id.get(current_id)
        target = by_id.get(target_id)

        if not current or not target:
            issues.append({
                "kind": "stale-fragment-reference",
                "fromFragment": target_id,
                "toFragment": current_id,
            })
            continue
        if current.get("printedTrainNumber") != ref.get("currentTrainNumber"):
            issues.append({
                "kind": "current-train-number-mismatch",
                "fragment": current_id,
                "dataset": current.get("printedTrainNumber"),
                "reference": ref.get("currentTrainNumber"),
            })
            continue
        if target.get("printedTrainNumber") != ref.get("previousTrainNumber"):
            issues.append({
                "kind": "previous-train-number-mismatch",
                "fragment": target_id,
                "dataset": target.get("printedTrainNumber"),
                "reference": ref.get("previousTrainNumber"),
            })
            continue
        if int(current.get("section", -1)) != current_section or int(target.get("section", -1)) != target_section:
            issues.append({"kind": "section-metadata-mismatch", "fragment": current_id})
            continue
        if target_id == current_id:
            issues.append({"kind": "self-reference", "fragment": current_id})
            continue

        pair = (target_id, current_id)
        if pair in seen_pairs:
            issues.append({
                "kind": "duplicate-reference-edge",
                "fromFragment": target_id,
                "toFragment": current_id,
            })
            continue
        seen_pairs.add(pair)
        edges.append({
            "fromFragment": target_id,
            "toFragment": current_id,
            "evidence": "keikyu-official-previous-publication-page-and-train-number",
            "previousPrintedPage": int(ref["previousPrintedPage"]),
            "previousTrainNumber": str(ref["previousTrainNumber"]),
            "currentPrintedPage": ref.get("printedPage"),
            "currentTrainNumber": ref.get("currentTrainNumber"),
            "previousPdfPage": target_page,
            "previousSection": target_section,
            "currentPdfPage": current_page,
            "currentSection": current_section,
        })

    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    nodes: set[str] = set()
    for edge in edges:
        source = edge["fromFragment"]
        target = edge["toFragment"]
        nodes.update((source, target))
        outgoing[source].append(target)
        incoming[target].append(source)

    branching = {node: sorted(targets) for node, targets in sorted(outgoing.items()) if len(targets) > 1}
    multiple_previous = {node: sorted(sources) for node, sources in sorted(incoming.items()) if len(sources) > 1}
    cycles = _find_cycles(nodes, outgoing)
    components = _components(nodes, [(e["fromFragment"], e["toFragment"]) for e in edges]) if nodes else []

    if branching:
        issues.append({"kind": "branching-reference-graph", "count": len(branching)})
    if multiple_previous:
        issues.append({"kind": "multiple-previous-references", "count": len(multiple_previous)})
    if cycles:
        issues.append({"kind": "cyclic-reference-graph", "count": len(cycles)})

    component_sizes: dict[str, int] = defaultdict(int)
    for group in components:
        component_sizes[str(len(group))] += 1

    return {
        "version": 2,
        "kind": "keikyu-official-section-cross-page-identity-audit",
        "sourceSha256": source_sha,
        "candidateReferenceCount": int(references.get("uniqueExplicitReferenceCandidateCount") or 0),
        "materializedCandidateEdgeCount": len(edges),
        "nodeCount": len(nodes),
        "identityComponentCount": len(components),
        "componentSizeHistogram": dict(sorted(component_sizes.items(), key=lambda item: int(item[0]))),
        "largestComponents": components[:20],
        "branchingTargets": branching,
        "multiplePreviousSources": multiple_previous,
        "cycles": cycles,
        "issues": issues,
        "edges": edges,
        "identityPolicy": {
            "officialPreviousPublicationPageRequired": True,
            "officialPreviousTrainNumberRequired": True,
            "uniqueTargetFragmentRequired": True,
            "pageSectionLocalFragmentMetadataMustMatch": True,
            "officialSectionIdentityRequired": True,
            "clockTimeUsedForIdentity": False,
            "destinationUsedForIdentity": False,
            "branchingAllowedForPromotion": False,
            "cyclesAllowedForPromotion": False,
            "crossPageIdentityEstablished": False,
            "runtimeSameTrainPromotions": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stop_times", type=Path)
    parser.add_argument("references", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = build_audit(load_json(args.stop_times), load_json(args.references))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "candidateReferences": payload["candidateReferenceCount"],
        "candidateEdges": payload["materializedCandidateEdgeCount"],
        "nodes": payload["nodeCount"],
        "components": payload["identityComponentCount"],
        "branchingTargets": len(payload["branchingTargets"]),
        "multiplePreviousSources": len(payload["multiplePreviousSources"]),
        "cycles": len(payload["cycles"]),
        "issues": len(payload["issues"]),
        "runtimeSameTrainPromotions": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
