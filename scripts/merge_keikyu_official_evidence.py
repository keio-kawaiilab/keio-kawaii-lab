#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_MARKER = "same-printed-column-spans-both-sides-of-sengakuji"
BOUNDARY_ID = "toei-keikyu-sengakuji"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def merge_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    calendars: dict[str, dict[str, int]] = {}
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for data in payloads:
        policy = data.get("policy") or {}
        if policy.get("trainNumberAloneMayEstablishIdentity") is not False:
            raise ValueError("unsafe source policy: train number may establish identity")
        if policy.get("timeProximityAloneMayEstablishIdentity") is not False:
            raise ValueError("unsafe source policy: time proximity may establish identity")
        source = data.get("source") or {}
        calendar = str(source.get("calendar") or "unknown")
        sources.append(source)
        summary = data.get("summary") or {}
        calendars[calendar] = {
            "officialColumnCandidates": int(summary.get("officialColumnCandidates") or 0),
            "matchedSingleton": int(summary.get("matchedSingleton") or 0),
            "ambiguous": int(summary.get("ambiguous") or 0),
            "unmatched": int(summary.get("unmatched") or 0),
        }
        for entry in data.get("entries") or []:
            if not isinstance(entry, dict) or entry.get("matchStatus") != "matched-singleton":
                continue
            evidence = [str(value) for value in entry.get("evidence") or []]
            source_id = str(entry.get("fromFragment") or "")
            target_id = str(entry.get("toFragment") or "")
            if entry.get("boundaryId") != BOUNDARY_ID or REQUIRED_MARKER not in evidence:
                raise ValueError(f"matched entry lacks official boundary proof: {entry.get('id')}")
            if not source_id or not target_id:
                raise ValueError(f"matched entry lacks fragment ids: {entry.get('id')}")
            if [str(v) for v in entry.get("sourceMatches") or []] != [source_id]:
                raise ValueError(f"source match is not singleton: {entry.get('id')}")
            if [str(v) for v in entry.get("targetMatches") or []] != [target_id]:
                raise ValueError(f"target match is not singleton: {entry.get('id')}")
            key = (source_id, target_id)
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)

    direction_counts: dict[str, int] = {}
    for entry in entries:
        direction = str(entry.get("direction") or "unknown")
        direction_counts[direction] = direction_counts.get(direction, 0) + 1

    return {
        "version": 3,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "policy": {
            "productionProjection": "matched-singleton-only",
            "autoPromoteUnknown": False,
            "officialColumnSpansBothBoundarySidesRequired": True,
            "verifiedOperationalBoundaryRequired": True,
            "singletonFragmentMatchRequired": True,
            "trainNumberAloneMayEstablishIdentity": False,
            "timeProximityAloneMayEstablishIdentity": False,
            "staleFragmentReferenceMustFailClosed": True,
        },
        "summary": {
            "calendars": calendars,
            "productionMatchedSingleton": len(entries),
            "directions": direction_counts,
        },
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge strict Keikyu official evidence into a production-only projection.")
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    data = merge_payloads([load(Path(path)) for path in args.inputs])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data["summary"], ensure_ascii=False, indent=2))
    if not data["entries"]:
        raise RuntimeError("production evidence projection is empty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
