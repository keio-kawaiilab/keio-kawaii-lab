#!/usr/bin/env python3
"""Measure the exact Toei Asakusa trips missing from the Keisei-led network.

This audit is intentionally conservative.  A Toei trip is considered already
represented only when a Keisei-led network trip has the same service calendar,
the same published train number, and matching times at at least two common
physical station IDs.  Train number, destination, or time proximity alone are
never enough.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOEI_PATH = ROOT / "data/transit/toei/timetables/899209dea5fc3a.json"
NETWORK_PATH = ROOT / "data/transit/keisei/timetables/official-network.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def calendar_key(value: str) -> str:
    value = str(value or "").lower()
    if "weekday" in value:
        return "weekday"
    if "holiday" in value or "saturday" in value:
        return "holiday"
    return value


def stop_events(stations: list[str], stops: list[list[Any]]) -> dict[str, set[tuple[str, int]]]:
    """Return exact arrival/departure events keyed by physical station ID."""
    result: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for stop in stops:
        if not isinstance(stop, list) or len(stop) < 3:
            continue
        station_index, arrival, departure = stop[0], stop[1], stop[2]
        if not isinstance(station_index, int) or not (0 <= station_index < len(stations)):
            continue
        station_id = stations[station_index]
        if isinstance(arrival, int):
            result[station_id].add(("arrival", arrival))
        if isinstance(departure, int):
            result[station_id].add(("departure", departure))
    return result


def matching_station_count(
    left: dict[str, set[tuple[str, int]]],
    right: dict[str, set[tuple[str, int]]],
) -> int:
    count = 0
    for station_id in left.keys() & right.keys():
        if left[station_id] & right[station_id]:
            count += 1
    return count


def main() -> int:
    toei = load(TOEI_PATH)
    network = load(NETWORK_PATH)

    assert toei.get("railway") == "odpt.Railway:Toei.Asakusa"
    assert len(toei.get("trips") or []) == 1260, "unexpected Asakusa source-trip count"

    toei_stations = list(toei.get("stations") or [])
    toei_calendars = list(toei.get("calendars") or [])
    network_stations = list(network.get("stationIds") or [])
    network_calendars = list(network.get("calendarNames") or [])

    network_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for trip_index, trip in enumerate(network.get("trips") or []):
        if not isinstance(trip, list) or len(trip) < 7:
            continue
        cal_index, train_number, _train_type, stops, _links, source_trip_id, railway_path = trip[:7]
        if not isinstance(cal_index, int) or not (0 <= cal_index < len(network_calendars)):
            continue
        key = (calendar_key(network_calendars[cal_index]), str(train_number or ""))
        network_by_key[key].append(
            {
                "index": trip_index,
                "events": stop_events(network_stations, stops or []),
                "sourceTripId": source_trip_id,
                "railwayPath": railway_path or [],
            }
        )

    exact = 0
    ambiguous = 0
    one_station_only = 0
    no_exact_match = 0
    unmatched_numbers: list[dict[str, Any]] = []
    matched_non_keisei_path = 0
    match_histogram: Counter[int] = Counter()

    for trip in toei.get("trips") or []:
        cal_index, _train_type, train_number, stops, destination, train_id, timetable_id = trip[:7]
        cal = calendar_key(toei_calendars[cal_index])
        key = (cal, str(train_number or ""))
        events = stop_events(toei_stations, stops or [])
        candidates = network_by_key.get(key, [])

        scored = [(matching_station_count(events, candidate["events"]), candidate) for candidate in candidates]
        best = max((score for score, _candidate in scored), default=0)
        winners = [candidate for score, candidate in scored if score == best and score >= 2]
        match_histogram[best] += 1

        if len(winners) == 1:
            exact += 1
            path = winners[0].get("railwayPath") or []
            if not any(str(railway).startswith("odpt.Railway:Keisei.") for railway in path):
                matched_non_keisei_path += 1
        elif len(winners) > 1:
            ambiguous += 1
            unmatched_numbers.append(
                {
                    "calendar": cal,
                    "trainNumber": train_number,
                    "reason": "multiple-exact-candidates",
                    "matchingStations": best,
                    "destination": destination,
                    "trainId": train_id,
                    "timetableId": timetable_id,
                }
            )
        elif best == 1:
            one_station_only += 1
            unmatched_numbers.append(
                {
                    "calendar": cal,
                    "trainNumber": train_number,
                    "reason": "only-one-shared-station-time",
                    "matchingStations": 1,
                    "destination": destination,
                    "trainId": train_id,
                    "timetableId": timetable_id,
                }
            )
        else:
            no_exact_match += 1
            unmatched_numbers.append(
                {
                    "calendar": cal,
                    "trainNumber": train_number,
                    "reason": "no-two-station-exact-match",
                    "matchingStations": best,
                    "destination": destination,
                    "trainId": train_id,
                    "timetableId": timetable_id,
                }
            )

    total = len(toei.get("trips") or [])
    unresolved = ambiguous + one_station_only + no_exact_match
    report = {
        "version": 1,
        "definition": "Asakusa trip is represented only by same calendar + same train number + exact published time match at >=2 shared physical stations.",
        "toeiAsakusaExactTrips": total,
        "representedInKeiseiLedNetwork": exact,
        "unresolvedOrMissing": unresolved,
        "ambiguous": ambiguous,
        "oneStationEvidenceOnly": one_station_only,
        "noExactMatch": no_exact_match,
        "representedWithoutKeiseiInRailwayPath": matched_non_keisei_path,
        "bestMatchingStationHistogram": {str(key): value for key, value in sorted(match_histogram.items())},
        "sampleUnresolved": unmatched_numbers[:40],
        "policy": {
            "trainNumberAloneMayMatch": False,
            "destinationAloneMayMatch": False,
            "timeProximityMayMatch": False,
            "minimumExactSharedStations": 2,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # This audit is informational while the family is being rebuilt.  Structural
    # failures should fail CI; the existence of a real gap must not.
    assert exact + unresolved == total
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
