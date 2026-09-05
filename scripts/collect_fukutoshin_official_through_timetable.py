#!/usr/bin/env python3
"""Retain Tokyo Metro's official Fukutoshin through-timetable e-book source.

The official timetable is a system-wide train matrix covering Yokohama Minatomirai,
Tokyu, Tokyo Metro, Seibu and Tobu. This collector deliberately DOES NOT infer
physical train identity from close times, train numbers, or destinations. It only
retains the official source pages so a later exact column parser can derive identity
from a single published train column.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.error
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
OPERATORS = ["横浜高速鉄道", "東急電鉄", "東京地下鉄", "西武鉄道", "東武鉄道"]
# The official e-book body identifies the five-company network by line names rather
# than printing all five company names on every timetable page. These route markers
# are therefore the stable page-level completeness check.
ROUTE_MARKERS = ["みなとみらい線", "東急東横線", "副都心線", "西武有楽町線", "東武東上線"]
# Official train numbers include both three- and four-digit numeric bodies, e.g.
# B915S and B1052K. Train number is diagnostic only; it never establishes identity.
TRAIN_NUMBER_RE = re.compile(r"[AB]\d{3,4}[A-Z]")
OUT = Path("data/transit/fukutoshin/official-through-pages.json")
REPORT = Path("data/transit/fukutoshin/official-through-report.json")


def fetch(url: str) -> bytes:
    last_error: Exception | None = None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
        "Referer": f"{BASE}/",
    }
    for attempt in range(4):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return res.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == 3:
                break
            time.sleep(2**attempt)
    raise RuntimeError(f"Failed to fetch official Fukutoshin page after retries: {url}: {last_error}")


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
    route_marker_complete_pages = 0

    for book, meta in BOOKS.items():
        for page_no in range(1, meta["pages"] + 1):
            url = f"{BASE}/book_{book}/pageindices/index{page_no}.html"
            raw = fetch(url)
            text = extract_text(raw)
            route_markers = [name for name in ROUTE_MARKERS if name in text]
            train_numbers = sorted(set(TRAIN_NUMBER_RE.findall(text)))
            is_timetable = len(route_markers) == len(ROUTE_MARKERS) and bool(train_numbers)
            timetable_pages += int(is_timetable)
            route_marker_complete_pages += int(len(route_markers) == len(ROUTE_MARKERS))
            train_number_occurrences += len(train_numbers)
            pages.append(
                {
                    "book": book,
                    "calendar": meta["calendar"],
                    "direction": meta["direction"],
                    "page": page_no,
                    "sourceUrl": url,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "routeMarkersPresent": route_markers,
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
        "version": 2,
        "collectedAt": now,
        "source": "Tokyo Metro official Fukutoshin through-train timetable e-book",
        "sourceBase": BASE,
        "identityPolicy": {
            "singlePublishedTrainColumnMayEstablishIdentity": True,
            "timeProximityMayEstablishIdentity": False,
            "trainNumberAloneMayEstablishIdentity": False,
            "destinationAloneMayEstablishIdentity": False,
        },
        "operators": OPERATORS,
        "routeMarkers": ROUTE_MARKERS,
        "books": BOOKS,
        "pages": pages,
    }
    report = {
        "version": 2,
        "generatedAt": now,
        "pageCount": len(pages),
        "routeMarkerCompletePages": route_marker_complete_pages,
        # Kept for compatibility with any existing readers of the v1 report.
        "operatorCompletePages": route_marker_complete_pages,
        "timetablePages": timetable_pages,
        "uniqueTrainNumberCellsByPage": train_number_occurrences,
        "operators": OPERATORS,
        "routeMarkers": ROUTE_MARKERS,
        "books": BOOKS,
        "sourceBase": BASE,
        "strictIdentity": True,
        "note": "Raw official page text is retained. Same-train identity may be emitted only by parsing one published timetable column exactly; close times, train numbers and destinations alone are forbidden.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
