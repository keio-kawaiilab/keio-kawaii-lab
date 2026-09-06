#!/usr/bin/env python3
"""Locate the printed timetable-grid divider from Keikyu header labels.

This diagnostic exists because omitted train numbers can occur before the first
explicit number, while the station-name / operating-km area on the far left also
contains time-like numeric text.  It measures where the printed 「列車番号」
header label ends relative to the selected train-number header and the inferred
15.6pt column phase.  No production grid is changed here.
"""
from __future__ import annotations

import json
import statistics
import tempfile
from pathlib import Path

from audit_keikyu_official_columns import FIRST_POSSIBLE_TIMETABLE_PAGE, page_scope_reason
from keikyu_official_pdf import (
    _candidate_header_rows,
    bbox_words,
    cluster_by_y,
    compact,
    download_official_pdf,
    page_count,
)


def select_header(words):
    candidates = _candidate_header_rows(words)
    if not candidates:
        return None

    def score(row):
        xs = [word.x for word in row]
        diffs = [b - a for a, b in zip(xs, xs[1:]) if b > a]
        regularity = statistics.pstdev(diffs) if len(diffs) >= 2 else 999.0
        return (len(row), -regularity, -statistics.median(word.y for word in row))

    return max(candidates, key=score)


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory(prefix="keikyu-header-divider-") as temp_dir:
        pdf_path = Path(temp_dir) / "schedule_all.pdf"
        download_official_pdf(pdf_path)
        total_pages = page_count(pdf_path)

        for page_number in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total_pages + 1):
            _width, _height, words = bbox_words(pdf_path, page_number)
            page_text = compact("".join(word.text for word in words))
            if page_scope_reason(page_text):
                continue
            header = select_header(words)
            if not header:
                continue

            header_y = statistics.median(word.y for word in header)
            first_x = min(word.x for word in header)
            labels = [
                word for word in words
                if "列車番号" in word.text and word.x < first_x and abs(word.y - header_y) <= 50
            ]
            labels.sort(key=lambda word: (abs(word.y - header_y), -word.x_max))
            chosen = labels[0] if labels else None

            nearby_text = []
            for row in cluster_by_y(words, tolerance=1.35):
                y = statistics.median(word.y for word in row)
                if abs(y - header_y) > 18:
                    continue
                text = "".join(word.text for word in sorted(row, key=lambda word: word.x))
                if text:
                    nearby_text.append({"y": round(y, 2), "text": text[:160]})

            rows.append({
                "page": page_number,
                "headerY": round(header_y, 2),
                "firstExplicitX": round(first_x, 2),
                "selectedLabel": None if chosen is None else {
                    "text": chosen.text,
                    "xMin": round(chosen.x_min, 2),
                    "xMax": round(chosen.x_max, 2),
                    "y": round(chosen.y, 2),
                    "yDelta": round(chosen.y - header_y, 2),
                    "gapToFirstExplicit": round(first_x - chosen.x_max, 2),
                },
                "labelCandidates": [
                    {
                        "text": word.text,
                        "xMin": round(word.x_min, 2),
                        "xMax": round(word.x_max, 2),
                        "y": round(word.y, 2),
                    }
                    for word in labels[:5]
                ],
                "nearbyRows": nearby_text[:8],
            })

    with_label = [row for row in rows if row["selectedLabel"]]
    gaps = [row["selectedLabel"]["gapToFirstExplicit"] for row in with_label]
    summary = {
        "pages": len(rows),
        "pagesWithNearbyTrainNumberLabel": len(with_label),
        "gapRange": [min(gaps), max(gaps)] if gaps else None,
        "sample": rows[:20],
        "missingLabelPages": [row["page"] for row in rows if not row["selectedLabel"]][:40],
        "policy": {
            "diagnosticOnly": True,
            "productionGridChanged": False,
            "clockTimeProximityUsed": False,
        },
    }
    print("KEIKYU_HEADER_DIVIDERS=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())