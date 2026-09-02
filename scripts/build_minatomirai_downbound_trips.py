#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

RAW = Path("data/transit/yokohama-minatomirai/official-downbound-departures.json")
MINA = Path("data/transit/yokohama-minatomirai/reconstructed-minatomirai-downbound.json")
SHIN = Path("data/transit/yokohama-minatomirai/reconstructed-shintakashima-downbound.json")
OVERRIDES = Path("data/transit/yokohama-minatomirai/verified-overrides-20260314.json")
OUT = Path("data/transit/yokohama-minatomirai/downbound-trips-candidate.json")
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


def apply_direct_board_replacements(boards: dict, overrides: dict) -> list[dict]:
    applied = []
    for item in overrides.get("directBoardReplacements", []):
        key = (item["station"], item["calendar"])
        if key not in boards:
            raise RuntimeError(f"override board not found: {key}")
        before = to_minute(item["from"])
        after = to_minute(item["to"])
        indexes = [i for i, value in enumerate(boards[key]) if value == before]
        if len(indexes) != 1:
            raise RuntimeError(
                f"override must identify exactly one raw cell: {key} {item['from']} -> {item['to']} indexes={indexes}"
            )
        idx = indexes[0]
        boards[key][idx] = after
        if any(a > b for a, b in zip(boards[key], boards[key][1:])):
            raise RuntimeError(f"override broke board order: {key} {item}")
        applied.append({**item, "index": idx})
    return applied


def load_complete_minatomirai(calendar: str, yoko: list[int], overrides: dict) -> tuple[list[int], list[dict]]:
    payload = json.loads(MINA.read_text(encoding="utf-8"))
    values = [to_minute(x) for x in payload["calendars"][calendar]["departures"]]
    if len(values) != len(yoko):
        raise RuntimeError(f"{calendar}: Yokohama/Minatomirai count mismatch {len(yoko)} != {len(values)}")

    applied = []
    for item in overrides.get("masterTrainStopOverrides", []):
        if item["calendar"] != calendar or item["station"] != "みなとみらい":
            continue
        y = to_minute(item["yokohamaDeparture"])
        indexes = [i for i, value in enumerate(yoko) if value == y]
        if len(indexes) != 1:
            raise RuntimeError(
                f"master override must identify one Yokohama train: {calendar} {item['yokohamaDeparture']} indexes={indexes}"
            )
        idx = indexes[0]
        before = values[idx]
        values[idx] = to_minute(item["departure"])
        applied.append({
            "trainIndex": idx,
            "yokohama": fmt(y),
            "before": fmt(before),
            "after": item["departure"],
        })

    if any(a > b for a, b in zip(values, values[1:])):
        raise RuntimeError(f"{calendar}: reconstructed Minatomirai board is not in train order")
    return values, applied


def load_shin(calendar: str) -> dict[int, int]:
    payload = json.loads(SHIN.read_text(encoding="utf-8"))
    item = payload["calendars"][calendar]
    return {
        int(index): to_minute(value)
        for index, value in zip(item["stoppingTrainIndexes"], item["departures"])
    }


def pair_middle_boards(basha: list[int], nihon: list[int]) -> tuple[list[tuple[int, int]], list[dict]]:
    if len(basha) != len(nihon):
        raise RuntimeError(f"Bashamichi/Nihon-odori counts differ: {len(basha)} != {len(nihon)}")
    pairs = []
    anomalies = []
    for idx, (b, n) in enumerate(zip(basha, nihon)):
        delta = n - b
        if not 1 <= delta <= 4:
            anomalies.append({"index": idx, "bashamichi": fmt(b), "nihonOdori": fmt(n), "delta": delta})
        pairs.append((b, n))
    return pairs, anomalies


def fixed_order_subsequence_match(master: list[int], downstream_pairs: list[tuple[int, int]]) -> tuple[dict[int, int], list[dict]]:
    """Attach stopping rows without ever changing train order.

    The Minatomirai line has no overtaking and no intermediate turn-backs here.
    Therefore the Bashamichi/Nihon-odori rows are a subsequence of the complete
    Yokohama/Minatomirai train list. We only move forward through the master
    list. A row may skip express trains, but it can never move backwards or
    swap two trains.
    """
    mapping: dict[int, int] = {}
    diagnostics: list[dict] = []
    cursor = 0

    for row_index, (basha, nihon) in enumerate(downstream_pairs):
        candidates = []
        for train_index in range(cursor, len(master)):
            mina = master[train_index]
            delta = basha - mina
            if 1 <= delta <= 4:
                candidates.append(train_index)
            # Once Minatomirai is already at/after this Bashamichi row,
            # all later master trains are impossible because order never reverses.
            if mina >= basha:
                break

        if not candidates:
            diagnostics.append({
                "rowIndex": row_index,
                "bashamichi": fmt(basha),
                "nihonOdori": fmt(nihon),
                "cursor": cursor,
                "classification": "no-forward-master-candidate",
            })
            continue

        # No overtaking means the earliest physically possible forward train is
        # the only safe assignment. Later candidates remain available to later
        # station rows instead of crossing the order.
        train_index = candidates[0]
        mapping[train_index] = row_index
        diagnostics.append({
            "rowIndex": row_index,
            "trainIndex": train_index,
            "minatomirai": fmt(master[train_index]),
            "bashamichi": fmt(basha),
            "nihonOdori": fmt(nihon),
            "candidateTrainIndexes": candidates,
        })
        cursor = train_index + 1

    return mapping, diagnostics


def build_calendar(boards: dict, calendar: str, overrides: dict) -> dict:
    yoko = boards[("横浜", calendar)]
    mina, mina_overrides = load_complete_minatomirai(calendar, yoko, overrides)
    shin = load_shin(calendar)
    basha = boards[("馬車道", calendar)]
    nihon = boards[("日本大通り", calendar)]

    middle_pairs, middle_anomalies = pair_middle_boards(basha, nihon)
    if middle_anomalies:
        raise RuntimeError(f"{calendar}: Bashamichi/Nihon-odori row-order anomaly: {middle_anomalies[:10]}")

    bmap, mapping_diagnostics = fixed_order_subsequence_match(mina, middle_pairs)
    unmatched_rows = [
        row for row in mapping_diagnostics
        if row.get("classification") == "no-forward-master-candidate"
    ]
    if unmatched_rows:
        raise RuntimeError(f"{calendar}: order-fixed mapping left rows unmatched: {unmatched_rows[:10]}")
    if len(bmap) != len(basha):
        raise RuntimeError(f"{calendar}: mapped {len(bmap)} of {len(basha)} Bashamichi rows")

    b_by_train = {train_index: basha[row_index] for train_index, row_index in bmap.items()}
    n_by_train = {train_index: nihon[row_index] for train_index, row_index in bmap.items()}

    trips = []
    physical_errors = []
    for i, y in enumerate(yoko):
        stops = [{"station": "横浜", "departure": fmt(y), "source": "official-board"}]
        if i in shin:
            stops.append({"station": "新高島", "departure": fmt(shin[i]), "source": "validated-reconstruction"})
        stops.append({"station": "みなとみらい", "departure": fmt(mina[i]), "source": "validated-reconstruction"})
        if i in b_by_train:
            stops.append({"station": "馬車道", "departure": fmt(b_by_train[i]), "source": "official-board"})
            stops.append({"station": "日本大通り", "departure": fmt(n_by_train[i]), "source": "official-board"})

        mins = [to_minute(stop["departure"]) for stop in stops]
        if any(a >= b for a, b in zip(mins, mins[1:])):
            physical_errors.append({"trainIndex": i, "stops": stops})
        trips.append({"trainIndex": i, "calendar": calendar, "stops": stops})

    return {
        "calendar": calendar,
        "masterTrainCount": len(yoko),
        "shintakashimaStopCount": len(shin),
        "bashamichiStopCount": len(basha),
        "nihonOdoriStopCount": len(nihon),
        "bashamichiMappedCount": len(bmap),
        "minatomiraiVerifiedOverrides": mina_overrides,
        "physicalErrorCount": len(physical_errors),
        "physicalErrors": physical_errors[:50],
        "mappingDiagnostics": mapping_diagnostics,
        "trips": trips,
    }


def main() -> int:
    payload = json.loads(RAW.read_text(encoding="utf-8"))
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    boards = board_map(payload)
    direct_applied = apply_direct_board_replacements(boards, overrides)

    calendars = {
        calendar: build_calendar(boards, calendar, overrides)
        for calendar in (HOLIDAY, WEEKDAY)
    }
    result = {
        "version": 3,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "effectiveFrom": overrides.get("effectiveFrom"),
        "direction": "odpt.RailDirection:Outbound",
        "method": "fixed train order; no overtaking or intermediate turn-back; station boards are forward subsequences",
        "verifiedDirectBoardReplacements": direct_applied,
        "calendars": calendars,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "directBoardReplacements": direct_applied,
        "calendars": {
            cal: {
                "masterTrainCount": data["masterTrainCount"],
                "shintakashimaStopCount": data["shintakashimaStopCount"],
                "bashamichiStopCount": data["bashamichiStopCount"],
                "bashamichiMappedCount": data["bashamichiMappedCount"],
                "physicalErrorCount": data["physicalErrorCount"],
                "minatomiraiVerifiedOverrideCount": len(data["minatomiraiVerifiedOverrides"]),
            }
            for cal, data in calendars.items()
        },
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)

    for calendar, data in calendars.items():
        if data["physicalErrorCount"]:
            raise RuntimeError(f"{calendar}: non-monotonic station chain: {data['physicalErrors'][:10]}")
        if data["bashamichiMappedCount"] != data["bashamichiStopCount"]:
            raise RuntimeError(f"{calendar}: not every Bashamichi row was attached")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
