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


def load_tokyu_through_departures() -> dict[str, list[dict]]:
    index = json.loads(TOKYU_INDEX.read_text(encoding="utf-8"))
    rel = index["lines"][TOYOKO]["file"]
    packed = json.loads((TOKYU_ROOT / rel).read_text(encoding="utf-8"))
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
        if not (0 <= destination_i < len(destinations)):
            continue
        destination = destinations[destination_i]
        if not destination.endswith(MOTOMACHI_SUFFIX):
            continue
        if not (0 <= direction_i < len(directions)):
            continue
        direction = directions[direction_i]
        # We do not hard-code which ordinal means southbound. Destination and
        # the presence of Yokohama are sufficient for through trains.
        for stop in stops:
            if len(stop) < 3 or stop[0] not in yokohama_indexes:
                continue
            departure = stop[2]
            if departure is None:
                continue
            calendar = calendars[calendar_i]
            result[calendar].append({
                "minute": int(departure),
                "time": service_time(int(departure)),
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


def main() -> int:
    mm = json.loads(MM_PATH.read_text(encoding="utf-8"))
    boards = {
        (board["stationTitle"], board["calendar"]): board
        for board in mm["boards"]
    }
    through = load_tokyu_through_departures()
    report = {
        "version": 1,
        "retrievedAt": mm.get("retrievedAt"),
        "tokyuThroughCounts": {},
        "yokohamaCrossCheck": {},
        "adjacentChecks": {},
    }
    for calendar, rows in through.items():
        report["tokyuThroughCounts"][calendar] = len(rows)
        official = [to_minute(value) for value in boards[("横浜", calendar)]["departures"]]
        reference = [row["minute"] for row in rows]
        report["yokohamaCrossCheck"][calendar] = match_times(official, reference, tolerance=1)

    station_order = ["横浜", "新高島", "みなとみらい", "馬車道", "日本大通り"]
    calendars = sorted({board["calendar"] for board in mm["boards"]})
    # For every downstream departure, check whether an upstream departure can
    # plausibly feed it. Passing trains may be absent at the downstream board,
    # so coverage is measured from downstream to upstream.
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
    # Do not yet block the snapshot on Tokyu parity because some special trains
    # can be represented differently across operator feeds. Adjacent official
    # station coverage, however, should be overwhelmingly high.
    bad = [
        (key, value["coverage"])
        for key, value in report["adjacentChecks"].items()
        if value["coverage"] < 0.90
    ]
    if bad:
        raise RuntimeError(f"adjacent timetable coverage below 90%: {bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
