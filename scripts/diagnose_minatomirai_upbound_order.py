#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

RAW = Path("data/transit/yokohama-minatomirai/official-upbound-departures.json")
OUT = Path("data/transit/yokohama-minatomirai/upbound-order-diagnostics.json")
WEEKDAY = "odpt.Calendar:Weekday"
HOLIDAY = "odpt.Calendar:SaturdayHoliday"


def minute(value: str) -> int:
    h, m = map(int, value.split(":"))
    return h * 60 + m


def fmt(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def boards(payload: dict) -> dict[tuple[str, str], list[int]]:
    return {
        (row["stationTitle"], row["calendar"]): [minute(x) for x in row["departures"]]
        for row in payload["boards"]
    }


def ordered_match(upstream: list[int], downstream: list[int], lo: int, hi: int, target: int):
    """Maximum-cardinality, order-preserving match.

    No overtaking means any valid solution must be a monotone subsequence.
    The first score component maximizes matched trains.  The second only
    breaks ties by preferring the ordinary running-time band around target.
    """
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
                    candidate = (state[0] + 1, state[1] - abs(delta - target))
                    if candidate > dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = candidate
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


def neighborhood(values: list[int], index: int, radius: int = 3) -> list[dict]:
    return [
        {"index": i, "time": fmt(values[i])}
        for i in range(max(0, index - radius), min(len(values), index + radius + 1))
    ]


def diagnose_calendar(b: dict, calendar: str) -> dict:
    moto = b[("元町・中華街", calendar)]
    nihon = b[("日本大通り", calendar)]
    basha = b[("馬車道", calendar)]
    mina = b[("みなとみらい", calendar)]
    shin = b[("新高島", calendar)]

    # Motomachi-Chukagai and Minatomirai are the all-train anchors.  A broad
    # 3..10 minute band deliberately avoids assuming a train type here.
    mm_map, mm_extra = ordered_match(moto, mina, 3, 10, 6)
    matched_deltas = [mina[j] - moto[i] for i, j in mm_map.items()]
    delta_hist = {}
    for delta in matched_deltas:
        delta_hist[str(delta)] = delta_hist.get(str(delta), 0) + 1

    missing_master = []
    for i in range(len(moto)):
        if i in mm_map:
            continue
        prev_match = next((k for k in range(i - 1, -1, -1) if k in mm_map), None)
        next_match = next((k for k in range(i + 1, len(moto)) if k in mm_map), None)
        missing_master.append({
            "trainIndex": i,
            "motomachi": fmt(moto[i]),
            "previousMatchedTrain": None if prev_match is None else {
                "trainIndex": prev_match,
                "motomachi": fmt(moto[prev_match]),
                "minatomirai": fmt(mina[mm_map[prev_match]]),
            },
            "nextMatchedTrain": None if next_match is None else {
                "trainIndex": next_match,
                "motomachi": fmt(moto[next_match]),
                "minatomirai": fmt(mina[mm_map[next_match]]),
            },
            "motomachiWindow": neighborhood(moto, i),
        })

    extra_rows = [
        {"rowIndex": j, "minatomirai": fmt(mina[j]), "window": neighborhood(mina, j)}
        for j in mm_extra
    ]

    # These two boards should represent the same stopping-train subsequence.
    middle_pair_anomalies = []
    if len(nihon) == len(basha):
        for idx, (n, ba) in enumerate(zip(nihon, basha)):
            delta = ba - n
            if not 1 <= delta <= 4:
                middle_pair_anomalies.append({
                    "rowIndex": idx,
                    "nihonOdori": fmt(n),
                    "bashamichi": fmt(ba),
                    "delta": delta,
                })

    # Shin-Takashima is another forward subsequence, using Minatomirai raw for
    # first-pass diagnostics only.  Final placement will use reconstructed Mina.
    shin_map, shin_extra = ordered_match(mina, shin, 1, 4, 2)

    return {
        "masterCount": len(moto),
        "rawMinatomiraiCount": len(mina),
        "matchedMinatomiraiCount": len(mm_map),
        "missingMasterCount": len(missing_master),
        "extraMinatomiraiRawCount": len(extra_rows),
        "runningTimeHistogramMinutes": delta_hist,
        "missingMaster": missing_master,
        "extraMinatomiraiRaw": extra_rows,
        "nihonOdoriCount": len(nihon),
        "bashamichiCount": len(basha),
        "middleBoardsSameCount": len(nihon) == len(basha),
        "middlePairAnomalies": middle_pair_anomalies,
        "shintakashimaRawCount": len(shin),
        "shintakashimaMatchedToRawMinatomirai": len(shin_map),
        "shintakashimaExtraRaw": [
            {"rowIndex": j, "time": fmt(shin[j])}
            for j in shin_extra
        ],
        "minatomiraiMapping": [
            {
                "trainIndex": i,
                "motomachi": fmt(moto[i]),
                "rawRowIndex": j,
                "minatomirai": fmt(mina[j]),
                "delta": mina[j] - moto[i],
            }
            for i, j in sorted(mm_map.items())
        ],
    }


def main() -> int:
    payload = json.loads(RAW.read_text(encoding="utf-8"))
    b = boards(payload)
    result = {
        "version": 1,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "method": "fixed train order; Motomachi-Chukagai is the master sequence",
        "calendars": {
            HOLIDAY: diagnose_calendar(b, HOLIDAY),
            WEEKDAY: diagnose_calendar(b, WEEKDAY),
        },
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        cal: {
            key: value
            for key, value in data.items()
            if key in {
                "masterCount", "rawMinatomiraiCount", "matchedMinatomiraiCount",
                "missingMasterCount", "extraMinatomiraiRawCount", "nihonOdoriCount",
                "bashamichiCount", "middleBoardsSameCount", "shintakashimaRawCount",
                "shintakashimaMatchedToRawMinatomirai"
            }
        }
        for cal, data in result["calendars"].items()
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
