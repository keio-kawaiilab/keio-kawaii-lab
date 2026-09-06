#!/usr/bin/env python3
"""Build an audit-only exact-identity graph from Keikyu's printed page references.

This stage is deliberately NOT a runtime same-train producer.  It consumes the
page-local stop-time dataset plus the explicit official 「前の掲載ページ／列車番号」
reference audit and materializes only uniquely resolved reference edges.  Every
edge is then checked for stale fragments, metadata mismatch, branching and
cycles before any later code is allowed to consider promotion.
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

    if stop_policy.get("pageColumnIsExactLocalIdentity") is not True:
        issues.append({"kind": "unsafe-stop-time-policy", "field": "pageColumnIsExactLocalIdentity"})
    if stop_policy.get("runtimeSameTrainPromotions") != 0:
        issues.append({"kind": "unexpected-upstream-runtime-promotion"})
    if ref_policy.get("officialPreviousPublicationMetadataExtracted") is not True:
        issues.append({"kind": "unsafe-reference-policy", "field": "officialPreviousPublicationMetadataExtracted"})
    if ref_policy.get("runtimeSameTrainPromotions") != 0:
        issues.append({"kind": "unexpected-reference-runtime-promotion"})

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
        current_column = int(ref["column"])
        target_page = int(ref["targetPdfPage"])
        target_column = int(ref["targetColumn"])
        current_id = fragment_id(current_page, current_column)
        target_id = fragment_id(target_page, target_column)
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

    branching = {
        node: sorted(targets)
        for node, targets in sorted(outgoing.items())
        if len(targets) > 1
    }
    multiple_previous = {
        node: sorted(sources)
        for node, sources in sorted(incoming.items())
        if len(sources) > 1
    }
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
        "version": 1,
        "kind": "keikyu-official-cross-page-identity-audit",
        "sourceSha256": (references.get("source") or {}).get("sha256"),
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
            "pageLocalFragmentMetadataMustMatch": True,
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
