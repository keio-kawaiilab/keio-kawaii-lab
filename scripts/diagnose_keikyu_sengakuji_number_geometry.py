#!/usr/bin/env python3
"""Dump raw PDF word geometry around unresolved Sengakuji official columns."""
from __future__ import annotations

import io
import json

import pdfplumber

from audit_toei_sengakuji_official_columns import TOEI_FILE, audit, load
from keikyu_official_train_evidence import (
    DEFAULT_HOLIDAY_URL,
    DEFAULT_WEEKDAY_URL,
    cy,
    extract_pdf,
    fetch_pdf,
    norm,
)


def page_words(content: bytes):
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return {
            number: page.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False, use_text_flow=False)
            for number, page in enumerate(pdf.pages, start=1)
        }


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
    unresolved = [row for row in audited["results"] if row.get("toeiMatchStatus") != "matched-singleton"]
    words_by_calendar = {calendar: page_words(content) for calendar, content in contents.items()}
    rows = []
    for row in unresolved:
        calendar = row["calendar"]
        page_number = int(row["pdfPage"])
        x = float(row["columnX"])
        # Recover the original candidate to obtain the train-number row Y.
        original = next(c for c in candidates if c["id"] == row["candidateId"])
        number_y = float((original.get("rowGeometry") or {}).get("boundaryTrainNumberY"))
        raw = words_by_calendar[calendar][page_number]
        nearby = []
        for word in raw:
            center_x = (float(word.get("x0", 0)) + float(word.get("x1", word.get("x0", 0)))) / 2
            center_y = cy(word)
            if abs(center_x - x) <= 26 and abs(center_y - number_y) <= 12:
                nearby.append({
                    "text": norm(word.get("text")),
                    "x": round(center_x, 2),
                    "y": round(center_y, 2),
                    "dx": round(center_x - x, 2),
                    "dy": round(center_y - number_y, 2),
                })
        nearby.sort(key=lambda item: (item["y"], item["x"]))
        rows.append({
            "candidateId": row["candidateId"],
            "calendar": calendar,
            "direction": row["direction"],
            "pdfPage": page_number,
            "columnX": x,
            "numberRowY": number_y,
            "extractedBoundaryTrainNumber": row.get("boundaryTrainNumber"),
            "status": row["toeiMatchStatus"],
            "toeiTrainNumbers": row.get("toeiTrainNumbers"),
            "nearbyRawWords": nearby,
        })
    print(json.dumps({"count": len(rows), "rows": rows}, ensure_ascii=False, indent=2))
    if len(rows) != 36:
        raise RuntimeError(f"expected 36 unresolved columns, got {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
