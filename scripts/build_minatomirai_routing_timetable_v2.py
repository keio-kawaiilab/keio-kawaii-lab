#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import build_minatomirai_routing_timetable as base

HOLIDAY_MINATOMIRAI = Path("data/transit/yokohama-minatomirai/verified-upbound-minatomirai-holiday-20260314.json")
_original_board_map = base.raw_board_map


def verified_board_map(payload: dict) -> dict[tuple[str, str], list[int]]:
    boards = _original_board_map(payload)
    verified = json.loads(HOLIDAY_MINATOMIRAI.read_text(encoding="utf-8"))
    values = base.flatten_rows(verified["rows"])
    if len(values) != 275:
        raise RuntimeError(f"verified holiday Minatomirai count changed: {len(values)}")
    boards[("みなとみらい", base.HOLIDAY)] = values
    return boards


base.raw_board_map = verified_board_map

if __name__ == "__main__":
    raise SystemExit(base.main())
