#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path("data/transit/keisei")
INDEX_PATH = ROOT / "timetable-index.json"
REPORT_PATH = ROOT / "official-conversion-report.json"
MANIFEST_PATH = Path("data/transit/manifest.json")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def trip_key(trip: Any) -> str:
    # Compact trips are already the exact scheduled representation consumed by
    # the route DB.  Equality here means same calendar/type/number/full stop
    # sequence and every arrival/departure minute.  We do not merge similar
    # trips or use time tolerance.
    return json.dumps(trip, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def trip_connections(trip: Any) -> int:
    if not isinstance(trip, list) or len(trip) < 4 or not isinstance(trip[3], list):
        return 0
    stops = trip[3]
    usable = 0
    for current, following in zip(stops, stops[1:]):
        if not isinstance(current, list) or len(current) < 3:
            continue
        if not isinstance(following, list) or len(following) < 3:
            continue
        current_time = current[2] if current[2] is not None else current[1]
        following_time = following[1] if following[1] is not None else following[2]
        if isinstance(current_time, (int, float)) and isinstance(following_time, (int, float)):
            usable += 1
    return usable


def dedupe_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    trips = payload.get("trips") or []
    if not isinstance(trips, list):
        raise RuntimeError("Keisei compact timetable trips is not a list")
    seen: set[str] = set()
    unique: list[Any] = []
    for trip in trips:
        key = trip_key(trip)
        if key in seen:
            continue
        seen.add(key)
        unique.append(trip)
    output = dict(payload)
    output["trips"] = unique
    return output, {
        "beforeTrips": len(trips),
        "afterTrips": len(unique),
        "removedTrips": len(trips) - len(unique),
        "connections": sum(trip_connections(trip) for trip in unique),
    }


def run(root: Path, index_path: Path, report_path: Path, manifest_path: Path) -> dict[str, Any]:
    index = load_json(index_path)
    lines = index.get("lines") or {}
    if not isinstance(lines, dict) or not lines:
        raise RuntimeError("Keisei timetable index has no lines")

    line_stats: dict[str, dict[str, int]] = {}
    total_before = 0
    total_after = 0
    total_removed = 0
    total_connections = 0

    for railway_id, row in lines.items():
        if not isinstance(row, dict) or not row.get("file"):
            raise RuntimeError(f"invalid Keisei timetable index row: {railway_id}")
        path = root / str(row["file"])
        payload = load_json(path)
        normalized, stats = dedupe_payload(payload)
        dump_json(path, normalized)
        row["trips"] = stats["afterTrips"]
        row["connections"] = stats["connections"]
        line_stats[str(railway_id)] = stats
        total_before += stats["beforeTrips"]
        total_after += stats["afterTrips"]
        total_removed += stats["removedTrips"]
        total_connections += stats["connections"]

    dump_json(index_path, index)

    report = load_json(report_path) if report_path.exists() else {}
    if not isinstance(report, dict):
        report = {}
    report["compactTripCountBeforeDedup"] = total_before
    report["compactTripCount"] = total_after
    report["duplicateCompactTripsRemoved"] = total_removed
    report["compactConnectionCount"] = total_connections
    report["deduplicationPolicy"] = {
        "exactCompactTripEqualityOnly": True,
        "timeTolerance": 0,
        "trainNumberAloneMayMerge": False,
    }
    report_lines = report.get("lines") or {}
    if isinstance(report_lines, dict):
        for railway_id, stats in line_stats.items():
            line_row = report_lines.get(railway_id)
            if isinstance(line_row, dict):
                line_row["tripsBeforeDedup"] = stats["beforeTrips"]
                line_row["trips"] = stats["afterTrips"]
                line_row["duplicateTripsRemoved"] = stats["removedTrips"]
                line_row["connections"] = stats["connections"]
    dump_json(report_path, report)

    if manifest_path.exists():
        manifest = load_json(manifest_path)
        operator = manifest.get("operators", {}).get("keisei") if isinstance(manifest, dict) else None
        if isinstance(operator, dict):
            operator["timetableConnections"] = total_connections
            operator["departures"] = total_connections
            operator["deduplicatedCompactTrips"] = total_removed
            notes = manifest.setdefault("notes", [])
            note = "Keisei official compact timetable rows are deduplicated only when their complete scheduled trip representation is exactly identical."
            if isinstance(notes, list) and note not in notes:
                notes.append(note)
            dump_json(manifest_path, manifest)

    summary = {
        "beforeTrips": total_before,
        "afterTrips": total_after,
        "removedTrips": total_removed,
        "connections": total_connections,
        "lines": line_stats,
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--index", default=str(INDEX_PATH))
    parser.add_argument("--report", default=str(REPORT_PATH))
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument("--require-removal", action="store_true")
    args = parser.parse_args()

    summary = run(Path(args.root), Path(args.index), Path(args.report), Path(args.manifest))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.require_removal and summary["removedTrips"] <= 0:
        raise RuntimeError("Expected duplicate Keisei compact trips, but none were removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
