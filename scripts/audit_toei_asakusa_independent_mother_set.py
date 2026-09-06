#!/usr/bin/env python3
"""Audit the independent Toei Asakusa Line train-timetable mother set.

This consumes the checked-in Toei train-timetable projection directly.  It does
not use the Keisei-led network to decide which Toei trains exist and it does not
promote any cross-operator same-train identity.  The goal is to prove that every
trip in the Toei Asakusa timetable file is structurally accounted for before
later reconciling exact identities at Sengakuji and Oshiage.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ASAKUSA = "odpt.Railway:Toei.Asakusa"
SENGAKUJI = "odpt.Station:Toei.Asakusa.Sengakuji"
OSHIAGE = "odpt.Station:Toei.Asakusa.Oshiage"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _time_values(stops: list[list[Any]]) -> list[int]:
    values: list[int] = []
    for stop in stops:
        if not isinstance(stop, list) or len(stop) != 3:
            continue
        _station_index, arrival, departure = stop
        if arrival is not None:
            values.append(int(arrival))
        if departure is not None:
            values.append(int(departure))
    return values


def build_audit(index: dict[str, Any], timetable: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    if timetable.get("railway") != ASAKUSA:
        issues.append({"kind": "wrong-railway", "actual": timetable.get("railway")})
    if timetable.get("timeBasis") != "train-timetable":
        issues.append({"kind": "wrong-time-basis", "actual": timetable.get("timeBasis")})

    line_meta = ((index.get("lines") or {}).get(ASAKUSA) or {})
    expected_trips = int(line_meta.get("trips") or 0)
    expected_connections = int(line_meta.get("connections") or 0)

    stations = [str(value) for value in timetable.get("stations") or []]
    calendars = [str(value) for value in timetable.get("calendars") or []]
    train_types = [str(value) for value in timetable.get("trainTypes") or []]
    schema = list(timetable.get("tripSchema") or [])
    trips = list(timetable.get("trips") or [])
    expected_schema = [
        "calendarIndex", "trainTypeIndex", "trainNumber", "stops",
        "destination", "trainId", "timetableId",
    ]
    if schema != expected_schema:
        issues.append({"kind": "unexpected-trip-schema", "actual": schema})
    if len(trips) != expected_trips:
        issues.append({"kind": "trip-count-mismatch", "expected": expected_trips, "actual": len(trips)})
    if len(set(stations)) != len(stations):
        issues.append({"kind": "duplicate-station-catalog-entry"})
    if SENGAKUJI not in stations or OSHIAGE not in stations:
        issues.append({"kind": "missing-through-boundary-station"})

    timetable_ids: set[str] = set()
    calendar_train_ids: set[tuple[int, str]] = set()
    calendar_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    destination_counts: Counter[str] = Counter()
    boundary_external_counts: Counter[str] = Counter()
    internal_destination = 0
    external_destination = 0
    connection_count = 0
    stop_count = 0
    time_value_count = 0
    chronology_issues = 0
    station_order_issues = 0
    invalid_stop_rows = 0

    station_set = set(stations)
    sengakuji_index = stations.index(SENGAKUJI) if SENGAKUJI in stations else -1
    oshiage_index = stations.index(OSHIAGE) if OSHIAGE in stations else -1

    for ordinal, trip in enumerate(trips):
        if not isinstance(trip, list) or len(trip) != 7:
            issues.append({"kind": "invalid-trip-row", "ordinal": ordinal})
            continue
        calendar_index, type_index, train_number, stops, destination, train_id, timetable_id = trip
        try:
            calendar_index = int(calendar_index)
            type_index = int(type_index)
        except (TypeError, ValueError):
            issues.append({"kind": "invalid-trip-index", "ordinal": ordinal})
            continue
        if not (0 <= calendar_index < len(calendars)):
            issues.append({"kind": "calendar-index-out-of-range", "ordinal": ordinal, "value": calendar_index})
            continue
        if not (0 <= type_index < len(train_types)):
            issues.append({"kind": "train-type-index-out-of-range", "ordinal": ordinal, "value": type_index})
            continue
        calendar = calendars[calendar_index]
        train_type = train_types[type_index]
        calendar_counts[calendar] += 1
        type_counts[train_type] += 1
        destination = str(destination or "")
        destination_counts[destination] += 1

        timetable_id = str(timetable_id or "")
        train_id = str(train_id or "")
        if not timetable_id:
            issues.append({"kind": "missing-timetable-id", "ordinal": ordinal})
        elif timetable_id in timetable_ids:
            issues.append({"kind": "duplicate-timetable-id", "ordinal": ordinal, "id": timetable_id})
        timetable_ids.add(timetable_id)
        key = (calendar_index, train_id)
        if not train_id:
            issues.append({"kind": "missing-train-id", "ordinal": ordinal})
        elif key in calendar_train_ids:
            issues.append({"kind": "duplicate-calendar-train-id", "ordinal": ordinal, "id": train_id, "calendar": calendar})
        calendar_train_ids.add(key)
        if not train_number:
            issues.append({"kind": "missing-train-number", "ordinal": ordinal})

        if not isinstance(stops, list) or not stops:
            issues.append({"kind": "empty-stops", "ordinal": ordinal})
            continue

        stop_indices: list[int] = []
        valid_stops: list[list[Any]] = []
        for stop in stops:
            if not isinstance(stop, list) or len(stop) != 3:
                invalid_stop_rows += 1
                continue
            try:
                station_index = int(stop[0])
            except (TypeError, ValueError):
                invalid_stop_rows += 1
                continue
            if not (0 <= station_index < len(stations)):
                invalid_stop_rows += 1
                continue
            if stop[1] is None and stop[2] is None:
                invalid_stop_rows += 1
                continue
            stop_indices.append(station_index)
            valid_stops.append(stop)
        stop_count += len(valid_stops)
        connection_count += max(0, len(valid_stops) - 1)

        if len(stop_indices) >= 2:
            diffs = [b - a for a, b in zip(stop_indices, stop_indices[1:])]
            if not (all(value > 0 for value in diffs) or all(value < 0 for value in diffs)):
                station_order_issues += 1
        values = _time_values(valid_stops)
        time_value_count += len(values)
        if any(b < a for a, b in zip(values, values[1:])):
            chronology_issues += 1

        if destination in station_set:
            internal_destination += 1
        else:
            external_destination += 1
            first_index = stop_indices[0] if stop_indices else -1
            last_index = stop_indices[-1] if stop_indices else -1
            if last_index == sengakuji_index or first_index == sengakuji_index:
                boundary_external_counts["Sengakuji"] += 1
            if last_index == oshiage_index or first_index == oshiage_index:
                boundary_external_counts["Oshiage"] += 1

    if invalid_stop_rows:
        issues.append({"kind": "invalid-stop-rows", "count": invalid_stop_rows})
    if station_order_issues:
        issues.append({"kind": "non-monotonic-station-order", "count": station_order_issues})
    if chronology_issues:
        issues.append({"kind": "non-monotonic-times", "count": chronology_issues})
    if expected_connections and connection_count != expected_connections:
        issues.append({"kind": "connection-count-mismatch", "expected": expected_connections, "actual": connection_count})

    return {
        "version": 1,
        "kind": "toei-asakusa-independent-mother-set-audit",
        "railway": ASAKUSA,
        "timeBasis": timetable.get("timeBasis"),
        "expectedTripCount": expected_trips,
        "actualTripCount": len(trips),
        "candidatePhysicalTrainCount": len(trips),
        "uniqueTimetableIdCount": len(timetable_ids),
        "uniqueCalendarTrainIdCount": len(calendar_train_ids),
        "stationCount": len(stations),
        "stopCount": stop_count,
        "connectionCount": connection_count,
        "expectedConnectionCount": expected_connections,
        "timeValueCount": time_value_count,
        "calendarCounts": dict(sorted(calendar_counts.items())),
        "trainTypeCounts": dict(sorted(type_counts.items())),
        "internalDestinationTrips": internal_destination,
        "externalDestinationTrips": external_destination,
        "externalDestinationBoundaryCounts": dict(sorted(boundary_external_counts.items())),
        "destinationCount": len(destination_counts),
        "issues": issues,
        "identityPolicy": {
            "motherSetComesFromToeiTrainTimetable": True,
            "keiseiMotherSetUsedToSelectTrips": False,
            "allTimetableTripsRetained": True,
            "trainTimetableIdIsExactLocalIdentity": True,
            "crossOperatorIdentityEstablished": False,
            "clockTimeMayEstablishCrossOperatorIdentity": False,
            "destinationMayEstablishCrossOperatorIdentity": False,
            "runtimeSameTrainPromotions": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, default=Path("data/transit/toei/timetable-index.json"))
    parser.add_argument("--timetable", type=Path, default=Path("data/transit/toei/timetables/899209dea5fc3a.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_audit(load(args.index), load(args.timetable))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "trips": payload["actualTripCount"],
        "timetableIds": payload["uniqueTimetableIdCount"],
        "calendarTrainIds": payload["uniqueCalendarTrainIdCount"],
        "connections": payload["connectionCount"],
        "internalDestinations": payload["internalDestinationTrips"],
        "externalDestinations": payload["externalDestinationTrips"],
        "boundaryExternal": payload["externalDestinationBoundaryCounts"],
        "issues": len(payload["issues"]),
        "runtimeSameTrainPromotions": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
