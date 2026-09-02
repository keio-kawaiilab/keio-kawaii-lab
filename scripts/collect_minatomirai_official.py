#!/usr/bin/env python3
from __future__ import annotations

import io
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from PIL import Image

import probe_minatomirai_ocr_v3 as ocr

OUT_DOWN = Path("data/transit/yokohama-minatomirai/official-downbound-departures.json")
OUT_UP = Path("data/transit/yokohama-minatomirai/official-upbound-departures.json")
JST = timezone(timedelta(hours=9))
BASE = "https://www.mm21railway.co.jp/station/timestable/{slug}/{slug}_{suffix}.jpg"

# Official artwork naming uses "bashamichi" for the image asset even though
# some current station-page URLs use "basyamichi".
DOWN_STATIONS = [
    ("横浜", "yokohama", "manual.Station:yokohama-minatomirai.横浜"),
    ("新高島", "shintakashima", "manual.Station:yokohama-minatomirai.新高島"),
    ("みなとみらい", "minatomirai", "manual.Station:yokohama-minatomirai.みなとみらい"),
    ("馬車道", "bashamichi", "manual.Station:yokohama-minatomirai.馬車道"),
    ("日本大通り", "nihonodori", "manual.Station:yokohama-minatomirai.日本大通り"),
]
UP_STATIONS = [
    ("元町・中華街", "motomachi", "manual.Station:yokohama-minatomirai.元町・中華街"),
    ("日本大通り", "nihonodori", "manual.Station:yokohama-minatomirai.日本大通り"),
    ("馬車道", "bashamichi", "manual.Station:yokohama-minatomirai.馬車道"),
    ("みなとみらい", "minatomirai", "manual.Station:yokohama-minatomirai.みなとみらい"),
    ("新高島", "shintakashima", "manual.Station:yokohama-minatomirai.新高島"),
]
CALENDARS = [
    ("weekday", "odpt.Calendar:Weekday", "w"),
    ("saturday-holiday", "odpt.Calendar:SaturdayHoliday", "h"),
]


def flatten(rows: dict[str, list[int]]) -> list[str]:
    result = []
    for raw_hour, minutes in rows.items():
        hour = int(raw_hour)
        for minute in minutes:
            result.append(f"{hour:02d}:{minute:02d}")
    return result


def collect_direction(
    session: requests.Session,
    *,
    stations: list[tuple[str, str, str]],
    calendar_suffix_letter: str,
    direction_id: str,
    destination_id: str,
    output: Path,
    retrieved_at: str,
) -> dict:
    collected = []
    for station_name, slug, station_id in stations:
        for calendar_name, calendar_id, day_prefix in CALENDARS:
            # m = Motomachi-Chukagai bound (down), y = Yokohama/Shibuya bound (up)
            suffix = f"{day_prefix}{calendar_suffix_letter}"
            url = BASE.format(slug=slug, suffix=suffix)
            response = session.get(url, timeout=60)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
            rows, diagnostics = ocr.parse_rows(image)
            departures = flatten(rows)
            # Local-only stations legitimately have fewer departures because
            # express/limited-express services pass without stopping.
            if len(departures) < 100:
                raise RuntimeError(
                    f"implausibly sparse timetable: {station_name} {calendar_name} {direction_id} {len(departures)}"
                )
            if departures != sorted(
                departures,
                key=lambda value: (int(value.split(':')[0]), int(value.split(':')[1])),
            ):
                raise RuntimeError(f"non-monotonic timetable: {station_name} {calendar_name} {direction_id}")
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
                "direction": direction_id,
                "destination": destination_id,
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
            print(
                direction_id,
                station_name,
                calendar_name,
                len(departures),
                repair_count,
                flush=True,
            )

    payload = {
        "version": 2,
        "source": "Yokohama Minatomirai Railway official timetable artwork",
        "retrievedAt": retrieved_at,
        "railway": "manual.Railway:YokohamaMinatomirai.Minatomirai",
        "direction": direction_id,
        "boards": collected,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        output,
        "boards",
        len(collected),
        "departures",
        sum(row["departureCount"] for row in collected),
        flush=True,
    )
    return payload


def main() -> int:
    session = requests.Session()
    session.headers["User-Agent"] = "Keio-Kawaii-Lab timetable collector/2.0"
    retrieved_at = datetime.now(JST).isoformat(timespec="seconds")

    collect_direction(
        session,
        stations=DOWN_STATIONS,
        calendar_suffix_letter="m",
        direction_id="odpt.RailDirection:Outbound",
        destination_id="manual.Station:yokohama-minatomirai.元町・中華街",
        output=OUT_DOWN,
        retrieved_at=retrieved_at,
    )
    collect_direction(
        session,
        stations=UP_STATIONS,
        calendar_suffix_letter="y",
        direction_id="odpt.RailDirection:Inbound",
        destination_id="manual.Station:yokohama-minatomirai.横浜",
        output=OUT_UP,
        retrieved_at=retrieved_at,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
