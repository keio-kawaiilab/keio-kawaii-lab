#!/usr/bin/env python3
"""Measure exact Toei Asakusa representation inside the Keisei-led network.

This audit is intentionally conservative. A Toei trip is considered already
represented only when a Keisei-led network trip has the same service calendar,
the same published train number, and matching published times at at least two
common physical stations. Station IDs are normalized to physical station names
because operator/line-local ODPT IDs may differ for the same station.

Train number, destination, or time proximity alone are never enough.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOEI_PATH = ROOT / "data/transit/toei/timetables/899209dea5fc3a.json"
NETWORK_PATH = ROOT / "data/transit/keisei/timetables/official-network.json"
ENTITY_PATHS = [
    ROOT / "data/transit/keisei/entities.json",
    ROOT / "data/transit/toei/entities.json",
    ROOT / "data/transit/keikyu/entities.json",
]


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
    text = re.sub(r"\s+", "", text)
    aliases = {
        "成田空港(成田第1ターミナル)": "成田空港",
        "空港第2ビル(成田第2・第3ターミナル)": "空港第2ビル",
        "空港第2ビル(成田第2・3ターミナル)": "空港第2ビル",
        "新鎌ケ谷": "新鎌ヶ谷",
        "羽田空港第1・第2ターミナル駅": "羽田空港第1・第2ターミナル",
        "羽田空港第3ターミナル駅": "羽田空港第3ターミナル",
        "逗子・葉山駅": "逗子・葉山",
    }
    return aliases.get(text, text)


def station_name_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in ENTITY_PATHS:
        entities = load(path)
        for row in entities.get("Station") or []:
            if not isinstance(row, dict):
                continue
            station_id = str(row.get("owl:sameAs") or "")
            title: Any = row.get("dc:title")
            station_title = row.get("odpt:stationTitle")
            if isinstance(station_title, dict):
                title = station_title.get("ja") or title
            elif isinstance(station_title, str):
                title = station_title or title
            if station_id and title:
                result[station_id] = normalize_station_name(title)
    return result


def stop_events(
    station_ids: list[str],
    id_to_name: dict[str, str],
    stops: list[list[Any]],
) -> dict[str, set[tuple[str, int]]]:
    result: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for stop in stops:
        if not isinstance(stop, list) or len(stop) < 3:
            continue
        station_index, arrival, departure = stop[:3]
        if not isinstance(station_index, int) or not (0 <= station_index < len(station_ids)):
            continue
        station_name = id_to_name.get(station_ids[station_index])
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
    return sum(
        1
        for station_name in left.keys() & right.keys()
        if left[station_name] & right[station_name]
    )


def railway_path_from_links(links: list[list[Any]], railways: list[str]) -> list[str]:
    result: list[str] = []
    for link in links:
        if not isinstance(link, list):
            continue
        for railway_index in link:
            if not isinstance(railway_index, int) or not (0 <= railway_index < len(railways)):
                continue
            railway = railways[railway_index]
            if not result or result[-1] != railway:
                result.append(railway)
    return result


def main() -> int:
    toei = load(TOEI_PATH)
    network = load(NETWORK_PATH)
    id_to_name = station_name_map()

    assert toei.get("railway") == "odpt.Railway:Toei.Asakusa"
    assert len(toei.get("trips") or []) == 1260, "unexpected Asakusa source-trip count"
    assert network.get("timeBasis") == "train-timetable-network"

    toei_stations = list(toei.get("stations") or [])
    toei_calendars = list(toei.get("calendars") or [])
    network_stations = list(network.get("stations") or [])
    network_calendars = list(network.get("calendars") or [])
    network_railways = list(network.get("railways") or [])

    missing_toei_station_names = [station_id for station_id in toei_stations if station_id not in id_to_name]
    assert not missing_toei_station_names, f"missing Toei station titles: {missing_toei_station_names}"

    # Network schema from build_keisei_network_timetable.py:
    # [calendarIndex, trainTypeIndex, trainNumber, stops, links]
    network_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    parsed_network_trips = 0
    for trip_index, trip in enumerate(network.get("trips") or []):
        if not isinstance(trip, list) or len(trip) < 5:
            continue
        cal_index, _train_type_index, train_number, stops, links = trip[:5]
        if not isinstance(cal_index, int) or not (0 <= cal_index < len(network_calendars)):
            continue
        parsed_network_trips += 1
        key = (calendar_key(network_calendars[cal_index]), str(train_number or ""))
        network_by_key[key].append(
            {
                "index": trip_index,
                "events": stop_events(network_stations, id_to_name, stops or []),
                "railwayPath": railway_path_from_links(links or [], network_railways),
            }
        )

    assert parsed_network_trips == len(network.get("trips") or []), (
        f"network trip schema mismatch: parsed={parsed_network_trips} total={len(network.get('trips') or [])}"
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
        if not isinstance(trip, list) or len(trip) < 7:
            raise RuntimeError(f"unexpected Toei trip schema: {trip!r}")
        cal_index, _train_type, train_number, stops, destination, train_id, timetable_id = trip[:7]
        cal = calendar_key(toei_calendars[cal_index])
        key = (cal, str(train_number or ""))
        events = stop_events(toei_stations, id_to_name, stops or [])
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
        "version": 3,
        "definition": "Asakusa trip is represented only by same calendar + same published train number + exact time match at >=2 shared physical station names.",
        "networkTripsParsed": parsed_network_trips,
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
