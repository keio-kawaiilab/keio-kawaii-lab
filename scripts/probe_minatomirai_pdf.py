#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import fitz
import requests

OUT = Path("data/transit/yokohama-minatomirai/pdf-probe.json")
URL = "https://www.mm21railway.co.jp/station/timestable/yokohama/pdf/yokohama_timeschedule.pdf"


def color_hex(value: int) -> str:
    return f"#{value & 0xffffff:06x}"


def main() -> int:
    response = requests.get(URL, timeout=60, headers={"User-Agent": "Keio-Kawaii-Lab timetable validation/1.0"})
    response.raise_for_status()
    doc = fitz.open(stream=response.content, filetype="pdf")
    result = {"version": 1, "url": URL, "pages": []}
    for page_number, page in enumerate(doc):
        words = [
            {
                "text": word[4],
                "x0": round(word[0], 2),
                "y0": round(word[1], 2),
                "x1": round(word[2], 2),
                "y1": round(word[3], 2),
                "block": word[5],
                "line": word[6],
                "word": word[7],
            }
            for word in page.get_text("words", sort=False)
        ]
        spans = []
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text") or "").strip()
                    if not text:
                        continue
                    spans.append({
                        "text": text,
                        "bbox": [round(v, 2) for v in span.get("bbox", [])],
                        "size": round(float(span.get("size") or 0), 2),
                        "color": color_hex(int(span.get("color") or 0)),
                        "font": span.get("font"),
                    })
        drawings = page.get_drawings()
        result["pages"].append({
            "number": page_number,
            "rect": [round(v, 2) for v in page.rect],
            "wordCount": len(words),
            "spanCount": len(spans),
            "drawingCount": len(drawings),
            "words": words,
            "spans": spans,
        })
        print("page", page_number, "words", len(words), "spans", len(spans), "drawings", len(drawings), flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if not result["pages"] or result["pages"][0]["wordCount"] < 100:
        raise RuntimeError("official PDF did not expose enough vector text")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
