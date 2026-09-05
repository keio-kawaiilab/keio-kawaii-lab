#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BOUNDARY_ID = "keisei-toei-oshiage"
MARKER = "same-keisei-official-train-page-spans-oshiage-boundary"
KEISEI = "odpt.Railway:Keisei.Oshiage"
TOEI = "odpt.Railway:Toei.Asakusa"
ALLOWED_PAIRS = {(KEISEI, TOEI), (TOEI, KEISEI)}
TRAIN_NUMBER_METHOD = "resolved-by-adjacent-anchor-and-official-train-number"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def safe_policy(policy: dict[str, Any]) -> bool:
    return (
        policy.get("trainNumberAloneMayEstablishIdentity") is False
        and policy.get("timeProximityAloneMayEstablishIdentity") is False
        and policy.get("exactBoundaryAnchorRequired") is True
        and policy.get("ambiguousBoundaryEndpointRequiresExactAdjacentOfficialAnchor") is True
        and policy.get("officialTrainNumberMayDisambiguateOnlyAfterExactBoundaryAndAdjacentAnchor") is True
    )


def train_number_resolution_is_valid(entry: dict[str, Any], source: dict[str, Any], target: dict[str, Any]) -> bool:
    if not entry.get("resolvedByOfficialTrainNumberAfterExactAnchors"):
        return True
    number = str(entry.get("officialTrainNumber") or "")
    if not number:
        return False
    pair = (str(entry.get("fromRailway") or ""), str(entry.get("toRailway") or ""))
    if pair[0] == KEISEI:
        keisei_fragment = source
        method = str(entry.get("sourceMatchMethod") or "")
        anchor = entry.get("sourceAdjacentAnchor") or {}
    elif pair[1] == KEISEI:
        keisei_fragment = target
        method = str(entry.get("targetMatchMethod") or "")
        anchor = entry.get("targetAdjacentAnchor") or {}
    else:
        return False
    return (
        method == TRAIN_NUMBER_METHOD
        and bool(str(anchor.get("station") or ""))
        and bool(anchor.get("minutes"))
        and keisei_fragment.get("sourceKind") == "exact-train-timetable"
        and str(keisei_fragment.get("trainNumber") or "") == number
    )


def apply_generated_evidence(
    fragments: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    indexes: dict[str, Any],
    evidence_path: Path,
) -> list[dict[str, Any]]:
    payload = load_json(evidence_path)
    if not payload:
        return list(edges)
    policy = payload.get("policy") or {}
    if not safe_policy(policy):
        unresolved.append({"kind": "keisei-oshiage-generated-evidence-unsafe-policy", "path": str(evidence_path)})
        return list(edges)

    by_id = {str(row.get("id") or ""): row for row in fragments if row.get("id")}
    output = list(edges)
    seen = {(str(row.get("fromFragment") or ""), str(row.get("toFragment") or "")) for row in output}
    resolved_sources: set[str] = set()

    for entry in payload.get("entries") or []:
        if not isinstance(entry, dict) or entry.get("matchStatus") != "matched-singleton":
            continue
        eid = str(entry.get("id") or "")
        source_id = str(entry.get("fromFragment") or "")
        target_id = str(entry.get("toFragment") or "")
        source = by_id.get(source_id)
        target = by_id.get(target_id)
        evidence = [str(value) for value in entry.get("evidence") or []]
        source_matches = [str(value) for value in entry.get("sourceMatches") or []]
        target_matches = [str(value) for value in entry.get("targetMatches") or []]
        pair = (str(entry.get("fromRailway") or ""), str(entry.get("toRailway") or ""))
        entry_policy = entry.get("matchPolicy") or {}

        reason = ""
        if entry.get("boundaryId") != BOUNDARY_ID or MARKER not in evidence:
            reason = "missing-official-train-page-marker"
        elif not safe_policy(entry_policy):
            reason = "unsafe-entry-match-policy"
        elif entry_policy.get("boundaryMinuteTolerance") != 0 or entry_policy.get("adjacentMinuteTolerance") != 0:
            reason = "nonzero-match-tolerance"
        elif source_matches != [source_id] or target_matches != [target_id]:
            reason = "non-singleton-recorded-match"
        elif not source or not target:
            reason = "stale-fragment-reference"
        elif pair not in ALLOWED_PAIRS:
            reason = "unexpected-railway-pair"
        elif str(source.get("railway") or "") != pair[0] or str(target.get("railway") or "") != pair[1]:
            reason = "fragment-railway-mismatch"
        elif not train_number_resolution_is_valid(entry, source, target):
            reason = "invalid-post-anchor-train-number-resolution"
        else:
            boundary = next(
                (
                    row for row in indexes.get("graph", {}).get(pair[0], [])
                    if str(row.get("toRailway") or "") == pair[1]
                    and str(row.get("boundaryId") or "") == BOUNDARY_ID
                ),
                None,
            )
            if not boundary:
                reason = "unverified-operational-boundary"

        if reason:
            unresolved.append({
                "kind": "keisei-oshiage-generated-evidence-rejected",
                "evidenceId": eid,
                "reason": reason,
                "fromFragment": source_id,
                "toFragment": target_id,
            })
            continue

        key = (source_id, target_id)
        if key not in seen:
            seen.add(key)
            output.append({
                "fromFragment": source_id,
                "toFragment": target_id,
                "classification": "same-train",
                "identityLevel": "evidence-backed",
                "evidence": ["keisei-official-per-train-timetable-spans-oshiage", eid],
                "sourceUrls": [str(entry.get("sourceUrl"))] if entry.get("sourceUrl") else [],
                "boundary": {"station": "押上", "fromRailway": pair[0], "toRailway": pair[1]},
            })
        resolved_sources.add(source_id)

    if resolved_sources:
        unresolved[:] = [
            row for row in unresolved
            if not (
                row.get("kind") == "ambiguous-boundary-fragment-alignment"
                and str(row.get("fragment") or "") in resolved_sources
            )
        ]
    return output
