#!/usr/bin/env python3
"""Inspect the four official Sengakuji columns with explicit train numbers but no exact-minute Toei match."""
from __future__ import annotations

import json
from pathlib import Path

TOEI = Path("data/transit/toei/timetables/899209dea5fc3a.json")
TARGETS = {
    "931N": {"calendar": "holiday", "direction": "keikyu-to-toei", "sourceMinute": 582, "targetMinute": 583},
    "1985K": {"calendar": "holiday", "direction": "keikyu-to-toei", "sourceMinute": 1185, "targetMinute": 1185},
    "2033N": {"calendar": "holiday", "direction": "keikyu-to-toei", "sourceMinute": 1265, "targetMinute": 1265},
    "2381K": {"calendar": "holiday", "direction": "keikyu-to-toei", "sourceMinute": 1399, "targetMinute": 1402},
}
SENGAKUJI = "odpt.Station:Toei.Asakusa.Sengakuji"


def main() -> int:
    p = json.loads(TOEI.read_text(encoding="utf-8"))
    stations = p["stations"]
    calendars = p["calendars"]
    sidx = stations.index(SENGAKUJI)
    output = {}
    for number, target in TARGETS.items():
        rows = []
        for ordinal, trip in enumerate(p["trips"]):
            cal_i, _type_i, train_number, stops, destination, train_id, timetable_id = trip
            if str(train_number or "") != number:
                continue
            calendar = str(calendars[int(cal_i)])
            endpoint = []
            for station_index, arrival, departure in stops:
                if int(station_index) == sidx:
                    endpoint.append({
                        "arrival": arrival,
                        "departure": departure,
                        "isFirst": stop_is_first(stops, station_index, arrival, departure),
                        "isLast": stop_is_last(stops, station_index, arrival, departure),
                    })
            rows.append({
                "ordinal": ordinal,
                "calendar": calendar,
                "trainNumber": train_number,
                "trainId": train_id,
                "timetableId": timetableId(timetable_id),
                "destination": destination,
                "firstStation": stations[int(stops[0][0])],
                "lastStation": stations[int(stops[-1][0])],
                "sengakuji": endpoint,
            })
        output[number] = {"official": target, "toeiRows": rows}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    missing = [number for number, row in output.items() if not row["toeiRows"]]
    if missing:
        raise RuntimeError(f"explicit official train numbers absent from Toei mother set: {missing}")
    return 0


def timetableId(value):
    return str(value or "")


def stop_is_first(stops, station_index, arrival, departure):
    first = stops[0]
    return int(first[0]) == int(station_index) and first[1] == arrival and first[2] == departure


def stop_is_last(stops, station_index, arrival, departure):
    last = stops[-1]
    return int(last[0]) == int(station_index) and last[1] == arrival and last[2] == departure


if __name__ == "__main__":
    raise SystemExit(main())
