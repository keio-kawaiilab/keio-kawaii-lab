#!/usr/bin/env python3
from __future__ import annotations

import json

import reconstruct_shintakashima_downbound_v3 as core


def classify_rejected_ocr(yokohama: list[int], observed: list[int], rows: list[dict], skipped: list[str]) -> list[dict]:
    used_train_indexes = {row["trainIndex"] for row in rows}
    rejected = []
    for value in skipped:
        minute = core.to_minute(value)
        all_candidates = [
            i for i, y in enumerate(yokohama)
            if 1 <= minute - y <= 5
        ]
        unused_candidates = [i for i in all_candidates if i not in used_train_indexes]
        rejected.append({
            "observed": value,
            "candidateTrainIndexes": all_candidates,
            "candidateYokohamaDepartures": [core.fmt(yokohama[i]) for i in all_candidates],
            "unusedCandidateTrainIndexes": unused_candidates,
            "classification": (
                "physically-impossible-extra-ocr-cell"
                if not unused_candidates
                else "unresolved-possible-train"
            ),
        })
    return rejected


def make_calendar(calendar: str, yokohama: list[int], minatomirai: list[int], observed: list[int]) -> dict:
    rows, diagnostics = core.reconstruct(yokohama, minatomirai, observed)
    rejected = classify_rejected_ocr(
        yokohama, observed, rows, diagnostics["skippedObserved"]
    )
    diagnostics = dict(diagnostics)
    diagnostics["rejectedOcrArtifacts"] = rejected
    diagnostics["acceptedStopCount"] = len(rows)
    diagnostics["accountedObservedCount"] = len(rows) + len(rejected)
    return {
        "calendar": calendar,
        "departureCount": len(rows),
        "departures": [row["reconstructed"] for row in rows],
        "stoppingTrainIndexes": [row["trainIndex"] for row in rows],
        "diagnostics": diagnostics,
        "rows": rows,
    }


def main() -> int:
    payload = json.loads(core.RAW.read_text(encoding="utf-8"))
    boards = core.board_map(payload)
    weekday_mina = [
        core.to_minute(x)
        for x in json.loads(core.MINA_RECON.read_text(encoding="utf-8"))["departures"]
    ]

    results = {}
    for calendar in (core.HOLIDAY, core.WEEKDAY):
        yoko = boards[("横浜", calendar)]
        mina = weekday_mina if calendar == core.WEEKDAY else boards[("みなとみらい", calendar)]
        shin = boards[("新高島", calendar)]
        results[calendar] = make_calendar(calendar, yoko, mina, shin)

    holiday = results[core.HOLIDAY]["diagnostics"]
    weekday = results[core.WEEKDAY]["diagnostics"]

    result = {
        "version": 4,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "station": "manual.Station:yokohama-minatomirai.新高島",
        "direction": "odpt.RailDirection:Outbound",
        "method": "immutable Yokohama anchors, local correction, and physically impossible OCR isolation",
        "acceptance": {
            "holidayTrustedExactCoverage": holiday["trustedExactCoverage"],
            "weekdayTrustedExactCoverage": weekday["trustedExactCoverage"],
            "weekdayAcceptedStopCount": weekday["acceptedStopCount"],
            "weekdayCorrectedCount": weekday["correctedCount"],
            "weekdayRejectedOcrArtifactCount": len(weekday["rejectedOcrArtifacts"]),
            "weekdayMaxCorrectionMinutes": weekday["maxCorrectionMinutes"],
        },
        "calendars": results,
    }
    core.OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        cal: {
            "observed": data["diagnostics"]["observedStopCount"],
            "accepted": data["diagnostics"]["acceptedStopCount"],
            "trusted": data["diagnostics"]["trustedExactCount"],
            "corrected": data["diagnostics"]["correctedCount"],
            "rejected": data["diagnostics"]["rejectedOcrArtifacts"],
            "maxCorrection": data["diagnostics"]["maxCorrectionMinutes"],
        }
        for cal, data in results.items()
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)

    # Saturday/holiday is the clean control board: every OCR row must remain.
    if holiday["trustedExactCoverage"] < 0.995:
        raise RuntimeError(f"holiday exact-anchor control failed: {summary}")
    if holiday["correctedCount"] or holiday["rejectedOcrArtifacts"]:
        raise RuntimeError(f"holiday clean board was altered: {summary}")

    # Weekday may contain OCR false positives, but they are removable only when
    # every Yokohama train that could physically produce that minute is already
    # occupied by another accepted Shin-Takashima row.
    unresolved = [
        row for row in weekday["rejectedOcrArtifacts"]
        if row["classification"] != "physically-impossible-extra-ocr-cell"
    ]
    if unresolved:
        raise RuntimeError(f"unresolved possible Shin-Takashima trains: {unresolved}")
    if weekday["trustedExactCoverage"] < 0.96:
        raise RuntimeError(f"weekday trusted anchors below 96%: {summary}")
    if weekday["correctedCount"] > 6 or weekday["maxCorrectionMinutes"] > 3:
        raise RuntimeError(f"weekday correction too aggressive: {summary}")
    if weekday["trustedRowsChanged"]:
        raise RuntimeError("trusted Shin-Takashima rows were changed")
    if weekday["accountedObservedCount"] != weekday["observedStopCount"]:
        raise RuntimeError(f"weekday OCR rows not fully accounted for: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
