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


def collect_raw(image: Image.Image, first_x: float):
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
    return rows, {"firstX": first_x, "candidateCount": len(cells), "dashCount": dash_count}


def single_cost(raw: str, value: int) -> int:
    target = f"{value:02d}"
    raw = "".join(ch for ch in str(raw) if ch.isdigit())
    if len(raw) == 2:
        return sum(a != b for a, b in zip(raw, target)) * 12
    if len(raw) == 1:
        if target[1] == raw:
            return 8
        if target[0] == raw:
            return 10
        return 20
    if len(raw) > 2:
        best = min(
            sum(a != b for a, b in zip(raw[start:start + 2], target))
            for start in range(len(raw) - 1)
        )
        return 16 + best * 8
    return 28


def repair_row(items, alternate_by_column, alt_shift: int):
    if not items:
        return [], {"edits": 0, "raw": [], "alternate": []}
    raws = [text for _, text, _ in items]
    raw_sets = []
    alternates = []
    for column, text, _ in items:
        alternate = alternate_by_column.get(column + alt_shift, "")
        alternatives = [text]
        if alternate and alternate != text:
            alternatives.append(alternate)
        raw_sets.append(alternatives)
        alternates.append(alternate)

    primary_numeric = [
        int(text) if len(text) == 2 and text.isdigit() and int(text) <= 59 else None
        for text in raws
    ]
    if all(v is not None for v in primary_numeric) and all(a < b for a, b in zip(primary_numeric, primary_numeric[1:])):
        return primary_numeric, {"edits": 0, "raw": raws, "alternate": alternates}

    trustworthy = []
    for alternatives in raw_sets:
        values = [int(text) for text in alternatives if len(text) == 2 and text.isdigit() and int(text) <= 59]
        trustworthy.append(values[0] if values else None)
    diffs = [
        b - a for a, b in zip(trustworthy, trustworthy[1:])
        if a is not None and b is not None and 1 <= b - a <= 15
    ]
    target_gap = float(statistics.median(diffs)) if diffs else 4.0
    n = len(items)
    inf = 10**9
    dp = [[inf] * 60 for _ in range(n)]
    prev = [[-1] * 60 for _ in range(n)]

    def cell_cost(index: int, value: int) -> int:
        # Either grid origin can supply the same physical cell. A clean
        # two-digit reading from the alternate origin is therefore real
        # evidence, not merely a tie-breaker.
        return min(single_cost(raw, value) for raw in raw_sets[index])

    for value in range(60):
        dp[0][value] = cell_cost(0, value)
    for i in range(1, n):
        for value in range(60):
            own = cell_cost(i, value)
            for p in range(value):
                if dp[i - 1][p] >= inf:
                    continue
                gap = value - p
                gap_penalty = abs(gap - target_gap)
                if gap > 18:
                    gap_penalty += (gap - 18) * 2
                cost = dp[i - 1][p] + own + gap_penalty
                if cost < dp[i][value]:
                    dp[i][value] = cost
                    prev[i][value] = p
    end = min(range(60), key=lambda value: dp[-1][value])
    result = [end]
    for i in range(n - 1, 0, -1):
        end = prev[i][end]
        if end < 0:
            return [], {"edits": n, "raw": raws, "alternate": alternates, "failed": True}
        result.append(end)
    result.reverse()
    edits = sum(f"{value:02d}" not in alternatives for value, alternatives in zip(result, raw_sets))
    return result, {
        "edits": edits,
        "targetGap": target_gap,
        "raw": raws,
        "alternate": alternates,
    }


def evaluate_origin(rows, meta, alternate_rows, alternate_x):
    first_x = float(meta["firstX"])
    # Physical x = firstX + pitch * column. Convert a selected column to the
    # other origin's column number.
    alt_shift = round((first_x - alternate_x) / base.X_PITCH)
    parsed = {str(hour): [] for hour in range(4, 25)}
    repairs = {}
    repair_count = 0
    for hour in range(4, 25):
        alt_map = {column: text for column, text, _ in alternate_rows[hour]}
        values, diag = repair_row(rows[hour], alt_map, alt_shift)
        parsed[str(hour)] = values
        if diag.get("edits"):
            repairs[str(hour)] = diag
            repair_count += int(diag["edits"])
    diag = dict(meta)
    diag.update({
        "recognizedCount": sum(len(v) for v in parsed.values()),
        "repairCount": repair_count,
        "repairs": repairs,
    })
    return parsed, diag


def parse_rows(image: Image.Image):
    raw_trials = [collect_raw(image, first_x) for first_x in base.FIRST_X_CANDIDATES]
    evaluated = []
    for index, (rows, meta) in enumerate(raw_trials):
        other_rows, other_meta = raw_trials[1 - index]
        evaluated.append(evaluate_origin(rows, meta, other_rows, float(other_meta["firstX"])))
    max_cells = max(diag["candidateCount"] for _, diag in evaluated)
    # Dropping one genuine first-column departure in most hours is worse than
    # needing one extra digit repair.  A 0.20 penalty per missing cell catches
    # that shifted-grid failure without forcing noisy origins on other boards.
    parsed, diag = min(
        evaluated,
        key=lambda item: item[1]["repairCount"] + 0.20 * (max_cells - item[1]["candidateCount"]),
    )
    diag = dict(diag)
    diag["originTrials"] = [trial_diag for _, trial_diag in evaluated]
    return parsed, diag


def main() -> int:
    result = {"version": 13, "samples": {}}
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
