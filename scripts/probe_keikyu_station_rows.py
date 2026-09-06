#!/usr/bin/env python3
"""Probe exact station/arrival/departure row semantics on one Keikyu PDF page.

The official timetable sometimes prints a station name on one Y row and its
arrival/departure times on an adjacent Y row.  This probe resolves that printed
structure spatially against the canonical Keikyu station list.  It never uses
clock-time proximity between trains and never guesses a station from a train's
destination.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from keikyu_official_pdf import (
    TIME_RE,
    bbox_words,
    cluster_by_y,
    detect_train_column_grid,
    download_official_pdf,
    nearest_column,
)

ROOT = Path(__file__).resolve().parents[1]
ENTITIES = ROOT / "data/transit/keikyu/entities.json"
PAGE = 7
IN_SCOPE_RAILWAYS = {
    "odpt.Railway:Keikyu.Main",
    "odpt.Railway:Keikyu.Airport",
    "odpt.Railway:Keikyu.Kurihama",
    "odpt.Railway:Keikyu.Zushi",
}

# The official all-line PDF shortens these two long airport station names in
# some continuation blocks.  This is a printed-name alias only; it must not be
# used to infer train identity or destination continuity.
STATION_ALIASES = {
    "羽田第１・第２": "羽田空港第１・第２ターミナル",
    "羽田第３": "羽田空港第３ターミナル",
}


def compact_join(words) -> str:
    return re.sub(r"\s+", "", "".join(word.text for word in sorted(words, key=lambda word: word.x)))


def station_titles() -> list[str]:
    payload = json.loads(ENTITIES.read_text(encoding="utf-8"))
    titles: set[str] = set()
    for row in payload.get("Station") or []:
        if not isinstance(row, dict) or row.get("odpt:railway") not in IN_SCOPE_RAILWAYS:
            continue
        title: Any = row.get("dc:title")
        station_title = row.get("odpt:stationTitle")
        if isinstance(station_title, dict):
            title = station_title.get("ja") or title
        if title:
            titles.add(re.sub(r"\s+", "", str(title)))
    # Longer first prevents a hypothetical short name from shadowing a long one.
    return sorted(titles, key=lambda value: (-len(value), value))


def station_matches(left_text: str, titles: list[str]) -> list[str]:
    matches = [title for title in titles if title in left_text]
    for alias, canonical in STATION_ALIASES.items():
        if alias in left_text and canonical in titles:
            matches.append(canonical)
    if not matches:
        return []
    matches = sorted(set(matches), key=lambda value: (-len(value), value))
    longest = len(matches[0])
    return [title for title in matches if len(title) == longest]


def operational_label_text(left_text: str) -> str:
    """Remove only proven continuation-cell artifacts from the label area.

    Keikyu prints a small 「前の掲載ページ」 continuation area immediately to
    the left of the main train grid.  Depending on the page, its HHMM values and
    ellipsis/symbol cells share the same PDF Y row as a station label, e.g.
    ``三崎口発………1851…``.  Those values are not part of the station label and
    must not prevent us from reading the printed 発/着/〃 marker.

    ASCII digits may be concatenated by PDF extraction (for example three
    adjacent continuation cells can become ``759810814``), so they must be
    removed as one run instead of assuming 3-4 digit tokens. Full-width digits
    in station names such as 羽田空港第１・第２ターミナル are intentionally
    untouched.

    This function does *not* move a time into another train column and does not
    establish any train identity.
    """
    value = re.sub(r"[0-9.]+", "", left_text)
    value = re.sub(r"[…!#$\"'\\]+", "", value)
    return value


def _marker_value(token: str) -> str | None:
    if token == "着":
        return "arrival"
    if token in ("発", "〃"):
        # In this timetable layout 〃 repeats the station row's departure label.
        # It is a row-semantic marker only and never a train-identity shortcut.
        return "departure"
    return None


def station_adjacent_marker(left_text: str, station: str) -> str | None:
    """Read a printed 着/発/〃 immediately following a proven station title.

    Some PDF rows contain continuation symbols or destination/branch annotations
    to the right of the station marker, so requiring the entire extracted label
    to *end* in 発/着/〃 loses valid rows (for example ``浦賀発%…`` or
    ``梅屋敷〃#…羽…``).  Once the station title itself has already been proven,
    an immediately adjacent marker is stronger evidence than the row suffix and
    remains independent of clock times or destination matching.
    """
    printed_names = [station]
    printed_names.extend(alias for alias, canonical in STATION_ALIASES.items() if canonical == station)
    for printed in sorted(set(printed_names), key=lambda value: (-len(value), value)):
        start = left_text.find(printed)
        if start < 0:
            continue
        suffix = left_text[start + len(printed):]
        if suffix:
            value = _marker_value(suffix[0])
            if value:
                return value
    return None


def marker(left_text: str) -> str | None:
    cleaned = operational_label_text(left_text)
    # Explicitly reject table headings whose Japanese contains 発/着 but is not
    # an operational arrival/departure row.
    if any(token in cleaned for token in ("発車番線", "到着番線", "始発")):
        return None
    if cleaned.endswith("着"):
        return "arrival"
    if cleaned.endswith("発"):
        return "departure"
    if cleaned.endswith("〃"):
        return "departure"
    return None


def main() -> int:
    titles = station_titles()
    if not titles:
        raise RuntimeError("no in-scope Keikyu station titles loaded")

    with tempfile.TemporaryDirectory(prefix="keikyu-row-probe-") as temp_dir:
        pdf_path = Path(temp_dir) / "schedule_all.pdf"
        download_official_pdf(pdf_path)
        _width, _height, words = bbox_words(pdf_path, PAGE)
        grid = detect_train_column_grid(words)
        if grid is None:
            raise RuntimeError("could not prove train-column grid")

        left_boundary = grid.centers[0] - grid.pitch * 0.55
        raw_rows: list[dict[str, Any]] = []
        for row in cluster_by_y(words, tolerance=1.35):
            y = sum(word.y for word in row) / len(row)
            if y <= grid.header_y + 20:
                continue

            left_words = [word for word in row if word.x < left_boundary]
            left_text = compact_join(left_words)
            if not left_text:
                continue

            cells = []
            for word in row:
                if word.x < left_boundary or not TIME_RE.fullmatch(word.text):
                    continue
                column = nearest_column(grid, word.x)
                if column is None:
                    continue
                cells.append({"column": column, "text": word.text, "x": round(word.x, 2)})

            matches = station_matches(left_text, titles)
            row_marker = marker(left_text)
            if len(matches) == 1:
                row_marker = station_adjacent_marker(left_text, matches[0]) or row_marker
            if not matches and row_marker is None and not cells:
                continue
            raw_rows.append(
                {
                    "y": y,
                    "left": left_text,
                    "stationMatches": matches,
                    "marker": row_marker,
                    "cells": cells,
                }
            )

        station_anchors = [
            {"y": row["y"], "station": row["stationMatches"][0], "marker": row["marker"]}
            for row in raw_rows
            if len(row["stationMatches"]) == 1
        ]

        resolved_rows = []
        unresolved_timed_rows = []
        for row in raw_rows:
            if not row["cells"]:
                continue

            station = None
            resolution = None
            if len(row["stationMatches"]) == 1:
                station = row["stationMatches"][0]
                resolution = "same-row-station-title"
            elif len(row["stationMatches"]) > 1:
                resolution = "ambiguous-same-row-station-title"
            elif row["marker"] == "arrival":
                # Printed arrival rows can sit immediately above the station's
                # named departure row.  Only use a following canonical label.
                candidates = [anchor for anchor in station_anchors if 0 < anchor["y"] - row["y"] <= 10.5]
                if candidates:
                    closest = min(candidates, key=lambda anchor: anchor["y"] - row["y"])
                    station = closest["station"]
                    resolution = "arrival-row-to-following-station-title"
            elif row["marker"] == "departure":
                # Conversely, a station's named arrival row can be followed by
                # a separate departure row.  Only use a preceding label.
                candidates = [anchor for anchor in station_anchors if 0 < row["y"] - anchor["y"] <= 10.5]
                if candidates:
                    closest = min(candidates, key=lambda anchor: row["y"] - anchor["y"])
                    station = closest["station"]
                    resolution = "departure-row-to-preceding-station-title"

            item = {
                "y": round(row["y"], 2),
                "left": row["left"],
                "marker": row["marker"],
                "station": station,
                "resolution": resolution,
                "cellCount": len(row["cells"]),
                "cells": row["cells"][:20],
            }
            if station and row["marker"]:
                resolved_rows.append(item)
            else:
                unresolved_timed_rows.append(item)

        total_timed = len(resolved_rows) + len(unresolved_timed_rows)
        resolved_cells = sum(row["cellCount"] for row in resolved_rows)
        unresolved_cells = sum(row["cellCount"] for row in unresolved_timed_rows)
        report = {
            "page": PAGE,
            "trainColumns": len(grid.centers),
            "canonicalStationTitles": len(titles),
            "timedRows": total_timed,
            "resolvedTimedRows": len(resolved_rows),
            "unresolvedTimedRows": len(unresolved_timed_rows),
            "resolvedTimeCells": resolved_cells,
            "unresolvedTimeCells": unresolved_cells,
            "sampleResolvedRows": resolved_rows[:24],
            "sampleUnresolvedRows": unresolved_timed_rows[:12],
            "policy": {
                "clockTimeProximityUsed": False,
                "destinationUsedToInferStation": False,
                "crossPageTrainIdentityEstablished": False,
            },
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not resolved_rows:
            raise RuntimeError("no station rows could be resolved")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())