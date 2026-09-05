#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BOUNDARY_ID = "keisei-toei-oshiage"
MARKER = "same-keisei-official-train-page-spans-oshiage-boundary"
ALLOWED_PAIRS = {
    ("odpt.Railway:Keisei.Oshiage", "odpt.Railway:Toei.Asakusa"),
    ("odpt.Railway:Toei.Asakusa", "odpt.Railway:Keisei.Oshiage"),
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


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
    if (
        policy.get("trainNumberAloneMayEstablishIdentity") is not False
        or policy.get("timeProximityAloneMayEstablishIdentity") is not False
    ):
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

        reason = ""
        if entry.get("boundaryId") != BOUNDARY_ID or MARKER not in evidence:
            reason = "missing-official-train-page-marker"
        elif source_matches != [source_id] or target_matches != [target_id]:
            reason = "non-singleton-recorded-match"
        elif not source or not target:
            reason = "stale-fragment-reference"
        elif pair not in ALLOWED_PAIRS:
            reason = "unexpected-railway-pair"
        elif str(source.get("railway") or "") != pair[0] or str(target.get("railway") or "") != pair[1]:
            reason = "fragment-railway-mismatch"
        else:
            boundary = next(
                (
                    row
                    for row in indexes.get("graph", {}).get(pair[0], [])
                    if str(row.get("toRailway") or "") == pair[1]
                    and str(row.get("boundaryId") or "") == BOUNDARY_ID
                ),
                None,
            )
            if not boundary:
                reason = "unverified-operational-boundary"

        if reason:
            unresolved.append(
                {
                    "kind": "keisei-oshiage-generated-evidence-rejected",
                    "evidenceId": eid,
                    "reason": reason,
                    "fromFragment": source_id,
                    "toFragment": target_id,
                }
            )
            continue

        key = (source_id, target_id)
        if key not in seen:
            seen.add(key)
            output.append(
                {
                    "fromFragment": source_id,
                    "toFragment": target_id,
                    "classification": "same-train",
                    "identityLevel": "evidence-backed",
                    "evidence": ["keisei-official-per-train-timetable-spans-oshiage", eid],
                    "sourceUrls": [str(entry.get("sourceUrl"))] if entry.get("sourceUrl") else [],
                    "boundary": {"station": "押上", "fromRailway": pair[0], "toRailway": pair[1]},
                }
            )
        resolved_sources.add(source_id)

    if resolved_sources:
        unresolved[:] = [
            row
            for row in unresolved
            if not (
                row.get("kind") == "ambiguous-boundary-fragment-alignment"
                and str(row.get("fragment") or "") in resolved_sources
            )
        ]
    return output
