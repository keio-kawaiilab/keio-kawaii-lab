#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import reconstruct_shintakashima_downbound_v3 as core

BASE = Path("data/transit/yokohama-minatomirai/reconstructed-shintakashima-downbound.json")
MINA = Path("data/transit/yokohama-minatomirai/reconstructed-minatomirai-downbound.json")
OUT = BASE


def choose_strict_minute(yokohama: int, minatomirai: int, current: int) -> int | None:
    lo = yokohama + 1
    hi = min(yokohama + 5, minatomirai - 1)
    if lo > hi:
        return None
    return min(
        range(lo, hi + 1),
        key=lambda minute: (
            abs(minute - current),
            abs((minute - yokohama) - 2) + abs((minatomirai - minute) - 2),
        ),
    )


def main() -> int:
    raw = json.loads(core.RAW.read_text(encoding="utf-8"))
    boards = core.board_map(raw)
    base = json.loads(BASE.read_text(encoding="utf-8"))
    mina_payload = json.loads(MINA.read_text(encoding="utf-8"))

    results = {}
    for calendar in (core.HOLIDAY, core.WEEKDAY):
        yoko = boards[("横浜", calendar)]
        mina = [core.to_minute(x) for x in mina_payload["calendars"][calendar]["departures"]]
        item = base["calendars"][calendar]
        rows = [dict(row) for row in item["rows"]]
        physical_corrections = []
        impossible = []

        for row in rows:
            ti = int(row["trainIndex"])
            current = core.to_minute(row["reconstructed"])
            if yoko[ti] < current < mina[ti]:
                row["physicalValidation"] = "preserved"
                continue
            chosen = choose_strict_minute(yoko[ti], mina[ti], current)
            if chosen is None:
                impossible.append({
                    "trainIndex": ti,
                    "yokohama": core.fmt(yoko[ti]),
                    "shintakashima": row["reconstructed"],
                    "minatomirai": core.fmt(mina[ti]),
                })
                row["physicalValidation"] = "unresolved"
                continue
            correction = abs(chosen - current)
            physical_corrections.append({
                "trainIndex": ti,
                "yokohama": core.fmt(yoko[ti]),
                "before": row["reconstructed"],
                "after": core.fmt(chosen),
                "minatomirai": core.fmt(mina[ti]),
                "correctionMinutes": correction,
            })
            row["reconstructedBeforePhysicalValidation"] = row["reconstructed"]
            row["reconstructed"] = core.fmt(chosen)
            row["physicalValidation"] = "corrected-strict-between-adjacent-stations"
            row["physicalCorrectionMinutes"] = correction

        rows.sort(key=lambda row: int(row["trainIndex"]))
        mins = [core.to_minute(row["reconstructed"]) for row in rows]
        if any(a >= b for a, b in zip(mins, mins[1:])):
            # Station departures themselves must remain chronologically ordered.
            bad = []
            for a, b in zip(rows, rows[1:]):
                if core.to_minute(a["reconstructed"]) >= core.to_minute(b["reconstructed"]):
                    bad.append({"left": a, "right": b})
            raise RuntimeError(f"{calendar}: Shin-Takashima order became non-monotonic: {bad[:5]}")

        diagnostics = dict(item["diagnostics"])
        diagnostics["physicalCorrectionCount"] = len(physical_corrections)
        diagnostics["physicalCorrections"] = physical_corrections
        diagnostics["physicalUnresolved"] = impossible
        diagnostics["physicalPreservedCount"] = len(rows) - len(physical_corrections) - len(impossible)

        results[calendar] = {
            "calendar": calendar,
            "departureCount": len(rows),
            "departures": [row["reconstructed"] for row in rows],
            "stoppingTrainIndexes": [int(row["trainIndex"]) for row in rows],
            "diagnostics": diagnostics,
            "rows": rows,
        }

    h = results[core.HOLIDAY]["diagnostics"]
    w = results[core.WEEKDAY]["diagnostics"]
    output = {
        "version": 5,
        "sourceRetrievedAt": raw.get("retrievedAt"),
        "station": "manual.Station:yokohama-minatomirai.新高島",
        "direction": "odpt.RailDirection:Outbound",
        "method": "OCR artifact isolation followed by strict Yokohama < Shin-Takashima < Minatomirai validation",
        "acceptance": {
            "holidayAcceptedStopCount": results[core.HOLIDAY]["departureCount"],
            "holidayPhysicalCorrectionCount": h["physicalCorrectionCount"],
            "weekdayAcceptedStopCount": results[core.WEEKDAY]["departureCount"],
            "weekdayPhysicalCorrectionCount": w["physicalCorrectionCount"],
        },
        "calendars": results,
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        core.HOLIDAY: {
            "count": results[core.HOLIDAY]["departureCount"],
            "physicalCorrections": h["physicalCorrections"],
            "unresolved": h["physicalUnresolved"],
        },
        core.WEEKDAY: {
            "count": results[core.WEEKDAY]["departureCount"],
            "physicalCorrectionCount": w["physicalCorrectionCount"],
            "physicalCorrections": w["physicalCorrections"],
            "unresolved": w["physicalUnresolved"],
        },
    }, ensure_ascii=False), flush=True)

    if h["physicalUnresolved"] or w["physicalUnresolved"]:
        raise RuntimeError("Shin-Takashima still contains physically unresolved rows")
    if h["physicalCorrectionCount"] > 2:
        raise RuntimeError(f"holiday Shin-Takashima corrections unexpectedly high: {h['physicalCorrections']}")
    if w["physicalCorrectionCount"] > 15:
        raise RuntimeError(f"weekday Shin-Takashima corrections unexpectedly high: {w['physicalCorrections']}")
    max_corr = max(
        [row["correctionMinutes"] for row in h["physicalCorrections"] + w["physicalCorrections"]] or [0]
    )
    if max_corr > 4:
        raise RuntimeError(f"Shin-Takashima physical correction exceeded 4 minutes: {max_corr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
