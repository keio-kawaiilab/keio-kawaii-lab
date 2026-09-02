#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

MM_PATH = Path("data/transit/yokohama-minatomirai/official-downbound-departures.json")
TOKYU_INDEX = Path("data/transit/tokyu/timetable-index.json")
TOKYU_ROOT = Path("data/transit/tokyu")
OUT = Path("data/transit/yokohama-minatomirai/downbound-audit.json")
TOYOKO = "odpt.Railway:Tokyu.Toyoko"
MOTOMACHI_SUFFIX = "MotomachiChukagai"
YOKOHAMA_SUFFIX = ".Yokohama"


def to_minute(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def service_time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def load_tokyu_pack() -> dict:
    index = json.loads(TOKYU_INDEX.read_text(encoding="utf-8"))
    rel = index["lines"][TOYOKO]["file"]
    return json.loads((TOKYU_ROOT / rel).read_text(encoding="utf-8"))


def inspect_tokyu_pack(packed: dict) -> dict:
    destinations = packed.get("destinations") or []
    stations = packed.get("stations") or []
    calendars = packed.get("calendars") or []
    directions = packed.get("directions") or []
    train_types = packed.get("trainTypes") or []
    trips = packed.get("inferredTrips") or []
    destination_usage = Counter()
    yokohama_destination_usage = Counter()
    motomachi_indexes = [i for i, value in enumerate(destinations) if str(value).endswith(MOTOMACHI_SUFFIX)]
    yokohama_indexes = {i for i, value in enumerate(stations) if str(value).endswith(YOKOHAMA_SUFFIX)}
    examples = []
    for trip in trips:
        if len(trip) < 6:
            continue
        calendar_i, direction_i, train_type_i, destination_i, confidence, stops = trip[:6]
        destination = destinations[destination_i] if isinstance(destination_i, int) and 0 <= destination_i < len(destinations) else f"<bad:{destination_i}>"
        destination_usage[destination] += 1
        has_yokohama = any(isinstance(stop, list) and len(stop) >= 3 and stop[0] in yokohama_indexes for stop in stops)
        if has_yokohama:
            yokohama_destination_usage[destination] += 1
        if len(examples) < 12 and (has_yokohama or destination_i in motomachi_indexes):
            examples.append({
                "calendar": calendars[calendar_i] if isinstance(calendar_i, int) and 0 <= calendar_i < len(calendars) else calendar_i,
                "direction": directions[direction_i] if isinstance(direction_i, int) and 0 <= direction_i < len(directions) else direction_i,
                "trainType": train_types[train_type_i] if isinstance(train_type_i, int) and 0 <= train_type_i < len(train_types) else train_type_i,
                "destinationIndex": destination_i,
                "destination": destination,
                "confidence": confidence,
                "yokohamaStop": next((stop for stop in stops if isinstance(stop, list) and len(stop) >= 3 and stop[0] in yokohama_indexes), None),
            })
    return {
        "tripCount": len(trips),
        "destinationCount": len(destinations),
        "motomachiDestinationIndexes": motomachi_indexes,
        "motomachiDestinationValues": [destinations[i] for i in motomachi_indexes],
        "destinationUsageTop": dict(destination_usage.most_common(20)),
        "yokohamaDestinationUsageTop": dict(yokohama_destination_usage.most_common(20)),
        "yokohamaStationIndexes": sorted(yokohama_indexes),
        "examples": examples,
    }


def load_tokyu_through_departures(packed: dict) -> dict[str, list[dict]]:
    stations = packed["stations"]
    calendars = packed["calendars"]
    directions = packed["directions"]
    train_types = packed["trainTypes"]
    destinations = packed["destinations"]
    yokohama_indexes = {i for i, station in enumerate(stations) if station.endswith(YOKOHAMA_SUFFIX)}
    result = defaultdict(list)
    for trip in packed.get("inferredTrips", []):
        if len(trip) < 6:
            continue
        calendar_i, direction_i, train_type_i, destination_i, confidence, stops = trip[:6]
        if not isinstance(destination_i, int) or not (0 <= destination_i < len(destinations)):
            continue
        destination = destinations[destination_i]
        if not destination.endswith(MOTOMACHI_SUFFIX):
            continue
        if not isinstance(direction_i, int) or not (0 <= direction_i < len(directions)):
            continue
        direction = directions[direction_i]
        for stop in stops:
            if len(stop) < 3 or stop[0] not in yokohama_indexes:
                continue
            arrival, departure = stop[1], stop[2]
            boundary_time = departure if departure is not None else arrival
            if boundary_time is None:
                continue
            calendar = calendars[calendar_i]
            result[calendar].append({
                "minute": int(boundary_time),
                "time": service_time(int(boundary_time)),
                "timeKind": "departure" if departure is not None else "arrival",
                "trainType": train_types[train_type_i],
                "destination": destination,
                "confidence": int(confidence),
                "direction": direction,
            })
    for calendar in result:
        result[calendar].sort(key=lambda item: item["minute"])
    return result


def match_times(official: list[int], reference: list[int], tolerance: int = 0) -> dict:
    ref_counts = Counter(reference)
    exact = 0
    near = 0
    unmatched = []
    for value in official:
        if ref_counts[value] > 0:
            ref_counts[value] -= 1
            exact += 1
            continue
        found = None
        for delta in range(1, tolerance + 1):
            for candidate in (value - delta, value + delta):
                if ref_counts[candidate] > 0:
                    found = candidate
                    break
            if found is not None:
                break
        if found is not None:
            ref_counts[found] -= 1
            near += 1
        else:
            unmatched.append(value)
    remaining = []
    for value, count in sorted(ref_counts.items()):
        remaining.extend([value] * count)
    return {
        "exact": exact,
        "near": near,
        "officialUnmatched": [service_time(value) for value in unmatched],
        "referenceUnmatched": [service_time(value) for value in remaining],
    }


def ordered_delta_report(upstream: list[int], downstream: list[int]) -> dict:
    if len(upstream) != len(downstream):
        return {"sameCount": False, "upstreamCount": len(upstream), "downstreamCount": len(downstream)}
    deltas = [b - a for a, b in zip(upstream, downstream)]
    return {
        "sameCount": True,
        "count": len(deltas),
        "deltaHistogram": {str(k): v for k, v in sorted(Counter(deltas).items())},
        "outliers": [
            {"upstream": service_time(a), "downstream": service_time(b), "delta": b - a}
            for a, b in zip(upstream, downstream)
            if not (2 <= b - a <= 5)
        ][:30],
    }


def main() -> int:
    mm = json.loads(MM_PATH.read_text(encoding="utf-8"))
    boards = {(board["stationTitle"], board["calendar"]): board for board in mm["boards"]}
    packed = load_tokyu_pack()
    through = load_tokyu_through_departures(packed)
    report = {
        "version": 3,
        "retrievedAt": mm.get("retrievedAt"),
        "tokyuPackDiagnostics": inspect_tokyu_pack(packed),
        "tokyuThroughCounts": {},
        "tokyuTrainTypeCounts": {},
        "yokohamaCrossCheck": {},
        "orderedBoundaryChecks": {},
        "adjacentChecks": {},
    }
    for calendar, rows in through.items():
        report["tokyuThroughCounts"][calendar] = len(rows)
        report["tokyuTrainTypeCounts"][calendar] = dict(Counter(row["trainType"] for row in rows))
        official = [to_minute(value) for value in boards[("横浜", calendar)]["departures"]]
        reference = [row["minute"] for row in rows]
        report["yokohamaCrossCheck"][calendar] = match_times(official, reference, tolerance=1)

    calendars = sorted({board["calendar"] for board in mm["boards"]})
    for calendar in calendars:
        yokohama = [to_minute(value) for value in boards[("横浜", calendar)]["departures"]]
        minatomirai = [to_minute(value) for value in boards[("みなとみらい", calendar)]["departures"]]
        report["orderedBoundaryChecks"][calendar] = ordered_delta_report(yokohama, minatomirai)

    station_order = ["横浜", "新高島", "みなとみらい", "馬車道", "日本大通り"]
    for calendar in calendars:
        for left, right in zip(station_order, station_order[1:]):
            upstream = [to_minute(value) for value in boards[(left, calendar)]["departures"]]
            downstream = [to_minute(value) for value in boards[(right, calendar)]["departures"]]
            deltas = Counter()
            matched = 0
            unmatched = []
            for value in downstream:
                candidates = [value - u for u in upstream if 1 <= value - u <= 5]
                if candidates:
                    delta = min(candidates, key=lambda d: (abs(d - 2), d))
                    deltas[delta] += 1
                    matched += 1
                else:
                    unmatched.append(value)
            key = f"{calendar}|{left}->{right}"
            report["adjacentChecks"][key] = {
                "upstreamCount": len(upstream),
                "downstreamCount": len(downstream),
                "matched": matched,
                "coverage": round(matched / max(1, len(downstream)), 4),
                "deltaHistogram": {str(k): v for k, v in sorted(deltas.items())},
                "unmatched": [service_time(value) for value in unmatched],
            }

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    bad = [(key, value["coverage"]) for key, value in report["adjacentChecks"].items() if value["coverage"] < 0.90]
    if bad:
        raise RuntimeError(f"adjacent timetable coverage below 90%: {bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
