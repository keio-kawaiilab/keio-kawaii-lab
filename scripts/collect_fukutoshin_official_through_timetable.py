#!/usr/bin/env python3
"""Retain Tokyo Metro's official Fukutoshin through-timetable e-book source.

The official timetable is a system-wide train matrix covering Yokohama Minatomirai,
Tokyu, Tokyo Metro, Seibu and Tobu.  This collector deliberately DOES NOT infer
physical train identity from close times, train numbers, or destinations.  It only
retains the official source pages so a later exact column parser can derive identity
from a single published train column.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://www.tokyometro.jp/info/files/timetable/fukutoshin/e-book_160326"
BOOKS = {
    "a": {"calendar": "Weekday", "direction": "MotomachiChukagai", "pages": 33},
    "b": {"calendar": "SaturdayHoliday", "direction": "MotomachiChukagai", "pages": 30},
    "c": {"calendar": "Weekday", "direction": "ShinrinKoenHanno", "pages": 30},
    "d": {"calendar": "SaturdayHoliday", "direction": "ShinrinKoenHanno", "pages": 28},
}
OPERATORS = ["横浜高速鉄道", "東京急行電鉄", "東京地下鉄", "西武鉄道", "東武鉄道"]
TRAIN_NUMBER_RE = re.compile(r"[AB]\d{4}[A-Z]")
OUT = Path("data/transit/fukutoshin/official-through-pages.json")
REPORT = Path("data/transit/fukutoshin/official-through-report.json")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "KeioKawaiiLabTransitDB/1.0 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read()


def extract_text(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    pages = []
    timetable_pages = 0
    train_number_occurrences = 0
    operator_complete_pages = 0

    for book, meta in BOOKS.items():
        for page_no in range(1, meta["pages"] + 1):
            url = f"{BASE}/book_{book}/pageindices/index{page_no}.html"
            raw = fetch(url)
            text = extract_text(raw)
            operators = [name for name in OPERATORS if name in text]
            train_numbers = sorted(set(TRAIN_NUMBER_RE.findall(text)))
            is_timetable = len(operators) == len(OPERATORS) and bool(train_numbers)
            timetable_pages += int(is_timetable)
            operator_complete_pages += int(len(operators) == len(OPERATORS))
            train_number_occurrences += len(train_numbers)
            pages.append(
                {
                    "book": book,
                    "calendar": meta["calendar"],
                    "direction": meta["direction"],
                    "page": page_no,
                    "sourceUrl": url,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "operatorsPresent": operators,
                    "trainNumbers": train_numbers,
                    "text": text,
                }
            )

    if timetable_pages < 20:
        raise SystemExit(f"Too few official timetable pages detected: {timetable_pages}")
    if train_number_occurrences < 100:
        raise SystemExit(f"Too few train-number cells detected: {train_number_occurrences}")

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "version": 1,
        "collectedAt": now,
        "source": "Tokyo Metro official Fukutoshin through-train timetable e-book",
        "sourceBase": BASE,
        "identityPolicy": {
            "singlePublishedTrainColumnMayEstablishIdentity": True,
            "timeProximityMayEstablishIdentity": False,
            "trainNumberAloneMayEstablishIdentity": False,
            "destinationAloneMayEstablishIdentity": False,
        },
        "books": BOOKS,
        "pages": pages,
    }
    report = {
        "version": 1,
        "generatedAt": now,
        "pageCount": len(pages),
        "operatorCompletePages": operator_complete_pages,
        "timetablePages": timetable_pages,
        "uniqueTrainNumberCellsByPage": train_number_occurrences,
        "operators": OPERATORS,
        "books": BOOKS,
        "sourceBase": BASE,
        "strictIdentity": True,
        "note": "Raw official page text is retained. No same-train edge is emitted until a published timetable column is parsed exactly.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
