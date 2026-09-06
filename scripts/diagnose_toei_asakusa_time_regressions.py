#!/usr/bin/env python3
"""Print exact Toei Asakusa trips whose raw timetable times decrease."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("data/transit/toei/timetables/899209dea5fc3a.json")


def main() -> int:
    payload = json.loads(PATH.read_text(encoding="utf-8"))
    stations = payload["stations"]
    calendars = payload["calendars"]
    rows = []
    for ordinal, trip in enumerate(payload["trips"]):
        calendar_index, _type_index, train_number, stops, destination, train_id, timetable_id = trip
        events = []
        for station_index, arrival, departure in stops:
            station = stations[int(station_index)]
            if arrival is not None:
                events.append({"stationIndex": station_index, "station": station, "kind": "arrival", "time": int(arrival)})
            if departure is not None:
                events.append({"stationIndex": station_index, "station": station, "kind": "departure", "time": int(departure)})
        drops = []
        for left, right in zip(events, events[1:]):
            if right["time"] < left["time"]:
                drops.append({"from": left, "to": right, "dropMinutes": left["time"] - right["time"]})
        if drops:
            rows.append({
                "ordinal": ordinal,
                "calendar": calendars[int(calendar_index)],
                "trainNumber": train_number,
                "trainId": train_id,
                "timetableId": timetable_id,
                "destination": destination,
                "drops": drops,
                "events": events,
            })
    print(json.dumps({"count": len(rows), "trips": rows}, ensure_ascii=False, indent=2))
    if len(rows) != 12:
        raise RuntimeError(f"expected current diagnostic set of 12, got {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
