#!/usr/bin/env python3
"""Strict geometry helpers for the official Keikyu full-line timetable PDF.

The timetable is a visual train-column table. We therefore use PDF word
coordinates instead of joining station departures by time proximity. Page-local
column geometry and physical-train identity are deliberately separate: an
anonymous published column is a valid page column, but can never by itself prove
cross-page or cross-operator same-train identity.

Raw PDF bytes are only downloaded to a caller-provided temporary path and are
never intended to be committed.
"""
from __future__ import annotations

import re
import statistics
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

OFFICIAL_PDF_URL = "https://www.keikyu.co.jp/ride/kakueki/pdf/schedule_all.pdf"
TRAIN_NUMBER_RE = re.compile(r"^\d{2,4}[A-Z]{0,2}[a-z]?$|^\d{2,4}$")
TIME_RE = re.compile(r"^(?:[0-2]?\d)[0-5]\d$")
PRINTED_HEADER_Y_LIMIT = 150.0


@dataclass(frozen=True)
class Word:
    text: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def x(self) -> float:
        return (self.x_min + self.x_max) / 2

    @property
    def y(self) -> float:
        return (self.y_min + self.y_max) / 2


@dataclass(frozen=True)
class TrainColumnGrid:
    header_y: float
    centers: tuple[float, ...]
    pitch: float
    explicit_numbers: tuple[str | None, ...]


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def download_official_pdf(path: Path) -> bytes:
    request = urllib.request.Request(
        OFFICIAL_PDF_URL,
        headers={"User-Agent": "Mozilla/5.0 transit-timetable-audit/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise RuntimeError("Keikyu official timetable response is not a PDF")
    if len(data) < 1_000_000:
        raise RuntimeError(f"Keikyu official timetable PDF unexpectedly small: {len(data)} bytes")
    path.write_bytes(data)
    return data


def page_count(pdf_path: Path) -> int:
    output = subprocess.check_output(
        ["pdfinfo", str(pdf_path)], text=True, encoding="utf-8", errors="replace"
    )
    match = re.search(r"^Pages:\s+(\d+)\s*$", output, re.MULTILINE)
    if not match:
        raise RuntimeError("could not determine Keikyu PDF page count")
    return int(match.group(1))


def bbox_words(pdf_path: Path, page_number: int) -> tuple[float, float, list[Word]]:
    xml = subprocess.check_output(
        [
            "pdftotext",
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-bbox-layout",
            str(pdf_path),
            "-",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    root = ET.fromstring(xml)
    page = next((node for node in root.iter() if node.tag.endswith("page")), None)
    if page is None:
        raise RuntimeError(f"bbox output contained no page for PDF page {page_number}")
    words: list[Word] = []
    for node in page.iter():
        if not node.tag.endswith("word"):
            continue
        text = compact("".join(node.itertext()))
        if not text:
            continue
        words.append(
            Word(
                text=text,
                x_min=float(node.attrib["xMin"]),
                y_min=float(node.attrib["yMin"]),
                x_max=float(node.attrib["xMax"]),
                y_max=float(node.attrib["yMax"]),
            )
        )
    return float(page.attrib.get("width", 0)), float(page.attrib.get("height", 0)), words


def cluster_by_y(words: Iterable[Word], tolerance: float = 1.2) -> list[list[Word]]:
    ordered = sorted(words, key=lambda word: (word.y, word.x))
    rows: list[list[Word]] = []
    for word in ordered:
        if not rows:
            rows.append([word])
            continue
        row_y = statistics.median(item.y for item in rows[-1])
        if abs(word.y - row_y) <= tolerance:
            rows[-1].append(word)
        else:
            rows.append([word])
    for row in rows:
        row.sort(key=lambda word: word.x)
    return rows


def _row_text(row: list[Word]) -> str:
    return compact("".join(word.text for word in sorted(row, key=lambda word: word.x)))


def _label_span(row: list[Word], needle: str = "列車番号") -> tuple[float, float] | None:
    """Return the bbox span of a printed label even when PDF words split it.

    ``pdftotext -bbox-layout`` can expose 「列 車 番 号」 as four separate Word
    objects although compact row text is exactly ``列車番号``.  Header detection
    must therefore prove the literal phrase as a consecutive word sequence,
    rather than require one Word whose text contains the whole phrase.
    """
    ordered = sorted(row, key=lambda word: word.x)
    for start in range(len(ordered)):
        assembled = ""
        start_x = ordered[start].x_min
        for end in range(start, min(len(ordered), start + 8)):
            token = compact(ordered[end].text)
            if not token:
                continue
            assembled += token
            if assembled == needle:
                return start_x, max(word.x_max for word in ordered[start : end + 1])
            if not needle.startswith(assembled):
                break
    return None


def _printed_train_number_rows(words: list[Word]) -> list[list[Word]]:
    """Return literal printed 「列車番号」 rows near the top of the page."""
    result: list[list[Word]] = []
    for row in cluster_by_y(words):
        row_y = statistics.median(word.y for word in row)
        if row_y > PRINTED_HEADER_Y_LIMIT:
            continue
        if "列車番号" in _row_text(row) and _label_span(row) is not None:
            result.append(row)
    return result


def _main_printed_header(words: list[Word]) -> tuple[list[Word], float] | None:
    """Return the lower printed train-number row and label right edge.

    When two header bands exist, the upper one belongs to 「前の掲載ページ」;
    the lower one is the current page's main timetable. This rule was audited
    across the official PDF instead of choosing whichever numeric row is densest.
    """
    rows = _printed_train_number_rows(words)
    if not rows:
        return None
    row = max(rows, key=lambda value: statistics.median(word.y for word in value))
    span = _label_span(row)
    if span is None:
        return None
    return row, span[1]


def _candidate_header_rows(words: list[Word]) -> list[list[Word]]:
    """Compatibility helper: explicit train-number tokens from printed headers."""
    result: list[list[Word]] = []
    for row in _printed_train_number_rows(words):
        span = _label_span(row)
        if span is None:
            continue
        label_x_max = span[1]
        tokens = [
            word for word in row
            if word.x > label_x_max and TRAIN_NUMBER_RE.fullmatch(word.text)
        ]
        if tokens:
            result.append(tokens)
    return result


def _infer_pitch(explicit: list[Word]) -> float | None:
    """Infer adjacent train-column pitch from explicit numbers on the true header."""
    xs = sorted(word.x for word in explicit)
    adjacent = [b - a for a, b in zip(xs, xs[1:]) if 10.0 <= b - a <= 22.0]
    if not adjacent:
        return None
    pitch = statistics.median(adjacent)
    return pitch if 10.0 <= pitch <= 22.0 else None


def _distinct_y_rows(words: list[Word], tolerance: float = 1.6) -> int:
    if not words:
        return 0
    ys = sorted(word.y for word in words)
    groups = 1
    anchor = ys[0]
    for value in ys[1:]:
        if value - anchor > tolerance:
            groups += 1
            anchor = value
    return groups


def _edge_slot_support(
    words: list[Word],
    *,
    x: float,
    pitch: float,
    header_y: float,
    max_fraction: float = 0.34,
) -> tuple[int, int]:
    matched = [
        word
        for word in words
        if word.y > header_y + 10
        and TIME_RE.fullmatch(word.text)
        and abs(word.x - x) <= pitch * max_fraction
    ]
    return len(matched), _distinct_y_rows(matched)


def _extend_right_edge_columns(
    words: list[Word],
    grid: TrainColumnGrid,
    *,
    max_slots: int = 4,
    min_distinct_rows: int = 3,
) -> TrainColumnGrid:
    """Recover only anonymous columns to the right of the last explicit number.

    The far left contains station names, operating-km values and continuation
    metadata, so it must never be discovered from numeric density. The left edge
    is instead bounded by the printed 「列車番号」 label. On the right there is no
    station metadata; repeated pitch-aligned time cells on >=3 Y rows may safely
    extend the page-local grid. Identity remains anonymous.
    """
    if not grid.centers:
        return grid
    last = grid.centers[-1]
    supported: list[int] = []
    for offset in range(1, max_slots + 1):
        _count, rows = _edge_slot_support(
            words,
            x=last + offset * grid.pitch,
            pitch=grid.pitch,
            header_y=grid.header_y,
        )
        if rows >= min_distinct_rows:
            supported.append(offset)
    append = max(supported, default=0)
    if append == 0:
        return grid
    right_centers = tuple(last + offset * grid.pitch for offset in range(1, append + 1))
    return TrainColumnGrid(
        header_y=grid.header_y,
        centers=grid.centers + right_centers,
        pitch=grid.pitch,
        explicit_numbers=grid.explicit_numbers + (None,) * append,
    )


def detect_train_column_grid(words: list[Word]) -> TrainColumnGrid | None:
    """Reconstruct a page-local train grid from the literal printed header.

    The lower printed 「列車番号」 row is the sole header anchor. Missing printed
    train numbers between explicit numbers, and between the label divider and
    the first explicit number, are represented as ``None``. Anonymous columns
    never establish cross-page or cross-operator identity.
    """
    selected = _main_printed_header(words)
    if selected is None:
        return None
    header_row, label_x_max = selected
    header_y = statistics.median(word.y for word in header_row)

    explicit = sorted(
        [
            word for word in header_row
            if word.x > label_x_max and TRAIN_NUMBER_RE.fullmatch(word.text)
        ],
        key=lambda word: word.x,
    )
    if len(explicit) < 3:
        return None

    pitch = _infer_pitch(explicit)
    if pitch is None:
        return None

    first_explicit_x = explicit[0].x
    last_explicit_x = explicit[-1].x
    first_center = first_explicit_x
    while first_center - pitch > label_x_max + pitch * 0.30:
        first_center -= pitch

    slot_count = int(round((last_explicit_x - first_center) / pitch)) + 1
    if not (3 <= slot_count <= 40):
        return None
    centers = tuple(first_center + index * pitch for index in range(slot_count))

    numbers: list[str | None] = [None] * slot_count
    max_snap = pitch * 0.34
    for word in explicit:
        index = min(range(slot_count), key=lambda i: abs(centers[i] - word.x))
        if abs(centers[index] - word.x) > max_snap:
            return None
        if numbers[index] is not None:
            return None
        numbers[index] = word.text

    initial = TrainColumnGrid(
        header_y=header_y,
        centers=centers,
        pitch=pitch,
        explicit_numbers=tuple(numbers),
    )
    return _extend_right_edge_columns(words, initial)


def nearest_column(grid: TrainColumnGrid, x: float, max_fraction: float = 0.42) -> int | None:
    index = min(range(len(grid.centers)), key=lambda i: abs(grid.centers[i] - x))
    if abs(grid.centers[index] - x) > grid.pitch * max_fraction:
        return None
    return index


def time_cells(words: list[Word], grid: TrainColumnGrid) -> list[tuple[int, Word]]:
    """Return time-like cells assigned to strict page columns.

    Station/arrival/departure row interpretation is intentionally left to the
    semantic parser. This helper proves horizontal column position only.
    """
    result: list[tuple[int, Word]] = []
    for word in words:
        if word.y <= grid.header_y + 10:
            continue
        if not TIME_RE.fullmatch(word.text):
            continue
        column = nearest_column(grid, word.x)
        if column is not None:
            result.append((column, word))
    return result