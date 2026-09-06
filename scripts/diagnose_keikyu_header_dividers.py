#!/usr/bin/env python3
"""Audit the *printed* Keikyu train-number header rows on every timetable page.

The production detector historically chose the densest numeric row.  That is
unsafe because a busy station-time row can contain more HHMM values than the
actual train-number header.  This diagnostic instead anchors on the literal
printed 「列車番号」 label, inventories every matching row near the top of the
page, and tests the rule that the lower such row is the main timetable header
(the upper one, when present, belongs to 「前の掲載ページ」 continuation data).

Diagnostic only: it does not modify the production grid and never uses time
proximity or destination matching.
"""
from __future__ import annotations

import json
import statistics
import tempfile
from pathlib import Path

from audit_keikyu_official_columns import FIRST_POSSIBLE_TIMETABLE_PAGE, page_scope_reason
from keikyu_official_pdf import (
    TRAIN_NUMBER_RE,
    bbox_words,
    cluster_by_y,
    compact,
    download_official_pdf,
    page_count,
)

TOP_HEADER_LIMIT = 150.0


def row_text(row) -> str:
    return compact("".join(word.text for word in sorted(row, key=lambda word: word.x)))


def explicit_train_tokens(row) -> list:
    # x>80 removes the left-hand label/reference cells while keeping the actual
    # train columns in all observed timetable layouts.  This is diagnostic only;
    # production will derive the column phase separately.
    return [
        word for word in row
        if word.x > 80 and TRAIN_NUMBER_RE.fullmatch(word.text)
    ]


def pitch_hint(tokens) -> float | None:
    xs = sorted(word.x for word in tokens)
    diffs = [b - a for a, b in zip(xs, xs[1:]) if 5 < b - a < 100]
    if not diffs:
        return None
    # The true column pitch is the common smallest spacing; explicit train
    # numbers may skip anonymous columns, so report the lower quartile rather
    # than treating every gap as adjacent.
    diffs.sort()
    take = max(1, len(diffs) // 4)
    return statistics.median(diffs[:take])


def main() -> int:
    pages = []
    with tempfile.TemporaryDirectory(prefix="keikyu-printed-header-audit-") as temp_dir:
        pdf_path = Path(temp_dir) / "schedule_all.pdf"
        download_official_pdf(pdf_path)
        total_pages = page_count(pdf_path)

        for page_number in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total_pages + 1):
            _width, _height, words = bbox_words(pdf_path, page_number)
            page_text = compact("".join(word.text for word in words))
            if page_scope_reason(page_text):
                continue

            candidates = []
            for row in cluster_by_y(words, tolerance=1.35):
                y = statistics.median(word.y for word in row)
                text = row_text(row)
                if y > TOP_HEADER_LIMIT or "列車番号" not in text:
                    continue
                tokens = explicit_train_tokens(row)
                candidates.append({
                    "y": round(y, 2),
                    "text": text[:180],
                    "explicitCount": len(tokens),
                    "firstExplicitX": round(min((word.x for word in tokens), default=0.0), 2) if tokens else None,
                    "lastExplicitX": round(max((word.x for word in tokens), default=0.0), 2) if tokens else None,
                    "pitchHint": None if not tokens else (None if pitch_hint(tokens) is None else round(pitch_hint(tokens), 3)),
                    "tokens": [word.text for word in sorted(tokens, key=lambda word: word.x)[:30]],
                })

            # The official layout prints the previous-page train-number band
            # above the main train-number band.  Therefore choose the lower
            # printed 「列車番号」 row, never the numerically densest arbitrary row.
            selected = max(candidates, key=lambda item: item["y"]) if candidates else None
            pages.append({
                "page": page_number,
                "candidateCount": len(candidates),
                "candidates": candidates,
                "selected": selected,
            })

    selected = [page["selected"] for page in pages if page["selected"]]
    no_label = [page["page"] for page in pages if not page["selected"]]
    no_numbers = [page["page"] for page in pages if page["selected"] and page["selected"]["explicitCount"] == 0]
    low_number_count = [
        page["page"] for page in pages
        if page["selected"] and 0 < page["selected"]["explicitCount"] < 3
    ]
    selected_ys = [item["y"] for item in selected]
    counts = [item["explicitCount"] for item in selected]

    summary = {
        "pages": len(pages),
        "pagesWithPrintedHeader": len(selected),
        "pagesWithoutPrintedHeader": no_label,
        "pagesSelectedHeaderHasNoExplicitTrainNumber": no_numbers,
        "pagesSelectedHeaderHasFewerThan3ExplicitTrainNumbers": low_number_count,
        "selectedHeaderYRange": [min(selected_ys), max(selected_ys)] if selected_ys else None,
        "selectedExplicitCountRange": [min(counts), max(counts)] if counts else None,
        "candidateCountDistribution": {
            str(value): sum(1 for page in pages if page["candidateCount"] == value)
            for value in sorted({page["candidateCount"] for page in pages})
        },
        "sample": pages[:30],
        "policy": {
            "diagnosticOnly": True,
            "productionGridChanged": False,
            "printedTrainNumberLabelRequired": True,
            "lowerPrintedHeaderPreferred": True,
            "clockTimeProximityUsed": False,
            "destinationMatchingUsed": False,
        },
    }
    print("KEIKYU_PRINTED_HEADER_AUDIT=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())