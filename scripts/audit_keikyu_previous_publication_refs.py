#!/usr/bin/env python3
"""Audit Keikyu's explicit previous-publication references without promoting identity.

The official full timetable prints, above the main train-number row, an explicit
"前の掲載ページ" row and (when applicable) the train number used on that previous
published page.  These are much stronger evidence than clock-time proximity, but
this audit intentionally stops before runtime same-train promotion.

Output is designed for ephemeral CI/research use.  It inventories every parsed
page-local column, preserves partial references, maps printed page numbers to PDF
pages only when the printed page number is uniquely detected, and reports whether
(page, previous train number) resolves to a unique page-local target.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import tempfile
from pathlib import Path
from typing import Any

from audit_keikyu_official_columns import FIRST_POSSIBLE_TIMETABLE_PAGE, page_scope_reason
from keikyu_official_pdf import (
    TRAIN_NUMBER_RE,
    TrainColumnGrid,
    Word,
    _label_span,
    _main_printed_header,
    _printed_train_number_rows,
    bbox_words,
    cluster_by_y,
    compact,
    detect_train_column_grid,
    download_official_pdf,
    nearest_column,
    page_count,
)

PRINTED_PAGE_RE = re.compile(r"^(\d{1,3})(?:ページ)?$")


def _row_y(row: list[Word]) -> float:
    return float(statistics.median(word.y for word in row))


def _assign_tokens(
    row: list[Word] | None,
    grid: TrainColumnGrid,
    *,
    label: str,
    parser,
) -> list[Any | None]:
    values: list[Any | None] = [None] * len(grid.centers)
    if row is None:
        return values
    span = _label_span(row, label)
    if span is None:
        return values
    label_x_max = span[1]
    for word in row:
        if word.x <= label_x_max:
            continue
        value = parser(word.text)
        if value is None:
            continue
        column = nearest_column(grid, word.x, max_fraction=0.34)
        if column is None:
            continue
        if values[column] is not None and values[column] != value:
            raise RuntimeError(
                f"multiple {label} values snapped to column {column}: "
                f"{values[column]!r}, {value!r}"
            )
        values[column] = value
    return values


def _parse_train_number(value: str) -> str | None:
    return value if TRAIN_NUMBER_RE.fullmatch(value) else None


def _parse_printed_page(value: str) -> int | None:
    match = PRINTED_PAGE_RE.fullmatch(value)
    if not match:
        return None
    number = int(match.group(1))
    return number if number > 0 else None


def extract_previous_publication_refs(words: list[Word], grid: TrainColumnGrid) -> list[dict[str, Any]]:
    """Return official previous-page metadata aligned to the current page grid.

    Alignment is geometric to the already-proven current page columns.  Missing
    values remain None.  This function does not claim that a reference has been
    matched to a target fragment.
    """
    main = _main_printed_header(words)
    if main is None:
        return [
            {"previousPrintedPage": None, "previousTrainNumber": None}
            for _ in grid.centers
        ]
    main_row, _label_right = main
    main_y = _row_y(main_row)

    upper_train_rows = [
        row for row in _printed_train_number_rows(words)
        if _row_y(row) < main_y - 1.0
    ]
    previous_train_row = max(upper_train_rows, key=_row_y) if upper_train_rows else None

    previous_page_rows: list[list[Word]] = []
    for row in cluster_by_y(words):
        if _row_y(row) >= main_y - 1.0:
            continue
        if _label_span(row, "前の掲載ページ") is not None:
            previous_page_rows.append(row)
    previous_page_row = max(previous_page_rows, key=_row_y) if previous_page_rows else None

    previous_numbers = _assign_tokens(
        previous_train_row,
        grid,
        label="列車番号",
        parser=_parse_train_number,
    )
    previous_pages = _assign_tokens(
        previous_page_row,
        grid,
        label="前の掲載ページ",
        parser=_parse_printed_page,
    )

    return [
        {
            "previousPrintedPage": previous_pages[column],
            "previousTrainNumber": previous_numbers[column],
        }
        for column in range(len(grid.centers))
    ]


def _footer_page_candidates(
    width: float,
    height: float,
    words: list[Word],
    *,
    min_y_fraction: float,
    edge_fraction: float,
) -> set[int]:
    candidates: set[int] = set()
    for word in words:
        if word.y < height * min_y_fraction:
            continue
        if not (word.x < width * edge_fraction or word.x > width * (1.0 - edge_fraction)):
            continue
        value = _parse_printed_page(word.text)
        if value is not None:
            candidates.add(value)
    return candidates


def detect_printed_page_number(width: float, height: float, words: list[Word]) -> int | None:
    """Detect the publication page number printed outside the timetable frame.

    The publication number lives in the extreme outer gutter, whereas operating
    kilometres and timetable cells begin inside the ruled table.  We therefore
    inspect that gutter first, including the slightly higher footer used by the
    special connection timetable on printed page 62.  A conventional bottom-edge
    pass is retained only as a compatibility fallback.  Ambiguity always fails
    closed; no PDF-page offset is guessed or hard-coded.
    """
    outer_gutter = _footer_page_candidates(
        width,
        height,
        words,
        min_y_fraction=0.86,
        edge_fraction=0.075,
    )
    if len(outer_gutter) == 1:
        return next(iter(outer_gutter))
    if len(outer_gutter) > 1:
        return None

    strict_bottom = _footer_page_candidates(
        width,
        height,
        words,
        min_y_fraction=0.94,
        edge_fraction=0.12,
    )
    if len(strict_bottom) == 1:
        return next(iter(strict_bottom))
    return None


def build_audit(pdf_path: Path, source_bytes: bytes) -> dict[str, Any]:
    total_pages = page_count(pdf_path)
    page_rows: list[dict[str, Any]] = []
    fragments: list[dict[str, Any]] = []
    excluded_pages: list[dict[str, Any]] = []

    for pdf_page in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total_pages + 1):
        width, height, words = bbox_words(pdf_path, pdf_page)
        page_text = compact("".join(word.text for word in words))
        excluded_reason = page_scope_reason(page_text)
        if excluded_reason:
            excluded_pages.append({"pdfPage": pdf_page, "reason": excluded_reason})
            continue
        grid = detect_train_column_grid(words)
        if grid is None:
            continue

        printed_page = detect_printed_page_number(width, height, words)
        refs = extract_previous_publication_refs(words, grid)
        if len(refs) != len(grid.centers):
            raise RuntimeError(f"reference/grid length mismatch on PDF page {pdf_page}")

        with_any = 0
        with_both = 0
        for column, ref in enumerate(refs):
            previous_page = ref["previousPrintedPage"]
            previous_number = ref["previousTrainNumber"]
            if previous_page is not None or previous_number is not None:
                with_any += 1
            if previous_page is not None and previous_number is not None:
                with_both += 1
            fragments.append(
                {
                    "pdfPage": pdf_page,
                    "printedPage": printed_page,
                    "column": column,
                    "currentTrainNumber": grid.explicit_numbers[column],
                    "previousPrintedPage": previous_page,
                    "previousTrainNumber": previous_number,
                    "targetStatus": "not-evaluated",
                    "targetPdfPage": None,
                    "targetColumn": None,
                }
            )

        page_rows.append(
            {
                "pdfPage": pdf_page,
                "printedPage": printed_page,
                "fragmentCount": len(grid.centers),
                "previousReferenceColumns": with_any,
                "completePreviousReferenceColumns": with_both,
            }
        )

    if not page_rows:
        raise RuntimeError("no in-scope Keikyu timetable pages audited")

    printed_to_pdf: dict[int, list[int]] = {}
    for page in page_rows:
        printed = page["printedPage"]
        if printed is None:
            continue
        printed_to_pdf.setdefault(int(printed), []).append(int(page["pdfPage"]))

    target_index: dict[tuple[int, str], list[tuple[int, int]]] = {}
    for fragment in fragments:
        printed = fragment["printedPage"]
        number = fragment["currentTrainNumber"]
        if printed is None or not number:
            continue
        target_index.setdefault((int(printed), str(number)), []).append(
            (int(fragment["pdfPage"]), int(fragment["column"]))
        )

    status_counts: dict[str, int] = {}
    for fragment in fragments:
        previous_page = fragment["previousPrintedPage"]
        previous_number = fragment["previousTrainNumber"]
        if previous_page is None and previous_number is None:
            status = "no-reference"
        elif previous_page is None:
            status = "train-number-only"
        elif previous_number is None:
            status = "printed-page-only"
        elif len(printed_to_pdf.get(int(previous_page), [])) != 1:
            status = "printed-page-unmapped-or-ambiguous"
        else:
            targets = target_index.get((int(previous_page), str(previous_number)), [])
            if len(targets) == 1:
                status = "unique-explicit-reference-candidate"
                fragment["targetPdfPage"], fragment["targetColumn"] = targets[0]
            elif not targets:
                status = "target-train-number-not-found"
            else:
                status = "target-train-number-ambiguous"
        fragment["targetStatus"] = status
        status_counts[status] = status_counts.get(status, 0) + 1

    unique_candidates = status_counts.get("unique-explicit-reference-candidate", 0)
    complete_refs = sum(
        1 for fragment in fragments
        if fragment["previousPrintedPage"] is not None and fragment["previousTrainNumber"] is not None
    )
    pages_without_printed_number = sum(1 for page in page_rows if page["printedPage"] is None)
    duplicate_printed_pages = {
        str(printed): pdf_pages
        for printed, pdf_pages in sorted(printed_to_pdf.items())
        if len(pdf_pages) != 1
    }

    return {
        "version": 1,
        "kind": "keikyu-official-previous-publication-reference-audit",
        "source": {
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "pdfPages": total_pages,
        },
        "pagesAudited": len(page_rows),
        "excludedPages": excluded_pages,
        "pagesWithoutDetectedPrintedPageNumber": pages_without_printed_number,
        "duplicatePrintedPageMappings": duplicate_printed_pages,
        "fragmentCount": len(fragments),
        "completePreviousReferenceCount": complete_refs,
        "uniqueExplicitReferenceCandidateCount": unique_candidates,
        "targetStatusCounts": status_counts,
        "identityPolicy": {
            "officialPreviousPublicationMetadataExtracted": True,
            "uniqueExplicitLookupIsCandidateOnly": True,
            "clockTimeUsedForMatching": False,
            "destinationUsedForMatching": False,
            "crossPageIdentityEstablished": False,
            "runtimeSameTrainPromotions": 0,
        },
        "pages": page_rows,
        "fragments": fragments,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.pdf:
        source_bytes = args.pdf.read_bytes()
        if not source_bytes.startswith(b"%PDF"):
            raise RuntimeError("--pdf is not a PDF")
        payload = build_audit(args.pdf, source_bytes)
    else:
        with tempfile.TemporaryDirectory(prefix="keikyu-previous-publication-") as temp_dir:
            pdf_path = Path(temp_dir) / "schedule_all.pdf"
            source_bytes = download_official_pdf(pdf_path)
            payload = build_audit(pdf_path, source_bytes)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sourceSha256": payload["source"]["sha256"],
                "pdfPages": payload["source"]["pdfPages"],
                "pagesAudited": payload["pagesAudited"],
                "fragments": payload["fragmentCount"],
                "completePreviousReferences": payload["completePreviousReferenceCount"],
                "uniqueExplicitReferenceCandidates": payload["uniqueExplicitReferenceCandidateCount"],
                "pagesWithoutPrintedPageNumber": payload["pagesWithoutDetectedPrintedPageNumber"],
                "targetStatusCounts": payload["targetStatusCounts"],
                "runtimeSameTrainPromotions": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
