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


def load_tokyu_yokohama_boards(packed: dict) -> dict[str, list[dict]]:
    stations = packed.get("stations") or []
    calendars = packed.get("calendars") or []
    directions = packed.get("directions") or []
    train_types = packed.get("trainTypes") or []
    destinations = packed.get("destinations") or []
    yokohama_indexes = {i for i, value in enumerate(stations) if str(value).endswith(YOKOHAMA_SUFFIX)}
    result: dict[str, list[dict]] = defaultdict(list)
    for board in packed.get("boards") or []:
        if len(board) < 4:
            continue
        station_i, calendar_i, direction_i, departures = board[:4]
        if station_i not in yokohama_indexes:
            continue
        if not isinstance(calendar_i, int) or not (0 <= calendar_i < len(calendars)):
            continue
        calendar = calendars[calendar_i]
        direction = directions[direction_i] if isinstance(direction_i, int) and 0 <= direction_i < len(directions) else str(direction_i)
        for row in departures:
            if len(row) < 3:
                continue
            minute, type_i, destination_i = row[:3]
            if not isinstance(destination_i, int) or not (0 <= destination_i < len(destinations)):
                continue
            destination = destinations[destination_i]
            if not str(destination).endswith(MOTOMACHI_SUFFIX):
                continue
            train_type = train_types[type_i] if isinstance(type_i, int) and 0 <= type_i < len(train_types) else str(type_i)
            result[calendar].append({
                "minute": int(minute),
                "time": service_time(int(minute)),
                "trainType": train_type,
                "destination": destination,
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


def type_delta_report(boundary_rows: list[dict], downstream: list[int]) -> dict:
    if len(boundary_rows) != len(downstream):
        return {"sameCount": False, "boundaryCount": len(boundary_rows), "downstreamCount": len(downstream)}
    by_type: dict[str, Counter] = defaultdict(Counter)
    examples = []
    for row, arrival in zip(boundary_rows, downstream):
        delta = arrival - row["minute"]
        by_type[row["trainType"]][delta] += 1
        if delta < 2 or delta > 5:
            examples.append({
                "yokohama": row["time"],
                "minatomirai": service_time(arrival),
                "trainType": row["trainType"],
                "delta": delta,
            })
    return {
        "sameCount": True,
        "byTrainType": {
            train_type: {str(delta): count for delta, count in sorted(counter.items())}
            for train_type, counter in sorted(by_type.items())
        },
        "outliers": examples[:30],
    }


def infer_modal_deltas(type_report: dict) -> dict[str, int]:
    result = {}
    for train_type, raw in (type_report.get("byTrainType") or {}).items():
        counter = Counter({int(delta): int(count) for delta, count in raw.items() if 2 <= int(delta) <= 5})
        if counter:
            result[train_type] = counter.most_common(1)[0][0]
    return result


def proposed_from_boundary(boundary_rows: list[dict], modal_deltas: dict[str, int]) -> list[int]:
    result = []
    for row in boundary_rows:
        delta = modal_deltas.get(row["trainType"])
        if delta is None:
            continue
        result.append(row["minute"] + delta)
    return result


def main() -> int:
    mm = json.loads(MM_PATH.read_text(encoding="utf-8"))
    boards = {(board["stationTitle"], board["calendar"]): board for board in mm["boards"]}
    packed = load_tokyu_pack()
    boundary = load_tokyu_yokohama_boards(packed)
    report = {
        "version": 4,
        "retrievedAt": mm.get("retrievedAt"),
        "tokyuBoundaryCounts": {},
        "tokyuTrainTypeCounts": {},
        "yokohamaCrossCheck": {},
        "orderedBoundaryChecks": {},
        "deltaByTrainType": {},
        "weekdayMinatomiraiProposal": {},
        "adjacentChecks": {},
    }
    calendars = sorted({board["calendar"] for board in mm["boards"]})
    for calendar in calendars:
        rows = boundary.get(calendar, [])
        report["tokyuBoundaryCounts"][calendar] = len(rows)
        report["tokyuTrainTypeCounts"][calendar] = dict(Counter(row["trainType"] for row in rows))
        official = [to_minute(value) for value in boards[("横浜", calendar)]["departures"]]
        reference = [row["minute"] for row in rows]
        report["yokohamaCrossCheck"][calendar] = match_times(official, reference, tolerance=1)
        minatomirai = [to_minute(value) for value in boards[("みなとみらい", calendar)]["departures"]]
        report["orderedBoundaryChecks"][calendar] = ordered_delta_report(official, minatomirai)
        report["deltaByTrainType"][calendar] = type_delta_report(rows, minatomirai)

    holiday = "odpt.Calendar:SaturdayHoliday"
    weekday = "odpt.Calendar:Weekday"
    modal_deltas = infer_modal_deltas(report["deltaByTrainType"].get(holiday, {}))
    weekday_proposed = proposed_from_boundary(boundary.get(weekday, []), modal_deltas)
    weekday_ocr = [to_minute(value) for value in boards[("みなとみらい", weekday)]["departures"]]
    report["weekdayMinatomiraiProposal"] = {
        "modalDeltasFromSaturdayHoliday": modal_deltas,
        "proposedCount": len(weekday_proposed),
        "ocrCount": len(weekday_ocr),
        "proposalVsOcr": match_times(weekday_proposed, weekday_ocr, tolerance=1),
        "proposedTimes": [service_time(value) for value in weekday_proposed],
    }

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
    print(json.dumps({
        "version": report["version"],
        "tokyuBoundaryCounts": report["tokyuBoundaryCounts"],
        "tokyuTrainTypeCounts": report["tokyuTrainTypeCounts"],
        "yokohamaCrossCheck": report["yokohamaCrossCheck"],
        "orderedBoundaryChecks": report["orderedBoundaryChecks"],
        "deltaByTrainType": report["deltaByTrainType"],
        "weekdayMinatomiraiProposal": {k: v for k, v in report["weekdayMinatomiraiProposal"].items() if k != "proposedTimes"},
    }, ensure_ascii=False), flush=True)
    bad = [(key, value["coverage"]) for key, value in report["adjacentChecks"].items() if value["coverage"] < 0.90]
    if bad:
        raise RuntimeError(f"adjacent timetable coverage below 90%: {bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
