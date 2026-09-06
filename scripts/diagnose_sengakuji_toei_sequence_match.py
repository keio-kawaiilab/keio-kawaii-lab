#!/usr/bin/env python3
"""Validate Sengakuji candidates with a multi-station Toei fingerprint.

This diagnostic deliberately reuses the already-generated and audited Keikyu
boundary evidence.  It only re-opens the official PDFs on pages that actually
contain boundary candidates, then compares several Toei-side station times in
that printed column with the recorded Toei TrainTimetable candidates.

The sequence is an identity check on the Toei side only.  It is never, by
itself, evidence that the same physical train crosses the operator boundary.
"""
from __future__ import annotations

import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pdfplumber

from audit_toei_sengakuji_official_columns import TOEI_FILE, load
from keikyu_official_train_evidence import (
    DEFAULT_HOLIDAY_URL,
    DEFAULT_WEEKDAY_URL,
    column_tolerance,
    fetch_pdf,
    nearest,
    norm,
    rows,
    time_cells,
)

EVIDENCE_FILE = Path("data/transit-v2/keikyu-official-train-evidence.json")
PDF_TO_ODPT_SUFFIX = {
    "泉岳寺": "Sengakuji",
    "三田": "Mita",
    "大門": "Daimon",
    "新橋": "Shimbashi",
    "東銀座": "HigashiGinza",
    "宝町": "Takaracho",
    "日本橋": "Nihombashi",
    "人形町": "Ningyocho",
    "東日本橋": "HigashiNihombashi",
    "浅草橋": "Asakusabashi",
    "蔵前": "Kuramae",
    "浅草": "Asakusa",
    "本所吾妻橋": "HonjoAzumabashi",
    "押上": "Oshiage",
}
TOKENS = sorted(PDF_TO_ODPT_SUFFIX, key=len, reverse=True)


def page_words(content: bytes, page_numbers: set[int]) -> dict[int, list[dict[str, Any]]]:
    """Extract words only from PDF pages referenced by audited candidates."""
    output: dict[int, list[dict[str, Any]]] = {}
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for number in sorted(page_numbers):
            if number < 1 or number > len(pdf.pages):
                continue
            page = pdf.pages[number - 1]
            output[number] = page.extract_words(
                x_tolerance=1,
                y_tolerance=1,
                keep_blank_chars=False,
                use_text_flow=False,
            )
    return output


def station_name(text: object) -> str:
    value = norm(text)
    for token in TOKENS:
        if token in value:
            return token
    return ""


def minute_equal(a: int, b: int) -> bool:
    return int(a) % 1440 == int(b) % 1440


def build_page_cache(words: list[dict[str, Any]]) -> dict[str, Any]:
    page_rows = rows(words)
    time_by_y: dict[float, list[dict[str, Any]]] = {}
    all_time_cells: list[dict[str, Any]] = []
    station_rows: list[dict[str, Any]] = []
    for row in page_rows:
        y = float(row["y"])
        cells_for_row = time_cells(words, y)
        time_by_y[y] = cells_for_row
        all_time_cells.extend(cells_for_row)
        name = station_name(row["text"])
        if name:
            station_rows.append({"station": name, "y": y})
    return {
        "stationRows": station_rows,
        "timeByY": time_by_y,
        "tolerance": max(5.0, min(10.5, column_tolerance(all_time_cells))),
    }


def extract_pdf_fingerprint(cache: dict[str, Any], candidate: dict[str, Any], *, max_points: int = 7) -> list[dict[str, Any]]:
    geometry = candidate.get("rowGeometry") or {}
    direction = str(candidate.get("direction") or "")
    x = float(candidate["columnX"])
    source_y = float(geometry["sourceBoundaryY"])
    target_y = float(geometry["targetBoundaryY"])
    tolerance = float(cache["tolerance"])
    time_by_y = cache["timeByY"]

    relevant: list[dict[str, Any]] = []
    for row in cache["stationRows"]:
        name = str(row["station"])
        y = float(row["y"])
        if direction == "keikyu-to-toei":
            if y < target_y - 2 or y > target_y + 230:
                continue
        elif direction == "toei-to-keikyu":
            if y > source_y + 2 or y < source_y - 230:
                continue
        else:
            continue
        cell = nearest(time_by_y.get(y, []), x, tolerance)
        if not cell:
            continue
        relevant.append({
            "station": name,
            "minute": int(cell["minute"]),
            "y": round(y, 2),
            "x": round(float(cell["x"]), 2),
            "dx": round(float(cell["x"]) - x, 2),
        })

    relevant.sort(key=lambda item: item["y"])
    boundary_positions = [i for i, item in enumerate(relevant) if item["station"] == "泉岳寺"]
    if not boundary_positions:
        return []
    if direction == "keikyu-to-toei":
        anchor = min(boundary_positions, key=lambda i: abs(relevant[i]["y"] - target_y))
        seq = relevant[anchor : anchor + max_points]
    else:
        anchor = min(boundary_positions, key=lambda i: abs(relevant[i]["y"] - source_y))
        seq = relevant[max(0, anchor - max_points + 1) : anchor + 1]

    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    iterable = seq if direction == "keikyu-to-toei" else list(reversed(seq))
    for item in iterable:
        if item["station"] in seen:
            continue
        seen.add(item["station"])
        output.append(item)
    if direction == "toei-to-keikyu":
        output.reverse()
    return output


def build_trip_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stations = [str(v) for v in payload.get("stations") or []]
    calendars = [str(v) for v in payload.get("calendars") or []]
    output: dict[str, dict[str, Any]] = {}
    for trip in payload.get("trips") or []:
        if not isinstance(trip, list) or len(trip) != 7:
            continue
        cal_i, _type_i, train_number, stops, destination, train_id, timetable_id = trip
        by_suffix: dict[str, tuple[int | None, int | None]] = {}
        for stop in stops or []:
            if not isinstance(stop, list) or len(stop) != 3:
                continue
            station_i, arrival, departure = stop
            station_id = stations[int(station_i)]
            suffix = station_id.rsplit(".", 1)[-1]
            by_suffix[suffix] = (
                None if arrival is None else int(arrival),
                None if departure is None else int(departure),
            )
        output[str(timetable_id or "")] = {
            "calendar": calendars[int(cal_i)],
            "trainNumber": str(train_number or ""),
            "trainId": str(train_id or ""),
            "destination": str(destination or ""),
            "stops": by_suffix,
        }
    return output


def score_trip(fingerprint: list[dict[str, Any]], trip: dict[str, Any]) -> dict[str, Any]:
    comparisons = []
    matched = 0
    for point in fingerprint:
        suffix = PDF_TO_ODPT_SUFFIX[point["station"]]
        event = (trip.get("stops") or {}).get(suffix)
        arrival, departure = event if event else (None, None)
        values = [int(v) for v in (arrival, departure) if v is not None]
        ok = any(minute_equal(point["minute"], v) for v in values)
        matched += int(ok)
        comparisons.append({
            "station": point["station"],
            "pdfMinute": point["minute"],
            "toeiArrival": arrival,
            "toeiDeparture": departure,
            "match": ok,
        })
    return {
        "trainNumber": trip.get("trainNumber"),
        "matchedPoints": matched,
        "totalPoints": len(fingerprint),
        "allMatched": bool(fingerprint) and matched == len(fingerprint),
        "comparisons": comparisons,
    }


def toei_candidate_ids(entry: dict[str, Any]) -> list[str]:
    direction = str(entry.get("direction") or "")
    key = "targetMatches" if direction == "keikyu-to-toei" else "sourceMatches"
    return [str(value) for value in entry.get(key) or [] if value]


def main() -> int:
    evidence_payload = load(EVIDENCE_FILE)
    entries = [entry for entry in evidence_payload.get("entries") or [] if isinstance(entry, dict)]
    entries = [entry for entry in entries if entry.get("calendar") in {"weekday", "holiday"} and entry.get("pdfPage")]
    print(f"loaded audited evidence entries: {len(entries)}", flush=True)

    pages_needed: dict[str, set[int]] = {"weekday": set(), "holiday": set()}
    for entry in entries:
        pages_needed[str(entry["calendar"])].add(int(entry["pdfPage"]))
    print(f"pages needed: { {k: sorted(v) for k, v in pages_needed.items()} }", flush=True)

    contents = {
        "weekday": fetch_pdf(DEFAULT_WEEKDAY_URL),
        "holiday": fetch_pdf(DEFAULT_HOLIDAY_URL),
    }
    print("official PDFs downloaded", flush=True)

    words_by_calendar = {
        calendar: page_words(contents[calendar], pages_needed[calendar])
        for calendar in ("weekday", "holiday")
    }
    print("required PDF pages extracted", flush=True)

    page_cache = {
        (calendar, page): build_page_cache(words)
        for calendar, pages in words_by_calendar.items()
        for page, words in pages.items()
    }
    print(f"page caches built: {len(page_cache)}", flush=True)

    toei_payload = load(TOEI_FILE)
    trip_index = build_trip_index(toei_payload)

    counts: Counter[str] = Counter()
    details = []
    for entry in entries:
        status = str(entry.get("matchStatus") or "")
        counts[status] += 1
        cache = page_cache.get((str(entry["calendar"]), int(entry["pdfPage"])))
        if not cache:
            counts[f"{status}:missing-page"] += 1
            continue

        fingerprint = extract_pdf_fingerprint(cache, entry)
        scored = []
        for timetable_id in toei_candidate_ids(entry):
            trip = trip_index.get(timetable_id)
            if not trip:
                continue
            scored.append({"timetableId": timetable_id, **score_trip(fingerprint, trip)})

        strong = [item for item in scored if item["allMatched"] and item["totalPoints"] >= 3]
        if len(fingerprint) < 3:
            counts[f"{status}:insufficient-fingerprint"] += 1
        elif len(strong) == 1:
            counts[f"{status}:sequence-singleton"] += 1
        elif len(strong) == 0:
            counts[f"{status}:sequence-none"] += 1
        else:
            counts[f"{status}:sequence-ambiguous"] += 1

        if status != "matched-singleton" or len(strong) != 1:
            details.append({
                "candidateId": entry.get("id"),
                "calendar": entry.get("calendar"),
                "direction": entry.get("direction"),
                "pdfPage": entry.get("pdfPage"),
                "columnX": entry.get("columnX"),
                "sourceBoundaryMinute": entry.get("sourceBoundaryMinute"),
                "targetBoundaryMinute": entry.get("targetBoundaryMinute"),
                "auditStatus": status,
                "fingerprint": fingerprint,
                "toeiCandidates": scored,
                "strongMatches": [item["timetableId"] for item in strong],
            })

    print(json.dumps({
        "counts": dict(sorted(counts.items())),
        "detailCount": len(details),
        "details": details,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
