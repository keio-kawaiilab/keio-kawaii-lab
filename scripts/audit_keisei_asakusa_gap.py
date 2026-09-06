#!/usr/bin/env python3
"""Measure exact Toei Asakusa representation inside the Keisei-led network.

This audit is intentionally conservative. A Toei trip is considered already
represented only when a Keisei-led network trip has the same service calendar,
the same published train number, and matching published times at at least two
common physical stations. Station IDs are NOT compared directly because the
same physical interchange may use operator/line-local ODPT IDs.

Train number, destination, or time proximity alone are never enough.
"""
from __future__ import annotations

import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOEI_PATH = ROOT / "data/transit/toei/timetables/899209dea5fc3a.json"
TOEI_ENTITIES_PATH = ROOT / "data/transit/toei/entities.json"
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


def normalize_station_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    # Known notation variants should compare as one physical station.
    return text.replace("ケ", "ヶ")


def station_name_map(entities: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in entities.get("Station") or []:
        if not isinstance(row, dict):
            continue
        station_id = str(row.get("owl:sameAs") or "")
        title = row.get("dc:title")
        if not title and isinstance(row.get("odpt:stationTitle"), dict):
            title = row["odpt:stationTitle"].get("ja")
        if station_id and title:
            result[station_id] = normalize_station_name(title)
    return result


def toei_stop_events(
    station_ids: list[str],
    id_to_name: dict[str, str],
    stops: list[list[Any]],
) -> dict[str, set[tuple[str, int]]]:
    result: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for stop in stops:
        if not isinstance(stop, list) or len(stop) < 3:
            continue
        station_index, arrival, departure = stop[0], stop[1], stop[2]
        if not isinstance(station_index, int) or not (0 <= station_index < len(station_ids)):
            continue
        station_id = station_ids[station_index]
        station_name = id_to_name.get(station_id)
        if not station_name:
            continue
        if isinstance(arrival, int):
            result[station_name].add(("arrival", arrival))
        if isinstance(departure, int):
            result[station_name].add(("departure", departure))
    return result


def network_stop_events(stops: list[list[Any]]) -> dict[str, set[tuple[str, int]]]:
    """Network stop schema includes canonical Japanese station name at index 5."""
    result: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for stop in stops:
        if not isinstance(stop, list) or len(stop) < 6:
            continue
        _station_index, arrival, departure, _operator_index, _railway, station_name = stop[:6]
        station_name = normalize_station_name(station_name)
        if not station_name:
            continue
        if isinstance(arrival, int):
            result[station_name].add(("arrival", arrival))
        if isinstance(departure, int):
            result[station_name].add(("departure", departure))
    return result


def matching_station_count(
    left: dict[str, set[tuple[str, int]]],
    right: dict[str, set[tuple[str, int]]],
) -> int:
    count = 0
    for station_name in left.keys() & right.keys():
        if left[station_name] & right[station_name]:
            count += 1
    return count


def main() -> int:
    toei = load(TOEI_PATH)
    toei_entities = load(TOEI_ENTITIES_PATH)
    network = load(NETWORK_PATH)

    assert toei.get("railway") == "odpt.Railway:Toei.Asakusa"
    assert len(toei.get("trips") or []) == 1260, "unexpected Asakusa source-trip count"

    toei_stations = list(toei.get("stations") or [])
    toei_calendars = list(toei.get("calendars") or [])
    id_to_name = station_name_map(toei_entities)
    missing_station_names = [station_id for station_id in toei_stations if station_id not in id_to_name]
    assert not missing_station_names, f"missing Toei station titles: {missing_station_names}"

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
                "events": network_stop_events(stops or []),
                "sourceTripId": source_trip_id,
                "railwayPath": railway_path or [],
            }
        )

    exact = 0
    ambiguous = 0
    one_station_only = 0
    no_exact_match = 0
    no_same_number_candidate = 0
    unresolved_rows: list[dict[str, Any]] = []
    matched_non_keisei_path = 0
    match_histogram: Counter[int] = Counter()

    for trip in toei.get("trips") or []:
        cal_index, _train_type, train_number, stops, destination, train_id, timetable_id = trip[:7]
        cal = calendar_key(toei_calendars[cal_index])
        key = (cal, str(train_number or ""))
        events = toei_stop_events(toei_stations, id_to_name, stops or [])
        candidates = network_by_key.get(key, [])
        if not candidates:
            no_same_number_candidate += 1

        scored = [(matching_station_count(events, candidate["events"]), candidate) for candidate in candidates]
        best = max((score for score, _candidate in scored), default=0)
        winners = [candidate for score, candidate in scored if score == best and score >= 2]
        match_histogram[best] += 1

        if len(winners) == 1:
            exact += 1
            path = winners[0].get("railwayPath") or []
            if not any(str(railway).startswith("odpt.Railway:Keisei.") for railway in path):
                matched_non_keisei_path += 1
            continue

        if len(winners) > 1:
            ambiguous += 1
            reason = "multiple-exact-candidates"
        elif best == 1:
            one_station_only += 1
            reason = "only-one-shared-station-time"
        else:
            no_exact_match += 1
            reason = "no-two-station-exact-match"

        unresolved_rows.append(
            {
                "calendar": cal,
                "trainNumber": train_number,
                "reason": reason,
                "sameNumberCandidates": len(candidates),
                "matchingStations": best,
                "destination": destination,
                "trainId": train_id,
                "timetableId": timetable_id,
            }
        )

    total = len(toei.get("trips") or [])
    unresolved = ambiguous + one_station_only + no_exact_match
    report = {
        "version": 2,
        "definition": "Asakusa trip is represented only by same calendar + same published train number + exact time match at >=2 shared physical station names.",
        "toeiAsakusaExactTrips": total,
        "representedInKeiseiLedNetwork": exact,
        "unresolvedOrMissing": unresolved,
        "noSameTrainNumberCandidate": no_same_number_candidate,
        "ambiguous": ambiguous,
        "oneStationEvidenceOnly": one_station_only,
        "noExactMatch": no_exact_match,
        "representedWithoutKeiseiInRailwayPath": matched_non_keisei_path,
        "bestMatchingStationHistogram": {str(key): value for key, value in sorted(match_histogram.items())},
        "sampleUnresolved": unresolved_rows[:40],
        "policy": {
            "stationIdsArePhysicalIdentity": False,
            "trainNumberAloneMayMatch": False,
            "destinationAloneMayMatch": False,
            "timeProximityMayMatch": False,
            "minimumExactSharedStations": 2,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    assert exact + unresolved == total
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
