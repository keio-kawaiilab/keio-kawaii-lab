#!/usr/bin/env python3
"""Build page-local Keikyu stop-time fragments from the official full timetable PDF.

This builder deliberately stops before cross-page physical-train identity.  A
fragment is exactly one proven physical train column on one PDF page.  Printed
train numbers are preserved as metadata but never used to join fragments.

The generated JSON is intended for ephemeral CI/research use until a separate
strict identity layer can prove which fragments are the same physical train.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from audit_keikyu_official_columns import FIRST_POSSIBLE_TIMETABLE_PAGE, page_scope_reason
from audit_keikyu_station_time_resolution import resolve_page
from keikyu_connected_station_catalog import station_titles
from keikyu_official_pdf import (
    OFFICIAL_PDF_URL,
    bbox_words,
    compact,
    detect_train_column_grid,
    download_official_pdf,
    page_count,
)


def fragment_id(page_number: int, column: int) -> str:
    return f"keikyu-official-pdf:p{page_number:03d}:c{column:02d}"


def build_page_fragments(
    page_number: int,
    grid,
    resolved_records: list[dict[str, Any]],
    unresolved_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group semantic cell records only by exact page-local physical column."""
    by_column: dict[int, dict[str, list[dict[str, Any]]]] = {
        index: {"resolved": [], "unresolved": []}
        for index in range(len(grid.centers))
    }
    for record in resolved_records:
        column = int(record["column"])
        if column not in by_column:
            raise RuntimeError(f"resolved cell references unknown column {column} on page {page_number}")
        by_column[column]["resolved"].append(record)
    for record in unresolved_records:
        column = int(record["column"])
        if column not in by_column:
            raise RuntimeError(f"unresolved cell references unknown column {column} on page {page_number}")
        by_column[column]["unresolved"].append(record)

    fragments: list[dict[str, Any]] = []
    for column in range(len(grid.centers)):
        explicit_number = grid.explicit_numbers[column]
        resolved = sorted(by_column[column]["resolved"], key=lambda item: (float(item["y"]), float(item["x"])))
        unresolved = sorted(by_column[column]["unresolved"], key=lambda item: (float(item["y"]), float(item["x"])))
        fragments.append(
            {
                "id": fragment_id(page_number, column),
                "page": page_number,
                "column": column,
                "columnCenterX": round(float(grid.centers[column]), 3),
                "printedTrainNumber": explicit_number,
                "anonymousColumn": explicit_number is None,
                "stopTimes": [
                    {
                        "station": item["station"],
                        "event": item["event"],
                        "time": item["time"],
                        "rowY": item["y"],
                        "resolution": item["resolution"],
                    }
                    for item in resolved
                ],
                "unresolvedCells": [
                    {
                        "time": item["time"],
                        "rowY": item["y"],
                        "left": item.get("left", ""),
                        "marker": item.get("marker"),
                        "stationMatches": item.get("stationMatches") or [],
                    }
                    for item in unresolved
                ],
            }
        )
    return fragments


def build_dataset(pdf_path: Path, source_bytes: bytes) -> dict[str, Any]:
    titles = station_titles()
    if not titles:
        raise RuntimeError("no canonical connected-system station titles loaded")

    total_pages = page_count(pdf_path)
    fragments: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    excluded_pages: list[dict[str, Any]] = []
    totals = {
        "sourceTimeCells": 0,
        "resolvedTimeCells": 0,
        "unresolvedTimeCells": 0,
        "trainColumnFragments": 0,
        "explicitTrainNumberFragments": 0,
        "anonymousFragments": 0,
    }

    for page_number in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total_pages + 1):
        _width, _height, words = bbox_words(pdf_path, page_number)
        page_text = compact("".join(word.text for word in words))
        excluded_reason = page_scope_reason(page_text)
        if excluded_reason:
            excluded_pages.append({"page": page_number, "reason": excluded_reason})
            continue

        grid = detect_train_column_grid(words)
        if grid is None:
            continue

        resolution = resolve_page(words, grid, titles, include_records=True)
        record_gap = int(resolution.get("recordAccountingGap", 0))
        if record_gap != 0:
            raise RuntimeError(
                f"page {page_number} semantic records do not account for all unresolved cells: gap={record_gap}"
            )

        page_fragments = build_page_fragments(
            page_number,
            grid,
            resolution["resolvedCellRecords"],
            resolution["unresolvedCellRecords"],
        )
        resolved_count = sum(len(item["stopTimes"]) for item in page_fragments)
        unresolved_count = sum(len(item["unresolvedCells"]) for item in page_fragments)
        if resolved_count != int(resolution["resolvedTimeCells"]):
            raise RuntimeError(f"page {page_number} resolved-cell generation mismatch")
        if unresolved_count != int(resolution["unresolvedTimeCells"]):
            raise RuntimeError(f"page {page_number} unresolved-cell generation mismatch")

        fragments.extend(page_fragments)
        explicit = sum(1 for item in page_fragments if not item["anonymousColumn"])
        anonymous = len(page_fragments) - explicit
        pages.append(
            {
                "page": page_number,
                "fragmentCount": len(page_fragments),
                "sourceTimeCells": int(resolution["timeCells"]),
                "resolvedTimeCells": resolved_count,
                "unresolvedTimeCells": unresolved_count,
                "resolutionCounts": resolution["resolutionCounts"],
            }
        )
        totals["sourceTimeCells"] += int(resolution["timeCells"])
        totals["resolvedTimeCells"] += resolved_count
        totals["unresolvedTimeCells"] += unresolved_count
        totals["trainColumnFragments"] += len(page_fragments)
        totals["explicitTrainNumberFragments"] += explicit
        totals["anonymousFragments"] += anonymous

    if not pages:
        raise RuntimeError("no in-scope Keikyu timetable pages generated")
    if totals["resolvedTimeCells"] + totals["unresolvedTimeCells"] != totals["sourceTimeCells"]:
        raise RuntimeError("dataset stop-time accounting mismatch")

    return {
        "version": 1,
        "kind": "keikyu-official-page-local-stop-times",
        "scope": "Keisei/Asakusa/Keikyu connected component; Keikyu Daishi excluded",
        "source": {
            "url": OFFICIAL_PDF_URL,
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "pdfPages": total_pages,
        },
        "canonicalStationTitleCount": len(titles),
        "excludedPages": excluded_pages,
        "pages": pages,
        "totals": totals,
        "fragments": fragments,
        "identityPolicy": {
            "pageColumnIsExactLocalIdentity": True,
            "printedTrainNumberMayJoinPages": False,
            "anonymousColumnMayJoinPages": False,
            "clockTimeProximityMayJoinFragments": False,
            "destinationMayJoinFragments": False,
            "crossPageIdentityEstablished": False,
            "runtimeSameTrainPromotions": 0,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, help="Use an already-downloaded official PDF")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.pdf:
        pdf_path = args.pdf
        source_bytes = pdf_path.read_bytes()
        if not source_bytes.startswith(b"%PDF"):
            raise RuntimeError("--pdf is not a PDF")
        dataset = build_dataset(pdf_path, source_bytes)
    else:
        with tempfile.TemporaryDirectory(prefix="keikyu-stop-times-") as temp_dir:
            pdf_path = Path(temp_dir) / "schedule_all.pdf"
            source_bytes = download_official_pdf(pdf_path)
            dataset = build_dataset(pdf_path, source_bytes)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    summary = {
        "output": str(args.output),
        "sourceSha256": dataset["source"]["sha256"],
        "pages": len(dataset["pages"]),
        **dataset["totals"],
        "runtimeSameTrainPromotions": 0,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
