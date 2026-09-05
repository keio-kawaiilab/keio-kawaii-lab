#!/usr/bin/env python3
"""Inspect the current official Seibu 2026 digital timetable without inferring train identity.

This intentionally downloads only a handful of HTML/JS resources.  Its purpose is
source discovery: find the official e-book assets that can later be parsed as exact
published train columns.  Close times, train numbers alone, and destinations alone
must never establish physical-train identity.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

BASE = "https://www.seiburailway.jp/railways/2026digitaltimetable/"
TARGETS = [
    "index.html",
    "pageindices/index.html",
    "pageindices/index1.html",
    "pageindices/index120.html",
    "pageindices/index240.html",
]
OUT = Path("data/transit/fukutoshin/seibu-2026-source-report.json")
ATTR_RE = re.compile(r"(?:href|src)\s*=\s*[\"']([^\"']+)[\"']", re.I)
URL_RE = re.compile(r"url\(\s*[\"']?([^\"')]+)", re.I)
ASSET_RE = re.compile(r"[^\"'\s<>]+\.(?:js|json|txt|xml|css|svg|png|jpe?g|gif|webp|html?)(?:\?[^\"'\s<>]*)?", re.I)
TRAIN_TOKEN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]?\d{3,5}[A-Z](?![A-Z0-9])")


def curl(url: str) -> bytes:
    proc = subprocess.run(
        [
            "curl", "-fLsS", "--retry", "3", "--retry-delay", "1",
            "--connect-timeout", "15", "--max-time", "45",
            "-A", "Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/1.0)",
            "-H", "Accept: text/html,application/xhtml+xml,application/javascript,text/javascript,*/*;q=0.8",
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"curl failed ({proc.returncode}) for {url}: {proc.stderr.decode('utf-8','replace')[-500:]}")
    return proc.stdout


def text_of(raw: bytes) -> str:
    for enc in ("utf-8", "shift_jis", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def extract_assets(text: str, base_url: str) -> list[str]:
    refs = []
    refs.extend(ATTR_RE.findall(text))
    refs.extend(URL_RE.findall(text))
    refs.extend(ASSET_RE.findall(text))
    out = []
    seen = set()
    for ref in refs:
        ref = ref.strip()
        if not ref or ref.startswith(("data:", "javascript:", "mailto:", "#")):
            continue
        url = urljoin(base_url, ref)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            continue
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def summarize(url: str, raw: bytes) -> dict:
    text = text_of(raw)
    assets = extract_assets(text, url)
    train_tokens = sorted(set(TRAIN_TOKEN_RE.findall(text)))
    return {
        "url": url,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "assetCount": len(assets),
        "assets": assets[:120],
        "scriptAssets": [u for u in assets if urlparse(u).path.lower().endswith(".js")][:40],
        "dataLikeAssets": [u for u in assets if urlparse(u).path.lower().endswith((".json", ".xml", ".txt"))][:40],
        "imageAssets": [u for u in assets if urlparse(u).path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"))][:40],
        "trainNumberLikeTokens": train_tokens[:40],
        "containsTimetableKeywords": any(k in text for k in ("時刻", "列車番号", "小竹向原", "飯能", "元町", "副都心")),
    }


def main() -> None:
    fetched = []
    errors = []
    discovered_scripts = []
    for rel in TARGETS:
        url = urljoin(BASE, rel)
        try:
            raw = curl(url)
            row = summarize(url, raw)
            fetched.append(row)
            discovered_scripts.extend(row["scriptAssets"])
        except Exception as exc:
            errors.append({"url": url, "error": str(exc)})

    # Inspect only a small number of JS files discovered from the official viewer.
    script_rows = []
    seen = set()
    for url in discovered_scripts:
        if url in seen or len(script_rows) >= 16:
            continue
        seen.add(url)
        try:
            raw = curl(url)
            row = summarize(url, raw)
            text = text_of(raw)
            row["mentionsPageData"] = bool(re.search(r"page|book|text|search|contents|thumb|image", text, re.I))
            row["notablePathTokens"] = sorted(set(re.findall(r"[A-Za-z0-9_./-]+\.(?:json|xml|txt|js|jpe?g|png|html?)", text, re.I)))[:80]
            script_rows.append(row)
        except Exception as exc:
            errors.append({"url": url, "error": str(exc)})

    reachable = len(fetched)
    report = {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Seibu Railway official Digital Seibu Timetable 2026",
        "sourceBase": BASE,
        "expectedEdition": "2026",
        "identityPolicy": {
            "singlePublishedTrainColumnMayEstablishIdentity": True,
            "timeProximityMayEstablishIdentity": False,
            "trainNumberAloneMayEstablishIdentity": False,
            "destinationAloneMayEstablishIdentity": False,
            "viewerAssetDiscoveryMayEstablishIdentity": False,
        },
        "sampleTargets": TARGETS,
        "reachableSamplePages": reachable,
        "fetched": fetched,
        "inspectedScripts": script_rows,
        "errors": errors,
        "sourceUsableForFurtherParsing": reachable >= 2,
        "note": "Discovery only. No same-train edge is emitted until a single current official published train column is parsed exactly.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "reachableSamplePages": reachable,
        "discoveredScripts": len(seen),
        "inspectedScripts": len(script_rows),
        "errors": len(errors),
        "sourceUsableForFurtherParsing": report["sourceUsableForFurtherParsing"],
    }, ensure_ascii=False, indent=2))
    if reachable < 2:
        raise SystemExit("Current Seibu official digital timetable could not be inspected from this runner")


if __name__ == "__main__":
    main()
