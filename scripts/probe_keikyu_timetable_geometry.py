#!/usr/bin/env python3
"""Inspect XY geometry of one official Keikyu timetable page.

The PDF is downloaded only into a temporary directory.  The output is a tiny
coordinate diagnostic used to design an exact train-column parser; no raw PDF
or full extracted page is retained.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

URL = "https://www.keikyu.co.jp/ride/kakueki/pdf/schedule_all.pdf"
PAGE = 7  # 1-based: first actual weekday grid
TOKEN_RE = re.compile(r"^\d{3,4}[A-Z]{0,2}[a-z]?$|^\d{3,4}$")


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="keikyu-geometry-") as temp_dir:
        pdf_path = Path(temp_dir) / "schedule_all.pdf"
        request = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 transit-timetable-audit/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            pdf_path.write_bytes(response.read())

        bbox = subprocess.check_output(
            ["pdftotext", "-f", str(PAGE), "-l", str(PAGE), "-bbox-layout", str(pdf_path), "-"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        root = ET.fromstring(bbox)
        page = next((node for node in root.iter() if node.tag.endswith("page")), None)
        if page is None:
            raise RuntimeError("bbox output did not contain a page")

        words: list[dict[str, object]] = []
        for node in page.iter():
            if not node.tag.endswith("word"):
                continue
            text = compact("".join(node.itertext()))
            if not text:
                continue
            words.append(
                {
                    "text": text,
                    "xMin": float(node.attrib["xMin"]),
                    "yMin": float(node.attrib["yMin"]),
                    "xMax": float(node.attrib["xMax"]),
                    "yMax": float(node.attrib["yMax"]),
                }
            )

        numeric = [word for word in words if TOKEN_RE.fullmatch(str(word["text"]))]
        top_numeric = [word for word in numeric if float(word["yMin"]) < 260]
        clusters: dict[int, list[dict[str, object]]] = defaultdict(list)
        for word in top_numeric:
            y = int(round((float(word["yMin"]) + float(word["yMax"])) / 4) * 2)
            clusters[y].append(word)

        cluster_rows = []
        for y, row in sorted(clusters.items(), key=lambda item: item[0]):
            row_sorted = sorted(row, key=lambda item: float(item["xMin"]))
            cluster_rows.append(
                {
                    "yApprox": y,
                    "count": len(row_sorted),
                    "tokens": [
                        {
                            "text": item["text"],
                            "x": round((float(item["xMin"]) + float(item["xMax"])) / 2, 2),
                        }
                        for item in row_sorted
                    ],
                }
            )

        report = {
            "page": PAGE,
            "pageWidth": float(page.attrib.get("width", 0)),
            "pageHeight": float(page.attrib.get("height", 0)),
            "wordCount": len(words),
            "numericWordCount": len(numeric),
            "topNumericRows": cluster_rows[:40],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
