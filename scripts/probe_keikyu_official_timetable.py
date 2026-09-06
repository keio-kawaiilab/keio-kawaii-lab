#!/usr/bin/env python3
"""Probe the current official Keikyu full-line timetable PDF.

This does not publish or retain the PDF. It downloads the official source into
a temporary directory during CI, validates it, and prints a small layout sample
needed to build an exact column parser. Raw PDF bytes are never committed.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

URL = "https://www.keikyu.co.jp/ride/kakueki/pdf/schedule_all.pdf"
EXPECTED_MIN_PAGES = 140
SAMPLE_PAGE = 7  # 1-based PDF page: first actual weekday timetable grid


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True, encoding="utf-8", errors="replace")


def main() -> int:
    for binary in ("pdfinfo", "pdftotext"):
        if shutil.which(binary) is None:
            raise RuntimeError(f"required executable missing: {binary}")

    with tempfile.TemporaryDirectory(prefix="keikyu-timetable-") as temp_dir:
        pdf_path = Path(temp_dir) / "schedule_all.pdf"
        request = urllib.request.Request(
            URL,
            headers={"User-Agent": "Mozilla/5.0 transit-timetable-audit/1.0"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        if not data.startswith(b"%PDF"):
            raise RuntimeError("official timetable response is not a PDF")
        if len(data) < 1_000_000:
            raise RuntimeError(f"official timetable PDF unexpectedly small: {len(data)} bytes")
        pdf_path.write_bytes(data)

        info = run("pdfinfo", str(pdf_path))
        match = re.search(r"^Pages:\s+(\d+)\s*$", info, re.MULTILINE)
        if not match:
            raise RuntimeError("could not read PDF page count")
        page_count = int(match.group(1))
        if page_count < EXPECTED_MIN_PAGES:
            raise RuntimeError(f"official timetable page count unexpectedly low: {page_count}")

        text = run(
            "pdftotext",
            "-f",
            str(SAMPLE_PAGE),
            "-l",
            str(SAMPLE_PAGE),
            "-layout",
            str(pdf_path),
            "-",
        )
        lines = [line.rstrip() for line in text.splitlines()]
        nonempty = [line for line in lines if line.strip()]
        if not any("列車番号" in line for line in nonempty):
            raise RuntimeError("sample timetable page did not contain 列車番号")
        if not any("泉岳寺" in line for line in nonempty):
            raise RuntimeError("sample timetable page did not contain 泉岳寺")

        # Print only a compact diagnostic; this is layout research, not a raw-PDF mirror.
        sample = nonempty[:80]
        train_number_tokens = sorted(
            set(re.findall(r"(?<!\d)\d{3,4}[A-Z][a-z]?(?![A-Za-z0-9])", text))
        )
        report = {
            "source": URL,
            "pdfBytes": len(data),
            "pageCount": page_count,
            "samplePage": SAMPLE_PAGE,
            "sampleNonEmptyLineCount": len(nonempty),
            "sampleTrainNumberTokens": train_number_tokens[:40],
            "sampleTrainNumberTokenCount": len(train_number_tokens),
            "layoutSample": sample,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
