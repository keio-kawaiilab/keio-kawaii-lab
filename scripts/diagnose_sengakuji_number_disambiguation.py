#!/usr/bin/env python3
"""Test whether official PDF train-number row can safely resolve ambiguous Sengakuji endpoint matches.

The printed timetable column is only a candidate: columns may be reused across the
train-number boundary.  A real cross-operator link still requires a Toei trip
whose endpoint is Sengakuji at the exact printed boundary minute.

For exact-minute ambiguities, train number is used only to identify *which* Toei
endpoint trip belongs to the already-established boundary candidate.  It never
creates a cross-operator link on its own.
"""
from __future__ import annotations

import io
import json
import re

import pdfplumber

from audit_toei_sengakuji_official_columns import TOEI_FILE, audit, load
from keikyu_official_train_evidence import (
    DEFAULT_HOLIDAY_URL,
    DEFAULT_WEEKDAY_URL,
    NUMBER_RE,
    cy,
    extract_pdf,
    fetch_pdf,
    norm,
)

CID_RE = re.compile(r"\(cid:\d+\)", re.IGNORECASE)


def clean_number(value: object) -> str:
    text = norm(value)
    text = CID_RE.sub("", text)
    return text if NUMBER_RE.fullmatch(text) else ""


def page_words(content: bytes):
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


def nearby_numbers(words, *, x: float, y: float, x_tolerance: float = 19.5, y_tolerance: float = 12.0):
    rows = []
    for word in words:
        center_x = (float(word.get("x0", 0)) + float(word.get("x1", word.get("x0", 0)))) / 2
        center_y = cy(word)
        if abs(center_x - x) > x_tolerance or abs(center_y - y) > y_tolerance:
            continue
        number = clean_number(word.get("text"))
        if number:
            rows.append({
                "number": number,
                "x": round(center_x, 2),
                "y": round(center_y, 2),
                "dx": round(center_x - x, 2),
                "dy": round(center_y - y, 2),
            })
    return sorted(rows, key=lambda row: (abs(row["dx"]), abs(row["dy"]), row["number"]))


def main() -> int:
    contents = {
        "weekday": fetch_pdf(DEFAULT_WEEKDAY_URL),
        "holiday": fetch_pdf(DEFAULT_HOLIDAY_URL),
    }
    candidates = []
    for calendar, content in contents.items():
        url = DEFAULT_WEEKDAY_URL if calendar == "weekday" else DEFAULT_HOLIDAY_URL
        candidates.extend(extract_pdf(content, calendar, url))

    audited = audit(candidates, load(TOEI_FILE))
    originals = {row["id"]: row for row in candidates}
    words_by_calendar = {calendar: page_words(content) for calendar, content in contents.items()}

    rows = []
    counts = {
        "ambiguous": 0,
        "ambiguous-resolved-by-number": 0,
        "ambiguous-no-number-resolution": 0,
        "unmatched": 0,
        "unmatched-with-nearby-number": 0,
    }
    for row in audited["results"]:
        status = row.get("toeiMatchStatus")
        if status not in {"ambiguous", "unmatched"}:
            continue
        original = originals[row["candidateId"]]
        calendar = row["calendar"]
        page = int(row["pdfPage"])
        x = float(row["columnX"])
        number_y = float((original.get("rowGeometry") or {}).get("boundaryTrainNumberY"))
        nearby = nearby_numbers(words_by_calendar[calendar][page], x=x, y=number_y)
        nearby_set = {item["number"] for item in nearby}
        toei_numbers = {str(value) for value in row.get("toeiTrainNumbers") or [] if value}
        intersection = sorted(nearby_set & toei_numbers)

        if status == "ambiguous":
            counts["ambiguous"] += 1
            if len(intersection) == 1:
                counts["ambiguous-resolved-by-number"] += 1
            else:
                counts["ambiguous-no-number-resolution"] += 1
        else:
            counts["unmatched"] += 1
            if nearby:
                counts["unmatched-with-nearby-number"] += 1

        rows.append({
            "candidateId": row["candidateId"],
            "calendar": calendar,
            "direction": row["direction"],
            "pdfPage": page,
            "columnX": x,
            "sourceBoundaryMinute": row["sourceBoundaryMinute"],
            "targetBoundaryMinute": row["targetBoundaryMinute"],
            "status": status,
            "currentBoundaryTrainNumber": row.get("boundaryTrainNumber"),
            "toeiTrainNumbers": sorted(toei_numbers),
            "nearbyNumbers": nearby,
            "intersection": intersection,
            "safeSingletonResolution": intersection[0] if len(intersection) == 1 else None,
        })

    print(json.dumps({"counts": counts, "rows": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
