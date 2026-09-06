#!/usr/bin/env python3
"""Match Keikyu's official Sengakuji through columns directly to exact Toei trips.

This deliberately bypasses the historical transit-v2 fragment projection.  The
Keikyu connection timetable itself proves that one printed column crosses both
sides of Sengakuji.  We then identify the corresponding *local* Toei
TrainTimetable only when calendar + travel direction + exact boundary minute
resolve to one trip.  Time alone never establishes cross-operator identity: the
cross-boundary fact comes from the operator's same printed column.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from keikyu_official_train_evidence import (
    DEFAULT_HOLIDAY_URL,
    DEFAULT_WEEKDAY_URL,
    extract_pdf,
    fetch_pdf,
)

TOEI_FILE = Path("data/transit/toei/timetables/899209dea5fc3a.json")
SENGAKUJI = "odpt.Station:Toei.Asakusa.Sengakuji"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def calendar_kind(value: str) -> str:
    text = str(value).lower()
    if "weekday" in text:
        return "weekday"
    if "saturdayholiday" in text or "holiday" in text:
        return "holiday"
    return "unknown"


def endpoint_event(stops: list[list[Any]], *, first: bool) -> tuple[int | None, int | None, int | None]:
    if not stops:
        return None, None, None
    stop = stops[0] if first else stops[-1]
    if not isinstance(stop, list) or len(stop) != 3:
        return None, None, None
    station_index, arrival, departure = stop
    return int(station_index), None if arrival is None else int(arrival), None if departure is None else int(departure)


def minute_matches(arrival: int | None, departure: int | None, target: int) -> bool:
    return arrival == target or departure == target


def build_toei_index(timetable: dict[str, Any]) -> tuple[dict[tuple[str, str, int], list[dict[str, Any]]], list[dict[str, Any]]]:
    stations = [str(v) for v in timetable.get("stations") or []]
    calendars = [str(v) for v in timetable.get("calendars") or []]
    if SENGAKUJI not in stations:
        raise RuntimeError("Sengakuji missing from Toei station catalog")
    sengakuji_index = stations.index(SENGAKUJI)
    index: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    boundary_rows: list[dict[str, Any]] = []

    for ordinal, trip in enumerate(timetable.get("trips") or []):
        if not isinstance(trip, list) or len(trip) != 7:
            continue
        cal_i, _type_i, train_number, stops, destination, train_id, timetable_id = trip
        calendar = calendar_kind(calendars[int(cal_i)])
        if calendar == "unknown" or not isinstance(stops, list) or not stops:
            continue
        first_i, first_arr, first_dep = endpoint_event(stops, first=True)
        last_i, last_arr, last_dep = endpoint_event(stops, first=False)
        row = {
            "ordinal": ordinal,
            "calendar": calendar,
            "trainNumber": str(train_number or ""),
            "trainId": str(train_id or ""),
            "timetableId": str(timetable_id or ""),
            "destination": str(destination or ""),
            "firstStationIndex": first_i,
            "lastStationIndex": last_i,
            "firstArrival": first_arr,
            "firstDeparture": first_dep,
            "lastArrival": last_arr,
            "lastDeparture": last_dep,
        }
        if first_i == sengakuji_index:
            boundary_rows.append({**row, "endpointRole": "starts-at-sengakuji"})
            for minute in {v for v in (first_arr, first_dep) if v is not None}:
                index[(calendar, "keikyu-to-toei", int(minute))].append(row)
        if last_i == sengakuji_index:
            boundary_rows.append({**row, "endpointRole": "ends-at-sengakuji"})
            for minute in {v for v in (last_arr, last_dep) if v is not None}:
                index[(calendar, "toei-to-keikyu", int(minute))].append(row)
    return index, boundary_rows


def audit(candidates: list[dict[str, Any]], timetable: dict[str, Any]) -> dict[str, Any]:
    index, boundary_rows = build_toei_index(timetable)
    results: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    direction_counts: Counter[str] = Counter()
    calendar_counts: Counter[str] = Counter()
    matched_ids: set[str] = set()
    duplicate_candidate_targets: Counter[str] = Counter()

    for candidate in candidates:
        calendar = str(candidate.get("calendar") or "")
        direction = str(candidate.get("direction") or "")
        if direction == "toei-to-keikyu":
            minute = int(candidate["sourceBoundaryMinute"])
        elif direction == "keikyu-to-toei":
            minute = int(candidate["targetBoundaryMinute"])
        else:
            status_counts["invalid-direction"] += 1
            results.append({**candidate, "toeiMatchStatus": "invalid-direction", "toeiMatches": []})
            continue
        matches = index.get((calendar, direction, minute), [])
        status = "matched-singleton" if len(matches) == 1 else "unmatched" if not matches else "ambiguous"
        status_counts[status] += 1
        direction_counts[direction] += 1
        calendar_counts[calendar] += 1
        ids = [str(row["timetableId"]) for row in matches]
        if len(matches) == 1:
            matched_ids.add(ids[0])
            duplicate_candidate_targets[ids[0]] += 1
        results.append({
            "candidateId": candidate.get("id"),
            "calendar": calendar,
            "direction": direction,
            "sourceBoundaryMinute": candidate.get("sourceBoundaryMinute"),
            "targetBoundaryMinute": candidate.get("targetBoundaryMinute"),
            "boundaryTrainNumber": candidate.get("boundaryTrainNumber"),
            "pdfPage": candidate.get("pdfPage"),
            "columnX": candidate.get("columnX"),
            "officialEvidence": candidate.get("evidence"),
            "toeiMatchStatus": status,
            "toeiMatches": ids,
            "toeiTrainNumbers": [str(row["trainNumber"]) for row in matches],
        })

    multiply_targeted = {k: v for k, v in sorted(duplicate_candidate_targets.items()) if v > 1}
    issues: list[dict[str, Any]] = []
    if multiply_targeted:
        issues.append({"kind": "multiple-official-columns-target-one-toei-trip", "count": len(multiply_targeted)})

    return {
        "version": 1,
        "kind": "toei-asakusa-sengakuji-official-column-audit",
        "officialColumnCandidateCount": len(candidates),
        "statusCounts": dict(sorted(status_counts.items())),
        "directionCounts": dict(sorted(direction_counts.items())),
        "calendarCounts": dict(sorted(calendar_counts.items())),
        "uniqueMatchedToeiTripCount": len(matched_ids),
        "toeiBoundaryEndpointRecordCount": len(boundary_rows),
        "multiplyTargetedToeiTrips": multiply_targeted,
        "issues": issues,
        "identityPolicy": {
            "crossBoundaryFactComesFromOfficialSamePrintedColumn": True,
            "toeiLocalTripMustResolveSingleton": True,
            "historicalTransitV2FragmentProjectionRequired": False,
            "timeAloneMayEstablishCrossOperatorIdentity": False,
            "trainNumberAloneMayEstablishCrossOperatorIdentity": False,
            "keikyuIndependentMotherSetLinked": False,
            "runtimeSameTrainPromotions": 0
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--toei", type=Path, default=TOEI_FILE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidates: list[dict[str, Any]] = []
    for calendar, url in (("weekday", DEFAULT_WEEKDAY_URL), ("holiday", DEFAULT_HOLIDAY_URL)):
        candidates.extend(extract_pdf(fetch_pdf(url), calendar, url))
    payload = audit(candidates, load(args.toei))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "officialColumns": payload["officialColumnCandidateCount"],
        "statusCounts": payload["statusCounts"],
        "directions": payload["directionCounts"],
        "calendars": payload["calendarCounts"],
        "uniqueMatchedToeiTrips": payload["uniqueMatchedToeiTripCount"],
        "multiplyTargeted": len(payload["multiplyTargetedToeiTrips"]),
        "issues": payload["issues"],
        "runtimeSameTrainPromotions": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
