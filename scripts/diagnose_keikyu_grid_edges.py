#!/usr/bin/env python3
"""Diagnose time-cell evidence just outside detected Keikyu train grids."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from keikyu_official_pdf import TIME_RE, bbox_words, detect_train_column_grid, download_official_pdf

PAGES = (44, 59, 74, 81, 125, 136, 139, 141)


def support(words, x, pitch):
    hits = [w for w in words if TIME_RE.fullmatch(w.text) and abs(w.x - x) <= pitch * 0.34]
    return {"count": len(hits), "sample": [w.text for w in sorted(hits, key=lambda w: w.y)[:8]]}


def main():
    with tempfile.TemporaryDirectory(prefix="keikyu-edge-diag-") as td:
        pdf = Path(td) / "schedule_all.pdf"
        download_official_pdf(pdf)
        out = []
        for page in PAGES:
            _w, _h, words = bbox_words(pdf, page)
            grid = detect_train_column_grid(words)
            if not grid:
                continue
            left = []
            right = []
            for n in range(1, 7):
                lx = grid.centers[0] - n * grid.pitch
                rx = grid.centers[-1] + n * grid.pitch
                left.append({"n": n, "x": round(lx, 2), **support(words, lx, grid.pitch)})
                right.append({"n": n, "x": round(rx, 2), **support(words, rx, grid.pitch)})
            out.append({
                "page": page,
                "first": round(grid.centers[0], 2),
                "last": round(grid.centers[-1], 2),
                "pitch": round(grid.pitch, 3),
                "left": left,
                "right": right,
            })
        print("KEIKYU_GRID_EDGE_DIAGNOSTIC=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
