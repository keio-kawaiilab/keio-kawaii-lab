#!/usr/bin/env python3
"""Scan the official Keikyu PDF for strict train-column geometry coverage.

This is a parser-readiness audit for the Keisei/Asakusa/Keikyu through-service
system, not a generic audit of every Keikyu branch. It counts pages where a
regular train-column grid can be proven from PDF geometry, including columns
whose train number is intentionally omitted by the published timetable.
Anonymous columns are never promoted to cross-page train identity.

Two kinds of pages are deliberately excluded by semantic content rather than
page number:
- timetable-guide/index pages ("時刻表の見方")
- Daishi-line-only pages, because Keikyu Daishi has no verified same-train
  through-service edge to the in-scope network and is explicitly outside the
  current system-scope definition.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from keikyu_official_pdf import (
    bbox_words,
    compact,
    detect_train_column_grid,
    download_official_pdf,
    page_count,
    time_cells,
)

FIRST_POSSIBLE_TIMETABLE_PAGE = 6


def page_scope_reason(page_text: str) -> str | None:
    """Return why this page is outside the exact through-system column audit."""
    if "時刻表の見方" in page_text:
        return "guide-index"

    # The Daishi-only sheets are a different multi-block table format. More
    # importantly, Daishi is not in the through-service connected component:
    # no verified same-train edge joins it to Keikyu Main. Do not quietly use
    # this exception for pages that also contain another in-scope line.
    daishi_markers = ("京急大師線", "京急川崎", "小島新田")
    if all(marker in page_text for marker in daishi_markers) and "京急本線" not in page_text:
        return "daishi-line-outside-through-system"
    return None


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="keikyu-column-audit-") as temp_dir:
        pdf_path = Path(temp_dir) / "schedule_all.pdf"
        data = download_official_pdf(pdf_path)
        total_pages = page_count(pdf_path)

        rows = []
        excluded_pages = []
        pages_with_grid = 0
        explicit_columns = 0
        anonymous_columns = 0
        parsed_time_cells = 0
        no_grid_pages = []

        for page_number in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total_pages + 1):
            _width, _height, words = bbox_words(pdf_path, page_number)
            page_text = compact("".join(word.text for word in words))
            excluded_reason = page_scope_reason(page_text)
            if excluded_reason:
                excluded_pages.append({"page": page_number, "reason": excluded_reason})
                continue

            grid = detect_train_column_grid(words)
            looks_like_timetable = "列車番号" in page_text and any(
                token in page_text for token in ("発", "着", "行先", "列車種別")
            )

            if grid is None:
                if looks_like_timetable:
                    no_grid_pages.append(page_number)
                continue

            pages_with_grid += 1
            explicit = sum(1 for value in grid.explicit_numbers if value is not None)
            anonymous = len(grid.centers) - explicit
            times = time_cells(words, grid)
            explicit_columns += explicit
            anonymous_columns += anonymous
            parsed_time_cells += len(times)
            rows.append(
                {
                    "page": page_number,
                    "columns": len(grid.centers),
                    "explicitTrainNumbers": explicit,
                    "anonymousColumns": anonymous,
                    "pitch": round(grid.pitch, 3),
                    "timeCells": len(times),
                    "firstTrainNumber": next((v for v in grid.explicit_numbers if v), None),
                    "lastTrainNumber": next((v for v in reversed(grid.explicit_numbers) if v), None),
                }
            )

        pitches = [row["pitch"] for row in rows]
        report = {
            "version": 2,
            "scope": "Keisei/Asakusa/Keikyu through-service connected component; Daishi excluded",
            "sourceSha256": hashlib.sha256(data).hexdigest(),
            "pdfPages": total_pages,
            "excludedPages": excluded_pages,
            "pagesWithTrainColumnGrid": pages_with_grid,
            "inScopeTimetablePagesWithoutGrid": no_grid_pages,
            "explicitTrainNumberColumns": explicit_columns,
            "anonymousTrainColumns": anonymous_columns,
            "parsedTimeCells": parsed_time_cells,
            "pitchRange": [min(pitches), max(pitches)] if pitches else None,
            "pages": rows,
            "identityPolicy": {
                "pageColumnIsExactLocalIdentity": True,
                "anonymousColumnMayCrossPage": False,
                "anonymousColumnMayCrossOperatorBoundary": False,
                "timeProximityMayJoinColumns": False,
                "destinationAloneMayJoinColumns": False,
                "outOfScopeLineMayCountTowardCompletion": False,
            },
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))

        if not rows:
            raise RuntimeError("no in-scope Keikyu train-column grids detected")
        if no_grid_pages:
            raise RuntimeError(
                "in-scope pages look like timetables but have no proven train-column grid: "
                + ",".join(map(str, no_grid_pages))
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
