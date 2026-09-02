#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import numpy as np
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


def numeric_tokens(image: Image.Image) -> list[dict]:
    gray = ImageEnhance.Contrast(ImageOps.autocontrast(ImageOps.grayscale(image))).enhance(1.4)
    data = pytesseract.image_to_data(
        gray,
        output_type=Output.DICT,
        config="--psm 11 -c tessedit_char_whitelist=0123456789",
        lang="eng",
    )
    rows = []
    for i, raw in enumerate(data["text"]):
        text = str(raw or "").strip()
        if not text.isdigit():
            continue
        conf = float(data["conf"][i]) if str(data["conf"][i]).strip() not in {"", "-1"} else -1
        rows.append({
            "text": text,
            "conf": round(conf, 1),
            "left": int(data["left"][i]),
            "top": int(data["top"][i]),
            "width": int(data["width"][i]),
            "height": int(data["height"][i]),
        })
    return rows


def hour_bands(image: Image.Image) -> list[tuple[int, int]]:
    rgb = np.asarray(image)
    # Both timetable palettes use a blue/cyan hour block on the far left.
    region = rgb[:, 70:210, :]
    r, g, b = region[..., 0], region[..., 1], region[..., 2]
    mask = (r < 100) & (b > 100) & ((b - r) > 35)
    counts = mask.sum(axis=1)
    active = counts > 1200
    runs: list[tuple[int, int]] = []
    start = None
    for y, value in enumerate(active.tolist() + [False]):
        if value and start is None:
            start = y
        elif not value and start is not None:
            if y - start >= 25:
                runs.append((start, y - 1))
            start = None
    # The official artwork has one band for each hour from 4 through 24.
    if len(runs) != 21:
        raise RuntimeError(f"expected 21 hour bands, found {len(runs)}: {runs}")
    return runs


def ocr_cell(cell: Image.Image) -> tuple[str | None, float]:
    gray = ImageOps.autocontrast(ImageOps.grayscale(cell))
    # Upscaling each minute cell avoids Tesseract merging adjacent departures.
    gray = gray.resize((gray.width * 3, gray.height * 3), Image.Resampling.LANCZOS)
    gray = ImageEnhance.Contrast(gray).enhance(1.7)
    data = pytesseract.image_to_data(
        gray,
        output_type=Output.DICT,
        config="--psm 10 -c tessedit_char_whitelist=0123456789",
        lang="eng",
    )
    candidates = []
    for text, conf in zip(data["text"], data["conf"]):
        digits = re.sub(r"\D", "", str(text or ""))
        if not digits:
            continue
        score = float(conf) if str(conf).strip() not in {"", "-1"} else -1
        candidates.append((digits, score))
    if not candidates:
        return None, -1
    digits, score = max(candidates, key=lambda row: row[1])
    if len(digits) == 1:
        digits = "0" + digits
    if len(digits) != 2:
        return None, score
    value = int(digits)
    return (digits if 0 <= value <= 59 else None), score


def parse_grid(image: Image.Image) -> dict:
    bands = hour_bands(image)
    # Geometry is fixed by the official 1654x1654 artwork.  Minutes sit on a
    # 68px pitch beginning around x=210.  A narrow crop leaves the destination
    # glyph above an upbound departure out of the recognizer's neighbours.
    centers = [210 + 68 * index for index in range(21)]
    parsed = {}
    for offset, (top, bottom) in enumerate(bands):
        hour = 4 + offset
        row = []
        for center in centers:
            left, right = max(0, center - 27), min(image.width, center + 28)
            # Keep the full hour band. Japanese destination glyphs are ignored by
            # the numeric whitelist, while minute digits remain large enough.
            cell = image.crop((left, top, right, bottom + 1))
            text, conf = ocr_cell(cell)
            if text is not None:
                row.append({"minute": int(text), "x": center, "conf": round(conf, 1)})
        # Deduplicate a rare OCR spill into the neighbouring cell.
        clean = []
        for item in row:
            if clean and item["minute"] == clean[-1]["minute"] and item["x"] - clean[-1]["x"] <= 68:
                if item["conf"] > clean[-1]["conf"]:
                    clean[-1] = item
            else:
                clean.append(item)
        parsed[str(hour)] = clean
    return {"bands": bands, "rows": parsed}


def main() -> int:
    result = {"version": 2, "samples": {}}
    session = requests.Session()
    session.headers["User-Agent"] = "Keio-Kawaii-Lab timetable validation/1.0"
    for name, url in SAMPLES.items():
        response = session.get(url, timeout=60)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        tokens = numeric_tokens(image)
        grid = parse_grid(image)
        result["samples"][name] = {
            "url": url,
            "size": list(image.size),
            "tokenCount": len(tokens),
            "grid": grid,
        }
        print(name, image.size, "rows", {h: len(v) for h, v in grid["rows"].items()}, flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
