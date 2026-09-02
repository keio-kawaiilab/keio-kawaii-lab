#!/usr/bin/env python3
from __future__ import annotations

import io
import json
from pathlib import Path

import pytesseract
import requests
from PIL import Image, ImageEnhance, ImageOps

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


def digit_boxes(image: Image.Image) -> list[dict]:
    gray = ImageEnhance.Contrast(ImageOps.autocontrast(ImageOps.grayscale(image))).enhance(1.35)
    raw = pytesseract.image_to_boxes(
        gray,
        config="--psm 11 -c tessedit_char_whitelist=0123456789",
        lang="eng",
    )
    rows = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 5 or len(parts[0]) != 1 or not parts[0].isdigit():
            continue
        char, left, bottom, right, top = parts[:5]
        left, bottom, right, top = map(int, (left, bottom, right, top))
        rows.append({
            "char": char,
            "left": left,
            "right": right,
            "top": image.height - top,
            "bottom": image.height - bottom,
            "cx": (left + right) / 2,
            "cy": image.height - (bottom + top) / 2,
        })
    return rows


def parse_rows(image: Image.Image, boxes: list[dict]) -> dict[str, list[int]]:
    # Official artwork is a fixed square template. The hour rows (4..24) are
    # evenly spaced; using normalized geometry avoids depending on text/color OCR.
    first_center = image.height * 0.0308
    pitch = image.height * 0.04505
    row_half_height = pitch * 0.42
    result: dict[str, list[int]] = {}
    for offset, hour in enumerate(range(4, 25)):
        center_y = first_center + offset * pitch
        chars = [
            row for row in boxes
            if row["cx"] > image.width * 0.19
            and abs(row["cy"] - center_y) <= row_half_height
            and (row["bottom"] - row["top"]) >= image.height * 0.018
        ]
        chars.sort(key=lambda row: row["left"])
        groups: list[list[dict]] = []
        for char in chars:
            if not groups:
                groups.append([char])
                continue
            previous = groups[-1][-1]
            gap = char["left"] - previous["right"]
            # Digits inside one minute value nearly touch; departures are spaced.
            if gap <= image.width * 0.008:
                groups[-1].append(char)
            else:
                groups.append([char])
        minutes: list[int] = []
        for group in groups:
            text = "".join(row["char"] for row in group)
            if len(text) != 2:
                continue
            value = int(text)
            if 0 <= value <= 59 and (not minutes or value > minutes[-1]):
                minutes.append(value)
        result[str(hour)] = minutes
    return result


def validate_sample(name: str, parsed: dict[str, list[int]]) -> None:
    for hour, expected in EXPECTED.get(name, {}).items():
        actual = parsed.get(str(hour), [])
        if actual != expected:
            raise RuntimeError(f"{name} hour {hour}: expected {expected}, got {actual}")


def main() -> int:
    result = {"version": 3, "samples": {}}
    session = requests.Session()
    session.headers["User-Agent"] = "Keio-Kawaii-Lab timetable validation/1.0"
    for name, url in SAMPLES.items():
        response = session.get(url, timeout=60)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        boxes = digit_boxes(image)
        parsed = parse_rows(image, boxes)
        validate_sample(name, parsed)
        result["samples"][name] = {
            "url": url,
            "size": list(image.size),
            "digitBoxCount": len(boxes),
            "rows": parsed,
            "departureCount": sum(len(row) for row in parsed.values()),
        }
        print(name, "digits", len(boxes), "departures", result["samples"][name]["departureCount"], flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
