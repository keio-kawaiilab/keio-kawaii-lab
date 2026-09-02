#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

RAW = Path("data/transit/yokohama-minatomirai/official-downbound-departures.json")
MINA = Path("data/transit/yokohama-minatomirai/reconstructed-minatomirai-downbound.json")
SHIN = Path("data/transit/yokohama-minatomirai/reconstructed-shintakashima-downbound.json")
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


def ordered_match(upstream: list[int], downstream: list[int], lo: int, hi: int, target: int):
    n, m = len(upstream), len(downstream)
    bad = (-10**9, -10**9)
    dp = [[bad] * (m + 1) for _ in range(n + 1)]
    move = [[""] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = (0, 0)
    for i in range(n + 1):
        for j in range(m + 1):
            state = dp[i][j]
            if state == bad:
                continue
            if i < n and state > dp[i + 1][j]:
                dp[i + 1][j] = state
                move[i + 1][j] = "skip_up"
            if j < m and state > dp[i][j + 1]:
                dp[i][j + 1] = state
                move[i][j + 1] = "skip_down"
            if i < n and j < m:
                delta = downstream[j] - upstream[i]
                if lo <= delta <= hi:
                    cand = (state[0] + 1, state[1] - abs(delta - target))
                    if cand > dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = cand
                        move[i + 1][j + 1] = "match"
    mapping = {}
    used_down = set()
    i, j = n, m
    while i > 0 or j > 0:
        mv = move[i][j]
        if mv == "match":
            mapping[i - 1] = j - 1
            used_down.add(j - 1)
            i -= 1
            j -= 1
        elif mv == "skip_up":
            i -= 1
        elif mv == "skip_down":
            j -= 1
        elif i:
            i -= 1
        else:
            j -= 1
    return mapping, [idx for idx in range(m) if idx not in used_down]


def load_complete_minatomirai(calendar: str) -> list[int]:
    payload = json.loads(MINA.read_text(encoding="utf-8"))
    return [to_minute(x) for x in payload["calendars"][calendar]["departures"]]


def load_shin(calendar: str) -> dict[int, int]:
    payload = json.loads(SHIN.read_text(encoding="utf-8"))
    item = payload["calendars"][calendar]
    return {int(index): to_minute(value) for index, value in zip(item["stoppingTrainIndexes"], item["departures"])}


def pair_middle_boards(basha: list[int], nihon: list[int]) -> dict:
    pairs, bad = [], []
    for idx, (b, n) in enumerate(zip(basha, nihon)):
        delta = n - b
        row = {"index": idx, "bashamichi": fmt(b), "nihonOdori": fmt(n), "delta": delta}
        pairs.append(row)
        if not 1 <= delta <= 4:
            bad.append(row)
    return {"sameCount": len(basha) == len(nihon), "pairs": pairs, "anomalies": bad}


def build_calendar(boards, calendar: str) -> dict:
    yoko = boards[("横浜", calendar)]
    mina = load_complete_minatomirai(calendar)
    shin = load_shin(calendar)
    basha = boards[("馬車道", calendar)]
    nihon = boards[("日本大通り", calendar)]
    if len(yoko) != len(mina):
        raise RuntimeError(f"{calendar}: Yokohama/Minatomirai count mismatch {len(yoko)} != {len(mina)}")
    middle = pair_middle_boards(basha, nihon)
    if not middle["sameCount"]:
        raise RuntimeError(f"{calendar}: Bashamichi/Nihon-odori counts differ")

    bmap, b_unmatched = ordered_match(mina, basha, 1, 4, 2)
    b_by_train = {ti: basha[oi] for ti, oi in bmap.items()}
    n_by_train = {ti: nihon[oi] for ti, oi in bmap.items() if oi < len(nihon)}

    trips, physical_errors = [], []
    for i, y in enumerate(yoko):
        stops = [{"station": "横浜", "departure": fmt(y), "source": "official-ocr"}]
        if i in shin:
            stops.append({"station": "新高島", "departure": fmt(shin[i]), "source": "validated-reconstruction"})
        stops.append({"station": "みなとみらい", "departure": fmt(mina[i]), "source": "validated-reconstruction"})
        if i in b_by_train:
            stops.append({"station": "馬車道", "departure": fmt(b_by_train[i]), "source": "official-ocr"})
        if i in n_by_train:
            stops.append({"station": "日本大通り", "departure": fmt(n_by_train[i]), "source": "official-ocr"})
        mins = [to_minute(stop["departure"]) for stop in stops]
        if any(a >= b for a, b in zip(mins, mins[1:])):
            physical_errors.append({"trainIndex": i, "stops": stops})
        trips.append({"trainIndex": i, "calendar": calendar, "stops": stops})

    return {
        "calendar": calendar,
        "masterTrainCount": len(yoko),
        "shintakashimaStopCount": len(shin),
        "bashamichiRawCount": len(basha),
        "nihonOdoriRawCount": len(nihon),
        "bashamichiMatchedCount": len(bmap),
        "bashamichiUnmatchedRaw": [fmt(basha[i]) for i in b_unmatched],
        "middleBoardAnomalies": middle["anomalies"],
        "physicalErrorCount": len(physical_errors),
        "physicalErrors": physical_errors[:50],
        "trips": trips,
    }


def main() -> int:
    payload = json.loads(RAW.read_text(encoding="utf-8"))
    boards = board_map(payload)
    calendars = {calendar: build_calendar(boards, calendar) for calendar in (HOLIDAY, WEEKDAY)}
    result = {
        "version": 2,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "direction": "odpt.RailDirection:Outbound",
        "method": "Yokohama master train order with calendar-independent reconstructed Minatomirai board",
        "calendars": calendars,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {cal: {k: v for k, v in data.items() if k not in ("trips", "physicalErrors")} for cal, data in calendars.items()}
    print(json.dumps(summary, ensure_ascii=False), flush=True)

    for calendar, data in calendars.items():
        if data["middleBoardAnomalies"]:
            raise RuntimeError(f"{calendar}: Bashamichi/Nihon-odori pair anomalies: {data['middleBoardAnomalies'][:10]}")
        if data["physicalErrorCount"]:
            raise RuntimeError(f"{calendar}: non-monotonic station chain: {data['physicalErrors'][:10]}")
        if data["bashamichiMatchedCount"] / max(1, data["bashamichiRawCount"]) < 0.97:
            raise RuntimeError(f"{calendar}: Bashamichi mapping below 97%: {summary[calendar]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
