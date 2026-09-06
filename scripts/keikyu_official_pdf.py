#!/usr/bin/env python3
"""Strict geometry helpers for the official Keikyu full-line timetable PDF.

The timetable is a visual train-column table.  We therefore use PDF word
coordinates instead of joining station departures by time proximity.  This
module deliberately separates *page-column identity* from cross-page or
cross-operator train identity: a column can be parsed exactly without being
allowed to prove that it is the same physical train as another column.

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


def _candidate_header_rows(words: list[Word]) -> list[list[Word]]:
    result: list[list[Word]] = []
    for row in cluster_by_y(words):
        numeric = [word for word in row if word.x > 165 and TRAIN_NUMBER_RE.fullmatch(word.text)]
        if len(numeric) < 6:
            continue
        xs = [word.x for word in numeric]
        if max(xs) - min(xs) < 70:
            continue
        result.append(numeric)
    return result


def detect_train_column_grid(words: list[Word]) -> TrainColumnGrid | None:
    """Find the train-number header and reconstruct its regular column grid.

    Missing printed train numbers are represented as None.  They remain valid
    *local page columns*, but must never prove cross-page/cross-operator identity.
    """
    candidates = _candidate_header_rows(words)
    if not candidates:
        return None

    # Header rows sit near the top and normally contain the widest regular run.
    def score(row: list[Word]) -> tuple[int, float, float]:
        xs = [word.x for word in row]
        diffs = [b - a for a, b in zip(xs, xs[1:]) if b > a]
        regularity = statistics.pstdev(diffs) if len(diffs) >= 2 else 999.0
        return (len(row), -regularity, -statistics.median(word.y for word in row))

    header = max(candidates, key=score)
    xs = [word.x for word in header]
    raw_diffs = [b - a for a, b in zip(xs, xs[1:]) if 5 < b - a < 40]
    if not raw_diffs:
        return None

    # Some printed train numbers are omitted, making a gap 2x or 3x the base
    # pitch.  Estimate the base pitch from the smallest regular half of gaps.
    sorted_diffs = sorted(raw_diffs)
    base_pool = sorted_diffs[: max(2, (len(sorted_diffs) + 1) // 2)]
    pitch = statistics.median(base_pool)
    if not (10.0 <= pitch <= 22.0):
        return None

    first = xs[0]
    last = xs[-1]
    slot_count = int(round((last - first) / pitch)) + 1
    if not (6 <= slot_count <= 40):
        return None
    centers = tuple(first + index * pitch for index in range(slot_count))

    numbers: list[str | None] = [None] * slot_count
    max_snap = pitch * 0.34
    for word in header:
        index = min(range(slot_count), key=lambda i: abs(centers[i] - word.x))
        if abs(centers[index] - word.x) > max_snap:
            return None
        if numbers[index] is not None:
            return None
        numbers[index] = word.text

    return TrainColumnGrid(
        header_y=statistics.median(word.y for word in header),
        centers=centers,
        pitch=pitch,
        explicit_numbers=tuple(numbers),
    )


def nearest_column(grid: TrainColumnGrid, x: float, max_fraction: float = 0.42) -> int | None:
    index = min(range(len(grid.centers)), key=lambda i: abs(grid.centers[i] - x))
    if abs(grid.centers[index] - x) > grid.pitch * max_fraction:
        return None
    return index


def time_cells(words: list[Word], grid: TrainColumnGrid) -> list[tuple[int, Word]]:
    """Return unlabelled time-like cells assigned to strict page columns.

    Station/arrival/departure row interpretation is intentionally left to a
    later semantic parser.  This helper only proves horizontal column position.
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
