#!/usr/bin/env python3
from __future__ import annotations

import io
import json
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


def numeric_tokens(image: Image.Image) -> list[dict]:
    # The source artwork is already high resolution. Grayscale + autocontrast makes
    # the small timetable digits easier for Tesseract while keeping their geometry.
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray)
    gray = ImageEnhance.Contrast(gray).enhance(1.4)
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


def main() -> int:
    result = {"version": 1, "samples": {}}
    session = requests.Session()
    session.headers["User-Agent"] = "Keio-Kawaii-Lab timetable validation/1.0"
    for name, url in SAMPLES.items():
        response = session.get(url, timeout=60)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        tokens = numeric_tokens(image)
        result["samples"][name] = {
            "url": url,
            "size": list(image.size),
            "tokenCount": len(tokens),
            "tokens": tokens,
        }
        print(name, image.size, "numeric tokens", len(tokens), flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
