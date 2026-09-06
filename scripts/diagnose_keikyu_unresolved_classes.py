#!/usr/bin/env python3
"""Classify unresolved Keikyu PDF time cells without guessing their meaning.

This diagnostic does not turn any residual row into a stop. It only measures
which printed structures remain after canonical station + arrival/departure
resolution, so each remaining format can be implemented deliberately.
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
)
from probe_keikyu_station_rows import compact_join, marker, station_adjacent_marker, station_matches


def category(left_text: str, matches: list[str], row_marker: str | None) -> str:
    if len(matches) > 1:
        return "ambiguous-station-title"
    if len(matches) == 1 and row_marker is None:
        return "station-without-marker"
    if not matches and row_marker is not None:
        return "marker-without-station"
    if "前の掲載ページ" in left_text:
        return "continuation-heading"
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
            left_boundary = grid.centers[0] - grid.pitch * 0.55

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
                if not cells:
                    continue

                matches = station_matches(left_text, titles) if left_text else []
                row_marker = marker(left_text) if left_text else None
                if len(matches) == 1:
                    row_marker = station_adjacent_marker(left_text, matches[0]) or row_marker
                if len(matches) == 1 and row_marker is not None:
                    continue

                kind = category(left_text, matches, row_marker)
                counts[kind] += len(cells)
                rows[kind] += 1
                if len(samples[kind]) < 8:
                    samples[kind].append(
                        {
                            "page": page_number,
                            "y": round(y, 2),
                            "left": left_text,
                            "stationMatches": matches,
                            "marker": row_marker,
                            "cellCount": len(cells),
                            "cells": cells[:6],
                        }
                    )
                if kind in ("station-without-marker", "unclassified-text"):
                    stripped = re.sub(r"[0-9…!#$%&\"'\\・.]+", "", left_text)
                    if stripped:
                        text_fragments[stripped] += len(cells)

    summary = {
        "residualTimeCells": sum(counts.values()),
        "residualTimedRows": sum(rows.values()),
        "cellsByClass": dict(counts.most_common()),
        "rowsByClass": dict(rows.most_common()),
        "topResidualTextFragmentsByCells": text_fragments.most_common(30),
        "samples": {key: value for key, value in samples.items()},
        "policy": {
            "diagnosticOnly": True,
            "residualRowsBecomeStops": False,
            "clockTimeProximityUsed": False,
            "destinationMatchingUsed": False,
        },
    }
    print("KEIKYU_RESIDUAL_CLASSES=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())