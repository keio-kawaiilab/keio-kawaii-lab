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
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def fmt(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def board_map(payload: dict) -> dict[tuple[str, str], list[int]]:
    return {
        (row["stationTitle"], row["calendar"]): [to_minute(value) for value in row["departures"]]
        for row in payload["boards"]
    }


def ordered_subset_match(
    upstream: list[int],
    downstream: list[int],
    *,
    min_delta: int,
    max_delta: int,
    target_delta: int,
) -> dict[int, int]:
    """Map downstream departures to a unique ordered subset of upstream trains."""
    n, m = len(upstream), len(downstream)
    inf = 10**9
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    take = [[False] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0
    for i in range(1, n + 1):
        dp[i][0] = 0
        for j in range(1, min(i, m) + 1):
            best = dp[i - 1][j]
            delta = downstream[j - 1] - upstream[i - 1]
            if min_delta <= delta <= max_delta and dp[i - 1][j - 1] < inf:
                cost = dp[i - 1][j - 1] + abs(delta - target_delta)
                if cost < best:
                    best = cost
                    take[i][j] = True
            dp[i][j] = best
    if dp[n][m] >= inf:
        raise RuntimeError(
            f"could not align {m} downstream departures to {n} upstream departures "
            f"within {min_delta}..{max_delta} minutes"
        )
    mapping: dict[int, int] = {}
    i, j = n, m
    while j > 0 and i > 0:
        if take[i][j]:
            mapping[i - 1] = downstream[j - 1]
            i -= 1
            j -= 1
        else:
            i -= 1
    if len(mapping) != m:
        raise RuntimeError(f"alignment backtrack lost departures: {len(mapping)} != {m}")
    return mapping


def nearest_distance(sorted_values: list[int], value: int) -> int:
    pos = bisect.bisect_left(sorted_values, value)
    choices = []
    if pos < len(sorted_values):
        choices.append(abs(sorted_values[pos] - value))
    if pos:
        choices.append(abs(sorted_values[pos - 1] - value))
    return min(choices) if choices else 99


def modal_delta_by_stop_pattern(
    yokohama: list[int],
    shintakashima: list[int],
    minatomirai: list[int],
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    if len(yokohama) != len(minatomirai):
        raise RuntimeError("control calendar must have equal Yokohama and Minatomirai counts")
    shin_map = ordered_subset_match(
        yokohama,
        shintakashima,
        min_delta=1,
        max_delta=4,
        target_delta=2,
    )
    hist = {"stopsShinTakashima": Counter(), "skipsShinTakashima": Counter()}
    for index, (yoko, mina) in enumerate(zip(yokohama, minatomirai)):
        delta = mina - yoko
        if 2 <= delta <= 6:
            key = "stopsShinTakashima" if index in shin_map else "skipsShinTakashima"
            hist[key][delta] += 1
    modal = {}
    for key, counter in hist.items():
        if not counter:
            raise RuntimeError(f"no calibration samples for {key}")
        modal[key] = counter.most_common(1)[0][0]
    serialised = {
        key: {str(delta): count for delta, count in sorted(counter.items())}
        for key, counter in hist.items()
    }
    return modal, serialised


def reconstruct(
    yokohama: list[int],
    shintakashima: list[int],
    bashamichi: list[int],
    raw_minatomirai: list[int],
    modal: dict[str, int],
) -> tuple[list[int], list[dict], dict]:
    shin_map = ordered_subset_match(
        yokohama,
        shintakashima,
        min_delta=1,
        max_delta=4,
        target_delta=2,
    )
    # Yokohama -> Bashamichi normally takes roughly 4-7 minutes.  Use a broad
    # window because limited/commuter-limited services can skip Bashamichi and
    # because timetable dwell occasionally adds a minute.
    basha_map = ordered_subset_match(
        yokohama,
        bashamichi,
        min_delta=3,
        max_delta=9,
        target_delta=6,
    )

    candidates: list[list[tuple[int, int, dict]]] = []
    for index, yoko in enumerate(yokohama):
        stops_shin = index in shin_map
        pattern = "stopsShinTakashima" if stops_shin else "skipsShinTakashima"
        expected_delta = modal[pattern]
        rows = []
        for delta in range(2, 7):
            minute = yoko + delta
            cost = abs(delta - expected_delta) * 4
            evidence = {
                "deltaFromYokohama": delta,
                "stopPattern": pattern,
                "ocrDistance": nearest_distance(raw_minatomirai, minute),
            }
            ocr_distance = evidence["ocrDistance"]
            if ocr_distance == 0:
                cost -= 8
            elif ocr_distance == 1:
                cost -= 4
            elif ocr_distance == 2:
                cost -= 1
            else:
                cost += 2

            if stops_shin:
                after_shin = minute - shin_map[index]
                evidence["shintakashima"] = fmt(shin_map[index])
                evidence["minutesAfterShinTakashima"] = after_shin
                if 1 <= after_shin <= 3:
                    cost -= 3
                else:
                    cost += 30 + abs(after_shin - 2) * 5

            if index in basha_map:
                before_basha = basha_map[index] - minute
                evidence["bashamichi"] = fmt(basha_map[index])
                evidence["minutesBeforeBashamichi"] = before_basha
                if 1 <= before_basha <= 3:
                    cost -= 3
                else:
                    cost += 30 + abs(before_basha - 2) * 5

            rows.append((minute, cost, evidence))
        candidates.append(rows)

    # Dynamic programming across the whole day guarantees a strictly
    # increasing one-train/one-departure sequence.
    dp: list[dict[int, tuple[int, int | None, dict]]] = []
    for index, rows in enumerate(candidates):
        current: dict[int, tuple[int, int | None, dict]] = {}
        if index == 0:
            for minute, cost, evidence in rows:
                current[minute] = (cost, None, evidence)
        else:
            previous = dp[-1]
            for minute, local_cost, evidence in rows:
                best: tuple[int, int | None, dict] | None = None
                for prev_minute, (prev_cost, _, _) in previous.items():
                    if prev_minute >= minute:
                        continue
                    total = prev_cost + local_cost
                    if best is None or total < best[0]:
                        best = (total, prev_minute, evidence)
                if best is not None:
                    current[minute] = best
        if not current:
            raise RuntimeError(f"no monotonic reconstruction path at train {index}")
        dp.append(current)

    last_minute = min(dp[-1], key=lambda minute: dp[-1][minute][0])
    final = [0] * len(yokohama)
    details = [None] * len(yokohama)
    minute = last_minute
    for index in range(len(yokohama) - 1, -1, -1):
        cost, previous, evidence = dp[index][minute]
        final[index] = minute
        details[index] = {
            "index": index,
            "yokohama": fmt(yokohama[index]),
            "minatomirai": fmt(minute),
            "cost": cost if index == len(yokohama) - 1 else None,
            **evidence,
            "supportedByExactOcr": minute in set(raw_minatomirai),
        }
        if previous is None:
            break
        minute = previous

    exact_ocr = sum(1 for value in final if value in set(raw_minatomirai))
    near_ocr = sum(1 for value in final if nearest_distance(raw_minatomirai, value) <= 1)
    diagnostics = {
        "yokohamaCount": len(yokohama),
        "shintakashimaCount": len(shintakashima),
        "bashamichiCount": len(bashamichi),
        "rawMinatomiraiCount": len(raw_minatomirai),
        "reconstructedCount": len(final),
        "exactOcrSupport": exact_ocr,
        "withinOneMinuteOcrSupport": near_ocr,
        "syntheticExactMissing": [fmt(value) for value in final if value not in set(raw_minatomirai)],
    }
    return final, details, diagnostics


def compare_exact(expected: list[int], actual: list[int]) -> dict:
    if len(expected) != len(actual):
        return {"sameCount": False, "expected": len(expected), "actual": len(actual)}
    mismatches = [
        {"index": index, "expected": fmt(exp), "actual": fmt(act), "delta": act - exp}
        for index, (exp, act) in enumerate(zip(expected, actual))
        if exp != act
    ]
    return {
        "sameCount": True,
        "exact": len(expected) - len(mismatches),
        "accuracy": round((len(expected) - len(mismatches)) / max(1, len(expected)), 4),
        "mismatchCount": len(mismatches),
        "mismatches": mismatches[:40],
    }


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    boards = board_map(payload)
    holiday_y = boards[("横浜", HOLIDAY)]
    holiday_s = boards[("新高島", HOLIDAY)]
    holiday_m = boards[("みなとみらい", HOLIDAY)]
    holiday_b = boards[("馬車道", HOLIDAY)]
    modal, calibration_hist = modal_delta_by_stop_pattern(holiday_y, holiday_s, holiday_m)

    # Control run: the Saturday/holiday Minatomirai board is already high
    # quality. Reconstruct it from adjacent boards and measure exact agreement.
    control, _, control_diag = reconstruct(holiday_y, holiday_s, holiday_b, holiday_m, modal)
    control_check = compare_exact(holiday_m, control)

    weekday_y = boards[("横浜", WEEKDAY)]
    weekday_s = boards[("新高島", WEEKDAY)]
    weekday_m = boards[("みなとみらい", WEEKDAY)]
    weekday_b = boards[("馬車道", WEEKDAY)]
    reconstructed, details, diagnostics = reconstruct(
        weekday_y, weekday_s, weekday_b, weekday_m, modal
    )

    result = {
        "version": 1,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "calendar": WEEKDAY,
        "station": "manual.Station:yokohama-minatomirai.みなとみらい",
        "direction": "odpt.RailDirection:Outbound",
        "method": "adjacent-official-board reconstruction calibrated on SaturdayHoliday",
        "calibration": {
            "modalDeltaFromYokohama": modal,
            "deltaHistograms": calibration_hist,
            "controlDiagnostics": control_diag,
            "controlCheck": control_check,
        },
        "diagnostics": diagnostics,
        "departures": [fmt(value) for value in reconstructed],
        "trains": details,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "modal": modal,
        "calibrationHistograms": calibration_hist,
        "controlCheck": control_check,
        "weekdayDiagnostics": diagnostics,
    }, ensure_ascii=False), flush=True)

    # Guardrail: do not accept a reconstruction method that cannot reproduce
    # at least 98% of the high-quality control timetable exactly.
    if not control_check.get("sameCount") or control_check.get("accuracy", 0) < 0.98:
        raise RuntimeError(f"control reconstruction below 98%: {control_check}")
    if len(reconstructed) != len(weekday_y):
        raise RuntimeError("weekday reconstruction does not preserve one train per Yokohama departure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
