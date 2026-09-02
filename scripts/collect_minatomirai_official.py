#!/usr/bin/env python3
from __future__ import annotations

import io
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from PIL import Image

import probe_minatomirai_ocr_v3 as ocr

OUT = Path("data/transit/yokohama-minatomirai/official-downbound-departures.json")
JST = timezone(timedelta(hours=9))
BASE = "https://www.mm21railway.co.jp/station/timestable/{slug}/{slug}_{suffix}.jpg"

STATIONS = [
    ("横浜", "yokohama", "manual.Station:yokohama-minatomirai.横浜"),
    ("新高島", "shintakashima", "manual.Station:yokohama-minatomirai.新高島"),
    ("みなとみらい", "minatomirai", "manual.Station:yokohama-minatomirai.みなとみらい"),
    ("馬車道", "bashamichi", "manual.Station:yokohama-minatomirai.馬車道"),
    ("日本大通り", "nihonodori", "manual.Station:yokohama-minatomirai.日本大通り"),
]
CALENDARS = [
    ("weekday", "odpt.Calendar:Weekday", "wm"),
    ("saturday-holiday", "odpt.Calendar:SaturdayHoliday", "hm"),
]


def flatten(rows: dict[str, list[int]]) -> list[str]:
    result = []
    for raw_hour, minutes in rows.items():
        hour = int(raw_hour)
        for minute in minutes:
            result.append(f"{hour:02d}:{minute:02d}")
    return result


def main() -> int:
    session = requests.Session()
    session.headers["User-Agent"] = "Keio-Kawaii-Lab timetable collector/1.0"
    collected = []
    for station_name, slug, station_id in STATIONS:
        for calendar_name, calendar_id, suffix in CALENDARS:
            url = BASE.format(slug=slug, suffix=suffix)
            response = session.get(url, timeout=60)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
            rows, diagnostics = ocr.parse_rows(image)
            departures = flatten(rows)
            # Local-only stations legitimately have far fewer departures than
            # Yokohama because express services pass without stopping.
            if len(departures) < 100:
                raise RuntimeError(f"implausibly sparse timetable: {station_name} {calendar_name} {len(departures)}")
            if departures != sorted(departures, key=lambda value: (int(value.split(':')[0]), int(value.split(':')[1]))):
                raise RuntimeError(f"non-monotonic timetable: {station_name} {calendar_name}")
            repair_count = int(diagnostics.get("repairCount") or 0)
            if repair_count > len(departures) * 0.55:
                raise RuntimeError(
                    f"OCR repair ratio too high: {station_name} {calendar_name} "
                    f"{repair_count}/{len(departures)}"
                )
            collected.append({
                "station": station_id,
                "stationTitle": station_name,
                "railway": "manual.Railway:YokohamaMinatomirai.Minatomirai",
                "calendar": calendar_id,
                "calendarKey": calendar_name,
                "direction": "odpt.RailDirection:Outbound",
                "destination": "manual.Station:yokohama-minatomirai.元町・中華街",
                "sourceUrl": url,
                "imageSize": list(image.size),
                "departureCount": len(departures),
                "departures": departures,
                "ocrDiagnostics": {
                    "firstX": diagnostics.get("firstX"),
                    "candidateCount": diagnostics.get("candidateCount"),
                    "repairCount": repair_count,
                    "dashCount": diagnostics.get("dashCount"),
                },
            })
            print(station_name, calendar_name, len(departures), repair_count, flush=True)

    payload = {
        "version": 1,
        "source": "Yokohama Minatomirai Railway official timetable artwork",
        "retrievedAt": datetime.now(JST).isoformat(timespec="seconds"),
        "railway": "manual.Railway:YokohamaMinatomirai.Minatomirai",
        "direction": "odpt.RailDirection:Outbound",
        "boards": collected,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("boards", len(collected), "departures", sum(row["departureCount"] for row in collected), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
