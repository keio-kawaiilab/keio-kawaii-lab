#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

DEFAULT_WEEKDAY_URL = "https://www.keikyu.co.jp/ride/kakueki/pdf/other_weekday.pdf"
DEFAULT_HOLIDAY_URL = "https://www.keikyu.co.jp/ride/kakueki/pdf/other_holiday.pdf"
BOUNDARY_ID = "toei-keikyu-sengakuji"
KEIKYU_MAIN = "odpt.Railway:Keikyu.Main"
TOEI_ASAKUSA = "odpt.Railway:Toei.Asakusa"
TIME_RE = re.compile(r"^[0-9]{3,4}$")
NUMBER_RE = re.compile(r"^[0-9]{2,6}[A-Za-z]{0,2}$")


def norm(value: Any) -> str:
    return re.sub(r"[\s\u3000]+", "", unicodedata.normalize("NFKC", str(value or "")))


def cx(word: dict[str, Any]) -> float:
    return (float(word.get("x0", 0)) + float(word.get("x1", word.get("x0", 0)))) / 2


def cy(word: dict[str, Any]) -> float:
    return (float(word.get("top", 0)) + float(word.get("bottom", word.get("top", 0)))) / 2


def label_limit(words: list[dict[str, Any]]) -> float:
    width = max((float(w.get("x1", 0)) for w in words), default=595)
    return max(120.0, min(190.0, width * 0.27))


def data_start(words: list[dict[str, Any]]) -> float:
    return max(95.0, label_limit(words) * 0.75)


def rows(words: list[dict[str, Any]], tolerance: float = 3.0) -> list[dict[str, Any]]:
    left = [w for w in words if float(w.get("x0", 0)) < label_limit(words) and norm(w.get("text"))]
    left.sort(key=lambda w: (cy(w), float(w.get("x0", 0))))
    groups: list[list[dict[str, Any]]] = []
    for word in left:
        if groups and abs(cy(word) - sum(cy(w) for w in groups[-1]) / len(groups[-1])) <= tolerance:
            groups[-1].append(word)
        else:
            groups.append([word])
    out = []
    for group in groups:
        group.sort(key=lambda w: float(w.get("x0", 0)))
        text = norm("".join(str(w.get("text") or "") for w in group))
        if text:
            out.append({"text": text, "y": sum(cy(w) for w in group) / len(group)})
    return out


def cells(words: list[dict[str, Any]], y: float, tolerance: float = 3.7) -> list[dict[str, Any]]:
    out = []
    for word in words:
        if float(word.get("x0", 0)) < data_start(words) or abs(cy(word) - y) > tolerance:
            continue
        text = norm(word.get("text"))
        if text:
            out.append({"text": text, "x": cx(word)})
    return sorted(out, key=lambda row: row["x"])


def hhmm(value: str) -> int | None:
    if not TIME_RE.fullmatch(value):
        return None
    raw = int(value)
    hour, minute = divmod(raw, 100)
    return hour * 60 + minute if hour <= 29 and minute <= 59 else None


def time_cells(words: list[dict[str, Any]], y: float) -> list[dict[str, Any]]:
    out = []
    for cell in cells(words, y):
        minute = hhmm(cell["text"])
        if minute is not None:
            out.append({**cell, "minute": minute})
    return out


def nearest(items: list[dict[str, Any]], x: float, tolerance: float) -> dict[str, Any] | None:
    if not items:
        return None
    item = min(items, key=lambda row: abs(float(row["x"]) - x))
    return item if abs(float(item["x"]) - x) <= tolerance else None


def column_tolerance(items: list[dict[str, Any]]) -> float:
    xs = sorted({round(float(row["x"]), 2) for row in items})
    gaps = [b - a for a, b in zip(xs, xs[1:]) if 2 < b - a < 80]
    return max(3.5, min(11.0, median(gaps) * 0.44)) if gaps else 8.0


def direction(above: str, below: str) -> str:
    above, below = norm(above), norm(below)
    if "泉岳寺" in above and "発" in above:
        return "keikyu-to-toei"
    if "泉岳寺" in below and "着" in below and "発" not in above:
        return "toei-to-keikyu"
    return ""


def stable_id(*parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "keikyu-connection-pdf:" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def extract_page_candidates(words: list[dict[str, Any]], *, page_number: int, calendar: str, source_url: str) -> list[dict[str, Any]]:
    page_rows = rows(words)
    number_rows = [row for row in page_rows if "列車番号" in row["text"]]
    sengakuji_rows = [row for row in page_rows if "泉岳寺" in row["text"]]
    output: list[dict[str, Any]] = []
    for number_row in number_rows:
        above = [row for row in sengakuji_rows if row["y"] < number_row["y"]]
        below = [row for row in sengakuji_rows if row["y"] > number_row["y"]]
        if not above or not below:
            continue
        before = max(above, key=lambda row: row["y"])
        after = min(below, key=lambda row: row["y"])
        if number_row["y"] - before["y"] > 70 or after["y"] - number_row["y"] > 70:
            continue
        travel_direction = direction(before["text"], after["text"])
        if not travel_direction:
            continue
        before_times, after_times = time_cells(words, before["y"]), time_cells(words, after["y"])
        if not before_times or not after_times:
            continue
        tolerance = column_tolerance(before_times + after_times)
        train_numbers = [row for row in cells(words, number_row["y"]) if NUMBER_RE.fullmatch(row["text"])]
        for first in before_times:
            second = nearest(after_times, float(first["x"]), tolerance)
            if not second:
                continue
            delta = int(second["minute"]) - int(first["minute"])
            while delta < -720:
                delta += 1440
            if not 0 <= delta <= 4:
                continue
            number = nearest(train_numbers, float(first["x"]), tolerance)
            item = {
                "status": "official-column-evidence",
                "operator": "keikyu",
                "calendar": calendar,
                "direction": travel_direction,
                "boundaryId": BOUNDARY_ID,
                "boundaryStation": "泉岳寺",
                "sourceBoundaryMinute": int(first["minute"]),
                "targetBoundaryMinute": int(second["minute"]),
                "boundaryTrainNumber": norm((number or {}).get("text")),
                "pdfPage": page_number,
                "columnX": round(float(first["x"]), 2),
                "evidence": ["operator-official-connection-timetable", "same-printed-column-spans-both-sides-of-sengakuji"],
                "sourceUrl": source_url,
                "rowGeometry": {"sourceBoundaryText": before["text"], "sourceBoundaryY": round(float(before["y"]), 2), "boundaryTrainNumberY": round(float(number_row["y"]), 2), "targetBoundaryText": after["text"], "targetBoundaryY": round(float(after["y"]), 2)},
            }
            item["id"] = stable_id(calendar, travel_direction, page_number, item["columnX"], item["sourceBoundaryMinute"], item["targetBoundaryMinute"], item["boundaryTrainNumber"])
            output.append(item)
    return list({row["id"]: row for row in output}.values())


def calendar_matches(raw: Any, service: str) -> bool:
    text = norm(raw).lower()
    return ("weekday" in text or "平日" in text) if service == "weekday" else any(token in text for token in ("saturdayholiday", "holiday", "休日", "土休日"))


def endpoint(fragment: dict[str, Any], first: bool) -> list[Any] | None:
    stops = fragment.get("stops") or []
    if not isinstance(stops, list) or not stops:
        return None
    stop = stops[0] if first else stops[-1]
    return stop if isinstance(stop, list) and len(stop) >= 3 else None


def minute_distance(a: int, b: int) -> int:
    return min(abs(a - b), abs(a + 1440 - b), abs(a - b - 1440))


def fragment_matches(fragment: dict[str, Any], railway: str, service: str, first: bool, minute: int, tolerance: int) -> bool:
    if str(fragment.get("railway") or "") != railway or not calendar_matches(fragment.get("calendar"), service):
        return False
    stop = endpoint(fragment, first)
    if not stop or not str(stop[0] or "").endswith(".Sengakuji"):
        return False
    values = [int(value) for value in stop[1:3] if isinstance(value, (int, float))]
    return any(minute_distance(value, minute) <= tolerance for value in values)


def match_candidates_to_fragments(candidates: list[dict[str, Any]], fragments: list[dict[str, Any]], *, minute_tolerance: int = 1) -> list[dict[str, Any]]:
    output = []
    for candidate in candidates:
        travel_direction = str(candidate.get("direction") or "")
        if travel_direction == "keikyu-to-toei":
            source_railway, target_railway = KEIKYU_MAIN, TOEI_ASAKUSA
        elif travel_direction == "toei-to-keikyu":
            source_railway, target_railway = TOEI_ASAKUSA, KEIKYU_MAIN
        else:
            output.append({**candidate, "matchStatus": "invalid-direction"})
            continue
        service = str(candidate.get("calendar") or "")
        source_minute = int(candidate["sourceBoundaryMinute"])
        target_minute = int(candidate["targetBoundaryMinute"])
        sources = [row for row in fragments if fragment_matches(row, source_railway, service, False, source_minute, minute_tolerance)]
        targets = [row for row in fragments if fragment_matches(row, target_railway, service, True, target_minute, minute_tolerance)]
        status = "matched-singleton" if len(sources) == 1 and len(targets) == 1 else "unmatched" if not sources or not targets else "ambiguous"
        output.append({
            **candidate,
            "matchStatus": status,
            "fromRailway": source_railway,
            "toRailway": target_railway,
            "fromFragment": sources[0].get("id") if len(sources) == 1 else None,
            "toFragment": targets[0].get("id") if len(targets) == 1 else None,
            "sourceMatches": [row.get("id") for row in sources],
            "targetMatches": [row.get("id") for row in targets],
            "matchPolicy": {"officialColumnSpansBothBoundarySidesRequired": True, "verifiedBoundaryRequired": True, "singletonFragmentMatchRequired": True, "boundaryMinuteTolerance": minute_tolerance, "trainNumberAloneMayEstablishIdentity": False, "timeProximityAloneMayEstablishIdentity": False},
        })
    return output


def load_fragments(folder: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for name in ("keikyu.json", "toei.json"):
        path = folder / name
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            output.extend(row for row in payload.get("fragments") or [] if isinstance(row, dict) and row.get("id"))
    return output


def fetch_pdf(url: str) -> bytes:
    import requests
    response = requests.get(url, headers={"User-Agent": "keio-kawaiilab-transit-evidence/2.0"}, timeout=(20, 180))
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise RuntimeError("official Keikyu source is not a PDF")
    return response.content


def extract_pdf(content: bytes, calendar: str, source_url: str) -> list[dict[str, Any]]:
    import pdfplumber
    output: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False, use_text_flow=False)
            output.extend(extract_page_candidates(words, page_number=page_number, calendar=calendar, source_url=source_url))
    return output


def diagnostics(content: bytes) -> None:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False, use_text_flow=False)
            found = [row for row in rows(words, 4.0) if "泉岳寺" in row["text"] or "列車番号" in row["text"]]
            if found:
                print("DEBUG_PAGE", page_number, json.dumps(found, ensure_ascii=False))


def payload(candidates: list[dict[str, Any]], matched: list[dict[str, Any]], source_url: str, calendar: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in matched:
        counts[row.get("matchStatus", "unknown")] = counts.get(row.get("matchStatus", "unknown"), 0) + 1
    return {
        "version": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": {"operator": "keikyu", "calendar": calendar, "url": source_url, "kind": "operator-official-connection-timetable-pdf"},
        "policy": {"autoPromoteUnknown": False, "officialColumnSpansBothBoundarySidesRequired": True, "verifiedOperationalBoundaryRequired": True, "singletonFragmentMatchRequired": True, "trainNumberAloneMayEstablishIdentity": False, "timeProximityAloneMayEstablishIdentity": False, "staleFragmentReferenceMustFailClosed": True},
        "summary": {"officialColumnCandidates": len(candidates), "matchedSingleton": counts.get("matched-singleton", 0), "ambiguous": counts.get("ambiguous", 0), "unmatched": counts.get("unmatched", 0)},
        "entries": matched,
    }


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--url", default="")
    cli.add_argument("--calendar", choices=("weekday", "holiday"), default="weekday")
    cli.add_argument("--fragment-dir", default="data/transit-v2/fragments")
    cli.add_argument("--output", default="data/transit-v2/keikyu-official-train-evidence.json")
    cli.add_argument("--minute-tolerance", type=int, default=1)
    args = cli.parse_args()
    source_url = args.url or (DEFAULT_WEEKDAY_URL if args.calendar == "weekday" else DEFAULT_HOLIDAY_URL)
    content = fetch_pdf(source_url)
    candidates = extract_pdf(content, args.calendar, source_url)
    matched = match_candidates_to_fragments(candidates, load_fragments(Path(args.fragment_dir)), minute_tolerance=max(0, args.minute_tolerance))
    data = payload(candidates, matched, source_url, args.calendar)
    Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data["summary"], ensure_ascii=False, indent=2))
    if not candidates:
        diagnostics(content)
        raise RuntimeError("No Sengakuji same-column candidates extracted from official connection timetable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
