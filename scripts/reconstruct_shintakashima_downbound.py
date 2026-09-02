#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

RAW = Path("data/transit/yokohama-minatomirai/official-downbound-departures.json")
MINA_RECON = Path("data/transit/yokohama-minatomirai/reconstructed-weekday-minatomirai.json")
OUT = Path("data/transit/yokohama-minatomirai/reconstructed-shintakashima-downbound.json")
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


def candidate_for_train(yoko: int, mina: int, observed: int) -> tuple[int, int] | None:
    # A Shin-Takashima stop must be after Yokohama and before Minatomirai.
    lo = max(yoko + 1, mina - 3)
    hi = min(yoko + 5, mina - 1)
    if lo > hi:
        return None
    minute = min(range(lo, hi + 1), key=lambda value: (abs(value - observed), abs((value - yoko) - 2)))
    correction = abs(minute - observed)
    return minute, correction


def reconstruct(yoko: list[int], mina: list[int], observed: list[int]) -> tuple[list[dict], dict]:
    if len(yoko) != len(mina):
        raise RuntimeError(f"complete adjacent boards must have equal counts: {len(yoko)} != {len(mina)}")
    n, m = len(yoko), len(observed)
    bad = (-10**9, -10**9)
    # Score is (matches, -cost). Skip a Yokohama/Minatomirai train freely
    # because express trains may pass Shin-Takashima. Skipping an observed
    # Shin-Takashima row is allowed only as a last resort and will be detected.
    dp = [[bad] * (m + 1) for _ in range(n + 1)]
    move = [[""] * (m + 1) for _ in range(n + 1)]
    chosen: dict[tuple[int, int], tuple[int, int]] = {}
    dp[0][0] = (0, 0)
    for i in range(n + 1):
        for j in range(m + 1):
            score = dp[i][j]
            if score == bad:
                continue
            if i < n and score > dp[i + 1][j]:
                dp[i + 1][j] = score
                move[i + 1][j] = "skip_train"
            if j < m:
                # Make losing an observed station row much more expensive than
                # a moderate OCR correction, while still permitting diagnosis.
                cand = (score[0], score[1] - 50)
                if cand > dp[i][j + 1]:
                    dp[i][j + 1] = cand
                    move[i][j + 1] = "skip_observed"
            if i < n and j < m:
                result = candidate_for_train(yoko[i], mina[i], observed[j])
                if result is not None:
                    minute, correction = result
                    # Strongly prefer preserving the official OCR minute.
                    travel_penalty = abs((minute - yoko[i]) - 2) + abs((mina[i] - minute) - 2)
                    cost = correction * 10 + travel_penalty
                    cand = (score[0] + 1, score[1] - cost)
                    if cand > dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = cand
                        move[i + 1][j + 1] = "match"
                        chosen[(i + 1, j + 1)] = (minute, correction)

    i, j = n, m
    rows = []
    skipped_observed = []
    while i > 0 or j > 0:
        mv = move[i][j]
        if mv == "match":
            minute, correction = chosen[(i, j)]
            rows.append({
                "trainIndex": i - 1,
                "yokohama": fmt(yoko[i - 1]),
                "observed": fmt(observed[j - 1]),
                "reconstructed": fmt(minute),
                "minatomirai": fmt(mina[i - 1]),
                "correctionMinutes": correction,
            })
            i -= 1
            j -= 1
        elif mv == "skip_train":
            i -= 1
        elif mv == "skip_observed":
            skipped_observed.append(fmt(observed[j - 1]))
            j -= 1
        elif i:
            i -= 1
        else:
            skipped_observed.append(fmt(observed[j - 1]))
            j -= 1
    rows.reverse()
    skipped_observed.reverse()
    corrected = [row for row in rows if row["correctionMinutes"] > 0]
    diagnostics = {
        "completeTrainCount": n,
        "observedStopCount": m,
        "matchedStopCount": len(rows),
        "skippedObserved": skipped_observed,
        "unchangedCount": sum(row["correctionMinutes"] == 0 for row in rows),
        "correctedCount": len(corrected),
        "maxCorrectionMinutes": max((row["correctionMinutes"] for row in rows), default=0),
        "corrections": corrected,
    }
    return rows, diagnostics


def main() -> int:
    payload = json.loads(RAW.read_text(encoding="utf-8"))
    boards = board_map(payload)
    weekday_mina = [to_minute(x) for x in json.loads(MINA_RECON.read_text(encoding="utf-8"))["departures"]]

    results = {}
    for calendar in (HOLIDAY, WEEKDAY):
        yoko = boards[("横浜", calendar)]
        mina = weekday_mina if calendar == WEEKDAY else boards[("みなとみらい", calendar)]
        shin = boards[("新高島", calendar)]
        rows, diagnostics = reconstruct(yoko, mina, shin)
        results[calendar] = {
            "calendar": calendar,
            "departureCount": len(rows),
            "departures": [row["reconstructed"] for row in rows],
            "stoppingTrainIndexes": [row["trainIndex"] for row in rows],
            "diagnostics": diagnostics,
            "rows": rows,
        }

    result = {
        "version": 1,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "station": "manual.Station:yokohama-minatomirai.新高島",
        "direction": "odpt.RailDirection:Outbound",
        "method": "adjacent complete-board constrained OCR correction",
        "calendars": results,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({calendar: data["diagnostics"] for calendar, data in results.items()}, ensure_ascii=False), flush=True)

    holiday = results[HOLIDAY]["diagnostics"]
    weekday = results[WEEKDAY]["diagnostics"]
    # The clean holiday board acts as a control: almost everything should be
    # preserved exactly, with no dropped observations.
    if holiday["skippedObserved"] or holiday["unchangedCount"] / max(1, holiday["observedStopCount"]) < 0.99:
        raise RuntimeError(f"holiday Shin-Takashima control failed: {holiday}")
    if weekday["skippedObserved"]:
        raise RuntimeError(f"weekday Shin-Takashima rows could not all be placed: {weekday}")
    if weekday["correctedCount"] > 12 or weekday["maxCorrectionMinutes"] > 5:
        raise RuntimeError(f"weekday Shin-Takashima correction too aggressive: {weekday}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
