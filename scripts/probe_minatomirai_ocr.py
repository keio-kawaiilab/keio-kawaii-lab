#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import math
from pathlib import Path

import pytesseract
import requests
from PIL import Image, ImageEnhance, ImageOps

OUT = Path("data/transit/yokohama-minatomirai/ocr-probe.json")
SAMPLES = {
    "yokohama_weekday_down": "https://www.mm21railway.co.jp/station/timestable/yokohama/yokohama_wm.jpg",
    "minatomirai_weekday_up": "https://www.mm21railway.co.jp/station/timestable/minatomirai/minatomirai_wy.jpg",
    "minatomirai_holiday_down": "https://www.mm21railway.co.jp/station/timestable/minatomirai/minatomirai_hm.jpg",
    "bashamichi_weekday_down": "https://www.mm21railway.co.jp/station/timestable/bashamichi/bashamichi_wm.jpg",
    "nihonodori_weekday_down": "https://www.mm21railway.co.jp/station/timestable/nihonodori/nihonodori_wm.jpg",
}
EXPECTED = {
    "yokohama_weekday_down": {
        5: [10, 19, 30, 41, 44, 55],
        6: [3, 10, 17, 22, 26, 29, 32, 35, 38, 42, 44, 48, 51, 55, 59],
        7: [1, 4, 6, 10, 13, 16, 19, 22, 24, 28, 31, 34, 36, 40, 43, 46, 48, 50, 55, 57],
    },
    "minatomirai_holiday_down": {
        5: [13, 22, 33, 45, 49, 59],
        6: [5, 7, 15, 24, 33, 39, 43, 49, 56, 58],
    },
    "bashamichi_weekday_down": {
        5: [15, 24, 35, 47, 49],
        6: [0, 8, 15, 22, 26, 31, 33, 37, 40, 44, 47, 49, 53, 56],
        7: [0, 3, 6, 9, 11, 15, 18, 22, 24, 26, 30, 33, 36, 39, 41, 45, 48, 51, 54, 56],
    },
    "nihonodori_weekday_down": {
        5: [16, 25, 36, 48, 50],
        6: [2, 9, 17, 24, 28, 33, 35, 38, 41, 45, 48, 50, 55, 57],
    },
}
BASE_SIZE = 1654.0
X_PITCH = 68.0
FIRST_Y = 47.0
Y_PITCH = 74.5
MAX_COLUMNS = 21
TILE_W = 168
TILE_H = 150
SHEET_COLUMNS = 7


def detect_first_x(image: Image.Image) -> float:
    """Find the minute-grid origin from the coloured 4-hour box.

    Official artwork has two horizontal layouts (for example Yokohama starts
    farther left than Minatomirai), but the first minute cell consistently
    begins about 40 source pixels to the right of the hour box.
    """
    rgb = image.convert("RGB")
    sx, sy = image.width / BASE_SIZE, image.height / BASE_SIZE
    cy = FIRST_Y * sy
    top = max(0, int(cy - 28 * sy))
    bottom = min(image.height, int(cy + 28 * sy))
    maximum_x = min(image.width, int(450 * sx))
    qualifying: list[int] = []
    for x in range(maximum_x):
        hits = 0
        for y in range(top, bottom):
            r, g, b = rgb.getpixel((x, y))
            spread = max(r, g, b) - min(r, g, b)
            if spread > 45 and b > r + 20 and b >= g - 35:
                hits += 1
        if hits >= max(4, int((bottom - top) * 0.45)):
            qualifying.append(x)
    if not qualifying:
        raise RuntimeError("could not find hour-box colour band")
    runs: list[tuple[int, int]] = []
    start = previous = qualifying[0]
    for x in qualifying[1:]:
        if x > previous + 1:
            runs.append((start, previous))
            start = x
        previous = x
    runs.append((start, previous))
    start, right = max(runs, key=lambda run: run[1] - run[0])
    width_base = (right - start + 1) / sx
    if not 45 <= width_base <= 100:
        raise RuntimeError(f"unexpected hour-box width {width_base:.1f}")
    return right / sx + 40.0


def minute_crop(image: Image.Image, first_x: float, hour: int, column: int) -> Image.Image:
    sx, sy = image.width / BASE_SIZE, image.height / BASE_SIZE
    cx = (first_x + X_PITCH * column) * sx
    cy = (FIRST_Y + Y_PITCH * (hour - 4)) * sy
    left, right = int(cx - 25 * sx), int(cx + 25 * sx)
    top, bottom = int(cy - 21 * sy), int(cy + 23 * sy)
    return image.crop((max(0, left), max(0, top), min(image.width, right), min(image.height, bottom)))


def ink_count(crop: Image.Image) -> int:
    count = 0
    for r, g, b in crop.convert("RGB").getdata():
        spread = max(r, g, b) - min(r, g, b)
        mean = (r + g + b) / 3
        if mean < 165 or (spread > 40 and mean < 238):
            count += 1
    return count


def candidate_cells(image: Image.Image, first_x: float) -> list[dict]:
    rows = []
    for hour in range(4, 25):
        for column in range(MAX_COLUMNS):
            crop = minute_crop(image, first_x, hour, column)
            ink = ink_count(crop)
            if ink < max(18, int(crop.width * crop.height * 0.010)):
                continue
            rows.append({"hour": hour, "column": column, "ink": ink, "crop": crop})
    return rows


def contact_sheet(cells: list[dict], *, threshold: bool = False) -> tuple[Image.Image, dict[tuple[int, int], int]]:
    rows = max(1, math.ceil(len(cells) / SHEET_COLUMNS))
    sheet = Image.new("L", (TILE_W * SHEET_COLUMNS, TILE_H * rows), 255)
    locator: dict[tuple[int, int], int] = {}
    for index, cell in enumerate(cells):
        crop = ImageOps.grayscale(cell["crop"])
        crop = ImageOps.autocontrast(crop)
        crop = ImageEnhance.Contrast(crop).enhance(1.55)
        crop = crop.resize((crop.width * 3, crop.height * 3), Image.Resampling.LANCZOS)
        if threshold:
            crop = crop.point(lambda value: 0 if value < 205 else 255)
        row, column = divmod(index, SHEET_COLUMNS)
        x = column * TILE_W + (TILE_W - crop.width) // 2
        y = row * TILE_H + (TILE_H - crop.height) // 2
        sheet.paste(crop, (x, y))
        locator[(row, column)] = index
    return sheet, locator


def read_sheet(sheet: Image.Image, locator: dict[tuple[int, int], int]) -> dict[int, str]:
    raw = pytesseract.image_to_boxes(
        sheet,
        config="--psm 6 -c tessedit_char_whitelist=0123456789",
        lang="eng",
    )
    grouped: dict[int, list[tuple[float, str]]] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        char = parts[0]
        if len(char) != 1 or not char.isdigit():
            continue
        left, bottom, right, top = map(int, parts[1:5])
        cx = (left + right) / 2
        cy_from_top = sheet.height - (bottom + top) / 2
        tile_row = int(cy_from_top // TILE_H)
        tile_column = int(cx // TILE_W)
        index = locator.get((tile_row, tile_column))
        if index is None:
            continue
        grouped.setdefault(index, []).append((cx, char))
    result = {}
    for index, chars in grouped.items():
        chars.sort(key=lambda row: row[0])
        result[index] = "".join(char for _, char in chars)
    return result


def parse_rows(image: Image.Image) -> tuple[dict[str, list[int]], dict]:
    first_x = detect_first_x(image)
    cells = candidate_cells(image, first_x)
    sheet, locator = contact_sheet(cells, threshold=False)
    first = read_sheet(sheet, locator)
    unresolved = [index for index in range(len(cells)) if len(first.get(index, "")) != 2]
    second: dict[int, str] = {}
    if unresolved:
        retry_cells = [cells[index] for index in unresolved]
        retry_sheet, retry_locator = contact_sheet(retry_cells, threshold=True)
        retry_values = read_sheet(retry_sheet, retry_locator)
        second = {unresolved[index]: value for index, value in retry_values.items()}
    values = dict(first)
    for index, value in second.items():
        if len(values.get(index, "")) != 2 and len(value) == 2:
            values[index] = value

    parsed: dict[str, list[int]] = {str(hour): [] for hour in range(4, 25)}
    unresolved_rows = []
    for index, cell in enumerate(cells):
        text = values.get(index, "")
        if len(text) != 2 or not text.isdigit() or int(text) > 59:
            unresolved_rows.append({"hour": cell["hour"], "column": cell["column"], "text": text, "ink": cell["ink"]})
            continue
        minute = int(text)
        row = parsed[str(cell["hour"])]
        if row and minute <= row[-1]:
            unresolved_rows.append({"hour": cell["hour"], "column": cell["column"], "text": text, "ink": cell["ink"], "reason": "non-monotonic"})
            continue
        row.append(minute)
    diagnostics = {
        "firstX": round(first_x, 2),
        "candidateCount": len(cells),
        "recognizedCount": sum(len(v) for v in parsed.values()),
        "unresolvedCount": len(unresolved_rows),
        "unresolved": unresolved_rows[:80],
    }
    return parsed, diagnostics


def validate_sample(name: str, parsed: dict[str, list[int]]) -> None:
    for hour, expected in EXPECTED.get(name, {}).items():
        actual = parsed.get(str(hour), [])
        if actual != expected:
            raise RuntimeError(f"{name} hour {hour}: expected {expected}, got {actual}")


def main() -> int:
    result = {"version": 8, "samples": {}}
    session = requests.Session()
    session.headers["User-Agent"] = "Keio-Kawaii-Lab timetable validation/1.0"
    failures = []
    for name, url in SAMPLES.items():
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
            validate_sample(name, parsed)
        except RuntimeError as exc:
            failures.append(str(exc))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if failures:
        raise RuntimeError("; ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
