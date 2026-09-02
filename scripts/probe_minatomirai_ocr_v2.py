#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import statistics
from pathlib import Path

import requests
from PIL import Image

import probe_minatomirai_ocr as base

OUT = Path("data/transit/yokohama-minatomirai/ocr-probe.json")


def raw_values(image: Image.Image, first_x: float):
    cells, dash_count = base.candidate_cells(image, first_x)
    sheet, locator = base.contact_sheet(cells, threshold=False)
    first = base.read_sheet(sheet, locator)
    unresolved = [i for i in range(len(cells)) if len(first.get(i, "")) != 2]
    second = {}
    if unresolved:
        retry_cells = [cells[i] for i in unresolved]
        retry_sheet, retry_locator = base.contact_sheet(retry_cells, threshold=True)
        retry_values = base.read_sheet(retry_sheet, retry_locator)
        second = {unresolved[i]: value for i, value in retry_values.items()}
    values = dict(first)
    for i, value in second.items():
        if len(values.get(i, "")) != 2 and len(value) == 2:
            values[i] = value
    rows = {hour: [] for hour in range(4, 25)}
    for i, cell in enumerate(cells):
        rows[cell["hour"]].append((cell["column"], values.get(i, ""), cell["ink"]))
    for hour in rows:
        rows[hour].sort()
    return rows, dash_count, len(cells)


def digit_cost(raw: str, value: int) -> int:
    target = f"{value:02d}"
    raw = "".join(ch for ch in str(raw) if ch.isdigit())
    if len(raw) == 2:
        return sum(a != b for a, b in zip(raw, target)) * 12
    if len(raw) == 1:
        # Tesseract often drops the leading zero on 01-09.
        if target[1] == raw:
            return 8
        if target[0] == raw:
            return 11
        return 20
    if len(raw) > 2:
        # Cell separation should prevent this, but keep a recoverable fallback.
        best = min(
            sum(a != b for a, b in zip(raw[start:start + 2], target))
            for start in range(len(raw) - 1)
        )
        return 16 + best * 8
    return 28


def repair_row(items):
    if not items:
        return [], {"edits": 0, "targetGap": None, "raw": []}
    raw = [text for _, text, _ in items]
    numeric = [int(text) if len(text) == 2 and text.isdigit() and int(text) <= 59 else None for text in raw]
    if all(v is not None for v in numeric) and all(a < b for a, b in zip(numeric, numeric[1:])):
        return numeric, {"edits": 0, "targetGap": None, "raw": raw}

    diffs = [
        b - a for a, b in zip(numeric, numeric[1:])
        if a is not None and b is not None and 1 <= b - a <= 15
    ]
    target_gap = float(statistics.median(diffs)) if diffs else 4.0
    n = len(items)
    inf = 10**9
    dp = [[inf] * 60 for _ in range(n)]
    prev = [[-1] * 60 for _ in range(n)]
    for value in range(60):
        dp[0][value] = digit_cost(raw[0], value)
    for i in range(1, n):
        for value in range(60):
            own = digit_cost(raw[i], value)
            best_cost = inf
            best_prev = -1
            for p in range(value):
                if dp[i - 1][p] >= inf:
                    continue
                gap = value - p
                # Train gaps on this line are usually small; this tie-breaker
                # resolves OCR collisions like 51,59,59 -> 51,55,59.
                gap_penalty = abs(gap - target_gap)
                if gap > 18:
                    gap_penalty += (gap - 18) * 2
                cost = dp[i - 1][p] + own + gap_penalty
                if cost < best_cost:
                    best_cost = cost
                    best_prev = p
            dp[i][value] = best_cost
            prev[i][value] = best_prev
    end = min(range(60), key=lambda value: dp[-1][value])
    result = [end]
    for i in range(n - 1, 0, -1):
        end = prev[i][end]
        if end < 0:
            return [], {"edits": n, "targetGap": target_gap, "raw": raw, "failed": True}
        result.append(end)
    result.reverse()
    edits = sum(f"{value:02d}" != text for value, text in zip(result, raw))
    return result, {"edits": edits, "targetGap": target_gap, "raw": raw}


def parse_at_origin(image: Image.Image, first_x: float):
    rows, dash_count, candidate_count = raw_values(image, first_x)
    parsed = {str(hour): [] for hour in range(4, 25)}
    repairs = {}
    total_edits = 0
    for hour, items in rows.items():
        values, diag = repair_row(items)
        parsed[str(hour)] = values
        if diag.get("edits"):
            repairs[str(hour)] = diag
            total_edits += int(diag["edits"])
    recognized = sum(len(v) for v in parsed.values())
    return parsed, {
        "firstX": first_x,
        "candidateCount": candidate_count,
        "dashCount": dash_count,
        "recognizedCount": recognized,
        "repairCount": total_edits,
        "repairs": repairs,
    }


def parse_rows(image: Image.Image):
    trials = [parse_at_origin(image, first_x) for first_x in base.FIRST_X_CANDIDATES]
    # Prefer the grid origin that needs the fewest repairs, then the one that
    # yields the most plausible timetable cells.
    parsed, diag = min(
        trials,
        key=lambda item: (
            item[1]["repairCount"],
            -item[1]["recognizedCount"],
            abs(item[1]["candidateCount"] - 270),
        ),
    )
    diag = dict(diag)
    diag["originTrials"] = [trial_diag for _, trial_diag in trials]
    return parsed, diag


def main() -> int:
    result = {"version": 12, "samples": {}}
    failures = []
    session = requests.Session()
    session.headers["User-Agent"] = "Keio-Kawaii-Lab timetable validation/1.0"
    for name, url in base.SAMPLES.items():
        response = session.get(url, timeout=60)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        parsed, diagnostics = parse_rows(image)
        result["samples"][name] = {
            "url": url,
            "size": list(image.size),
            "rows": parsed,
            "departureCount": sum(len(row) for row in parsed.values()),
            "diagnostics": diagnostics,
        }
        print(name, "departures", result["samples"][name]["departureCount"], diagnostics, flush=True)
        try:
            base.validate_sample(name, parsed)
        except RuntimeError as exc:
            failures.append(str(exc))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if failures:
        raise RuntimeError("; ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
