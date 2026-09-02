#!/usr/bin/env python3
from __future__ import annotations

import json

import reconstruct_minatomirai_weekday_downbound_v3 as core


def coverage(matched: int, total: int) -> float:
    return matched / max(1, total)


def main() -> int:
    payload = json.loads(core.SOURCE.read_text(encoding="utf-8"))
    b = core.board_map(payload)

    hy = b[("横浜", core.HOLIDAY)]
    hs = b[("新高島", core.HOLIDAY)]
    hm = b[("みなとみらい", core.HOLIDAY)]
    hb = b[("馬車道", core.HOLIDAY)]
    modal, hist = core.calibrate(hy, hs, hm)
    control, control_diag = core.reconstruct(hy, hs, hm, hb, modal)
    control_check = core.compare(hm, control)

    wy = b[("横浜", core.WEEKDAY)]
    ws = b[("新高島", core.WEEKDAY)]
    wm = b[("みなとみらい", core.WEEKDAY)]
    wb = b[("馬車道", core.WEEKDAY)]
    final, diag = core.reconstruct(wy, ws, wm, wb, modal)

    control_trusted_coverage = coverage(
        control_diag["rawMinatomiraiTrustedMatches"],
        control_diag["rawMinatomiraiCount"],
    )
    weekday_trusted_coverage = coverage(
        diag["rawMinatomiraiTrustedMatches"],
        diag["rawMinatomiraiCount"],
    )

    result = {
        "version": 7,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "calendar": core.WEEKDAY,
        "station": "manual.Station:yokohama-minatomirai.みなとみらい",
        "direction": "odpt.RailDirection:Outbound",
        "method": "one-to-one trusted OCR preservation plus adjacent-board gap reconstruction",
        "acceptance": {
            "controlTrustedOcrCoverage": round(control_trusted_coverage, 4),
            "controlBashamichiCoverage": control_diag["bashamichiCoverage"],
            "weekdayTrustedOcrCoverage": round(weekday_trusted_coverage, 4),
            "weekdayBashamichiCoverage": diag["bashamichiCoverage"],
            "syntheticTrainCount": diag["syntheticTrainCount"],
        },
        "calibration": {
            "modalDelta": modal,
            "histograms": hist,
            # This comparison is diagnostic only. The raw control board itself
            # contains a few OCR anomalies, so exact equality to every raw cell
            # is not an acceptance criterion.
            "rawControlComparison": control_check,
            "controlDiagnostics": control_diag,
        },
        "diagnostics": diag,
        "departures": [core.fmt(x) for x in final],
    }
    core.OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "modal": modal,
        "controlTrustedOcrCoverage": round(control_trusted_coverage, 4),
        "controlBashamichiCoverage": control_diag["bashamichiCoverage"],
        "weekdayTrustedOcrCoverage": round(weekday_trusted_coverage, 4),
        "weekdayBashamichiCoverage": diag["bashamichiCoverage"],
        "weekdayTrustedMatches": diag["rawMinatomiraiTrustedMatches"],
        "weekdayRawRows": diag["rawMinatomiraiCount"],
        "weekdaySyntheticTrains": diag["syntheticTrainCount"],
        "weekdayUnmatchedRaw": diag["rawMinatomiraiUnmatched"],
        "weekdayYokohamaWithoutTrustedMinatomirai": diag["yokohamaWithoutTrustedMinatomirai"],
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)

    # Acceptance is based on physically plausible one-to-one station matches,
    # not equality to known-bad OCR cells.
    if control_trusted_coverage < 0.99:
        raise RuntimeError(f"control trusted OCR coverage below 99%: {summary}")
    if control_diag["bashamichiCoverage"] < 0.99:
        raise RuntimeError(f"control Bashamichi coverage below 99%: {summary}")
    if control_diag["trustedOcrChanged"]:
        raise RuntimeError("control changed trusted OCR rows")
    if weekday_trusted_coverage < 0.98:
        raise RuntimeError(f"weekday trusted OCR coverage below 98%: {summary}")
    if diag["bashamichiCoverage"] < 0.98:
        raise RuntimeError(f"weekday Bashamichi coverage below 98%: {summary}")
    if diag["trustedOcrChanged"]:
        raise RuntimeError("weekday changed trusted OCR rows")
    if diag["syntheticTrainCount"] > 30:
        raise RuntimeError(f"too many synthetic trains: {summary}")
    if len(final) != len(wy):
        raise RuntimeError("weekday reconstruction count mismatch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
