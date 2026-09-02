#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

RAW = Path("data/transit/yokohama-minatomirai/official-upbound-departures.json")
VERIFIED_MINA = Path("data/transit/yokohama-minatomirai/verified-upbound-minatomirai-20260314.json")
OUT = Path("data/transit/yokohama-minatomirai/upbound-trips-candidate.json")
WEEKDAY = "odpt.Calendar:Weekday"
HOLIDAY = "odpt.Calendar:SaturdayHoliday"


def to_minute(value: str) -> int:
    h, m = map(int, value.split(":"))
    return h * 60 + m


def fmt(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def board_map(payload: dict) -> dict[tuple[str, str], list[int]]:
    return {
        (row["stationTitle"], row["calendar"]): [to_minute(x) for x in row["departures"]]
        for row in payload["boards"]
    }


def verified_weekday_minatomirai() -> list[int]:
    payload = json.loads(VERIFIED_MINA.read_text(encoding="utf-8"))
    values = []
    for raw_hour, minutes in payload["rows"].items():
        hour = int(raw_hour)
        values.extend(hour * 60 + int(value) for value in minutes)
    expected = int(payload["departureCount"])
    if len(values) != expected:
        raise RuntimeError(f"verified Minatomirai count mismatch: {len(values)} != {expected}")
    return values


def map_middle_rows(
    motomachi: list[int],
    minatomirai: list[int],
    nihon: list[int],
    basha: list[int],
) -> tuple[dict[int, int], list[dict]]:
    if len(nihon) != len(basha):
        raise RuntimeError(f"Nihon-odori/Bashamichi counts differ: {len(nihon)} != {len(basha)}")

    mapping: dict[int, int] = {}
    diagnostics: list[dict] = []
    cursor = 0
    for row_index, (n, b) in enumerate(zip(nihon, basha)):
        candidates = []
        for train_index in range(cursor, len(motomachi)):
            m = motomachi[train_index]
            mm = minatomirai[train_index]
            if m < n < b < mm and 1 <= n - m <= 5 and 1 <= mm - b <= 5:
                candidates.append(train_index)
            if m >= n:
                break
        if candidates:
            train_index = candidates[0]
            mapping[train_index] = row_index
            cursor = train_index + 1
            diagnostics.append({
                "rowIndex": row_index,
                "trainIndex": train_index,
                "motomachi": fmt(motomachi[train_index]),
                "nihonOdori": fmt(n),
                "bashamichi": fmt(b),
                "minatomirai": fmt(minatomirai[train_index]),
                "candidateTrainIndexes": candidates,
            })
        else:
            diagnostics.append({
                "rowIndex": row_index,
                "nihonOdori": fmt(n),
                "bashamichi": fmt(b),
                "cursor": cursor,
                "classification": "no-forward-master-candidate",
            })
    return mapping, diagnostics


def map_shintakashima(minatomirai: list[int], shintakashima: list[int]) -> tuple[dict[int, int], list[dict]]:
    mapping: dict[int, int] = {}
    diagnostics: list[dict] = []
    cursor = 0
    for row_index, shin in enumerate(shintakashima):
        candidates = []
        for train_index in range(cursor, len(minatomirai)):
            mm = minatomirai[train_index]
            delta = shin - mm
            if 1 <= delta <= 4:
                candidates.append(train_index)
            if mm >= shin:
                break
        if candidates:
            train_index = candidates[0]
            mapping[train_index] = row_index
            cursor = train_index + 1
            diagnostics.append({
                "rowIndex": row_index,
                "trainIndex": train_index,
                "minatomirai": fmt(minatomirai[train_index]),
                "shintakashima": fmt(shin),
                "candidateTrainIndexes": candidates,
            })
        else:
            diagnostics.append({
                "rowIndex": row_index,
                "shintakashima": fmt(shin),
                "cursor": cursor,
                "classification": "no-forward-master-candidate",
            })
    return mapping, diagnostics


def build_calendar(boards: dict, calendar: str) -> dict:
    motomachi = boards[("元町・中華街", calendar)]
    nihon = boards[("日本大通り", calendar)]
    basha = boards[("馬車道", calendar)]
    raw_minatomirai = boards[("みなとみらい", calendar)]
    minatomirai = verified_weekday_minatomirai() if calendar == WEEKDAY else raw_minatomirai
    shin = boards[("新高島", calendar)]

    if len(motomachi) != len(minatomirai):
        raise RuntimeError(
            f"{calendar}: Motomachi/Minatomirai master count mismatch "
            f"{len(motomachi)} != {len(minatomirai)}"
        )

    master_anomalies = []
    for i, (m, mm) in enumerate(zip(motomachi, minatomirai)):
        delta = mm - m
        if not 3 <= delta <= 10:
            master_anomalies.append({
                "trainIndex": i,
                "motomachi": fmt(m),
                "minatomirai": fmt(mm),
                "delta": delta,
            })

    middle_map, middle_diag = map_middle_rows(motomachi, minatomirai, nihon, basha)
    shin_map, shin_diag = map_shintakashima(minatomirai, shin)
    middle_unmatched = [x for x in middle_diag if x.get("classification")]
    shin_unmatched = [x for x in shin_diag if x.get("classification")]

    trips = []
    physical_errors = []
    for i, m in enumerate(motomachi):
        stops = [{"station": "元町・中華街", "departure": fmt(m), "source": "official-board"}]
        if i in middle_map:
            row = middle_map[i]
            stops.extend([
                {"station": "日本大通り", "departure": fmt(nihon[row]), "source": "official-board"},
                {"station": "馬車道", "departure": fmt(basha[row]), "source": "official-board"},
            ])
        stops.append({
            "station": "みなとみらい",
            "departure": fmt(minatomirai[i]),
            "source": "official-artwork-direct-verification" if calendar == WEEKDAY else "official-board",
        })
        if i in shin_map:
            row = shin_map[i]
            stops.append({"station": "新高島", "departure": fmt(shin[row]), "source": "official-board"})
        mins = [to_minute(stop["departure"]) for stop in stops]
        if any(a >= b for a, b in zip(mins, mins[1:])):
            physical_errors.append({"trainIndex": i, "stops": stops})
        trips.append({"trainIndex": i, "calendar": calendar, "stops": stops})

    return {
        "calendar": calendar,
        "masterTrainCount": len(motomachi),
        "rawMinatomiraiCount": len(raw_minatomirai),
        "effectiveMinatomiraiCount": len(minatomirai),
        "minatomiraiSource": "verified-official-artwork" if calendar == WEEKDAY else "raw-official-artwork-ocr",
        "middleStopCount": len(nihon),
        "middleMappedCount": len(middle_map),
        "shintakashimaStopCount": len(shin),
        "shintakashimaMappedCount": len(shin_map),
        "masterAnomalies": master_anomalies,
        "middleUnmatched": middle_unmatched,
        "shintakashimaUnmatched": shin_unmatched,
        "physicalErrors": physical_errors,
        "middleMappingDiagnostics": middle_diag,
        "shintakashimaMappingDiagnostics": shin_diag,
        "trips": trips,
    }


def main() -> int:
    payload = json.loads(RAW.read_text(encoding="utf-8"))
    boards = board_map(payload)
    calendars = {cal: build_calendar(boards, cal) for cal in (HOLIDAY, WEEKDAY)}
    result = {
        "version": 2,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "direction": "odpt.RailDirection:Inbound",
        "method": "fixed train order; no overtaking or intermediate turn-back; station boards are forward subsequences",
        "calendars": calendars,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        cal: {
            "masterTrainCount": data["masterTrainCount"],
            "rawMinatomiraiCount": data["rawMinatomiraiCount"],
            "effectiveMinatomiraiCount": data["effectiveMinatomiraiCount"],
            "middleStopCount": data["middleStopCount"],
            "middleMappedCount": data["middleMappedCount"],
            "shintakashimaStopCount": data["shintakashimaStopCount"],
            "shintakashimaMappedCount": data["shintakashimaMappedCount"],
            "masterAnomalyCount": len(data["masterAnomalies"]),
            "middleUnmatchedCount": len(data["middleUnmatched"]),
            "shintakashimaUnmatchedCount": len(data["shintakashimaUnmatched"]),
            "physicalErrorCount": len(data["physicalErrors"]),
        }
        for cal, data in calendars.items()
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
