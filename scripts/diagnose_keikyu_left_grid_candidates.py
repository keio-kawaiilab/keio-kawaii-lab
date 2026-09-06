#!/usr/bin/env python3
"""Measure whether pitch-aligned slots left of the detected Keikyu grid are real train columns.

The existing detector intentionally starts its train-number search at x>165,
which can hide physical columns printed to the left.  This diagnostic does not
extend the grid.  For each pitch-aligned candidate it counts time-like words and
asks whether their Y coordinates coincide with station arrival/departure rows
already proven by canonical station labels and printed row markers.

No clock-time similarity, destination matching, or train identity inference is
used.
"""
from __future__ import annotations

import json
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
    page_count,
)
from probe_keikyu_station_rows import compact_join, marker, station_adjacent_marker, station_matches

MAX_LEFT_SLOTS = 8
X_FRACTION = 0.34
Y_TOLERANCE = 1.6


def proven_operational_ys(words, grid, titles: list[str]) -> list[float]:
    """Return Y positions whose station + row meaning are independently proven."""
    # Keep the label region conservative: only words left of the first currently
    # detected train column can establish station/marker anchors here.
    left_boundary = grid.centers[0] - grid.pitch * 0.55
    raw = []
    for row in cluster_by_y(words, tolerance=1.35):
        y = sum(word.y for word in row) / len(row)
        if y <= grid.header_y + 10:
            continue
        left_words = [word for word in row if word.x < left_boundary]
        left_text = compact_join(left_words) if left_words else ""
        matches = station_matches(left_text, titles) if left_text else []
        row_marker = marker(left_text) if left_text else None
        if len(matches) == 1:
            row_marker = station_adjacent_marker(left_text, matches[0]) or row_marker
        raw.append({"y": y, "matches": matches, "marker": row_marker})

    station_anchors = [row for row in raw if len(row["matches"]) == 1]
    proven: list[float] = []
    for row in raw:
        station = len(row["matches"]) == 1
        if not station and row["marker"] == "arrival":
            station = any(0 < anchor["y"] - row["y"] <= 10.5 for anchor in station_anchors)
        elif not station and row["marker"] == "departure":
            station = any(0 < row["y"] - anchor["y"] <= 10.5 for anchor in station_anchors)
        if station and row["marker"]:
            proven.append(row["y"])
    return proven


def main() -> int:
    titles = station_titles()
    aggregate = {n: Counter() for n in range(1, MAX_LEFT_SLOTS + 1)}
    page_examples: dict[int, list[dict]] = defaultdict(list)

    with tempfile.TemporaryDirectory(prefix="keikyu-left-grid-candidates-") as temp_dir:
        pdf_path = Path(temp_dir) / "schedule_all.pdf"
        download_official_pdf(pdf_path)
        total_pages = page_count(pdf_path)

        pages = 0
        for page_number in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total_pages + 1):
            _width, _height, words = bbox_words(pdf_path, page_number)
            page_text = compact("".join(word.text for word in words))
            if page_scope_reason(page_text):
                continue
            grid = detect_train_column_grid(words)
            if grid is None:
                continue
            pages += 1
            proven_ys = proven_operational_ys(words, grid, titles)

            for n in range(1, MAX_LEFT_SLOTS + 1):
                x = grid.centers[0] - n * grid.pitch
                candidates = [
                    word for word in words
                    if word.y > grid.header_y + 10
                    and TIME_RE.fullmatch(word.text)
                    and abs(word.x - x) <= grid.pitch * X_FRACTION
                ]
                aligned = [
                    word for word in candidates
                    if any(abs(word.y - row_y) <= Y_TOLERANCE for row_y in proven_ys)
                ]
                total = len(candidates)
                aligned_count = len(aligned)
                aggregate[n]["total"] += total
                aggregate[n]["aligned"] += aligned_count
                if total:
                    aggregate[n]["pagesWithCells"] += 1
                if aligned_count:
                    aggregate[n]["pagesWithAlignedCells"] += 1
                if total and len(page_examples[n]) < 12:
                    page_examples[n].append({
                        "page": page_number,
                        "x": round(x, 2),
                        "total": total,
                        "aligned": aligned_count,
                        "ratio": round(aligned_count / total, 4),
                        "sampleAligned": [word.text for word in aligned[:8]],
                        "sampleOther": [word.text for word in candidates if word not in aligned][:8],
                    })

    slots = []
    for n in range(1, MAX_LEFT_SLOTS + 1):
        row = aggregate[n]
        total = row["total"]
        aligned = row["aligned"]
        slots.append({
            "offset": n,
            "totalTimeLikeWords": total,
            "alignedWithProvenStationRows": aligned,
            "alignmentRate": round(aligned / total if total else 0.0, 6),
            "pagesWithCells": row["pagesWithCells"],
            "pagesWithAlignedCells": row["pagesWithAlignedCells"],
            "examples": page_examples[n],
        })

    print("KEIKYU_LEFT_GRID_CANDIDATES=" + json.dumps({
        "pages": pages,
        "slots": slots,
        "policy": {
            "diagnosticOnly": True,
            "gridExtended": False,
            "clockTimeSimilarityUsed": False,
            "destinationMatchingUsed": False,
            "evidence": "candidate X pitch alignment plus Y coincidence with independently proven station arrival/departure rows",
        },
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())