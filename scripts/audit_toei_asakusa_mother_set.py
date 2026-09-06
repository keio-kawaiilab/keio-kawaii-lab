#!/usr/bin/env python3
"""Audit the independent Toei Asakusa Line train-timetable mother set.

This audit treats every compact train-timetable row as a Toei-local scheduled
train identity. It validates IDs, calendars, stop order and time accounting, and
classifies how each trip touches Sengakuji and Oshiage. Boundary contact is only
an inventory signal; it never establishes cross-operator same-train identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "data/transit/toei/timetable-index.json"
ASAKUSA = "odpt.Railway:Toei.Asakusa"
SENGAKUJI = "odpt.Station:Toei.Asakusa.Sengakuji"
OSHIAGE = "odpt.Station:Toei.Asakusa.Oshiage"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def operator_of_destination(value: Any) -> str:
    text = str(value or "")
    if text.startswith("odpt.Station:Keikyu."):
        return "keikyu"
    if text.startswith("odpt.Station:Keisei."):
        return "keisei"
    if text.startswith("odpt.Station:Hokuso.") or text.startswith("manual.Station:Hokuso."):
        return "hokuso"
    if text.startswith("odpt.Station:Toei.Asakusa."):
        return "toei-asakusa"
    if text.startswith("odpt.Station:Toei."):
        return "toei-other"
    return "other-or-unknown"


def boundary_position(station_indexes: list[int], boundary_index: int) -> str:
    if boundary_index not in station_indexes:
        return "not-touched"
    if len(station_indexes) == 1:
        return "only-stop"
    if station_indexes[0] == boundary_index:
        return "starts"
    if station_indexes[-1] == boundary_index:
        return "ends"
    return "middle"


def build_audit(index_path: Path) -> dict[str, Any]:
    index = load_json(index_path)
    line = (index.get("lines") or {}).get(ASAKUSA)
    if not isinstance(line, dict) or not line.get("file"):
        raise RuntimeError("Toei Asakusa timetable index entry missing")
    timetable_path = index_path.parent / str(line["file"])
    raw_bytes = timetable_path.read_bytes()
    timetable = json.loads(raw_bytes.decode("utf-8"))

    issues: list[dict[str, Any]] = []
    if timetable.get("railway") != ASAKUSA:
        issues.append({"kind": "railway-mismatch", "value": timetable.get("railway")})
    if timetable.get("timeBasis") != "train-timetable":
        issues.append({"kind": "unexpected-time-basis", "value": timetable.get("timeBasis")})

    stations = [str(x) for x in timetable.get("stations") or []]
    calendars = [str(x) for x in timetable.get("calendars") or []]
    train_types = [str(x) for x in timetable.get("trainTypes") or []]
    schema = [str(x) for x in timetable.get("tripSchema") or []]
    trips = timetable.get("trips") or []
    expected_trips = int(line.get("trips") or 0)

    required_fields = {"calendarIndex", "trainTypeIndex", "trainNumber", "stops", "destination", "trainId", "timetableId"}
    if set(schema) != required_fields:
        issues.append({"kind": "unexpected-trip-schema", "schema": schema})

    try:
        sengakuji_index = stations.index(SENGAKUJI)
    except ValueError:
        sengakuji_index = -1
        issues.append({"kind": "sengakuji-station-missing"})
    try:
        oshiage_index = stations.index(OSHIAGE)
    except ValueError:
        oshiage_index = -1
        issues.append({"kind": "oshiage-station-missing"})

    calendar_counts = Counter()
    direction_counts = Counter()
    train_type_counts = Counter()
    destination_operator_counts = Counter()
    sengakuji_positions = Counter()
    oshiage_positions = Counter()
    sengakuji_endpoint_destinations = Counter()
    oshiage_endpoint_destinations = Counter()
    stop_count_histogram = Counter()
    timetable_ids: set[str] = set()
    local_identity_keys: set[tuple[str, str]] = set()
    duplicate_timetable_ids: list[str] = []
    duplicate_local_identity_keys: list[str] = []
    blank_train_numbers = 0
    total_stop_rows = 0
    total_time_cells = 0
    arrival_cells = 0
    departure_cells = 0
    detailed_issue_count = 0

    for trip_index, raw in enumerate(trips):
        if not isinstance(raw, list) or len(raw) != len(schema):
            issues.append({"kind": "trip-shape-mismatch", "tripIndex": trip_index})
            continue
        row = dict(zip(schema, raw))
        calendar_index = row.get("calendarIndex")
        train_type_index = row.get("trainTypeIndex")
        if not isinstance(calendar_index, int) or not 0 <= calendar_index < len(calendars):
            issues.append({"kind": "invalid-calendar-index", "tripIndex": trip_index, "value": calendar_index})
            continue
        if not isinstance(train_type_index, int) or not 0 <= train_type_index < len(train_types):
            issues.append({"kind": "invalid-train-type-index", "tripIndex": trip_index, "value": train_type_index})
            continue

        calendar = calendars[calendar_index]
        train_type = train_types[train_type_index]
        train_number = str(row.get("trainNumber") or "")
        train_id = str(row.get("trainId") or "")
        timetable_id = str(row.get("timetableId") or "")
        destination = str(row.get("destination") or "")
        calendar_counts[calendar] += 1
        train_type_counts[train_type] += 1
        destination_operator_counts[operator_of_destination(destination)] += 1
        if not train_number:
            blank_train_numbers += 1
        if not train_id:
            issues.append({"kind": "missing-train-id", "tripIndex": trip_index})
        if not timetable_id:
            issues.append({"kind": "missing-timetable-id", "tripIndex": trip_index})
        elif timetable_id in timetable_ids:
            duplicate_timetable_ids.append(timetable_id)
        else:
            timetable_ids.add(timetable_id)
        identity_key = (calendar, timetable_id)
        if identity_key in local_identity_keys:
            duplicate_local_identity_keys.append(f"{calendar}|{timetable_id}")
        else:
            local_identity_keys.add(identity_key)

        raw_stops = row.get("stops") or []
        if not isinstance(raw_stops, list) or not raw_stops:
            issues.append({"kind": "empty-stops", "tripIndex": trip_index, "timetableId": timetable_id})
            continue

        station_indexes: list[int] = []
        previous_event_time: int | None = None
        trip_bad = False
        for stop_pos, stop in enumerate(raw_stops):
            if not isinstance(stop, list) or len(stop) < 3:
                issues.append({"kind": "invalid-stop-shape", "tripIndex": trip_index, "stopPosition": stop_pos})
                trip_bad = True
                continue
            station_index, arrival, departure = stop[:3]
            if not isinstance(station_index, int) or not 0 <= station_index < len(stations):
                issues.append({"kind": "invalid-station-index", "tripIndex": trip_index, "stopPosition": stop_pos, "value": station_index})
                trip_bad = True
                continue
            station_indexes.append(station_index)
            values = [value for value in (arrival, departure) if value is not None]
            if not values:
                issues.append({"kind": "stop-without-time", "tripIndex": trip_index, "stopPosition": stop_pos})
                trip_bad = True
                continue
            if any(not isinstance(value, int) for value in values):
                issues.append({"kind": "non-integer-time", "tripIndex": trip_index, "stopPosition": stop_pos})
                trip_bad = True
                continue
            if arrival is not None:
                arrival_cells += 1
            if departure is not None:
                departure_cells += 1
            total_time_cells += len(values)
            total_stop_rows += 1
            if arrival is not None and departure is not None and arrival > departure:
                issues.append({"kind": "arrival-after-departure", "tripIndex": trip_index, "stopPosition": stop_pos})
                trip_bad = True
            first_event = int(arrival if arrival is not None else departure)
            last_event = int(departure if departure is not None else arrival)
            if previous_event_time is not None and first_event < previous_event_time:
                issues.append({"kind": "non-monotonic-time", "tripIndex": trip_index, "stopPosition": stop_pos})
                trip_bad = True
            previous_event_time = last_event

        if len(station_indexes) >= 2:
            deltas = [b - a for a, b in zip(station_indexes, station_indexes[1:])]
            if all(delta > 0 for delta in deltas):
                direction = "increasing-station-index"
            elif all(delta < 0 for delta in deltas):
                direction = "decreasing-station-index"
            else:
                direction = "non-monotonic-station-order"
                issues.append({"kind": "non-monotonic-station-order", "tripIndex": trip_index, "timetableId": timetable_id})
                trip_bad = True
        else:
            direction = "single-stop"
        direction_counts[direction] += 1
        stop_count_histogram[str(len(station_indexes))] += 1

        if sengakuji_index >= 0:
            pos = boundary_position(station_indexes, sengakuji_index)
            sengakuji_positions[pos] += 1
            if pos in {"starts", "ends", "only-stop"}:
                sengakuji_endpoint_destinations[operator_of_destination(destination)] += 1
        if oshiage_index >= 0:
            pos = boundary_position(station_indexes, oshiage_index)
            oshiage_positions[pos] += 1
            if pos in {"starts", "ends", "only-stop"}:
                oshiage_endpoint_destinations[operator_of_destination(destination)] += 1
        if trip_bad:
            detailed_issue_count += 1

    if duplicate_timetable_ids:
        issues.append({"kind": "duplicate-timetable-ids", "count": len(duplicate_timetable_ids), "examples": duplicate_timetable_ids[:50]})
    if duplicate_local_identity_keys:
        issues.append({"kind": "duplicate-local-identity-keys", "count": len(duplicate_local_identity_keys), "examples": duplicate_local_identity_keys[:50]})

    return {
        "version": 1,
        "kind": "toei-asakusa-independent-mother-set-audit",
        "source": {
            "indexPath": str(index_path.relative_to(ROOT)) if index_path.is_relative_to(ROOT) else str(index_path),
            "timetablePath": str(timetable_path.relative_to(ROOT)) if timetable_path.is_relative_to(ROOT) else str(timetable_path),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "timeBasis": timetable.get("timeBasis"),
        },
        "railway": timetable.get("railway"),
        "indexExpectedTripCount": expected_trips,
        "tripCount": len(trips),
        "uniqueTimetableIdCount": len(timetable_ids),
        "uniqueLocalIdentityKeyCount": len(local_identity_keys),
        "blankTrainNumberCount": blank_train_numbers,
        "stationCount": len(stations),
        "calendarCount": len(calendars),
        "calendars": calendars,
        "trainTypeCount": len(train_types),
        "calendarTripCounts": dict(sorted(calendar_counts.items())),
        "directionTripCounts": dict(sorted(direction_counts.items())),
        "trainTypeTripCounts": dict(sorted(train_type_counts.items())),
        "destinationOperatorCounts": dict(sorted(destination_operator_counts.items())),
        "stopCountHistogram": dict(sorted(stop_count_histogram.items(), key=lambda item: int(item[0]))),
        "totalStopRows": total_stop_rows,
        "totalTimeCells": total_time_cells,
        "arrivalTimeCells": arrival_cells,
        "departureTimeCells": departure_cells,
        "sengakuji": {
            "stationIndex": sengakuji_index,
            "positionCounts": dict(sorted(sengakuji_positions.items())),
            "endpointDestinationOperatorCounts": dict(sorted(sengakuji_endpoint_destinations.items())),
        },
        "oshiage": {
            "stationIndex": oshiage_index,
            "positionCounts": dict(sorted(oshiage_positions.items())),
            "endpointDestinationOperatorCounts": dict(sorted(oshiage_endpoint_destinations.items())),
        },
        "tripRowsWithDetailedIssue": detailed_issue_count,
        "issues": issues,
        "identityPolicy": {
            "timetableIdIsExactToeiLocalScheduledIdentity": True,
            "allIndexedTripsRequired": True,
            "boundaryContactMayEstablishCrossOperatorIdentity": False,
            "trainNumberAloneMayEstablishCrossOperatorIdentity": False,
            "timeProximityMayEstablishCrossOperatorIdentity": False,
            "destinationAloneMayEstablishCrossOperatorIdentity": False,
            "runtimeSameTrainPromotions": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_audit(args.index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "trips": payload["tripCount"],
        "uniqueTimetableIds": payload["uniqueTimetableIdCount"],
        "calendars": payload["calendarTripCounts"],
        "directions": payload["directionTripCounts"],
        "destinationOperators": payload["destinationOperatorCounts"],
        "sengakuji": payload["sengakuji"],
        "oshiage": payload["oshiage"],
        "timeCells": payload["totalTimeCells"],
        "issues": len(payload["issues"]),
        "runtimeSameTrainPromotions": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
