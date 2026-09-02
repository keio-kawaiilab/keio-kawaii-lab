#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import math
import re
from pathlib import Path

import pytesseract
import requests
from PIL import Image, ImageEnhance, ImageOps
from pytesseract import Output

OUT = Path("data/transit/yokohama-minatomirai/ocr-probe.json")
SAMPLES = {
    "yokohama_weekday_down": "https://www.mm21railway.co.jp/station/timestable/yokohama/yokohama_wm.jpg",
    "minatomirai_weekday_up": "https://www.mm21railway.co.jp/station/timestable/minatomirai/minatomirai_wy.jpg",
    "minatomirai_holiday_down": "https://www.mm21railway.co.jp/station/timestable/minatomirai/minatomirai_hm.jpg",
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
}
BASE_SIZE = 1654.0
FIRST_X = 226.0
X_PITCH = 68.0
FIRST_Y = 47.0
Y_PITCH = 74.5
MAX_COLUMNS = 21


def minute_crop(image: Image.Image, hour: int, column: int) -> Image.Image:
    sx, sy = image.width / BASE_SIZE, image.height / BASE_SIZE
    cx = (FIRST_X + X_PITCH * column) * sx
    cy = (FIRST_Y + Y_PITCH * (hour - 4)) * sy
    # Destination abbreviations on upbound artwork sit above this narrow band.
    left, right = int(cx - 25 * sx), int(cx + 25 * sx)
    top, bottom = int(cy - 21 * sy), int(cy + 23 * sy)
    return image.crop((max(0, left), max(0, top), min(image.width, right), min(image.height, bottom)))


def ink_count(crop: Image.Image) -> int:
    count = 0
    for r, g, b in crop.convert("RGB").getdata():
        spread = max(r, g, b) - min(r, g, b)
        mean = (r + g + b) / 3
        if mean < 155 or (spread > 45 and mean < 235):
            count += 1
    return count


def candidate_cells(image: Image.Image) -> list[dict]:
    rows = []
    for hour in range(4, 25):
        for column in range(MAX_COLUMNS):
            crop = minute_crop(image, hour, column)
            ink = ink_count(crop)
            if ink < max(25, int(crop.width * crop.height * 0.018)):
                continue
            rows.append({"hour": hour, "column": column, "ink": ink, "crop": crop})
    return rows


def contact_sheet(cells: list[dict], *, threshold: bool = False) -> tuple[Image.Image, dict[tuple[int, int], int]]:
    tile_w, tile_h, columns = 156, 144, 8
    rows = max(1, math.ceil(len(cells) / columns))
    sheet = Image.new("L", (tile_w * columns, tile_h * rows), 255)
    locator: dict[tuple[int, int], int] = {}
    for index, cell in enumerate(cells):
        crop = ImageOps.grayscale(cell["crop"])
        crop = ImageOps.autocontrast(crop)
        crop = ImageEnhance.Contrast(crop).enhance(1.55)
        crop = crop.resize((crop.width * 3, crop.height * 3), Image.Resampling.LANCZOS)
        if threshold:
            crop = crop.point(lambda value: 0 if value < 190 else 255)
        row, column = divmod(index, columns)
        x = column * tile_w + (tile_w - crop.width) // 2
        y = row * tile_h + (tile_h - crop.height) // 2
        sheet.paste(crop, (x, y))
        locator[(row, column)] = index
    return sheet, locator


def read_sheet(sheet: Image.Image, locator: dict[tuple[int, int], int]) -> dict[int, str]:
    data = pytesseract.image_to_data(
        sheet,
        output_type=Output.DICT,
        config="--psm 11 -c tessedit_char_whitelist=0123456789",
        lang="eng",
    )
    result: dict[int, tuple[str, float]] = {}
    tile_w, tile_h = 156, 144
    for i, raw in enumerate(data["text"]):
        digits = re.sub(r"\D", "", str(raw or ""))
        if not digits:
            continue
        cx = int(data["left"][i]) + int(data["width"][i]) / 2
        cy = int(data["top"][i]) + int(data["height"][i]) / 2
        key = (int(cy // tile_h), int(cx // tile_w))
        index = locator.get(key)
        if index is None:
            continue
        conf = float(data["conf"][i]) if str(data["conf"][i]).strip() not in {"", "-1"} else -1
        old = result.get(index)
        if old is None or conf > old[1]:
            result[index] = (digits, conf)
    return {index: value[0] for index, value in result.items()}


def parse_rows(image: Image.Image) -> tuple[dict[str, list[int]], dict]:
    cells = candidate_cells(image)
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
    diagnostics = {"candidateCount": len(cells), "recognizedCount": sum(len(v) for v in parsed.values()), "unresolved": unresolved_rows}
    return parsed, diagnostics


def validate_sample(name: str, parsed: dict[str, list[int]]) -> None:
    for hour, expected in EXPECTED.get(name, {}).items():
        actual = parsed.get(str(hour), [])
        if actual != expected:
            raise RuntimeError(f"{name} hour {hour}: expected {expected}, got {actual}")


def main() -> int:
    result = {"version": 5, "samples": {}}
    session = requests.Session()
    session.headers["User-Agent"] = "Keio-Kawaii-Lab timetable validation/1.0"
    for name, url in SAMPLES.items():
        response = session.get(url, timeout=60)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        parsed, diagnostics = parse_rows(image)
        validate_sample(name, parsed)
        result["samples"][name] = {
            "url": url,
            "size": list(image.size),
            "rows": parsed,
            "departureCount": sum(len(row) for row in parsed.values()),
            "diagnostics": diagnostics,
        }
        print(name, "departures", result["samples"][name]["departureCount"], diagnostics, flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
