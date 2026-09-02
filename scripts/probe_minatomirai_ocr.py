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
FIRST_X_CANDIDATES = (226.0, 294.0)
X_PITCH = 68.0
FIRST_Y = 47.0
Y_PITCH = 74.5
MAX_COLUMNS = 21
TILE_W = 168
TILE_H = 150
SHEET_COLUMNS = 7


def minute_crop(image: Image.Image, first_x: float, hour: int, column: int) -> Image.Image:
    sx, sy = image.width / BASE_SIZE, image.height / BASE_SIZE
    cx = (first_x + X_PITCH * column) * sx
    cy = (FIRST_Y + Y_PITCH * (hour - 4)) * sy
    left, right = int(cx - 25 * sx), int(cx + 25 * sx)
    top, bottom = int(cy - 21 * sy), int(cy + 23 * sy)
    return image.crop((max(0, left), max(0, top), min(image.width, right), min(image.height, bottom)))


def ink_pixels(crop: Image.Image) -> list[tuple[int, int]]:
    pixels: list[tuple[int, int]] = []
    rgb = crop.convert("RGB")
    for y in range(rgb.height):
        for x in range(rgb.width):
            r, g, b = rgb.getpixel((x, y))
            spread = max(r, g, b) - min(r, g, b)
            mean = (r + g + b) / 3
            if mean < 165 or (spread > 40 and mean < 238):
                pixels.append((x, y))
    return pixels


def is_pass_dash(crop: Image.Image, pixels: list[tuple[int, int]]) -> bool:
    """Recognise the orange em dash used for a train that passes this station."""
    if not pixels:
        return False
    xs = [point[0] for point in pixels]
    ys = [point[1] for point in pixels]
    width = max(xs) - min(xs) + 1
    height = max(ys) - min(ys) + 1
    # Digits are roughly 30-40 px tall in the source artwork.  A pass marker
    # is a wide horizontal stroke only a few pixels tall.
    return width >= max(8, int(crop.width * 0.20)) and height <= max(8, int(crop.height * 0.24))


def candidate_cells(image: Image.Image, first_x: float) -> tuple[list[dict], int]:
    rows = []
    dash_count = 0
    for hour in range(4, 25):
        for column in range(MAX_COLUMNS):
            crop = minute_crop(image, first_x, hour, column)
            pixels = ink_pixels(crop)
            ink = len(pixels)
            if ink < max(18, int(crop.width * crop.height * 0.010)):
                continue
            if is_pass_dash(crop, pixels):
                dash_count += 1
                continue
            rows.append({"hour": hour, "column": column, "ink": ink, "crop": crop})
    return rows, dash_count


def prepare_ocr_crop(source: Image.Image, *, threshold: bool) -> Image.Image:
    # Trim the thin rectangle around commuter/limited-express numbers.  The
    # border was being mistaken for 9/0 while the actual two digits sit safely
    # inside this inset.
    inset_x = max(2, int(source.width * 0.10))
    inset_y = max(1, int(source.height * 0.06))
    if source.width > inset_x * 2 + 4 and source.height > inset_y * 2 + 4:
        source = source.crop((inset_x, inset_y, source.width - inset_x, source.height - inset_y))
    crop = ImageOps.grayscale(source)
    crop = ImageOps.autocontrast(crop)
    crop = ImageEnhance.Contrast(crop).enhance(1.55)
    crop = crop.resize((crop.width * 3, crop.height * 3), Image.Resampling.LANCZOS)
    if threshold:
        crop = crop.point(lambda value: 0 if value < 205 else 255)
    return crop


def contact_sheet(cells: list[dict], *, threshold: bool = False) -> tuple[Image.Image, dict[tuple[int, int], int]]:
    rows = max(1, math.ceil(len(cells) / SHEET_COLUMNS))
    sheet = Image.new("L", (TILE_W * SHEET_COLUMNS, TILE_H * rows), 255)
    locator: dict[tuple[int, int], int] = {}
    for index, cell in enumerate(cells):
        crop = prepare_ocr_crop(cell["crop"], threshold=threshold)
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


def parse_rows_at_origin(image: Image.Image, first_x: float) -> tuple[dict[str, list[int]], dict]:
    cells, dash_count = candidate_cells(image, first_x)
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
        "firstX": first_x,
        "candidateCount": len(cells),
        "dashCount": dash_count,
        "recognizedCount": sum(len(v) for v in parsed.values()),
        "unresolvedCount": len(unresolved_rows),
        "unresolved": unresolved_rows[:80],
    }
    return parsed, diagnostics


def parse_rows(image: Image.Image) -> tuple[dict[str, list[int]], dict]:
    trials = []
    for first_x in FIRST_X_CANDIDATES:
        parsed, diagnostics = parse_rows_at_origin(image, first_x)
        trials.append((parsed, diagnostics))
    parsed, diagnostics = max(
        trials,
        key=lambda item: (
            item[1]["recognizedCount"],
            -item[1]["unresolvedCount"],
        ),
    )
    diagnostics = dict(diagnostics)
    diagnostics["originTrials"] = [
        {
            "firstX": trial_diag["firstX"],
            "candidateCount": trial_diag["candidateCount"],
            "dashCount": trial_diag["dashCount"],
            "recognizedCount": trial_diag["recognizedCount"],
            "unresolvedCount": trial_diag["unresolvedCount"],
        }
        for _, trial_diag in trials
    ]
    return parsed, diagnostics


def validate_sample(name: str, parsed: dict[str, list[int]]) -> None:
    for hour, expected in EXPECTED.get(name, {}).items():
        actual = parsed.get(str(hour), [])
        if actual != expected:
            raise RuntimeError(f"{name} hour {hour}: expected {expected}, got {actual}")


def main() -> int:
    result = {"version": 11, "samples": {}}
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
