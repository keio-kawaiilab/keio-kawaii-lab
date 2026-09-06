#!/usr/bin/env python3
"""Audit station + arrival/departure resolution for every in-scope Keikyu timetable page.

This intentionally measures semantic parser coverage separately from train identity.
A time cell is considered resolved only when PDF structure proves both a canonical
station in the verified Keisei/Asakusa/Keikyu connected component and the
operational row meaning. No clock-time proximity, destination matching, or
cross-page inference is permitted here.

``resolve_page(..., include_records=True)`` is also the single semantic source for
the structured stop-time builder. Keeping audit and generation on the same
resolver prevents the generated dataset from silently using weaker rules.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

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
from probe_keikyu_station_rows import (
    compact_join,
    marker,
    semantic_label_boundary,
    station_adjacent_marker,
    station_matches,
)


def resolve_page(words, grid, titles: list[str], *, include_records: bool = False) -> dict[str, Any]:
    """Resolve printed timetable cells without establishing train identity.

    When ``include_records`` is true, each semantically proven cell is returned
    with its page-local physical column.  Callers must still treat that column as
    local identity only; this function deliberately has no page number and no
    cross-page joining logic.
    """
    label_boundary = semantic_label_boundary(words, grid)
    raw_rows: list[dict[str, Any]] = []

    for row in cluster_by_y(words, tolerance=1.35):
        y = sum(word.y for word in row) / len(row)
        if y <= grid.header_y + 10:
            continue

        left_words = [
            word for word in row
            if word.x < label_boundary and not TIME_RE.fullmatch(word.text)
        ]
        left_text = compact_join(left_words) if left_words else ""
        cells = []
        for word in row:
            if not TIME_RE.fullmatch(word.text):
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

    resolved_rows = 0
    resolved_cells = 0
    unresolved_rows: list[dict[str, Any]] = []
    resolution_counts: dict[str, int] = {}
    resolved_records: list[dict[str, Any]] = []
    unresolved_records: list[dict[str, Any]] = []

    for row in raw_rows:
        if not row["cells"]:
            continue

        station = None
        resolution = None
        if len(row["stationMatches"]) == 1:
            station = row["stationMatches"][0]
            resolution = "same-row-station-title"
        elif len(row["stationMatches"]) > 1:
            resolution = "ambiguous-same-row-station-title"
        elif row["marker"] == "arrival":
            candidates = [anchor for anchor in station_anchors if 0 < anchor["y"] - row["y"] <= 10.5]
            if candidates:
                closest = min(candidates, key=lambda anchor: anchor["y"] - row["y"])
                station = closest["station"]
                resolution = "arrival-row-to-following-station-title"
        elif row["marker"] == "departure":
            candidates = [anchor for anchor in station_anchors if 0 < row["y"] - anchor["y"] <= 10.5]
            if candidates:
                closest = min(candidates, key=lambda anchor: row["y"] - anchor["y"])
                station = closest["station"]
                resolution = "departure-row-to-preceding-station-title"

        if station and row["marker"]:
            resolved_rows += 1
            resolved_cells += len(row["cells"])
            resolution_counts[resolution or "unknown"] = resolution_counts.get(resolution or "unknown", 0) + len(row["cells"])
            if include_records:
                for cell in row["cells"]:
                    resolved_records.append(
                        {
                            "column": cell["column"],
                            "station": station,
                            "event": row["marker"],
                            "time": cell["text"],
                            "x": cell["x"],
                            "y": round(row["y"], 2),
                            "resolution": resolution,
                        }
                    )
        else:
            unresolved_rows.append(
                {
                    "y": round(row["y"], 2),
                    "left": row["left"],
                    "marker": row["marker"],
                    "stationMatches": row["stationMatches"],
                    "cellCount": len(row["cells"]),
                    "sampleCells": row["cells"][:6],
                }
            )
            if include_records:
                for cell in row["cells"]:
                    unresolved_records.append(
                        {
                            "column": cell["column"],
                            "time": cell["text"],
                            "x": cell["x"],
                            "y": round(row["y"], 2),
                            "left": row["left"],
                            "marker": row["marker"],
                            "stationMatches": row["stationMatches"],
                        }
                    )

    all_cells = time_cells(words, grid)
    unresolved_cells = len(all_cells) - resolved_cells
    result: dict[str, Any] = {
        "timeCells": len(all_cells),
        "resolvedTimeCells": resolved_cells,
        "unresolvedTimeCells": unresolved_cells,
        "resolvedTimedRows": resolved_rows,
        "unresolvedTimedRows": len(unresolved_rows),
        "resolutionCounts": resolution_counts,
        "unresolvedSample": unresolved_rows[:8],
    }
    if include_records:
        result["resolvedCellRecords"] = resolved_records
        result["unresolvedCellRecords"] = unresolved_records
        result["recordAccountingGap"] = unresolved_cells - len(unresolved_records)
    return result


def main() -> int:
    titles = station_titles()
    if not titles:
        raise RuntimeError("no canonical connected-system station titles loaded")

    with tempfile.TemporaryDirectory(prefix="keikyu-station-time-audit-") as temp_dir:
        pdf_path = Path(temp_dir) / "schedule_all.pdf"
        data = download_official_pdf(pdf_path)
        total_pages = page_count(pdf_path)

        page_reports = []
        skipped = []
        totals = {
            "timeCells": 0,
            "resolvedTimeCells": 0,
            "unresolvedTimeCells": 0,
            "resolvedTimedRows": 0,
            "unresolvedTimedRows": 0,
        }
        aggregate_resolution_counts: dict[str, int] = {}

        for page_number in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total_pages + 1):
            _width, _height, words = bbox_words(pdf_path, page_number)
            page_text = compact("".join(word.text for word in words))
            excluded_reason = page_scope_reason(page_text)
            if excluded_reason:
                skipped.append({"page": page_number, "reason": excluded_reason})
                continue

            grid = detect_train_column_grid(words)
            if grid is None:
                continue

            result = resolve_page(words, grid, titles)
            report = {"page": page_number, **result}
            page_reports.append(report)
            for key in totals:
                totals[key] += int(result[key])
            for key, value in result["resolutionCounts"].items():
                aggregate_resolution_counts[key] = aggregate_resolution_counts.get(key, 0) + value

        if not page_reports:
            raise RuntimeError("no in-scope Keikyu timetable pages audited")
        if totals["resolvedTimeCells"] + totals["unresolvedTimeCells"] != totals["timeCells"]:
            raise RuntimeError("station-time accounting mismatch")

        pages_with_unresolved = [row for row in page_reports if row["unresolvedTimeCells"] > 0]
        zero_resolution_pages = [
            row["page"]
            for row in page_reports
            if row["timeCells"] > 0 and row["resolvedTimeCells"] == 0
        ]
        worst_pages = sorted(
            page_reports,
            key=lambda row: (
                row["resolvedTimeCells"] / row["timeCells"] if row["timeCells"] else 1.0,
                -row["unresolvedTimeCells"],
            ),
        )[:15]
        resolution_rate = totals["resolvedTimeCells"] / totals["timeCells"] if totals["timeCells"] else 0.0

        output = {
            "version": 6,
            "scope": "Keisei/Asakusa/Keikyu connected component; Keikyu Daishi excluded",
            "sourceSha256": hashlib.sha256(data).hexdigest(),
            "canonicalStationTitleCount": len(titles),
            "pagesAudited": len(page_reports),
            "excludedPages": skipped,
            **totals,
            "resolutionRate": round(resolution_rate, 6),
            "pagesWithUnresolvedTimeCells": len(pages_with_unresolved),
            "pagesWithZeroResolvedTimeCells": zero_resolution_pages,
            "resolutionCounts": aggregate_resolution_counts,
            "worstPages": [
                {
                    "page": row["page"],
                    "timeCells": row["timeCells"],
                    "resolvedTimeCells": row["resolvedTimeCells"],
                    "unresolvedTimeCells": row["unresolvedTimeCells"],
                    "resolutionRate": round(row["resolvedTimeCells"] / row["timeCells"] if row["timeCells"] else 1.0, 6),
                    "unresolvedSample": row["unresolvedSample"],
                }
                for row in worst_pages
            ],
            "policy": {
                "canonicalConnectedSystemStationRequired": True,
                "printedArrivalDepartureStructureRequired": True,
                "stationLabelBandIndependentOfTrainGridEdge": True,
                "operationMarkerBandProvenFromRepeatedGeometry": True,
                "stationAdjacentMarkerMayResolveRow": True,
                "clockTimeProximityMayResolveStation": False,
                "destinationMayResolveStation": False,
                "crossPageIdentityEstablishedHere": False,
                "structuredBuilderUsesThisResolver": True,
            },
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

        if zero_resolution_pages:
            raise RuntimeError(
                "in-scope timetable pages have zero semantically resolved time cells: "
                + ",".join(map(str, zero_resolution_pages))
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
