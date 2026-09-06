#!/usr/bin/env python3
"""Classify zero-time Keikyu page-local grid fragments without dropping them.

This audit distinguishes real timetable evidence from geometry-only blank slots.
A zero-time fragment is considered train-bearing only when it has another exact
published signal: an explicit printed train number or incidence in the verified
official previous-publication reference graph. Anonymous, zero-time,
unreferenced slots remain visible as structural-grid candidates and must not be
silently counted as physical trains.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
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
    fragments = stop_times.get("fragments") or []
    incident: set[str] = set()
    for edge in graph.get("edges") or []:
        incident.add(str(edge.get("fromFragment") or ""))
        incident.add(str(edge.get("toFragment") or ""))

    page_columns: dict[int, list[int]] = defaultdict(list)
    for row in fragments:
        page_columns[int(row.get("page") or 0)].append(int(row.get("column") or 0))
    page_max = {page: max(columns) for page, columns in page_columns.items() if columns}

    empty_rows: list[dict[str, Any]] = []
    counts = Counter()
    position_counts = Counter()
    page_empty_counts = Counter()
    structural_candidates: list[str] = []
    evidence_bearing_empty: list[str] = []

    for row in fragments:
        fragment_id = str(row.get("id") or "")
        resolved = len(row.get("stopTimes") or [])
        unresolved = len(row.get("unresolvedCells") or [])
        if resolved + unresolved:
            continue
        page = int(row.get("page") or 0)
        column = int(row.get("column") or 0)
        explicit = bool(row.get("printedTrainNumber"))
        referenced = fragment_id in incident
        anonymous = bool(row.get("anonymousColumn"))
        if column == 0:
            position = "left-edge"
        elif column == page_max.get(page):
            position = "right-edge"
        else:
            position = "interior"

        if explicit:
            counts["explicit"] += 1
        if anonymous:
            counts["anonymous"] += 1
        if referenced:
            counts["referenced"] += 1
        if explicit or referenced:
            classification = "evidence-bearing-empty"
            evidence_bearing_empty.append(fragment_id)
        else:
            classification = "anonymous-unreferenced-zero-time-grid-slot"
            structural_candidates.append(fragment_id)
        counts[classification] += 1
        position_counts[position] += 1
        page_empty_counts[str(page)] += 1
        empty_rows.append({
            "id": fragment_id,
            "page": page,
            "column": column,
            "position": position,
            "columnCenterX": row.get("columnCenterX"),
            "printedTrainNumber": row.get("printedTrainNumber"),
            "anonymousColumn": anonymous,
            "referencedByOfficialIdentityGraph": referenced,
            "classification": classification,
        })

    nonempty_anonymous = sum(
        1 for row in fragments
        if row.get("anonymousColumn") and (row.get("stopTimes") or row.get("unresolvedCells"))
    )
    return {
        "version": 1,
        "kind": "keikyu-empty-fragment-classification-audit",
        "fragmentCount": len(fragments),
        "emptyFragmentCount": len(empty_rows),
        "emptyCounts": dict(sorted(counts.items())),
        "emptyPositionCounts": dict(sorted(position_counts.items())),
        "pagesWithEmptyFragments": len(page_empty_counts),
        "pageEmptyCounts": dict(sorted(page_empty_counts.items(), key=lambda item: int(item[0]))),
        "nonemptyAnonymousFragmentCount": nonempty_anonymous,
        "evidenceBearingEmptyFragmentCount": len(evidence_bearing_empty),
        "structuralBlankCandidateCount": len(structural_candidates),
        "evidenceBearingEmptyFragments": evidence_bearing_empty,
        "structuralBlankCandidates": structural_candidates,
        "emptyFragments": empty_rows,
        "policy": {
            "zeroTimeAloneMayNotProveTrain": True,
            "anonymousUnreferencedZeroTimeMayBePhysicalTrain": False,
            "explicitNumberOrOfficialReferencePreservesEmptyTrainEvidence": True,
            "structuralCandidatesRemainAudited": True,
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
        "fragments": payload["fragmentCount"],
        "emptyFragments": payload["emptyFragmentCount"],
        "emptyCounts": payload["emptyCounts"],
        "emptyPositions": payload["emptyPositionCounts"],
        "nonemptyAnonymousFragments": payload["nonemptyAnonymousFragmentCount"],
        "evidenceBearingEmptyFragments": payload["evidenceBearingEmptyFragmentCount"],
        "structuralBlankCandidates": payload["structuralBlankCandidateCount"],
        "runtimeSameTrainPromotions": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
