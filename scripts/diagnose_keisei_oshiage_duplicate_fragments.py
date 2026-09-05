#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(fragment: dict[str, Any]) -> str:
    payload = {
        "railway": fragment.get("railway"),
        "calendar": fragment.get("calendar"),
        "trainType": fragment.get("trainType"),
        "trainNumber": fragment.get("trainNumber"),
        "trainId": fragment.get("trainId"),
        "timetableId": fragment.get("timetableId"),
        "destination": fragment.get("destination") or [],
        "stops": fragment.get("stops") or [],
        "sourceKind": fragment.get("sourceKind"),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def projection(fragment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": fragment.get("id"),
        "sourceTripIndex": fragment.get("sourceTripIndex"),
        "sourceKind": fragment.get("sourceKind"),
        "railway": fragment.get("railway"),
        "calendar": fragment.get("calendar"),
        "trainType": fragment.get("trainType"),
        "trainNumber": fragment.get("trainNumber"),
        "trainId": fragment.get("trainId"),
        "timetableId": fragment.get("timetableId"),
        "destination": fragment.get("destination") or [],
        "stops": fragment.get("stops") or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", default="data/transit-v2/keisei-official-oshiage-evidence.json")
    parser.add_argument("--fragments", default="data/transit-v2/fragments/keisei.json")
    parser.add_argument("--output", default="/tmp/keisei-oshiage-duplicate-fragments.json")
    args = parser.parse_args()

    evidence = load(Path(args.evidence))
    fragments = load(Path(args.fragments)).get("fragments") or []
    by_id = {str(row.get("id") or ""): row for row in fragments if isinstance(row, dict) and row.get("id")}

    counts: Counter[str] = Counter()
    group_sizes: Counter[int] = Counter()
    examples: list[dict[str, Any]] = []
    total = 0

    for row in evidence.get("allCandidates") or []:
        if not isinstance(row, dict) or row.get("matchStatus") != "ambiguous":
            continue
        direction = str(row.get("direction") or "")
        ids = row.get("sourceMatches") if direction == "keisei-to-toei" else row.get("targetMatches")
        candidates = [by_id.get(str(fid or "")) for fid in ids or []]
        candidates = [value for value in candidates if isinstance(value, dict)]
        if len(candidates) < 2:
            counts["ambiguous-without-multiple-keisei-fragments"] += 1
            continue
        total += 1
        group_sizes[len(candidates)] += 1
        signatures = {canonical(fragment) for fragment in candidates}
        train_numbers = {str(fragment.get("trainNumber") or "") for fragment in candidates}
        stop_signatures = {json.dumps(fragment.get("stops") or [], separators=(",", ":")) for fragment in candidates}
        types = {str(fragment.get("trainType") or "") for fragment in candidates}
        destinations = {json.dumps(fragment.get("destination") or [], sort_keys=True, separators=(",", ":")) for fragment in candidates}
        source_kinds = {str(fragment.get("sourceKind") or "") for fragment in candidates}

        if len(signatures) == 1:
            counts["canonical-identical"] += 1
        else:
            counts["canonical-different"] += 1
        if len(train_numbers) == 1:
            counts["same-train-number"] += 1
        if len(stop_signatures) == 1:
            counts["same-full-stop-sequence"] += 1
        if len(types) == 1:
            counts["same-train-type"] += 1
        if len(destinations) == 1:
            counts["same-destination"] += 1
        if source_kinds == {"exact-train-timetable"}:
            counts["all-exact-train-timetable"] += 1

        if len(examples) < 20:
            examples.append({
                "evidenceId": row.get("id"),
                "direction": direction,
                "sourceTrainId": row.get("sourceTrainId"),
                "officialTrainNumber": row.get("officialTrainNumber"),
                "sourceBoundaryMinute": row.get("sourceBoundaryMinute"),
                "targetBoundaryMinute": row.get("targetBoundaryMinute"),
                "keiseiCandidateCount": len(candidates),
                "canonicalSignatureCount": len(signatures),
                "fragments": [projection(fragment) for fragment in candidates],
            })

    report = {
        "ambiguousKeiseiGroups": total,
        "groupSizes": {str(key): value for key, value in sorted(group_sizes.items())},
        "properties": dict(counts),
        "examples": examples,
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "examples"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
