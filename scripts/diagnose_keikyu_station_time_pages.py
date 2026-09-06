#!/usr/bin/env python3
"""Print a compact diagnostic for Keikyu station/time semantic resolution.

Unlike the strict audit, this command never treats unresolved pages as success
criteria. It exists only so CI logs clearly expose which printed page layouts
still need parser support. Same-train identity is deliberately out of scope.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from audit_keikyu_official_columns import FIRST_POSSIBLE_TIMETABLE_PAGE, page_scope_reason
from audit_keikyu_station_time_resolution import resolve_page
from keikyu_connected_station_catalog import station_titles
from keikyu_official_pdf import (
    bbox_words,
    compact,
    detect_train_column_grid,
    download_official_pdf,
    page_count,
)


def main() -> int:
    titles = station_titles()
    with tempfile.TemporaryDirectory(prefix="keikyu-semantic-diagnose-") as temp_dir:
        pdf_path = Path(temp_dir) / "schedule_all.pdf"
        download_official_pdf(pdf_path)
        total_pages = page_count(pdf_path)

        rows = []
        for page_number in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total_pages + 1):
            _width, _height, words = bbox_words(pdf_path, page_number)
            page_text = compact("".join(word.text for word in words))
            if page_scope_reason(page_text):
                continue
            grid = detect_train_column_grid(words)
            if grid is None:
                continue
            result = resolve_page(words, grid, titles)
            rate = (
                result["resolvedTimeCells"] / result["timeCells"]
                if result["timeCells"]
                else 1.0
            )
            rows.append(
                {
                    "page": page_number,
                    "time": result["timeCells"],
                    "resolved": result["resolvedTimeCells"],
                    "unresolved": result["unresolvedTimeCells"],
                    "rate": round(rate, 4),
                    "sample": result["unresolvedSample"][:3],
                }
            )

        zero = [row for row in rows if row["time"] and row["resolved"] == 0]
        worst = sorted(rows, key=lambda row: (row["rate"], -row["unresolved"]))[:12]
        total = sum(row["time"] for row in rows)
        resolved = sum(row["resolved"] for row in rows)
        unresolved = sum(row["unresolved"] for row in rows)
        summary = {
            "stationCatalogTitles": len(titles),
            "pages": len(rows),
            "timeCells": total,
            "resolved": resolved,
            "unresolved": unresolved,
            "rate": round(resolved / total if total else 0.0, 6),
            "zeroPages": [row["page"] for row in zero],
            "worstPages": worst,
        }
        print("KEIKYU_SEMANTIC_DIAGNOSTIC=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
