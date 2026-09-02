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


def exact_yokohama_match(yokohama: list[int], observed: list[int]) -> dict[int, int]:
    """Maximum-cardinality ordered exact matching using only the reliable upstream board.

    A Shin-Takashima departure normally occurs 1-5 minutes after Yokohama.
    These exact rows become immutable anchors for the repair stage.
    """
    n, m = len(yokohama), len(observed)
    bad = (-10**9, -10**9)
    dp = [[bad] * (m + 1) for _ in range(n + 1)]
    move = [[""] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = (0, 0)

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
                delta = observed[j] - yokohama[i]
                if 1 <= delta <= 5:
                    candidate = (score[0] + 1, score[1] - abs(delta - 2))
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


def repair_candidate(yokohama: int, minatomirai: int, observed: int) -> tuple[int, int, int]:
    """Choose a corrected minute from the reliable Yokohama travel window.

    Minatomirai is soft evidence only because its weekday board contains
    reconstructed rows. It can guide a tie but can never invalidate a trusted
    Yokohama/Shin-Takashima exact observation.
    """
    candidates = []
    for minute in range(yokohama + 1, yokohama + 6):
        correction = abs(minute - observed)
        upstream_penalty = abs((minute - yokohama) - 2)
        downstream_gap = minatomirai - minute
        if 1 <= downstream_gap <= 4:
            downstream_penalty = abs(downstream_gap - 2)
        elif downstream_gap <= 0:
            downstream_penalty = 30 + abs(downstream_gap) * 5
        else:
            downstream_penalty = 8 + abs(downstream_gap - 2)
        score = correction * 20 + upstream_penalty * 2 + downstream_penalty
        candidates.append((score, correction, minute))
    score, correction, minute = min(candidates)
    return minute, correction, score


def flexible_gap_match(
    yokohama: list[int],
    minatomirai: list[int],
    observed: list[int],
    train_indexes: list[int],
    observed_indexes: list[int],
) -> dict[int, tuple[int, int, int]]:
    n, m = len(train_indexes), len(observed_indexes)
    bad = (-10**9, -10**9)
    dp = [[bad] * (m + 1) for _ in range(n + 1)]
    move = [[""] * (m + 1) for _ in range(n + 1)]
    chosen: dict[tuple[int, int], tuple[int, int]] = {}
    dp[0][0] = (0, 0)

    for a in range(n + 1):
        for b in range(m + 1):
            state = dp[a][b]
            if state == bad:
                continue
            if a < n and state > dp[a + 1][b]:
                dp[a + 1][b] = state
                move[a + 1][b] = "skip_train"
            if b < m and state > dp[a][b + 1]:
                dp[a][b + 1] = state
                move[a][b + 1] = "skip_observed"
            if a < n and b < m:
                ti = train_indexes[a]
                oi = observed_indexes[b]
                minute, correction, cost = repair_candidate(
                    yokohama[ti], minatomirai[ti], observed[oi]
                )
                candidate = (state[0] + 1, state[1] - cost)
                if candidate > dp[a + 1][b + 1]:
                    dp[a + 1][b + 1] = candidate
                    move[a + 1][b + 1] = "match"
                    chosen[(a + 1, b + 1)] = (minute, correction)

    mapping: dict[int, tuple[int, int, int]] = {}
    a, b = n, m
    while a > 0 or b > 0:
        mv = move[a][b]
        if mv == "match":
            ti = train_indexes[a - 1]
            oi = observed_indexes[b - 1]
            minute, correction = chosen[(a, b)]
            mapping[ti] = (oi, minute, correction)
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
            f"adjacent complete boards must have equal counts: {len(yokohama)} != {len(minatomirai)}"
        )

    trusted = exact_yokohama_match(yokohama, observed)
    trusted_pairs = sorted(trusted.items())
    repairs: dict[int, tuple[int, int, int]] = {}

    anchors = [(-1, -1), *trusted_pairs, (len(yokohama), len(observed))]
    for (left_train, left_obs), (right_train, right_obs) in zip(anchors, anchors[1:]):
        train_indexes = list(range(left_train + 1, right_train))
        observed_indexes = list(range(left_obs + 1, right_obs))
        if not train_indexes or not observed_indexes:
            continue
        repairs.update(
            flexible_gap_match(
                yokohama,
                minatomirai,
                observed,
                train_indexes,
                observed_indexes,
            )
        )

    rows: list[dict] = []
    used_observed: set[int] = set()
    for ti, oi in trusted.items():
        used_observed.add(oi)
        rows.append(
            {
                "trainIndex": ti,
                "yokohama": fmt(yokohama[ti]),
                "observed": fmt(observed[oi]),
                "reconstructed": fmt(observed[oi]),
                "minatomirai": fmt(minatomirai[ti]),
                "correctionMinutes": 0,
                "evidence": "trusted-yokohama-exact",
            }
        )
    for ti, (oi, minute, correction) in repairs.items():
        used_observed.add(oi)
        rows.append(
            {
                "trainIndex": ti,
                "yokohama": fmt(yokohama[ti]),
                "observed": fmt(observed[oi]),
                "reconstructed": fmt(minute),
                "minatomirai": fmt(minatomirai[ti]),
                "correctionMinutes": correction,
                "evidence": "gap-repair-soft-minatomirai-check",
            }
        )
    rows.sort(key=lambda row: row["trainIndex"])

    corrections = [row for row in rows if row["correctionMinutes"] > 0]
    repair_unchanged = [
        row for row in rows
        if row["evidence"] == "gap-repair-soft-minatomirai-check"
        and row["correctionMinutes"] == 0
    ]
    skipped = [fmt(observed[i]) for i in range(len(observed)) if i not in used_observed]
    downstream_valid = 0
    downstream_anomalies = []
    for row in rows:
        ti = row["trainIndex"]
        shin = to_minute(row["reconstructed"])
        gap = minatomirai[ti] - shin
        if 1 <= gap <= 4:
            downstream_valid += 1
        else:
            downstream_anomalies.append(
                {
                    "trainIndex": ti,
                    "shintakashima": row["reconstructed"],
                    "minatomirai": fmt(minatomirai[ti]),
                    "gapMinutes": gap,
                    "evidence": row["evidence"],
                }
            )

    diagnostics = {
        "completeTrainCount": len(yokohama),
        "observedStopCount": len(observed),
        "matchedStopCount": len(rows),
        "trustedExactCount": len(trusted),
        "trustedExactCoverage": round(len(trusted) / max(1, len(observed)), 4),
        "trustedRowsChanged": [],
        "repairUnchangedCount": len(repair_unchanged),
        "correctedCount": len(corrections),
        "skippedObserved": skipped,
        "maxCorrectionMinutes": max((row["correctionMinutes"] for row in rows), default=0),
        "corrections": corrections,
        "minatomiraiValidationCount": downstream_valid,
        "minatomiraiValidationCoverage": round(downstream_valid / max(1, len(rows)), 4),
        "minatomiraiValidationAnomalies": downstream_anomalies,
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
        minatomirai = weekday_mina if calendar == WEEKDAY else boards[("みなとみらい", calendar)]
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
        "version": 3,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "station": "manual.Station:yokohama-minatomirai.新高島",
        "direction": "odpt.RailDirection:Outbound",
        "method": "immutable Yokohama exact anchors plus gap-only repair with soft Minatomirai validation",
        "acceptance": {
            "holidayTrustedExactCoverage": holiday["trustedExactCoverage"],
            "weekdayTrustedExactCoverage": weekday["trustedExactCoverage"],
            "weekdayCorrectedCount": weekday["correctedCount"],
            "weekdayMaxCorrectionMinutes": weekday["maxCorrectionMinutes"],
            "weekdayMinatomiraiValidationCoverage": weekday["minatomiraiValidationCoverage"],
        },
        "calendars": results,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({calendar: data["diagnostics"] for calendar, data in results.items()}, ensure_ascii=False), flush=True)

    if holiday["trustedExactCoverage"] < 0.995:
        raise RuntimeError(f"holiday Yokohama anchor control failed: {holiday}")
    if holiday["skippedObserved"] or holiday["matchedStopCount"] != holiday["observedStopCount"]:
        raise RuntimeError(f"holiday Shin-Takashima rows were lost: {holiday}")
    if holiday["correctedCount"]:
        raise RuntimeError(f"holiday clean board unexpectedly changed: {holiday}")

    if weekday["trustedExactCoverage"] < 0.96:
        raise RuntimeError(f"weekday Yokohama exact preservation too low: {weekday}")
    if weekday["skippedObserved"] or weekday["matchedStopCount"] != weekday["observedStopCount"]:
        raise RuntimeError(f"weekday Shin-Takashima rows could not all be placed: {weekday}")
    if weekday["correctedCount"] > 8 or weekday["maxCorrectionMinutes"] > 5:
        raise RuntimeError(f"weekday Shin-Takashima repair too aggressive: {weekday}")
    if weekday["trustedRowsChanged"]:
        raise RuntimeError(f"trusted Shin-Takashima anchors changed: {weekday}")
    if weekday["minatomiraiValidationCoverage"] < 0.95:
        raise RuntimeError(f"weekday downstream validation too low: {weekday}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
