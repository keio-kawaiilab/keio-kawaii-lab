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


def physical_window(yokohama: int, minatomirai: int) -> tuple[int, int] | None:
    """Return plausible Shin-Takashima departure minutes for one train."""
    lo = max(yokohama + 1, minatomirai - 3)
    hi = min(yokohama + 5, minatomirai - 1)
    if lo > hi:
        return None
    return lo, hi


def travel_penalty(yokohama: int, shin: int, minatomirai: int) -> int:
    return abs((shin - yokohama) - 2) + abs((minatomirai - shin) - 2)


def exact_ordered_match(
    yokohama: list[int], minatomirai: list[int], observed: list[int]
) -> dict[int, int]:
    """Maximise exact physical matches while preserving timetable order.

    Returns train_index -> observed_index.  These rows are treated as trusted
    anchors and are never changed by the second-stage repair.
    """
    n, m = len(yokohama), len(observed)
    bad = (-10**9, -10**9)
    dp = [[bad] * (m + 1) for _ in range(n + 1)]
    move = [[""] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = (0, 0)  # (matches, -penalty)

    for i in range(n + 1):
        for j in range(m + 1):
            score = dp[i][j]
            if score == bad:
                continue
            if i < n and score > dp[i + 1][j]:
                dp[i + 1][j] = score
                move[i + 1][j] = "skip_train"
            if j < m and score > dp[i][j + 1]:
                dp[i][j + 1] = score
                move[i][j + 1] = "skip_observed"
            if i < n and j < m:
                window = physical_window(yokohama[i], minatomirai[i])
                if window is not None and window[0] <= observed[j] <= window[1]:
                    penalty = travel_penalty(yokohama[i], observed[j], minatomirai[i])
                    candidate = (score[0] + 1, score[1] - penalty)
                    if candidate > dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = candidate
                        move[i + 1][j + 1] = "match"

    mapping: dict[int, int] = {}
    i, j = n, m
    while i > 0 or j > 0:
        mv = move[i][j]
        if mv == "match":
            mapping[i - 1] = j - 1
            i -= 1
            j -= 1
        elif mv == "skip_train":
            i -= 1
        elif mv == "skip_observed":
            j -= 1
        elif i:
            i -= 1
        else:
            j -= 1
    return mapping


def corrected_candidate(
    yokohama: int, minatomirai: int, observed: int
) -> tuple[int, int, int] | None:
    window = physical_window(yokohama, minatomirai)
    if window is None:
        return None
    lo, hi = window
    reconstructed = min(
        range(lo, hi + 1),
        key=lambda value: (
            abs(value - observed),
            travel_penalty(yokohama, value, minatomirai),
            value,
        ),
    )
    correction = abs(reconstructed - observed)
    penalty = correction * 20 + travel_penalty(yokohama, reconstructed, minatomirai)
    return reconstructed, correction, penalty


def flexible_segment_match(
    yokohama: list[int],
    minatomirai: list[int],
    observed: list[int],
    train_indexes: list[int],
    observed_indexes: list[int],
) -> dict[int, tuple[int, int, int]]:
    """Repair only rows between trusted anchors.

    Returns train_index -> (observed_index, reconstructed_minute, correction).
    """
    n, m = len(train_indexes), len(observed_indexes)
    bad = (-10**9, -10**9)
    dp = [[bad] * (m + 1) for _ in range(n + 1)]
    move = [[""] * (m + 1) for _ in range(n + 1)]
    chosen: dict[tuple[int, int], tuple[int, int]] = {}
    dp[0][0] = (0, 0)

    for a in range(n + 1):
        for b in range(m + 1):
            score = dp[a][b]
            if score == bad:
                continue
            if a < n and score > dp[a + 1][b]:
                dp[a + 1][b] = score
                move[a + 1][b] = "skip_train"
            if b < m and score > dp[a][b + 1]:
                dp[a][b + 1] = score
                move[a][b + 1] = "skip_observed"
            if a < n and b < m:
                ti = train_indexes[a]
                oi = observed_indexes[b]
                candidate = corrected_candidate(yokohama[ti], minatomirai[ti], observed[oi])
                if candidate is None:
                    continue
                reconstructed, correction, penalty = candidate
                # Cardinality is the first priority; correction size is second.
                cand_score = (score[0] + 1, score[1] - penalty)
                if cand_score > dp[a + 1][b + 1]:
                    dp[a + 1][b + 1] = cand_score
                    move[a + 1][b + 1] = "match"
                    chosen[(a + 1, b + 1)] = (reconstructed, correction)

    mapping: dict[int, tuple[int, int, int]] = {}
    a, b = n, m
    while a > 0 or b > 0:
        mv = move[a][b]
        if mv == "match":
            ti = train_indexes[a - 1]
            oi = observed_indexes[b - 1]
            reconstructed, correction = chosen[(a, b)]
            mapping[ti] = (oi, reconstructed, correction)
            a -= 1
            b -= 1
        elif mv == "skip_train":
            a -= 1
        elif mv == "skip_observed":
            b -= 1
        elif a:
            a -= 1
        else:
            b -= 1
    return mapping


def reconstruct(
    yokohama: list[int], minatomirai: list[int], observed: list[int]
) -> tuple[list[dict], dict]:
    if len(yokohama) != len(minatomirai):
        raise RuntimeError(
            f"complete adjacent boards must have equal counts: {len(yokohama)} != {len(minatomirai)}"
        )

    trusted = exact_ordered_match(yokohama, minatomirai, observed)
    trusted_pairs = sorted((train_i, obs_i) for train_i, obs_i in trusted.items())

    repaired: dict[int, tuple[int, int, int]] = {}
    anchors = [(-1, -1), *trusted_pairs, (len(yokohama), len(observed))]
    for (left_train, left_obs), (right_train, right_obs) in zip(anchors, anchors[1:]):
        train_indexes = list(range(left_train + 1, right_train))
        observed_indexes = list(range(left_obs + 1, right_obs))
        if not train_indexes or not observed_indexes:
            continue
        repaired.update(
            flexible_segment_match(
                yokohama,
                minatomirai,
                observed,
                train_indexes,
                observed_indexes,
            )
        )

    rows: list[dict] = []
    used_observed: set[int] = set()
    for train_i, obs_i in trusted.items():
        used_observed.add(obs_i)
        rows.append(
            {
                "trainIndex": train_i,
                "yokohama": fmt(yokohama[train_i]),
                "observed": fmt(observed[obs_i]),
                "reconstructed": fmt(observed[obs_i]),
                "minatomirai": fmt(minatomirai[train_i]),
                "correctionMinutes": 0,
                "evidence": "trusted-exact-physical-match",
            }
        )
    for train_i, (obs_i, reconstructed, correction) in repaired.items():
        used_observed.add(obs_i)
        rows.append(
            {
                "trainIndex": train_i,
                "yokohama": fmt(yokohama[train_i]),
                "observed": fmt(observed[obs_i]),
                "reconstructed": fmt(reconstructed),
                "minatomirai": fmt(minatomirai[train_i]),
                "correctionMinutes": correction,
                "evidence": "gap-repair-between-trusted-anchors",
            }
        )

    rows.sort(key=lambda row: row["trainIndex"])
    unmatched_observed = [
        fmt(observed[i]) for i in range(len(observed)) if i not in used_observed
    ]
    corrections = [row for row in rows if row["correctionMinutes"] > 0]
    second_stage_unchanged = [
        row for row in rows
        if row["evidence"] == "gap-repair-between-trusted-anchors"
        and row["correctionMinutes"] == 0
    ]
    diagnostics = {
        "completeTrainCount": len(yokohama),
        "observedStopCount": len(observed),
        "matchedStopCount": len(rows),
        "trustedExactCount": len(trusted),
        "trustedExactCoverage": round(len(trusted) / max(1, len(observed)), 4),
        "trustedRowsChanged": [],
        "secondStageUnchangedCount": len(second_stage_unchanged),
        "correctedCount": len(corrections),
        "skippedObserved": unmatched_observed,
        "maxCorrectionMinutes": max((row["correctionMinutes"] for row in rows), default=0),
        "corrections": corrections,
    }
    return rows, diagnostics


def main() -> int:
    payload = json.loads(RAW.read_text(encoding="utf-8"))
    boards = board_map(payload)
    weekday_mina = [
        to_minute(x)
        for x in json.loads(MINA_RECON.read_text(encoding="utf-8"))["departures"]
    ]

    results = {}
    for calendar in (HOLIDAY, WEEKDAY):
        yokohama = boards[("横浜", calendar)]
        minatomirai = (
            weekday_mina
            if calendar == WEEKDAY
            else boards[("みなとみらい", calendar)]
        )
        observed = boards[("新高島", calendar)]
        rows, diagnostics = reconstruct(yokohama, minatomirai, observed)
        results[calendar] = {
            "calendar": calendar,
            "departureCount": len(rows),
            "departures": [row["reconstructed"] for row in rows],
            "stoppingTrainIndexes": [row["trainIndex"] for row in rows],
            "diagnostics": diagnostics,
            "rows": rows,
        }

    holiday = results[HOLIDAY]["diagnostics"]
    weekday = results[WEEKDAY]["diagnostics"]
    result = {
        "version": 2,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "station": "manual.Station:yokohama-minatomirai.新高島",
        "direction": "odpt.RailDirection:Outbound",
        "method": "trusted exact physical anchors plus gap-only OCR correction",
        "acceptance": {
            "holidayTrustedExactCoverage": holiday["trustedExactCoverage"],
            "weekdayTrustedExactCoverage": weekday["trustedExactCoverage"],
            "holidayCorrectedCount": holiday["correctedCount"],
            "weekdayCorrectedCount": weekday["correctedCount"],
            "weekdayMaxCorrectionMinutes": weekday["maxCorrectionMinutes"],
        },
        "calendars": results,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {calendar: data["diagnostics"] for calendar, data in results.items()},
            ensure_ascii=False,
        ),
        flush=True,
    )

    # Holiday is the clean control. Two known adjacent-board OCR anomalies are
    # tolerated, but virtually all observed Shin-Takashima rows must remain
    # exact and every observed row must still be placeable.
    if holiday["trustedExactCoverage"] < 0.985:
        raise RuntimeError(f"holiday exact-preservation control failed: {holiday}")
    if holiday["skippedObserved"] or holiday["matchedStopCount"] != holiday["observedStopCount"]:
        raise RuntimeError(f"holiday Shin-Takashima rows were lost: {holiday}")
    if holiday["correctedCount"] > 2 or holiday["maxCorrectionMinutes"] > 5:
        raise RuntimeError(f"holiday correction exceeded known anomaly budget: {holiday}")

    # Weekday must preserve the overwhelming majority of OCR rows exactly and
    # only repair the small set that cannot physically fit between validated
    # Yokohama and Minatomirai boards.
    if weekday["trustedExactCoverage"] < 0.95:
        raise RuntimeError(f"weekday exact-preservation too low: {weekday}")
    if weekday["skippedObserved"] or weekday["matchedStopCount"] != weekday["observedStopCount"]:
        raise RuntimeError(f"weekday Shin-Takashima rows could not all be placed: {weekday}")
    if weekday["correctedCount"] > 10 or weekday["maxCorrectionMinutes"] > 5:
        raise RuntimeError(f"weekday Shin-Takashima repair too aggressive: {weekday}")
    if weekday["trustedRowsChanged"]:
        raise RuntimeError(f"trusted Shin-Takashima rows changed: {weekday}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
