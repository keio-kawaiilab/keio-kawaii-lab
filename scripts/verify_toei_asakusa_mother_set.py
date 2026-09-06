#!/usr/bin/env python3
"""Fail-closed verifier for the independent Toei Asakusa mother-set audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify(payload: dict) -> dict:
    errors: list[str] = []
    if payload.get("version") != 1:
        errors.append("version must be 1")
    if payload.get("kind") != "toei-asakusa-independent-mother-set-audit":
        errors.append("unexpected dataset kind")
    if payload.get("railway") != "odpt.Railway:Toei.Asakusa":
        errors.append("unexpected railway")
    if (payload.get("source") or {}).get("timeBasis") != "train-timetable":
        errors.append("timeBasis must be train-timetable")

    trips = int(payload.get("tripCount") or 0)
    expected = int(payload.get("indexExpectedTripCount") or 0)
    unique_timetables = int(payload.get("uniqueTimetableIdCount") or 0)
    unique_local = int(payload.get("uniqueLocalIdentityKeyCount") or 0)
    if trips <= 0:
        errors.append("no Toei Asakusa trips")
    if expected != trips:
        errors.append(f"timetable-index trip count mismatch: {trips}/{expected}")
    if unique_timetables != trips:
        errors.append(f"timetableId is not unique: {unique_timetables}/{trips}")
    if unique_local != trips:
        errors.append(f"local identity key is not unique: {unique_local}/{trips}")

    calendars = payload.get("calendarTripCounts") or {}
    if sum(int(v) for v in calendars.values()) != trips:
        errors.append("calendar trip accounting mismatch")
    if not calendars.get("odpt.Calendar:Weekday"):
        errors.append("weekday trips missing")
    if not calendars.get("odpt.Calendar:SaturdayHoliday"):
        errors.append("SaturdayHoliday trips missing")

    directions = payload.get("directionTripCounts") or {}
    if sum(int(v) for v in directions.values()) != trips:
        errors.append("direction trip accounting mismatch")
    if not directions.get("increasing-station-index"):
        errors.append("increasing-direction trips missing")
    if not directions.get("decreasing-station-index"):
        errors.append("decreasing-direction trips missing")
    if directions.get("non-monotonic-station-order"):
        errors.append("non-monotonic station-order trips present")

    total_stops = int(payload.get("totalStopRows") or 0)
    total_times = int(payload.get("totalTimeCells") or 0)
    arrivals = int(payload.get("arrivalTimeCells") or 0)
    departures = int(payload.get("departureTimeCells") or 0)
    if total_stops <= 0 or total_times <= 0:
        errors.append("empty stop/time inventory")
    if arrivals + departures != total_times:
        errors.append("arrival/departure time-cell accounting mismatch")

    for boundary_name in ("sengakuji", "oshiage"):
        boundary = payload.get(boundary_name) or {}
        if int(boundary.get("stationIndex", -1)) < 0:
            errors.append(f"{boundary_name} station missing")
        positions = boundary.get("positionCounts") or {}
        if sum(int(v) for v in positions.values()) != trips:
            errors.append(f"{boundary_name} position accounting mismatch")

    policy = payload.get("identityPolicy") or {}
    if policy.get("timetableIdIsExactToeiLocalScheduledIdentity") is not True:
        errors.append("local timetable identity policy must be true")
    if policy.get("allIndexedTripsRequired") is not True:
        errors.append("all indexed trips must be required")
    for key in (
        "boundaryContactMayEstablishCrossOperatorIdentity",
        "trainNumberAloneMayEstablishCrossOperatorIdentity",
        "timeProximityMayEstablishCrossOperatorIdentity",
        "destinationAloneMayEstablishCrossOperatorIdentity",
    ):
        if policy.get(key) is not False:
            errors.append(f"{key} must be false")
    if policy.get("runtimeSameTrainPromotions") != 0:
        errors.append("runtimeSameTrainPromotions must remain zero")

    if payload.get("tripRowsWithDetailedIssue"):
        errors.append(f"{payload['tripRowsWithDetailedIssue']} trip row(s) have detailed structural/time issues")
    if payload.get("issues"):
        errors.append(f"mother-set audit has {len(payload['issues'])} issue(s)")

    if errors:
        raise RuntimeError("Toei Asakusa mother-set verification failed:\n- " + "\n- ".join(errors[:100]))
    return {
        "verified": True,
        "trips": trips,
        "weekdayTrips": int(calendars.get("odpt.Calendar:Weekday") or 0),
        "holidayTrips": int(calendars.get("odpt.Calendar:SaturdayHoliday") or 0),
        "increasingTrips": int(directions.get("increasing-station-index") or 0),
        "decreasingTrips": int(directions.get("decreasing-station-index") or 0),
        "timeCells": total_times,
        "sengakujiPositions": (payload.get("sengakuji") or {}).get("positionCounts") or {},
        "oshiagePositions": (payload.get("oshiage") or {}).get("positionCounts") or {},
        "runtimeSameTrainPromotions": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    print(json.dumps(verify(payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
