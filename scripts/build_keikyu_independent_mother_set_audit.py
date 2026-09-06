#!/usr/bin/env python3
"""Audit a complete independent Keikyu physical-train mother set.

Every parsed official PDF train column is retained. Page-local columns are exact
local identities; only already-verified official cross-page reference edges are
used to union columns into larger candidate physical-train components. This is
still audit-only and never promotes runtime zero-transfer identity.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from verify_keikyu_cross_page_identity_audit import verify as verify_identity_graph


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def build_audit(stop_times: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    verify_identity_graph(graph)
    stop_policy = stop_times.get("identityPolicy") or {}
    issues: list[dict[str, Any]] = []
    if stop_policy.get("pageColumnIsExactLocalIdentity") is not True:
        issues.append({"kind": "unsafe-stop-time-policy", "field": "pageColumnIsExactLocalIdentity"})
    if stop_policy.get("runtimeSameTrainPromotions") != 0:
        issues.append({"kind": "unexpected-upstream-runtime-promotion"})

    fragments = stop_times.get("fragments") or []
    by_id = {str(row.get("id")): row for row in fragments if row.get("id")}
    if len(by_id) != len(fragments):
        issues.append({"kind": "duplicate-or-missing-fragment-id"})

    parent = {fragment_id: fragment_id for fragment_id in by_id}

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

    edge_count = 0
    for edge in graph.get("edges") or []:
        source = str(edge.get("fromFragment") or "")
        target = str(edge.get("toFragment") or "")
        if source not in by_id or target not in by_id:
            issues.append({"kind": "identity-edge-missing-fragment", "from": source, "to": target})
            continue
        union(source, target)
        edge_count += 1

    groups: dict[str, list[str]] = defaultdict(list)
    for fragment_id in sorted(by_id):
        groups[find(fragment_id)].append(fragment_id)

    components: list[dict[str, Any]] = []
    assigned: set[str] = set()
    total_resolved = 0
    total_unresolved = 0
    empty_fragments: list[str] = []
    for member_ids in sorted((sorted(v) for v in groups.values()), key=lambda x: x[0]):
        resolved = 0
        unresolved = 0
        numbers: set[str] = set()
        pages: set[int] = set()
        empty_members: list[str] = []
        for fragment_id in member_ids:
            assigned.add(fragment_id)
            row = by_id[fragment_id]
            stop_count = len(row.get("stopTimes") or [])
            unresolved_count = len(row.get("unresolvedCells") or [])
            resolved += stop_count
            unresolved += unresolved_count
            pages.add(int(row.get("page") or 0))
            number = row.get("printedTrainNumber")
            if number:
                numbers.add(str(number))
            if stop_count + unresolved_count == 0:
                empty_members.append(fragment_id)
                empty_fragments.append(fragment_id)
        total_resolved += resolved
        total_unresolved += unresolved
        components.append({
            "id": f"keikyu-mother:{member_ids[0]}",
            "fragments": member_ids,
            "fragmentCount": len(member_ids),
            "pdfPages": sorted(pages),
            "printedTrainNumbers": sorted(numbers),
            "resolvedTimeCells": resolved,
            "unresolvedTimeCells": unresolved,
            "sourceTimeCells": resolved + unresolved,
            "emptyFragments": empty_members,
            "hasAnyTimeCell": resolved + unresolved > 0,
            "identityBasis": "page-local-column" if len(member_ids) == 1 else "official-previous-publication-reference",
        })

    totals = stop_times.get("totals") or {}
    expected_fragments = int(totals.get("trainColumnFragments") or 0)
    expected_source = int(totals.get("sourceTimeCells") or 0)
    expected_resolved = int(totals.get("resolvedTimeCells") or 0)
    expected_unresolved = int(totals.get("unresolvedTimeCells") or 0)
    if len(by_id) != expected_fragments:
        issues.append({"kind": "fragment-count-mismatch", "expected": expected_fragments, "actual": len(by_id)})
    if assigned != set(by_id):
        issues.append({"kind": "fragment-assignment-gap", "missing": sorted(set(by_id) - assigned)[:50]})
    if total_resolved != expected_resolved:
        issues.append({"kind": "resolved-cell-accounting-mismatch", "expected": expected_resolved, "actual": total_resolved})
    if total_unresolved != expected_unresolved:
        issues.append({"kind": "unresolved-cell-accounting-mismatch", "expected": expected_unresolved, "actual": total_unresolved})
    if total_resolved + total_unresolved != expected_source:
        issues.append({"kind": "source-cell-accounting-mismatch", "expected": expected_source, "actual": total_resolved + total_unresolved})

    empty_components = [row["id"] for row in components if not row["hasAnyTimeCell"]]
    joined_components = [row for row in components if row["fragmentCount"] > 1]
    histogram: dict[str, int] = defaultdict(int)
    for row in components:
        histogram[str(row["fragmentCount"])] += 1

    return {
        "version": 1,
        "kind": "keikyu-independent-mother-set-audit",
        "sourceSha256": (stop_times.get("source") or {}).get("sha256"),
        "localFragmentCount": len(by_id),
        "officialCrossPageEdgeCount": edge_count,
        "candidatePhysicalTrainCount": len(components),
        "joinedPhysicalTrainCandidateCount": len(joined_components),
        "singletonPhysicalTrainCandidateCount": len(components) - len(joined_components),
        "componentSizeHistogram": dict(sorted(histogram.items(), key=lambda item: int(item[0]))),
        "resolvedTimeCells": total_resolved,
        "unresolvedTimeCells": total_unresolved,
        "sourceTimeCells": total_resolved + total_unresolved,
        "emptyLocalFragmentCount": len(empty_fragments),
        "emptyLocalFragments": empty_fragments,
        "emptyComponentCount": len(empty_components),
        "emptyComponents": empty_components,
        "issues": issues,
        "components": components,
        "identityPolicy": {
            "allOfficialPageLocalColumnsRetained": True,
            "onlyVerifiedOfficialCrossPageEdgesMayUnion": True,
            "clockTimeMayEstablishIdentity": False,
            "destinationMayEstablishIdentity": False,
            "crossPageIdentityCandidateOnly": True,
            "runtimeSameTrainPromotions": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stop_times", type=Path)
    parser.add_argument("identity_graph", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_audit(load_json(args.stop_times), load_json(args.identity_graph))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "localFragments": payload["localFragmentCount"],
        "officialCrossPageEdges": payload["officialCrossPageEdgeCount"],
        "candidatePhysicalTrains": payload["candidatePhysicalTrainCount"],
        "joinedCandidates": payload["joinedPhysicalTrainCandidateCount"],
        "singletons": payload["singletonPhysicalTrainCandidateCount"],
        "componentSizeHistogram": payload["componentSizeHistogram"],
        "resolvedTimeCells": payload["resolvedTimeCells"],
        "unresolvedTimeCells": payload["unresolvedTimeCells"],
        "sourceTimeCells": payload["sourceTimeCells"],
        "emptyLocalFragments": payload["emptyLocalFragmentCount"],
        "emptyComponents": payload["emptyComponentCount"],
        "issues": len(payload["issues"]),
        "runtimeSameTrainPromotions": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
