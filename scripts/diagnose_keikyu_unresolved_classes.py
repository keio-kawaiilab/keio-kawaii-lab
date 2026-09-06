#!/usr/bin/env python3
"""Classify only the time cells still unresolved by the strict Keikyu parser.

This diagnostic deliberately mirrors the station/arrival/departure resolver,
including the printed split-row linkage between a 着/発 row and a nearby
canonical station-title row. It never turns residual rows into stops; it only
measures the remaining printed structures so they can be handled deliberately.
"""
from __future__ import annotations

import json
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from audit_keikyu_official_columns import FIRST_POSSIBLE_TIMETABLE_PAGE, page_scope_reason
from keikyu_connected_station_catalog import station_titles
from keikyu_official_pdf import (
    TIME_RE,
    bbox_words,
    cluster_by_y,
    compact,
    detect_train_column_grid,
    download_official_pdf,
    nearest_column,
    page_count,
    time_cells,
)
from probe_keikyu_station_rows import compact_join, marker, station_adjacent_marker, station_matches


def category(left_text: str, matches: list[str], row_marker: str | None) -> str:
    if "前の掲載ページ" in left_text:
        return "continuation-heading"
    if "次の掲載ページ" in left_text:
        return "continuation-heading"
    if len(matches) > 1:
        return "ambiguous-station-title"
    if len(matches) == 1 and row_marker is None:
        return "station-without-marker"
    if not matches and row_marker is not None:
        return "unanchored-marker-row"
    if not left_text:
        return "blank-label"
    if re.fullmatch(r"[0-9…!#$%&\"'\\・.]+", left_text):
        return "symbol-or-time-only-label"
    return "unclassified-text"


def main() -> int:
    titles = station_titles()
    counts = Counter()
    rows = Counter()
    samples: dict[str, list[dict]] = defaultdict(list)
    text_fragments = Counter()
    total_pdf_time_cells = 0
    resolved_by_same_rules = 0

    with tempfile.TemporaryDirectory(prefix="keikyu-residual-classes-") as temp_dir:
        pdf_path = Path(temp_dir) / "schedule_all.pdf"
        download_official_pdf(pdf_path)
        total_pages = page_count(pdf_path)

        for page_number in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total_pages + 1):
            _width, _height, words = bbox_words(pdf_path, page_number)
            page_text = compact("".join(word.text for word in words))
            if page_scope_reason(page_text):
                continue
            grid = detect_train_column_grid(words)
            if grid is None:
                continue

            all_cells = time_cells(words, grid)
            total_pdf_time_cells += len(all_cells)
            left_boundary = grid.centers[0] - grid.pitch * 0.55
            raw_rows = []

            for row in cluster_by_y(words, tolerance=1.35):
                y = sum(word.y for word in row) / len(row)
                if y <= grid.header_y + 10:
                    continue
                left_words = [word for word in row if word.x < left_boundary]
                left_text = compact_join(left_words) if left_words else ""
                cells = []
                for word in row:
                    if word.x < left_boundary or not TIME_RE.fullmatch(word.text):
                        continue
                    column = nearest_column(grid, word.x)
                    if column is None:
                        continue
                    cells.append({"column": column, "text": word.text, "x": round(word.x, 2)})
                if not cells and not left_text:
                    continue

                matches = station_matches(left_text, titles) if left_text else []
                row_marker = marker(left_text) if left_text else None
                if len(matches) == 1:
                    row_marker = station_adjacent_marker(left_text, matches[0]) or row_marker
                raw_rows.append(
                    {
                        "y": y,
                        "left": left_text,
                        "stationMatches": matches,
                        "marker": row_marker,
                        "cells": cells,
                    }
                )

            station_anchors = [
                {"y": row["y"], "station": row["stationMatches"][0], "marker": row["marker"]}
                for row in raw_rows
                if len(row["stationMatches"]) == 1
            ]

            for row in raw_rows:
                cells = row["cells"]
                if not cells:
                    continue

                station = None
                if len(row["stationMatches"]) == 1:
                    station = row["stationMatches"][0]
                elif row["marker"] == "arrival":
                    candidates = [anchor for anchor in station_anchors if 0 < anchor["y"] - row["y"] <= 10.5]
                    if candidates:
                        station = min(candidates, key=lambda anchor: anchor["y"] - row["y"])["station"]
                elif row["marker"] == "departure":
                    candidates = [anchor for anchor in station_anchors if 0 < row["y"] - anchor["y"] <= 10.5]
                    if candidates:
                        station = min(candidates, key=lambda anchor: row["y"] - anchor["y"])["station"]

                if station and row["marker"]:
                    resolved_by_same_rules += len(cells)
                    continue

                kind = category(row["left"], row["stationMatches"], row["marker"])
                counts[kind] += len(cells)
                rows[kind] += 1
                if len(samples[kind]) < 12:
                    samples[kind].append(
                        {
                            "page": page_number,
                            "y": round(row["y"], 2),
                            "left": row["left"],
                            "stationMatches": row["stationMatches"],
                            "marker": row["marker"],
                            "cellCount": len(cells),
                            "cells": cells[:8],
                        }
                    )
                if kind in ("station-without-marker", "unclassified-text"):
                    stripped = re.sub(r"[0-9…!#$%&\"'\\・.]+", "", row["left"])
                    if stripped:
                        text_fragments[stripped] += len(cells)

    residual = sum(counts.values())
    accounting_gap = total_pdf_time_cells - resolved_by_same_rules - residual
    summary = {
        "totalPdfTimeCells": total_pdf_time_cells,
        "resolvedByMirroredRules": resolved_by_same_rules,
        "residualTimeCells": residual,
        "accountingGap": accounting_gap,
        "residualTimedRows": sum(rows.values()),
        "cellsByClass": dict(counts.most_common()),
        "rowsByClass": dict(rows.most_common()),
        "topResidualTextFragmentsByCells": text_fragments.most_common(40),
        "samples": dict(samples),
        "policy": {
            "diagnosticOnly": True,
            "mirrorsSplitRowSpatialResolution": True,
            "residualRowsBecomeStops": False,
            "clockTimeProximityUsed": False,
            "destinationMatchingUsed": False,
        },
    }
    print("KEIKYU_RESIDUAL_CLASSES=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    if accounting_gap != 0:
        raise RuntimeError(f"residual classifier accounting mismatch: {accounting_gap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())