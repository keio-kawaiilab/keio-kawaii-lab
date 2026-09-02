#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import reconstruct_minatomirai_weekday_downbound_v3 as core

OUT = Path("data/transit/yokohama-minatomirai/reconstructed-minatomirai-downbound.json")


def coverage(matched: int, total: int) -> float:
    return round(matched / max(1, total), 4)


def main() -> int:
    payload = json.loads(core.SOURCE.read_text(encoding="utf-8"))
    b = core.board_map(payload)
    hy, hs, hm = b[("横浜", core.HOLIDAY)], b[("新高島", core.HOLIDAY)], b[("みなとみらい", core.HOLIDAY)]
    modal, hist = core.calibrate(hy, hs, hm)

    calendars = {}
    for calendar in (core.HOLIDAY, core.WEEKDAY):
        yoko = b[("横浜", calendar)]
        shin = b[("新高島", calendar)]
        raw_mina = b[("みなとみらい", calendar)]
        basha = b[("馬車道", calendar)]
        final, diag = core.reconstruct(yoko, shin, raw_mina, basha, modal)
        calendars[calendar] = {
            "calendar": calendar,
            "departureCount": len(final),
            "departures": [core.fmt(x) for x in final],
            "diagnostics": diag,
            "acceptance": {
                "trustedRawCoverage": coverage(diag["rawMinatomiraiTrustedMatches"], diag["rawMinatomiraiCount"]),
                "bashamichiCoverage": diag["bashamichiCoverage"],
                "syntheticTrainCount": diag["syntheticTrainCount"],
            },
        }

    result = {
        "version": 8,
        "sourceRetrievedAt": payload.get("retrievedAt"),
        "station": "manual.Station:yokohama-minatomirai.みなとみらい",
        "direction": "odpt.RailDirection:Outbound",
        "method": "calendar-independent one-to-one OCR preservation with adjacent-board physical reconstruction",
        "calibration": {"modalDelta": modal, "histograms": hist},
        "calendars": calendars,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        cal: {
            "count": row["departureCount"],
            **row["acceptance"],
            "unmatchedRaw": row["diagnostics"]["rawMinatomiraiUnmatched"],
        }
        for cal, row in calendars.items()
    }, ensure_ascii=False), flush=True)

    h = calendars[core.HOLIDAY]
    w = calendars[core.WEEKDAY]
    if h["acceptance"]["trustedRawCoverage"] < 0.99 or h["acceptance"]["bashamichiCoverage"] < 0.99:
        raise RuntimeError(f"holiday Minatomirai reconstruction below threshold: {h['acceptance']}")
    if w["acceptance"]["trustedRawCoverage"] < 0.98 or w["acceptance"]["bashamichiCoverage"] < 0.98:
        raise RuntimeError(f"weekday Minatomirai reconstruction below threshold: {w['acceptance']}")
    if h["departureCount"] != len(hy):
        raise RuntimeError("holiday Minatomirai master count mismatch")
    if w["departureCount"] != len(b[("横浜", core.WEEKDAY)]):
        raise RuntimeError("weekday Minatomirai master count mismatch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
