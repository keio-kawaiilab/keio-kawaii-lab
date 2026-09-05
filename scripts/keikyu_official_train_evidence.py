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
from typing import Any, Iterable

DEFAULT_WEEKDAY_URL = "https://www.keikyu.co.jp/ride/kakueki/pdf/mainline_weekday.pdf"
BOUNDARY_ID = "toei-keikyu-sengakuji"
KEIKYU_MAIN = "odpt.Railway:Keikyu.Main"
TOEI_ASAKUSA = "odpt.Railway:Toei.Asakusa"

TRAIN_NUMBER_RE = re.compile(r"^[0-9]{2,5}[A-Za-z]?$")
TIME_RE = re.compile(r"^[0-9]{3,4}$")


def normalize_text(value: Any) -> str:
    return re.sub(r"[\s\u3000]+", "", unicodedata.normalize("NFKC", str(value or "")))


def stable_id(prefix: str, *parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"{prefix}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


def word_center_y(word: dict[str, Any]) -> float:
    return (float(word.get("top", 0.0)) + float(word.get("bottom", word.get("top", 0.0)))) / 2.0


def word_center_x(word: dict[str, Any]) -> float:
    return (float(word.get("x0", 0.0)) + float(word.get("x1", word.get("x0", 0.0)))) / 2.0


def cluster_rows(
    words: Iterable[dict[str, Any]],
    *,
    x_max: float = 180.0,
    y_tolerance: float = 2.6,
) -> list[dict[str, Any]]:
    labels = [
        word
        for word in words
        if float(word.get("x0", 0.0)) < x_max and normalize_text(word.get("text"))
    ]
    labels.sort(key=lambda word: (word_center_y(word), float(word.get("x0", 0.0))))
    groups: list[list[dict[str, Any]]] = []
    for word in labels:
        y = word_center_y(word)
        if groups:
            previous_y = sum(word_center_y(item) for item in groups[-1]) / len(groups[-1])
            if abs(y - previous_y) <= y_tolerance:
                groups[-1].append(word)
                continue
        groups.append([word])
    rows = []
    for group in groups:
        ordered = sorted(group, key=lambda word: float(word.get("x0", 0.0)))
        text = normalize_text("".join(str(word.get("text") or "") for word in ordered))
        if not text:
            continue
        rows.append(
            {
                "text": text,
                "y": sum(word_center_y(word) for word in group) / len(group),
                "words": ordered,
            }
        )
    return rows


def words_on_row(
    words: Iterable[dict[str, Any]],
    y: float,
    *,
    x_min: float = 180.0,
    y_tolerance: float = 3.4,
) -> list[dict[str, Any]]:
    result = []
    for word in words:
        if float(word.get("x0", 0.0)) < x_min:
            continue
        if abs(word_center_y(word) - y) > y_tolerance:
            continue
        text = normalize_text(word.get("text"))
        if not text:
            continue
        result.append({"text": text, "x": word_center_x(word)})
    return sorted(result, key=lambda item: item["x"])


def parse_hhmm(value: Any) -> int | None:
    text = normalize_text(value)
    if not TIME_RE.fullmatch(text):
        return None
    raw = int(text)
    hour, minute = divmod(raw, 100)
    if hour > 29 or minute > 59:
        return None
    return hour * 60 + minute


def raw_number_cells(words: Iterable[dict[str, Any]], y: float) -> list[dict[str, Any]]:
    # Train numbers can be all digits and therefore look like HHMM values.
    # Row semantics ("列車番号") establish that these are train-number cells;
    # the number itself never establishes train identity.
    return [
        cell
        for cell in words_on_row(words, y)
        if TRAIN_NUMBER_RE.fullmatch(cell["text"])
    ]


def time_cells(words: Iterable[dict[str, Any]], y: float) -> list[dict[str, Any]]:
    result = []
    for cell in words_on_row(words, y):
        minute = parse_hhmm(cell["text"])
        if minute is not None:
            result.append({**cell, "minute": minute})
    return result


def estimate_column_tolerance(header_cells: list[dict[str, Any]]) -> float:
    xs = sorted({round(float(cell["x"]), 2) for cell in header_cells})
    gaps = [b - a for a, b in zip(xs, xs[1:]) if 2.0 < (b - a) < 80.0]
    if not gaps:
        return 9.0
    return max(4.0, min(12.0, median(gaps) * 0.42))


def nearest_cell(
    cells: list[dict[str, Any]],
    x: float,
    max_dx: float,
) -> dict[str, Any] | None:
    if not cells:
        return None
    nearest = min(cells, key=lambda cell: abs(float(cell["x"]) - x))
    return nearest if abs(float(nearest["x"]) - x) <= max_dx else None


def extract_page_candidates(
    words: list[dict[str, Any]],
    *,
    page_number: int,
    calendar: str,
    source_url: str,
) -> list[dict[str, Any]]:
    rows = cluster_rows(words)
    train_number_rows = [row for row in rows if "列車番号" in row["text"]]
    boundary_rows = [row for row in rows if "泉岳寺" in row["text"]]

    if not train_number_rows or not boundary_rows:
        return []

    header_candidates = [row for row in train_number_rows if row["y"] < 220.0]
    header_row = min(header_candidates or train_number_rows, key=lambda row: row["y"])
    header_cells = raw_number_cells(words, header_row["y"])
    if not header_cells:
        return []

    boundary_number_rows = [
        row for row in train_number_rows if abs(row["y"] - header_row["y"]) > 8.0
    ]
    if not boundary_number_rows:
        return []

    tolerance = estimate_column_tolerance(header_cells)
    output: list[dict[str, Any]] = []

    for number_row in boundary_number_rows:
        boundary_row = min(boundary_rows, key=lambda row: abs(row["y"] - number_row["y"]))
        if abs(boundary_row["y"] - number_row["y"]) > 135.0:
            continue

        continuation_cells = raw_number_cells(words, number_row["y"])
        boundary_time_cells = time_cells(words, boundary_row["y"])
        if not continuation_cells or not boundary_time_cells:
            continue

        direction = (
            "keikyu-to-toei"
            if number_row["y"] > boundary_row["y"]
            else "toei-to-keikyu"
        )
        boundary_time_kind = (
            "arrival"
            if "着" in boundary_row["text"]
            else "departure"
            if "発" in boundary_row["text"]
            else "unspecified"
        )

        for continuation in continuation_cells:
            x = float(continuation["x"])
            header = nearest_cell(header_cells, x, tolerance)
            boundary_time = nearest_cell(boundary_time_cells, x, tolerance)
            if not header or not boundary_time:
                continue
            local_number = normalize_text(header["text"])
            continuation_number = normalize_text(continuation["text"])
            if not local_number or not continuation_number:
                continue
            minute = int(boundary_time["minute"])
            candidate_id = stable_id(
                "keikyu-pdf",
                calendar,
                direction,
                page_number,
                round(x, 1),
                local_number,
                continuation_number,
                minute,
            )
            output.append(
                {
                    "id": candidate_id,
                    "status": "official-column-evidence",
                    "operator": "keikyu",
                    "calendar": calendar,
                    "direction": direction,
                    "boundaryId": BOUNDARY_ID,
                    "boundaryStation": "泉岳寺",
                    "boundaryMinute": minute,
                    "boundaryTimeKind": boundary_time_kind,
                    "localKeikyuTrainNumber": local_number,
                    "continuationTrainNumber": continuation_number,
                    "pdfPage": page_number,
                    "columnX": round(x, 2),
                    "evidence": [
                        "operator-official-full-timetable",
                        "same-printed-train-column-across-sengakuji",
                    ],
                    "sourceUrl": source_url,
                    "rowGeometry": {
                        "headerTrainNumberY": round(float(header_row["y"]), 2),
                        "boundaryTimeY": round(float(boundary_row["y"]), 2),
                        "continuationTrainNumberY": round(float(number_row["y"]), 2),
                    },
                }
            )

    unique: dict[str, dict[str, Any]] = {}
    for row in output:
        unique[row["id"]] = row
    return list(unique.values())


def calendar_matches(raw: Any, service: str) -> bool:
    value = normalize_text(raw).lower()
    if service == "weekday":
        return "weekday" in value or "平日" in value
    return any(token in value for token in ("saturdayholiday", "holiday", "休日", "土休日"))


def endpoint_stop(
    fragment: dict[str, Any],
    *,
    first: bool,
) -> list[Any] | None:
    stops = fragment.get("stops") or []
    if not isinstance(stops, list) or not stops:
        return None
    stop = stops[0] if first else stops[-1]
    return stop if isinstance(stop, list) and len(stop) >= 3 else None


def is_sengakuji_stop(stop: list[Any] | None) -> bool:
    if not stop:
        return False
    station = str(stop[0] or "")
    return station.endswith(".Sengakuji")


def minute_distance(a: int, b: int) -> int:
    values = (abs(a - b), abs((a + 1440) - b), abs(a - (b + 1440)))
    return min(values)


def stop_matches_minute(stop: list[Any] | None, minute: int, tolerance: int) -> bool:
    if not stop:
        return False
    values = [
        int(value)
        for value in stop[1:3]
        if isinstance(value, (int, float))
    ]
    return any(minute_distance(value, minute) <= tolerance for value in values)


def normalized_train_number(fragment: dict[str, Any]) -> str:
    return normalize_text(fragment.get("trainNumber")).upper()


def fragment_matches_candidate(
    fragment: dict[str, Any],
    *,
    railway: str,
    service: str,
    first_stop: bool,
    boundary_minute: int,
    expected_train_number: str,
    minute_tolerance: int = 2,
) -> bool:
    if str(fragment.get("railway") or "") != railway:
        return False
    if not calendar_matches(fragment.get("calendar"), service):
        return False
    stop = endpoint_stop(fragment, first=first_stop)
    if not is_sengakuji_stop(stop):
        return False
    if not stop_matches_minute(stop, boundary_minute, minute_tolerance):
        return False

    actual_number = normalized_train_number(fragment)
    expected = normalize_text(expected_train_number).upper()
    # Inferred station-timetable fragments intentionally have no train number.
    # If an official fragment does publish one, use it only as an additional
    # consistency check alongside the official same-column evidence and
    # boundary endpoint/time selector.
    if actual_number and expected and actual_number != expected:
        return False
    return True


def match_candidates_to_fragments(
    candidates: list[dict[str, Any]],
    fragments: list[dict[str, Any]],
    *,
    minute_tolerance: int = 2,
) -> list[dict[str, Any]]:
    output = []
    for candidate in candidates:
        direction = str(candidate.get("direction") or "")
        service = str(candidate.get("calendar") or "")
        minute = int(candidate.get("boundaryMinute"))
        local_number = str(candidate.get("localKeikyuTrainNumber") or "")
        continuation_number = str(candidate.get("continuationTrainNumber") or "")

        if direction == "keikyu-to-toei":
            source_railway, target_railway = KEIKYU_MAIN, TOEI_ASAKUSA
            source_first, target_first = False, True
            source_number, target_number = local_number, continuation_number
        elif direction == "toei-to-keikyu":
            source_railway, target_railway = TOEI_ASAKUSA, KEIKYU_MAIN
            source_first, target_first = False, True
            source_number, target_number = continuation_number, local_number
        else:
            output.append({**candidate, "matchStatus": "invalid-direction"})
            continue

        sources = [
            fragment
            for fragment in fragments
            if fragment_matches_candidate(
                fragment,
                railway=source_railway,
                service=service,
                first_stop=source_first,
                boundary_minute=minute,
                expected_train_number=source_number,
                minute_tolerance=minute_tolerance,
            )
        ]
        targets = [
            fragment
            for fragment in fragments
            if fragment_matches_candidate(
                fragment,
                railway=target_railway,
                service=service,
                first_stop=target_first,
                boundary_minute=minute,
                expected_train_number=target_number,
                minute_tolerance=minute_tolerance,
            )
        ]

        if len(sources) == 1 and len(targets) == 1:
            status = "matched-singleton"
        elif not sources or not targets:
            status = "unmatched"
        else:
            status = "ambiguous"

        output.append(
            {
                **candidate,
                "matchStatus": status,
                "fromRailway": source_railway,
                "toRailway": target_railway,
                "fromFragment": sources[0].get("id") if len(sources) == 1 else None,
                "toFragment": targets[0].get("id") if len(targets) == 1 else None,
                "sourceMatches": [fragment.get("id") for fragment in sources],
                "targetMatches": [fragment.get("id") for fragment in targets],
                "matchPolicy": {
                    "sameOfficialPrintedColumnRequired": True,
                    "verifiedBoundaryRequired": True,
                    "singletonFragmentMatchRequired": True,
                    "boundaryMinuteTolerance": minute_tolerance,
                    "trainNumberAloneMayEstablishIdentity": False,
                    "timeProximityAloneMayEstablishIdentity": False,
                },
            }
        )
    return output


def load_fragment_files(fragment_dir: Path) -> list[dict[str, Any]]:
    fragments: list[dict[str, Any]] = []
    for name in ("keikyu.json", "toei.json"):
        path = fragment_dir / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        fragments.extend(
            row
            for row in payload.get("fragments") or []
            if isinstance(row, dict) and row.get("id")
        )
    return fragments


def extract_pdf(
    content: bytes,
    *,
    calendar: str,
    source_url: str,
) -> list[dict[str, Any]]:
    import pdfplumber  # type: ignore

    candidates: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(
                x_tolerance=1,
                y_tolerance=1,
                keep_blank_chars=False,
                use_text_flow=False,
            )
            candidates.extend(
                extract_page_candidates(
                    words,
                    page_number=page_number,
                    calendar=calendar,
                    source_url=source_url,
                )
            )
    return candidates


def fetch_pdf(url: str) -> bytes:
    import requests  # type: ignore

    response = requests.get(
        url,
        headers={"User-Agent": "keio-kawaiilab-transit-evidence/1.0"},
        timeout=(20, 180),
    )
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"official Keikyu source is not a PDF: {url}")
    return response.content


def build_payload(
    candidates: list[dict[str, Any]],
    matched: list[dict[str, Any]],
    *,
    source_url: str,
    calendar: str,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in matched:
        key = str(row.get("matchStatus") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": {
            "operator": "keikyu",
            "calendar": calendar,
            "url": source_url,
            "kind": "operator-official-full-timetable-pdf",
        },
        "policy": {
            "purpose": "Per-train same-column evidence at the verified Sengakuji operational boundary.",
            "autoPromoteUnknown": False,
            "sameOfficialPrintedColumnRequired": True,
            "verifiedOperationalBoundaryRequired": True,
            "singletonFragmentMatchRequired": True,
            "trainNumberAloneMayEstablishIdentity": False,
            "timeProximityAloneMayEstablishIdentity": False,
            "staleFragmentReferenceMustFailClosed": True,
        },
        "summary": {
            "officialColumnCandidates": len(candidates),
            "matchedSingleton": counts.get("matched-singleton", 0),
            "ambiguous": counts.get("ambiguous", 0),
            "unmatched": counts.get("unmatched", 0),
            "other": sum(
                count
                for key, count in counts.items()
                if key not in {"matched-singleton", "ambiguous", "unmatched"}
            ),
        },
        "entries": matched,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract strict Keikyu official same-train evidence at Sengakuji."
    )
    parser.add_argument("--url", default=DEFAULT_WEEKDAY_URL)
    parser.add_argument("--calendar", choices=("weekday", "holiday"), default="weekday")
    parser.add_argument(
        "--fragment-dir",
        default="data/transit-v2/fragments",
        help="Directory containing keikyu.json and toei.json fragment files.",
    )
    parser.add_argument(
        "--output",
        default="data/transit-v2/keikyu-official-train-evidence.json",
    )
    parser.add_argument("--minute-tolerance", type=int, default=2)
    args = parser.parse_args()

    content = fetch_pdf(args.url)
    candidates = extract_pdf(content, calendar=args.calendar, source_url=args.url)
    fragments = load_fragment_files(Path(args.fragment_dir))
    matched = match_candidates_to_fragments(
        candidates,
        fragments,
        minute_tolerance=max(0, int(args.minute_tolerance)),
    )
    payload = build_payload(
        candidates,
        matched,
        source_url=args.url,
        calendar=args.calendar,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    if not candidates:
        raise RuntimeError("No Sengakuji same-column candidates were extracted from the official PDF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
