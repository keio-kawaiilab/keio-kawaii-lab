#!/usr/bin/env python3
"""Validate Sengakuji boundary candidates with a multi-station Toei fingerprint.

A matching minute at Sengakuji is not enough to identify a train, and a reused
printed x-position around the train-number row is not proof of continuation.
This diagnostic therefore compares several Toei-side station times printed in
one official Keikyu timetable column with the exact Toei TrainTimetable trip.

The sequence is only an identity check on the Toei side.  It does not by itself
promote any runtime same-train edge.
"""
from __future__ import annotations

import io
import json
from collections import Counter
from typing import Any

import pdfplumber

from audit_toei_sengakuji_official_columns import TOEI_FILE, audit, load
from keikyu_official_train_evidence import (
    DEFAULT_HOLIDAY_URL,
    DEFAULT_WEEKDAY_URL,
    column_tolerance,
    extract_pdf,
    fetch_pdf,
    nearest,
    norm,
    rows,
    time_cells,
)

# Stations shared by the Toei Asakusa main trunk north of Sengakuji.  Matching
# is done by official station name/order + printed minute; train number and
# destination are deliberately not used as identity evidence here.
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


def page_words(content: bytes) -> dict[int, list[dict[str, Any]]]:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return {
            number: page.extract_words(
                x_tolerance=1,
                y_tolerance=1,
                keep_blank_chars=False,
                use_text_flow=False,
            )
            for number, page in enumerate(pdf.pages, start=1)
        }


def station_name(text: object) -> str:
    value = norm(text)
    for token in TOKENS:
        if token in value:
            return token
    return ""


def minute_equal(a: int, b: int) -> bool:
    return int(a) % 1440 == int(b) % 1440


def extract_pdf_fingerprint(words: list[dict[str, Any]], candidate: dict[str, Any], *, max_points: int = 7) -> list[dict[str, Any]]:
    geometry = candidate.get("rowGeometry") or {}
    direction = str(candidate.get("direction") or "")
    x = float(candidate["columnX"])
    source_y = float(geometry["sourceBoundaryY"])
    target_y = float(geometry["targetBoundaryY"])

    page_rows = rows(words)
    all_time_cells = []
    for row in page_rows:
        all_time_cells.extend(time_cells(words, float(row["y"])))
    tolerance = max(5.0, min(10.5, column_tolerance(all_time_cells)))

    relevant: list[dict[str, Any]] = []
    for row in page_rows:
        name = station_name(row["text"])
        if not name:
            continue
        y = float(row["y"])
        if direction == "keikyu-to-toei":
            # Toei portion begins at the lower Sengakuji row and continues
            # downward toward Mita / Daimon / Shimbashi / Oshiage.
            if y < target_y - 2 or y > target_y + 230:
                continue
        elif direction == "toei-to-keikyu":
            # Toei portion approaches the upper Sengakuji row from above.
            if y > source_y + 2 or y < source_y - 230:
                continue
        else:
            continue
        cell = nearest(time_cells(words, y), x, tolerance)
        if not cell:
            continue
        relevant.append({
            "station": name,
            "minute": int(cell["minute"]),
            "y": round(y, 2),
            "x": round(float(cell["x"]), 2),
            "dx": round(float(cell["x"]) - x, 2),
        })

    # Keep only the contiguous Toei trunk around Sengakuji.  Page halves can
    # repeat the same station labels, so anchor at the boundary occurrence.
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

    # Deduplicate accidental repeated labels by keeping the point closest to
    # the boundary within this small local sequence.
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


def main() -> int:
    contents = {
        "weekday": fetch_pdf(DEFAULT_WEEKDAY_URL),
        "holiday": fetch_pdf(DEFAULT_HOLIDAY_URL),
    }
    candidates: list[dict[str, Any]] = []
    for calendar, content in contents.items():
        url = DEFAULT_WEEKDAY_URL if calendar == "weekday" else DEFAULT_HOLIDAY_URL
        candidates.extend(extract_pdf(content, calendar, url))

    toei_payload = load(TOEI_FILE)
    audited = audit(candidates, toei_payload)
    originals = {row["id"]: row for row in candidates}
    trip_index = build_trip_index(toei_payload)
    words_by_calendar = {calendar: page_words(content) for calendar, content in contents.items()}

    counts: Counter[str] = Counter()
    details = []
    for row in audited["results"]:
        original = originals[row["candidateId"]]
        words = words_by_calendar[row["calendar"]][int(row["pdfPage"])]
        fingerprint = extract_pdf_fingerprint(words, original)
        candidate_ids = [str(v) for v in row.get("toeiMatches") or []]
        scored = []
        for timetable_id in candidate_ids:
            trip = trip_index.get(timetable_id)
            if not trip:
                continue
            scored.append({"timetableId": timetable_id, **score_trip(fingerprint, trip)})

        strong = [item for item in scored if item["allMatched"] and item["totalPoints"] >= 3]
        status = str(row.get("toeiMatchStatus") or "")
        counts[status] += 1
        if len(fingerprint) < 3:
            counts[f"{status}:insufficient-fingerprint"] += 1
        elif len(strong) == 1:
            counts[f"{status}:sequence-singleton"] += 1
        elif len(strong) == 0:
            counts[f"{status}:sequence-none"] += 1
        else:
            counts[f"{status}:sequence-ambiguous"] += 1

        # Keep full detail for every unresolved row and for singleton rows that
        # fail the independent multi-station check; those are the dangerous ones.
        if status != "matched-singleton" or len(strong) != 1:
            details.append({
                "candidateId": row["candidateId"],
                "calendar": row["calendar"],
                "direction": row["direction"],
                "pdfPage": row["pdfPage"],
                "columnX": row["columnX"],
                "sourceBoundaryMinute": row["sourceBoundaryMinute"],
                "targetBoundaryMinute": row["targetBoundaryMinute"],
                "auditStatus": status,
                "fingerprint": fingerprint,
                "toeiCandidates": scored,
                "strongMatches": [item["timetableId"] for item in strong],
            })

    summary = {
        "counts": dict(sorted(counts.items())),
        "detailCount": len(details),
        "details": details,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
