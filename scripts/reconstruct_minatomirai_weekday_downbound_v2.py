#!/usr/bin/env python3
from __future__ import annotations

import bisect
import json
from collections import Counter
from pathlib import Path

SOURCE = Path("data/transit/yokohama-minatomirai/official-downbound-departures.json")
OUT = Path("data/transit/yokohama-minatomirai/reconstructed-weekday-minatomirai.json")
WEEKDAY = "odpt.Calendar:Weekday"
HOLIDAY = "odpt.Calendar:SaturdayHoliday"


def to_minute(value: str) -> int:
    h, m = map(int, value.split(":"))
    return h * 60 + m


def fmt(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def boards(payload: dict) -> dict[tuple[str, str], list[int]]:
    return {
        (row["stationTitle"], row["calendar"]): [to_minute(x) for x in row["departures"]]
        for row in payload["boards"]
    }


def partial_ordered_match(
    upstream: list[int], downstream: list[int], *, lo: int, hi: int, target: int
) -> tuple[dict[int, int], list[int], list[int]]:
    """Maximum-cardinality ordered matching, then minimum timing penalty."""
    n, m = len(upstream), len(downstream)
    # state=(matches, -cost); maximize lexicographically.
    dp = [[(-1, -10**9)] * (m + 1) for _ in range(n + 1)]
    move = [[""] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = (0, 0)
    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j][0] < 0:
                continue
            score = dp[i][j]
            if i < n and score > dp[i + 1][j]:
                dp[i + 1][j] = score
                move[i + 1][j] = "skip_up"
            if j < m and score > dp[i][j + 1]:
                dp[i][j + 1] = score
                move[i][j + 1] = "skip_down"
            if i < n and j < m:
                delta = downstream[j] - upstream[i]
                if lo <= delta <= hi:
                    penalty = abs(delta - target)
                    cand = (score[0] + 1, score[1] - penalty)
                    if cand > dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = cand
                        move[i + 1][j + 1] = "match"

    i, j = n, m
    mapping: dict[int, int] = {}
    matched_downstream: set[int] = set()
    matched_upstream: set[int] = set()
    while i > 0 or j > 0:
        mv = move[i][j]
        if mv == "match":
            mapping[i - 1] = downstream[j - 1]
            matched_upstream.add(i - 1)
            matched_downstream.add(j - 1)
            i -= 1
            j -= 1
        elif mv == "skip_up":
            i -= 1
        elif mv == "skip_down":
            j -= 1
        elif i > 0:
            i -= 1
        elif j > 0:
            j -= 1
    missing_down = [downstream[k] for k in range(m) if k not in matched_downstream]
    missing_up = [upstream[k] for k in range(n) if k not in matched_upstream]
    return mapping, missing_down, missing_up


def add_stop_evidence_anomalies(
    upstream: list[int], mapping: dict[int, int], unmatched_downstream: list[int]
) -> tuple[dict[int, int], list[dict]]:
    """Recover only stop/non-stop evidence from isolated bad OCR timestamps."""
    used = set(mapping)
    result = dict(mapping)
    anomalies = []
    for bad in unmatched_downstream:
        options = [
            (abs(bad - value), idx, value)
            for idx, value in enumerate(upstream)
            if idx not in used and abs(bad - value) <= 2
        ]
        if not options:
            anomalies.append({"downstream": fmt(bad), "recovered": False})
            continue
        distance, idx, value = min(options)
        result[idx] = bad
        used.add(idx)
        anomalies.append({
            "downstream": fmt(bad),
            "associatedYokohama": fmt(value),
            "difference": bad - value,
            "recovered": True,
            "timeTrusted": False,
        })
    return result, anomalies


def nearest_distance(values: list[int], value: int) -> int:
    pos = bisect.bisect_left(values, value)
    choices = []
    if pos < len(values): choices.append(abs(values[pos] - value))
    if pos: choices.append(abs(values[pos - 1] - value))
    return min(choices) if choices else 99


def calibrate(yoko: list[int], shin: list[int], mina: list[int]) -> tuple[dict[str, int], dict]:
    mapping, unmatched, _ = partial_ordered_match(yoko, shin, lo=1, hi=5, target=2)
    if unmatched:
        raise RuntimeError(f"control Shin-Takashima has unmatched rows: {[fmt(x) for x in unmatched]}")
    hist = {"stop": Counter(), "skip": Counter()}
    for idx, (a, b) in enumerate(zip(yoko, mina)):
        d = b - a
        if 2 <= d <= 6:
            hist["stop" if idx in mapping else "skip"][d] += 1
    modal = {key: counter.most_common(1)[0][0] for key, counter in hist.items()}
    return modal, {key: {str(k): v for k, v in sorted(c.items())} for key, c in hist.items()}


def reconstruct(
    yoko: list[int], shin: list[int], raw_mina: list[int], basha: list[int], modal: dict[str, int]
) -> tuple[list[int], dict]:
    trusted, unmatched_shin, _ = partial_ordered_match(yoko, shin, lo=1, hi=5, target=2)
    stop_map, anomalies = add_stop_evidence_anomalies(yoko, trusted, unmatched_shin)
    trusted_indexes = set(trusted)
    raw_set = set(raw_mina)

    # Candidates for every Yokohama train. The station is major enough that
    # the full official Yokohama downbound board is the train-count spine.
    candidates: list[list[tuple[int, int]]] = []
    for idx, y in enumerate(yoko):
        pattern = "stop" if idx in stop_map else "skip"
        expected = modal[pattern]
        rows = []
        for delta in range(2, 7):
            minute = y + delta
            cost = abs(delta - expected) * 4
            dist = nearest_distance(raw_mina, minute)
            if dist == 0: cost -= 10
            elif dist == 1: cost -= 4
            elif dist == 2: cost -= 1
            else: cost += 2
            # Use Shin-Takashima time only when it came from a physically
            # plausible high-confidence match. Anomaly association contributes
            # only the fact that the train stops there.
            if idx in trusted_indexes:
                after = minute - trusted[idx]
                if 1 <= after <= 3: cost -= 3
                else: cost += 25 + abs(after - 2) * 5
            rows.append((minute, cost))
        candidates.append(rows)

    dp: list[dict[int, tuple[int, int | None]]] = []
    for idx, rows in enumerate(candidates):
        cur = {}
        if idx == 0:
            for minute, cost in rows: cur[minute] = (cost, None)
        else:
            prev = dp[-1]
            for minute, local in rows:
                best = None
                for pminute, (pcost, _) in prev.items():
                    if pminute >= minute: continue
                    cand = (pcost + local, pminute)
                    if best is None or cand[0] < best[0]: best = cand
                if best is not None: cur[minute] = best
        if not cur:
            raise RuntimeError(f"no monotonic path at Yokohama train {idx}")
        dp.append(cur)

    minute = min(dp[-1], key=lambda x: dp[-1][x][0])
    final = [0] * len(yoko)
    for idx in range(len(yoko) - 1, -1, -1):
        final[idx] = minute
        _, previous = dp[idx][minute]
        if previous is None: break
        minute = previous

    # Validation only: Bashamichi omits passing trains. We require almost all
    # of its board to fit as an ordered subset shortly after Minatomirai.
    bmap, bunmatched, _ = partial_ordered_match(final, basha, lo=1, hi=5, target=2)
    diagnostics = {
        "yokohamaCount": len(yoko),
        "shintakashimaCount": len(shin),
        "shintakashimaTrustedMatches": len(trusted),
        "shintakashimaUnmatched": [fmt(x) for x in unmatched_shin],
        "shintakashimaAnomalies": anomalies,
        "rawMinatomiraiCount": len(raw_mina),
        "reconstructedCount": len(final),
        "exactOcrSupport": sum(x in raw_set for x in final),
        "withinOneMinuteOcrSupport": sum(nearest_distance(raw_mina, x) <= 1 for x in final),
        "syntheticExactMissing": [fmt(x) for x in final if x not in raw_set],
        "bashamichiCount": len(basha),
        "bashamichiMatched": len(bmap),
        "bashamichiUnmatched": [fmt(x) for x in bunmatched],
        "bashamichiCoverage": round(len(bmap) / max(1, len(basha)), 4),
    }
    return final, diagnostics


def compare(expected: list[int], actual: list[int]) -> dict:
    if len(expected) != len(actual):
        return {"sameCount": False, "expected": len(expected), "actual": len(actual), "accuracy": 0}
    mismatch = [
        {"index": i, "expected": fmt(a), "actual": fmt(b), "delta": b-a}
        for i, (a, b) in enumerate(zip(expected, actual)) if a != b
    ]
    return {
        "sameCount": True,
        "exact": len(expected)-len(mismatch),
        "mismatchCount": len(mismatch),
        "accuracy": round((len(expected)-len(mismatch))/max(1,len(expected)),4),
        "mismatches": mismatch[:50],
    }


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    b = boards(payload)
    hy, hs, hm, hb = b[("横浜",HOLIDAY)], b[("新高島",HOLIDAY)], b[("みなとみらい",HOLIDAY)], b[("馬車道",HOLIDAY)]
    modal, hist = calibrate(hy, hs, hm)
    control, control_diag = reconstruct(hy, hs, hm, hb, modal)
    control_check = compare(hm, control)

    wy, ws, wm, wb = b[("横浜",WEEKDAY)], b[("新高島",WEEKDAY)], b[("みなとみらい",WEEKDAY)], b[("馬車道",WEEKDAY)]
    final, diag = reconstruct(wy, ws, wm, wb, modal)
    result = {
        "version": 5,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "calendar": WEEKDAY,
        "station": "manual.Station:yokohama-minatomirai.みなとみらい",
        "direction": "odpt.RailDirection:Outbound",
        "method": "maximum-cardinality adjacent official-board reconstruction",
        "calibration": {"modalDelta": modal, "histograms": hist, "controlCheck": control_check, "controlDiagnostics": control_diag},
        "diagnostics": diag,
        "departures": [fmt(x) for x in final],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"modal":modal,"histograms":hist,"controlCheck":control_check,"controlDiagnostics":control_diag,"weekdayDiagnostics":diag},ensure_ascii=False),flush=True)

    if control_check.get("accuracy",0) < 0.98:
        raise RuntimeError(f"control accuracy below 98%: {control_check}")
    if len(final) != len(wy):
        raise RuntimeError("weekday reconstruction train count mismatch")
    if diag["bashamichiCoverage"] < 0.95:
        raise RuntimeError(f"Bashamichi validation below 95%: {diag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
