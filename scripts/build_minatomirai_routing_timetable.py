#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path("data/transit/yokohama-minatomirai")
DOWN = BASE / "downbound-trips-candidate.json"
UP_CANDIDATE = BASE / "upbound-trips-candidate.json"
UP_RAW = BASE / "official-upbound-departures.json"
UP_SUPPLEMENT = BASE / "verified-upbound-supplement-20260314.json"
OUT_TABLE = BASE / "timetables/minatomirai.json"
OUT_INDEX = BASE / "timetable-index.json"
ENTITIES = BASE / "entities.json"
MANIFEST = Path("data/transit/manifest.json")

RAILWAY = "manual.Railway:YokohamaMinatomirai.Minatomirai"
WEEKDAY = "odpt.Calendar:Weekday"
HOLIDAY = "odpt.Calendar:SaturdayHoliday"
OUTBOUND = "odpt.RailDirection:Outbound"
INBOUND = "odpt.RailDirection:Inbound"
CALENDARS = [WEEKDAY, HOLIDAY]
DIRECTIONS = [OUTBOUND, INBOUND]
STATION_NAMES = ["横浜", "新高島", "みなとみらい", "馬車道", "日本大通り", "元町・中華街"]
STATION_IDS = [f"manual.Station:yokohama-minatomirai.{name}" for name in STATION_NAMES]
STATION_INDEX = {name: i for i, name in enumerate(STATION_NAMES)}
TYPE_IDS = [
    "manual.TrainType:YokohamaMinatomirai.Local",
    "manual.TrainType:YokohamaMinatomirai.Express",
    "manual.TrainType:YokohamaMinatomirai.Fast",
]
TYPE_TITLES = ["各駅停車", "急行", "特急系"]
DESTINATIONS = [STATION_IDS[-1], STATION_IDS[0]]
JST = timezone(timedelta(hours=9))


def to_minute(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def fmt(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def flatten_rows(rows: dict) -> list[int]:
    result: list[int] = []
    for raw_hour, minutes in sorted(rows.items(), key=lambda item: int(item[0])):
        hour = int(raw_hour)
        result.extend(hour * 60 + int(minute) for minute in minutes)
    return result


def raw_board_map(payload: dict) -> dict[tuple[str, str], list[int]]:
    return {
        (row["stationTitle"], row["calendar"]): [to_minute(value) for value in row["departures"]]
        for row in payload["boards"]
    }


def classify_type(stops: list[dict]) -> int:
    names = {stop["station"] for stop in stops}
    if "新高島" in names:
        return 0
    if "馬車道" in names or "日本大通り" in names:
        return 1
    return 2


def assert_strict(stops: list[dict], label: str) -> None:
    values = [to_minute(stop["departure"]) for stop in stops if stop.get("departure")]
    if any(a >= b for a, b in zip(values, values[1:])):
        raise RuntimeError(f"non-monotonic train {label}: {stops}")


def dp_map_single(master: list[int], observed: list[int], allowed: set[int]) -> dict[int, int]:
    """Map Shin-Takashima stops to Minatomirai trains without ever changing order."""
    n = len(master)
    inf = 10**9
    parents: list[list[int]] = []
    previous = [inf] * n
    for row_index, value in enumerate(observed):
        current = [inf] * n
        parent = [-1] * n
        prefix_cost = inf
        prefix_index = -1
        for train_index in range(n):
            if row_index > 0 and train_index > 0 and previous[train_index - 1] < prefix_cost:
                prefix_cost = previous[train_index - 1]
                prefix_index = train_index - 1
            delta = value - master[train_index]
            if train_index not in allowed or not 1 <= delta <= 4:
                continue
            own = abs(delta - 2)
            if row_index == 0:
                current[train_index] = own
            elif prefix_index >= 0:
                current[train_index] = prefix_cost + own
                parent[train_index] = prefix_index
        if min(current) >= inf:
            raise RuntimeError(f"cannot order-map Shin-Takashima row {row_index} {fmt(value)}")
        parents.append(parent)
        previous = current
    end = min(range(n), key=lambda i: previous[i])
    result: dict[int, int] = {}
    for row_index in range(len(observed) - 1, -1, -1):
        result[end] = observed[row_index]
        if row_index:
            end = parents[row_index][end]
            if end < 0:
                raise RuntimeError("broken Shin-Takashima DP backtrack")
    return result


def fit_middle(moto: int, mina: int, nihon: int, basha_observed: int) -> tuple[int, int] | None:
    if not (moto < nihon < mina):
        return None
    if nihon - moto > 4 or mina - nihon > 5:
        return None
    candidates = [
        basha for basha in range(nihon + 1, mina)
        if basha - nihon <= 3 and mina - basha <= 3
    ]
    if not candidates:
        return None
    basha = min(candidates, key=lambda value: (abs(value - basha_observed), value))
    return basha, abs(basha - basha_observed)


def dp_map_middle(master_moto: list[int], master_mina: list[int], nihon: list[int], basha: list[int]) -> tuple[dict[int, tuple[int, int]], list[dict]]:
    """Attach the equal-length Nihon-odori/Bashamichi rows as a forward subsequence.

    Nihon-odori is direct-PDF verified for the holiday board. Bashamichi remains
    the official artwork reading; only a cell that cannot physically fit between
    the two neighbouring verified times is corrected to the closest feasible
    minute. No train order is ever swapped.
    """
    if len(nihon) != len(basha):
        raise RuntimeError(f"middle-board count mismatch {len(nihon)} != {len(basha)}")
    rows = len(nihon)
    trains = len(master_moto)
    inf = 10**9
    previous = [inf] * trains
    parents: list[list[int]] = []
    fits: list[list[tuple[int, int] | None]] = []
    for row_index in range(rows):
        current = [inf] * trains
        parent = [-1] * trains
        row_fits: list[tuple[int, int] | None] = [None] * trains
        prefix_cost = inf
        prefix_index = -1
        for train_index in range(trains):
            if row_index > 0 and train_index > 0 and previous[train_index - 1] < prefix_cost:
                prefix_cost = previous[train_index - 1]
                prefix_index = train_index - 1
            fitted = fit_middle(master_moto[train_index], master_mina[train_index], nihon[row_index], basha[row_index])
            row_fits[train_index] = fitted
            if fitted is None:
                continue
            _, correction = fitted
            if row_index == 0:
                current[train_index] = correction
            elif prefix_index >= 0:
                current[train_index] = prefix_cost + correction
                parent[train_index] = prefix_index
        if min(current) >= inf:
            raise RuntimeError(f"cannot order-map middle row {row_index}: {fmt(nihon[row_index])}/{fmt(basha[row_index])}")
        fits.append(row_fits)
        parents.append(parent)
        previous = current
    end = min(range(trains), key=lambda i: previous[i])
    result: dict[int, tuple[int, int]] = {}
    corrections: list[dict] = []
    for row_index in range(rows - 1, -1, -1):
        fitted = fits[row_index][end]
        if fitted is None:
            raise RuntimeError("broken middle DP fit")
        corrected_basha, correction = fitted
        result[end] = (nihon[row_index], corrected_basha)
        if correction:
            corrections.append({
                "rowIndex": row_index,
                "trainIndex": end,
                "nihonOdori": fmt(nihon[row_index]),
                "bashamichiObserved": fmt(basha[row_index]),
                "bashamichiCorrected": fmt(corrected_basha),
                "correctionMinutes": correction,
            })
        if row_index:
            end = parents[row_index][end]
            if end < 0:
                raise RuntimeError("broken middle DP backtrack")
    corrections.reverse()
    return result, corrections


def make_up_weekday(candidate: dict, exact_shin: list[int]) -> tuple[list[dict], dict]:
    source = candidate["calendars"][WEEKDAY]
    if source["masterTrainCount"] != 298 or source["middleMappedCount"] != 266 or source["physicalErrors"]:
        raise RuntimeError("weekday upbound candidate is not in the verified state")
    trips = []
    middle_indices = set()
    mina = []
    for trip in source["trips"]:
        stops = [dict(stop) for stop in trip["stops"] if stop["station"] != "新高島"]
        by_name = {stop["station"]: stop for stop in stops}
        if "馬車道" in by_name:
            middle_indices.add(int(trip["trainIndex"]))
        mina.append(to_minute(by_name["みなとみらい"]["departure"]))
        trips.append({"trainIndex": int(trip["trainIndex"]), "calendar": WEEKDAY, "stops": stops})
    shin_map = dp_map_single(mina, exact_shin, middle_indices)
    if len(shin_map) != 159:
        raise RuntimeError(f"weekday Shin-Takashima map count {len(shin_map)} != 159")
    for trip in trips:
        index = trip["trainIndex"]
        if index not in shin_map:
            continue
        stops = trip["stops"]
        position = next(i for i, stop in enumerate(stops) if stop["station"] == "みなとみらい")
        stops.insert(position + 1, {"station": "新高島", "departure": fmt(shin_map[index]), "source": "official-pdf-direct"})
        # Upbound order is Motomachi -> ... -> Minatomirai -> Shin-Takashima -> Yokohama.
        stops.sort(key=lambda stop: -STATION_INDEX[stop["station"]])
        assert_strict(stops, f"up weekday {index}")
    return trips, {"master": 298, "middle": len(middle_indices), "shintakashima": len(shin_map)}


def make_up_holiday(raw: dict, supplement: dict, exact_shin: list[int], exact_nihon: list[int]) -> tuple[list[dict], dict]:
    boards = raw_board_map(raw)
    moto = list(boards[("元町・中華街", HOLIDAY)])
    mina = list(boards[("みなとみらい", HOLIDAY)])
    basha = list(boards[("馬車道", HOLIDAY)])
    if len(moto) != 275 or len(mina) != 275 or len(basha) != 212 or len(exact_nihon) != 212:
        raise RuntimeError(f"holiday source counts changed: moto={len(moto)} mina={len(mina)} basha={len(basha)} nihon={len(exact_nihon)}")
    applied = []
    for item in supplement["masterDepartureOverrides"]:
        if item["calendar"] != HOLIDAY or item["station"] != "元町・中華街":
            continue
        index = int(item["trainIndex"])
        before = to_minute(item["from"])
        after = to_minute(item["to"])
        if moto[index] != before:
            raise RuntimeError(f"holiday master override source changed at {index}: {fmt(moto[index])} != {item['from']}")
        moto[index] = after
        applied.append(item)
    if any(a >= b for a, b in zip(moto, moto[1:])):
        raise RuntimeError("corrected holiday Motomachi board is not strictly ordered")
    bad_master = [
        (i, fmt(m), fmt(mm), mm - m)
        for i, (m, mm) in enumerate(zip(moto, mina))
        if not 3 <= mm - m <= 8
    ]
    if bad_master:
        raise RuntimeError(f"holiday master/minatomirai anomalies remain: {bad_master[:10]}")

    middle_map, corrections = dp_map_middle(moto, mina, exact_nihon, basha)
    if len(middle_map) != 212:
        raise RuntimeError(f"holiday middle map {len(middle_map)} != 212")
    middle_indices = set(middle_map)
    shin_map = dp_map_single(mina, exact_shin, middle_indices)
    if len(shin_map) != 149:
        raise RuntimeError(f"holiday Shin-Takashima map {len(shin_map)} != 149")

    trips = []
    for index, departure in enumerate(moto):
        stops = [{"station": "元町・中華街", "departure": fmt(departure), "source": "official-board-verified"}]
        if index in middle_map:
            nihon, basha_value = middle_map[index]
            stops.append({"station": "日本大通り", "departure": fmt(nihon), "source": "official-pdf-direct"})
            stops.append({"station": "馬車道", "departure": fmt(basha_value), "source": "official-board-order-repaired" if any(c["trainIndex"] == index for c in corrections) else "official-board"})
        stops.append({"station": "みなとみらい", "departure": fmt(mina[index]), "source": "official-board"})
        if index in shin_map:
            stops.append({"station": "新高島", "departure": fmt(shin_map[index]), "source": "official-pdf-direct"})
        stops.sort(key=lambda stop: -STATION_INDEX[stop["station"]])
        assert_strict(stops, f"up holiday {index}")
        trips.append({"trainIndex": index, "calendar": HOLIDAY, "stops": stops})
    return trips, {
        "master": len(trips),
        "middle": len(middle_map),
        "shintakashima": len(shin_map),
        "masterOverrides": applied,
        "bashamichiCorrections": corrections,
        "maxBashamichiCorrection": max((item["correctionMinutes"] for item in corrections), default=0),
    }


def add_terminal_and_encode(trip: dict, direction: str) -> tuple[int, int, list[list[int | None]], list[tuple[str, int]]]:
    stops = [dict(stop) for stop in trip["stops"]]
    assert_strict(stops, f"pre-terminal {direction} {trip['trainIndex']}")
    train_type = classify_type(stops)
    observed_departures = [(stop["station"], to_minute(stop["departure"])) for stop in stops]
    if direction == OUTBOUND:
        last = stops[-1]
        last_minute = to_minute(last["departure"])
        terminal_arrival = last_minute + (2 if last["station"] == "日本大通り" else 4)
        terminal = "元町・中華街"
        direction_index = 0
        destination_index = 0
    else:
        by_name = {stop["station"]: stop for stop in stops}
        if "新高島" in by_name:
            terminal_arrival = to_minute(by_name["新高島"]["departure"]) + 2
        else:
            terminal_arrival = to_minute(by_name["みなとみらい"]["departure"]) + 3
        terminal = "横浜"
        direction_index = 1
        destination_index = 1
    encoded = []
    for index, stop in enumerate(stops):
        minute = to_minute(stop["departure"])
        encoded.append([STATION_INDEX[stop["station"]], None if index == 0 else minute, minute])
    encoded.append([STATION_INDEX[terminal], terminal_arrival, None])
    times = [row[2] if row[2] is not None else row[1] for row in encoded]
    if any(a is None or b is None or int(a) >= int(b) for a, b in zip(times, times[1:])):
        raise RuntimeError(f"encoded terminal order failure {direction} {trip['trainIndex']} {encoded}")
    return train_type, destination_index, encoded, observed_departures


def main() -> int:
    down = json.loads(DOWN.read_text(encoding="utf-8"))
    up_candidate = json.loads(UP_CANDIDATE.read_text(encoding="utf-8"))
    up_raw = json.loads(UP_RAW.read_text(encoding="utf-8"))
    supplement = json.loads(UP_SUPPLEMENT.read_text(encoding="utf-8"))

    exact_shin = {
        calendar: flatten_rows(supplement["exactBoards"]["新高島"][calendar])
        for calendar in CALENDARS
    }
    if len(exact_shin[WEEKDAY]) != 159 or len(exact_shin[HOLIDAY]) != 149:
        raise RuntimeError("verified Shin-Takashima counts changed")
    exact_nihon_holiday = flatten_rows(supplement["exactBoards"]["日本大通り"][HOLIDAY])
    if len(exact_nihon_holiday) != 212:
        raise RuntimeError("verified Nihon-odori holiday count changed")

    up_weekday, up_weekday_summary = make_up_weekday(up_candidate, exact_shin[WEEKDAY])
    up_holiday, up_holiday_summary = make_up_holiday(up_raw, supplement, exact_shin[HOLIDAY], exact_nihon_holiday)

    source_trips: list[tuple[str, dict]] = []
    expected_down = {WEEKDAY: 297, HOLIDAY: 274}
    for calendar in (WEEKDAY, HOLIDAY):
        item = down["calendars"][calendar]
        if item["masterTrainCount"] != expected_down[calendar] or item["physicalErrorCount"]:
            raise RuntimeError(f"downbound source not verified for {calendar}")
        source_trips.extend((OUTBOUND, trip) for trip in item["trips"])
    source_trips.extend((INBOUND, trip) for trip in up_weekday)
    source_trips.extend((INBOUND, trip) for trip in up_holiday)
    if len(source_trips) != 1144:
        raise RuntimeError(f"expected 1144 trains, got {len(source_trips)}")

    inferred_trips = []
    board_rows: dict[tuple[int, int, int], list[list[int]]] = {}
    inferred_connections = 0
    for direction, trip in source_trips:
        calendar_index = CALENDARS.index(trip["calendar"])
        train_type, destination_index, encoded, observed = add_terminal_and_encode(trip, direction)
        direction_index = DIRECTIONS.index(direction)
        inferred_trips.append([calendar_index, direction_index, train_type, destination_index, 95, encoded])
        inferred_connections += max(0, len(encoded) - 1)
        for station_name, minute in observed:
            key = (STATION_INDEX[station_name], calendar_index, direction_index)
            board_rows.setdefault(key, []).append([minute, train_type, destination_index])

    boards = []
    for (station_index, calendar_index, direction_index), rows in sorted(board_rows.items()):
        rows.sort(key=lambda row: (row[0], row[1], row[2]))
        deduped = []
        for row in rows:
            if row not in deduped:
                deduped.append(row)
        boards.append([station_index, calendar_index, direction_index, deduped])
    departure_count = sum(len(board[3]) for board in boards)

    edge_minutes = []
    for a, b, minutes in [(0, 1, 2), (1, 2, 2), (2, 3, 2), (3, 4, 1), (4, 5, 2)]:
        edge_minutes.append([a, b, minutes])
        edge_minutes.append([b, a, minutes])

    table = {
        "version": 2,
        "railway": RAILWAY,
        "timeBasis": "station-departure-only",
        "stations": STATION_IDS,
        "calendars": CALENDARS,
        "directions": DIRECTIONS,
        "trainTypes": TYPE_IDS,
        "destinations": DESTINATIONS,
        "destinationAuthoritative": False,
        "destinationBasis": "line-local-placeholder",
        "order": STATION_IDS,
        "ascendingDirection": OUTBOUND,
        "descendingDirection": INBOUND,
        "boards": boards,
        "inferredTrips": inferred_trips,
        "edgeMinutes": edge_minutes,
        "typeDurations": [],
        "sourceMetadata": {
            "effectiveFrom": "2026-03-14",
            "source": "Yokohama Minatomirai Railway official timetables",
            "method": "fixed train order; no overtaking or intermediate turn-back; direct-PDF corrections replace OCR artifacts",
            "terminalArrivalBasis": "estimated from adjacent-station running time because terminal arrival is not printed on station departure boards",
        },
    }
    OUT_TABLE.parent.mkdir(parents=True, exist_ok=True)
    OUT_TABLE.write_text(json.dumps(table, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    index = {
        "version": 1,
        "lines": {
            RAILWAY: {
                "file": "timetables/minatomirai.json",
                "trips": 0,
                "connections": 0,
                "inferredTrips": len(inferred_trips),
                "inferredConnections": inferred_connections,
                "departures": departure_count,
                "source": "station-timetable",
            }
        },
    }
    OUT_INDEX.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    entities = json.loads(ENTITIES.read_text(encoding="utf-8"))
    existing_types = {item.get("owl:sameAs") for item in entities.get("TrainType", [])}
    train_types = list(entities.get("TrainType", []))
    for type_id, title in zip(TYPE_IDS, TYPE_TITLES):
        if type_id not in existing_types:
            train_types.append({
                "dc:title": title,
                "owl:sameAs": type_id,
                "odpt:operator": "odpt.Operator:Minatomirai",
                "odpt:trainTypeTitle": {"ja": title},
            })
    entities["TrainType"] = train_types
    ENTITIES.write_text(json.dumps(entities, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    operator = manifest["operators"]["yokohama-minatomirai"]
    operator.update({
        "timetableStatus": "departure-only",
        "stationTimetables": len(boards),
        "trainTimetables": 0,
        "timetableLines": 1,
        "timetableConnections": 0,
        "inferredConnections": inferred_connections,
        "departures": departure_count,
        "timetableSource": "Yokohama Minatomirai Railway official timetable / 2026-03-14 revision",
        "timetableBuiltAt": datetime.now(JST).isoformat(timespec="seconds"),
    })
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    summary = {
        "trains": len(inferred_trips),
        "downbound": {"weekday": 297, "holiday": 274},
        "upbound": {"weekday": up_weekday_summary, "holiday": up_holiday_summary},
        "boards": len(boards),
        "departures": departure_count,
        "inferredConnections": inferred_connections,
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if up_holiday_summary["maxBashamichiCorrection"] > 10:
        raise RuntimeError(f"holiday Bashamichi correction unexpectedly large: {up_holiday_summary['maxBashamichiCorrection']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
