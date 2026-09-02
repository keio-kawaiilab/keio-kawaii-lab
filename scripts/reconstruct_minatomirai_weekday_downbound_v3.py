#!/usr/bin/env python3
from __future__ import annotations

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


def board_map(payload: dict) -> dict[tuple[str, str], list[int]]:
    return {
        (row["stationTitle"], row["calendar"]): [to_minute(x) for x in row["departures"]]
        for row in payload["boards"]
    }


def partial_ordered_match(
    upstream: list[int], downstream: list[int], *, lo: int, hi: int, target: int
) -> tuple[dict[int, tuple[int, int]], list[int], list[int]]:
    """Return maximum-cardinality, minimum-penalty ordered matching.

    mapping maps upstream_index -> (downstream_index, downstream_minute).
    """
    n, m = len(upstream), len(downstream)
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
                move[i + 1][j] = "skip_up"
            if j < m and score > dp[i][j + 1]:
                dp[i][j + 1] = score
                move[i][j + 1] = "skip_down"
            if i < n and j < m:
                delta = downstream[j] - upstream[i]
                if lo <= delta <= hi:
                    cand = (score[0] + 1, score[1] - abs(delta - target))
                    if cand > dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = cand
                        move[i + 1][j + 1] = "match"

    i, j = n, m
    mapping: dict[int, tuple[int, int]] = {}
    used_down: set[int] = set()
    used_up: set[int] = set()
    while i > 0 or j > 0:
        mv = move[i][j]
        if mv == "match":
            mapping[i - 1] = (j - 1, downstream[j - 1])
            used_up.add(i - 1)
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
    unmatched_down = [idx for idx in range(m) if idx not in used_down]
    unmatched_up = [idx for idx in range(n) if idx not in used_up]
    return mapping, unmatched_down, unmatched_up


def recover_stop_only_anomalies(
    yoko: list[int], trusted: dict[int, tuple[int, int]], shin: list[int], unmatched_shin: list[int]
) -> tuple[set[int], list[dict]]:
    stops = set(trusted)
    used = set(trusted)
    anomalies = []
    for sidx in unmatched_shin:
        minute = shin[sidx]
        options = [
            (abs(minute - yoko[idx]), idx)
            for idx in range(len(yoko))
            if idx not in used and abs(minute - yoko[idx]) <= 2
        ]
        if not options:
            anomalies.append({"shintakashima": fmt(minute), "recovered": False})
            continue
        distance, idx = min(options)
        stops.add(idx)
        used.add(idx)
        anomalies.append({
            "shintakashima": fmt(minute),
            "associatedYokohama": fmt(yoko[idx]),
            "difference": minute - yoko[idx],
            "recovered": True,
            "timeTrusted": False,
        })
    return stops, anomalies


def calibrate(yoko: list[int], shin: list[int], mina: list[int]) -> tuple[dict[str, int], dict]:
    smap, sunmatched, _ = partial_ordered_match(yoko, shin, lo=1, hi=5, target=2)
    if sunmatched:
        raise RuntimeError(f"control Shin-Takashima unmatched: {[fmt(shin[i]) for i in sunmatched]}")
    hist = {"stop": Counter(), "skip": Counter()}
    for idx, (a, b) in enumerate(zip(yoko, mina)):
        delta = b - a
        if 2 <= delta <= 6:
            hist["stop" if idx in smap else "skip"][delta] += 1
    modal = {key: counter.most_common(1)[0][0] for key, counter in hist.items()}
    return modal, {key: {str(k): v for k, v in sorted(c.items())} for key, c in hist.items()}


def reconstruct(
    yoko: list[int], shin: list[int], raw_mina: list[int], basha: list[int], modal: dict[str, int]
) -> tuple[list[int], dict]:
    smap, sunmatched, _ = partial_ordered_match(yoko, shin, lo=1, hi=5, target=2)
    stop_indexes, shin_anomalies = recover_stop_only_anomalies(yoko, smap, shin, sunmatched)

    # This is the crucial v3 step: assign each plausible OCR Minatomirai row to
    # one and only one Yokohama train before filling gaps. A good OCR minute is
    # therefore never reused as evidence for adjacent trains.
    mmap, munmatched, y_unmatched = partial_ordered_match(yoko, raw_mina, lo=2, hi=6, target=4)
    trusted_mina: dict[int, int] = {idx: row[1] for idx, row in mmap.items()}

    candidates: list[list[tuple[int, int]]] = []
    for idx, y in enumerate(yoko):
        expected = modal["stop" if idx in stop_indexes else "skip"]
        observed = trusted_mina.get(idx)
        rows = []
        for delta in range(2, 7):
            minute = y + delta
            cost = abs(delta - expected) * 5

            # Preserve individually matched OCR rows unless stronger station
            # constraints make them impossible. This prevents the former v2
            # behaviour where one OCR minute could attract multiple trains.
            if observed is not None:
                if minute == observed:
                    cost -= 60
                else:
                    cost += 18

            if idx in smap:
                shin_minute = smap[idx][1]
                after = minute - shin_minute
                if 1 <= after <= 3:
                    cost -= 4
                else:
                    cost += 30 + abs(after - 2) * 5
            rows.append((minute, cost))
        candidates.append(rows)

    dp: list[dict[int, tuple[int, int | None]]] = []
    for idx, rows in enumerate(candidates):
        cur: dict[int, tuple[int, int | None]] = {}
        if idx == 0:
            for minute, cost in rows:
                cur[minute] = (cost, None)
        else:
            prev = dp[-1]
            for minute, local in rows:
                best = None
                for pminute, (pcost, _) in prev.items():
                    if pminute >= minute:
                        continue
                    cand = (pcost + local, pminute)
                    if best is None or cand[0] < best[0]:
                        best = cand
                if best is not None:
                    cur[minute] = best
        if not cur:
            raise RuntimeError(f"no monotonic path at train {idx}")
        dp.append(cur)

    minute = min(dp[-1], key=lambda x: dp[-1][x][0])
    final = [0] * len(yoko)
    for idx in range(len(yoko) - 1, -1, -1):
        final[idx] = minute
        _, previous = dp[idx][minute]
        if previous is None:
            break
        minute = previous

    bmap, bunmatched, _ = partial_ordered_match(final, basha, lo=1, hi=5, target=2)
    preserved = sum(idx in trusted_mina and final[idx] == trusted_mina[idx] for idx in range(len(yoko)))
    changed_trusted = [
        {
            "yokohama": fmt(yoko[idx]),
            "ocr": fmt(trusted_mina[idx]),
            "reconstructed": fmt(final[idx]),
        }
        for idx in trusted_mina
        if final[idx] != trusted_mina[idx]
    ]
    diagnostics = {
        "yokohamaCount": len(yoko),
        "shintakashimaCount": len(shin),
        "shintakashimaTrustedMatches": len(smap),
        "shintakashimaUnmatched": [fmt(shin[i]) for i in sunmatched],
        "shintakashimaAnomalies": shin_anomalies,
        "rawMinatomiraiCount": len(raw_mina),
        "rawMinatomiraiTrustedMatches": len(mmap),
        "rawMinatomiraiUnmatched": [fmt(raw_mina[i]) for i in munmatched],
        "yokohamaWithoutTrustedMinatomirai": [fmt(yoko[i]) for i in y_unmatched],
        "reconstructedCount": len(final),
        "trustedOcrPreserved": preserved,
        "trustedOcrChanged": changed_trusted,
        "syntheticTrainCount": len(yoko) - len(mmap),
        "bashamichiCount": len(basha),
        "bashamichiMatched": len(bmap),
        "bashamichiUnmatched": [fmt(basha[i]) for i in bunmatched],
        "bashamichiCoverage": round(len(bmap) / max(1, len(basha)), 4),
    }
    return final, diagnostics


def compare(expected: list[int], actual: list[int]) -> dict:
    mismatch = []
    if len(expected) == len(actual):
        mismatch = [
            {"index": i, "expected": fmt(a), "actual": fmt(b), "delta": b-a}
            for i, (a, b) in enumerate(zip(expected, actual)) if a != b
        ]
    return {
        "sameCount": len(expected) == len(actual),
        "exact": len(expected) - len(mismatch) if len(expected) == len(actual) else 0,
        "mismatchCount": len(mismatch) if len(expected) == len(actual) else None,
        "accuracy": round((len(expected)-len(mismatch))/max(1,len(expected)),4) if len(expected)==len(actual) else 0,
        "mismatches": mismatch[:50],
    }


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    b = board_map(payload)
    hy, hs, hm, hb = b[("横浜",HOLIDAY)], b[("新高島",HOLIDAY)], b[("みなとみらい",HOLIDAY)], b[("馬車道",HOLIDAY)]
    modal, hist = calibrate(hy, hs, hm)
    control, control_diag = reconstruct(hy, hs, hm, hb, modal)
    control_check = compare(hm, control)

    wy, ws, wm, wb = b[("横浜",WEEKDAY)], b[("新高島",WEEKDAY)], b[("みなとみらい",WEEKDAY)], b[("馬車道",WEEKDAY)]
    final, diag = reconstruct(wy, ws, wm, wb, modal)
    result = {
        "version": 6,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "calendar": WEEKDAY,
        "station": "manual.Station:yokohama-minatomirai.みなとみらい",
        "direction": "odpt.RailDirection:Outbound",
        "method": "one-to-one trusted OCR preservation plus adjacent-board gap reconstruction",
        "calibration": {"modalDelta": modal, "histograms": hist, "controlCheck": control_check, "controlDiagnostics": control_diag},
        "diagnostics": diag,
        "departures": [fmt(x) for x in final],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"modal":modal,"histograms":hist,"controlCheck":control_check,"controlDiagnostics":control_diag,"weekdayDiagnostics":diag},ensure_ascii=False),flush=True)

    if control_check.get("accuracy",0) < 0.99:
        raise RuntimeError(f"control accuracy below 99%: {control_check}")
    if len(final) != len(wy):
        raise RuntimeError("weekday reconstruction count mismatch")
    if diag["bashamichiCoverage"] < 0.95:
        raise RuntimeError(f"Bashamichi validation below 95%: {diag}")
    if diag["trustedOcrChanged"]:
        raise RuntimeError(f"trusted OCR rows were changed: {diag['trustedOcrChanged'][:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
