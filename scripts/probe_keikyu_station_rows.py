#!/usr/bin/env python3
"""Probe station/arrival/departure row semantics on one Keikyu timetable page.

This is deliberately diagnostic. It proves whether PDF Y-coordinate rows can
bind a strict train column to the published station row without using any time
proximity between trains.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from keikyu_official_pdf import (
    TIME_RE,
    bbox_words,
    cluster_by_y,
    detect_train_column_grid,
    download_official_pdf,
    nearest_column,
)

PAGE = 7


def compact_join(words) -> str:
    return "".join(word.text for word in sorted(words, key=lambda word: word.x))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="keikyu-row-probe-") as temp_dir:
        pdf_path = Path(temp_dir) / "schedule_all.pdf"
        download_official_pdf(pdf_path)
        _width, _height, words = bbox_words(pdf_path, PAGE)
        grid = detect_train_column_grid(words)
        if grid is None:
            raise RuntimeError("could not prove train-column grid")

        left_boundary = grid.centers[0] - grid.pitch * 0.55
        rows = []
        inherited_station_label = None
        for row in cluster_by_y(words, tolerance=1.35):
            y = sum(word.y for word in row) / len(row)
            if y <= grid.header_y + 20:
                continue

            left_words = [word for word in row if word.x < left_boundary]
            left_text = compact_join(left_words)
            if not left_text:
                continue

            cells = []
            for word in row:
                if word.x < left_boundary or not TIME_RE.fullmatch(word.text):
                    continue
                column = nearest_column(grid, word.x)
                if column is None:
                    continue
                cells.append({"column": column, "text": word.text, "x": round(word.x, 2)})

            # Rows with station labels but no time cells are still useful because
            # some arrival/departure labels occupy a separate printed row.
            looks_operational = any(token in left_text for token in ("発", "着", "〃"))
            if not looks_operational and not cells:
                continue

            # Diagnostic inheritance only: do not yet publish this as station
            # identity. A subsequent parser must resolve it against known station
            # titles and validate row ordering.
            if any(token in left_text for token in ("発", "着", "〃")) and len(left_text) > 1:
                inherited_station_label = left_text

            rows.append(
                {
                    "y": round(y, 2),
                    "left": left_text,
                    "candidatePreviousOperationalRow": inherited_station_label,
                    "cellCount": len(cells),
                    "cells": cells[:20],
                }
            )

        report = {
            "page": PAGE,
            "columnCount": len(grid.centers),
            "headerY": round(grid.header_y, 2),
            "leftBoundary": round(left_boundary, 2),
            "operationalOrTimedRows": len(rows),
            "rows": rows[:140],
            "policy": {
                "sameYBindsTimeToPrintedRow": True,
                "timeProximityBindsTrains": False,
                "rowInheritanceMayPublishStationIdentity": False,
            },
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not any(row["cellCount"] > 0 and "泉岳寺" in row["left"] for row in rows):
            raise RuntimeError("did not bind any timetable cell to 泉岳寺 row")
        if not any(row["cellCount"] > 0 and "三崎口" in row["left"] for row in rows):
            raise RuntimeError("did not bind any timetable cell to 三崎口 row")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
