#!/usr/bin/env python3
"""Upgrade the Toei Asakusa mother-set audit with strict service-day chronology.

The checked-in compact timetable stores minutes after midnight modulo 24 hours:
late trains therefore legitimately move from 23:xx (1380-1439) to 00:xx (0+).
This layer accepts only that narrow midnight wrap. Any other raw decrease remains
a hard audit issue. Raw timetable values are never rewritten.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from audit_toei_asakusa_independent_mother_set import build_audit, load


def event_values(stops: list[list[Any]]) -> list[int]:
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


def classify_service_day(values: list[int]) -> tuple[list[int], list[dict[str, int]], list[dict[str, int]]]:
    """Return normalized times, accepted wraps, and unsafe decreases.

    A wrap is accepted only when the previous normalized clock-of-day value is
    at least 23:00 and the next raw clock value is at most 02:00. This is narrow
    enough to model the observed official data without turning arbitrary time
    regressions into valid chronology.
    """
    if not values:
        return [], [], []
    offset = 0
    normalized = [values[0]]
    wraps: list[dict[str, int]] = []
    unsafe: list[dict[str, int]] = []
    previous_raw = values[0]
    for index, raw in enumerate(values[1:], start=1):
        if raw < previous_raw:
            if previous_raw >= 23 * 60 and raw <= 2 * 60 and offset == 0:
                offset = 24 * 60
                wraps.append({"index": index, "from": previous_raw, "to": raw})
            else:
                unsafe.append({"index": index, "from": previous_raw, "to": raw})
        value = raw + offset
        if value < normalized[-1]:
            unsafe.append({"index": index, "fromNormalized": normalized[-1], "toNormalized": value})
        normalized.append(value)
        previous_raw = raw
    return normalized, wraps, unsafe


def build_service_day_audit(index: dict[str, Any], timetable: dict[str, Any]) -> dict[str, Any]:
    payload = build_audit(index, timetable)
    raw_non_monotonic = [row for row in payload["issues"] if row.get("kind") == "non-monotonic-times"]
    payload["issues"] = [row for row in payload["issues"] if row.get("kind") != "non-monotonic-times"]

    wrap_trips: list[dict[str, Any]] = []
    unsafe_trips: list[dict[str, Any]] = []
    calendars = timetable.get("calendars") or []
    for ordinal, trip in enumerate(timetable.get("trips") or []):
        if not isinstance(trip, list) or len(trip) != 7:
            continue
        calendar_index, _type_index, train_number, stops, destination, train_id, timetable_id = trip
        values = event_values(stops if isinstance(stops, list) else [])
        normalized, wraps, unsafe = classify_service_day(values)
        if wraps:
            wrap_trips.append({
                "ordinal": ordinal,
                "calendar": calendars[int(calendar_index)] if 0 <= int(calendar_index) < len(calendars) else None,
                "trainNumber": train_number,
                "trainId": train_id,
                "timetableId": timetable_id,
                "destination": destination,
                "wraps": wraps,
                "firstRawTime": values[0] if values else None,
                "lastRawTime": values[-1] if values else None,
                "firstServiceDayTime": normalized[0] if normalized else None,
                "lastServiceDayTime": normalized[-1] if normalized else None,
            })
        if unsafe:
            unsafe_trips.append({
                "ordinal": ordinal,
                "trainNumber": train_number,
                "timetableId": timetable_id,
                "unsafeDecreases": unsafe,
                "rawTimes": values,
            })

    observed_raw_count = sum(int(row.get("count") or 0) for row in raw_non_monotonic)
    if observed_raw_count != len(wrap_trips) + len(unsafe_trips):
        payload["issues"].append({
            "kind": "raw-regression-accounting-mismatch",
            "rawNonMonotonicTrips": observed_raw_count,
            "wrapTrips": len(wrap_trips),
            "unsafeTrips": len(unsafe_trips),
        })
    if unsafe_trips:
        payload["issues"].append({"kind": "unsafe-service-day-time-regressions", "count": len(unsafe_trips)})

    payload["version"] = 2
    payload["kind"] = "toei-asakusa-independent-mother-set-service-day-audit"
    payload["rawNonMonotonicTripCount"] = observed_raw_count
    payload["acceptedMidnightWrapTripCount"] = len(wrap_trips)
    payload["acceptedMidnightWrapTrips"] = wrap_trips
    payload["unsafeTimeRegressionTripCount"] = len(unsafe_trips)
    payload["unsafeTimeRegressionTrips"] = unsafe_trips
    payload["identityPolicy"]["rawTimesPreserved"] = True
    payload["identityPolicy"]["midnightWrapNormalizationForChronologyOnly"] = True
    payload["identityPolicy"]["only2300To0200WrapMayNormalize"] = True
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, default=Path("data/transit/toei/timetable-index.json"))
    parser.add_argument("--timetable", type=Path, default=Path("data/transit/toei/timetables/899209dea5fc3a.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_service_day_audit(load(args.index), load(args.timetable))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "trips": payload["actualTripCount"],
        "rawNonMonotonicTrips": payload["rawNonMonotonicTripCount"],
        "acceptedMidnightWrapTrips": payload["acceptedMidnightWrapTripCount"],
        "unsafeTimeRegressionTrips": payload["unsafeTimeRegressionTripCount"],
        "issues": payload["issues"],
        "runtimeSameTrainPromotions": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
