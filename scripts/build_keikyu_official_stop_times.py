#!/usr/bin/env python3
"""Build section-local Keikyu stop-time fragments from the official full timetable PDF.

A physical fragment is one proven train column inside one independently detected
printed timetable section on one PDF page.  Printed train numbers are preserved
as metadata but never used here to join sections or pages.
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
    detect_train_column_sections,
    download_official_pdf,
    page_count,
)


def fragment_id(page_number: int, section: int, column: int) -> str:
    return f"keikyu-official-pdf:p{page_number:03d}:s{section:02d}:c{column:02d}"


def build_section_fragments(
    page_number: int,
    section_index: int,
    header_ordinal: int,
    y_min: float,
    y_max: float,
    grid,
    resolved_records: list[dict[str, Any]],
    unresolved_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_column: dict[int, dict[str, list[dict[str, Any]]]] = {
        index: {"resolved": [], "unresolved": []}
        for index in range(len(grid.centers))
    }
    for record in resolved_records:
        column = int(record["column"])
        if column not in by_column:
            raise RuntimeError(
                f"resolved cell references unknown column {column} on page {page_number} section {section_index}"
            )
        by_column[column]["resolved"].append(record)
    for record in unresolved_records:
        column = int(record["column"])
        if column not in by_column:
            raise RuntimeError(
                f"unresolved cell references unknown column {column} on page {page_number} section {section_index}"
            )
        by_column[column]["unresolved"].append(record)

    fragments: list[dict[str, Any]] = []
    for column in range(len(grid.centers)):
        explicit_number = grid.explicit_numbers[column]
        resolved = sorted(by_column[column]["resolved"], key=lambda item: (float(item["y"]), float(item["x"])))
        unresolved = sorted(by_column[column]["unresolved"], key=lambda item: (float(item["y"]), float(item["x"])))
        fragments.append(
            {
                "id": fragment_id(page_number, section_index, column),
                "page": page_number,
                "section": section_index,
                "headerOrdinal": header_ordinal,
                "sectionYMin": round(float(y_min), 3),
                "sectionYMax": round(float(y_max), 3),
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
        "timetableSections": 0,
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

        sections = detect_train_column_sections(words)
        if not sections:
            continue

        page_section_rows: list[dict[str, Any]] = []
        page_resolved = 0
        page_unresolved = 0
        page_cells = 0
        page_fragment_count = 0

        for section in sections:
            resolution = resolve_page(list(section.words), section.grid, titles, include_records=True)
            record_gap = int(resolution.get("recordAccountingGap", 0))
            if record_gap != 0:
                raise RuntimeError(
                    f"page {page_number} section {section.section_index} semantic accounting gap={record_gap}"
                )

            section_fragments = build_section_fragments(
                page_number,
                section.section_index,
                section.header_ordinal,
                section.y_min,
                section.y_max,
                section.grid,
                resolution["resolvedCellRecords"],
                resolution["unresolvedCellRecords"],
            )
            resolved_count = sum(len(item["stopTimes"]) for item in section_fragments)
            unresolved_count = sum(len(item["unresolvedCells"]) for item in section_fragments)
            if resolved_count != int(resolution["resolvedTimeCells"]):
                raise RuntimeError(
                    f"page {page_number} section {section.section_index} resolved-cell generation mismatch"
                )
            if unresolved_count != int(resolution["unresolvedTimeCells"]):
                raise RuntimeError(
                    f"page {page_number} section {section.section_index} unresolved-cell generation mismatch"
                )

            fragments.extend(section_fragments)
            explicit = sum(1 for item in section_fragments if not item["anonymousColumn"])
            anonymous = len(section_fragments) - explicit
            page_section_rows.append(
                {
                    "section": section.section_index,
                    "headerOrdinal": section.header_ordinal,
                    "yMin": round(float(section.y_min), 3),
                    "yMax": round(float(section.y_max), 3),
                    "fragmentCount": len(section_fragments),
                    "sourceTimeCells": int(resolution["timeCells"]),
                    "resolvedTimeCells": resolved_count,
                    "unresolvedTimeCells": unresolved_count,
                    "resolutionCounts": resolution["resolutionCounts"],
                }
            )

            page_cells += int(resolution["timeCells"])
            page_resolved += resolved_count
            page_unresolved += unresolved_count
            page_fragment_count += len(section_fragments)
            totals["timetableSections"] += 1
            totals["sourceTimeCells"] += int(resolution["timeCells"])
            totals["resolvedTimeCells"] += resolved_count
            totals["unresolvedTimeCells"] += unresolved_count
            totals["trainColumnFragments"] += len(section_fragments)
            totals["explicitTrainNumberFragments"] += explicit
            totals["anonymousFragments"] += anonymous

        pages.append(
            {
                "page": page_number,
                "sectionCount": len(page_section_rows),
                "fragmentCount": page_fragment_count,
                "sourceTimeCells": page_cells,
                "resolvedTimeCells": page_resolved,
                "unresolvedTimeCells": page_unresolved,
                "sections": page_section_rows,
            }
        )

    if not pages:
        raise RuntimeError("no in-scope Keikyu timetable sections generated")
    if totals["resolvedTimeCells"] + totals["unresolvedTimeCells"] != totals["sourceTimeCells"]:
        raise RuntimeError("dataset stop-time accounting mismatch")
    ids = [str(item.get("id") or "") for item in fragments]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise RuntimeError("duplicate or missing section-local fragment id")

    return {
        "version": 2,
        "kind": "keikyu-official-section-local-stop-times",
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
            "pageSectionColumnIsExactLocalIdentity": True,
            "literalTrainNumberRowsAreHardSectionBoundaries": True,
            "minimumDistinctTimedRowsPerIdentitySection": 3,
            "printedTrainNumberMayJoinSectionsOrPages": False,
            "anonymousColumnMayJoinSectionsOrPages": False,
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
