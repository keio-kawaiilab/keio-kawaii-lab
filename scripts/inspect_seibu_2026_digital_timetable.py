#!/usr/bin/env python3
"""Inspect the current official Seibu 2026 digital timetable without inferring train identity.

This downloads only a small set of official viewer/config resources and writes a
compact report. Its purpose is source discovery: find an exact published train-column
source that can later establish physical-train identity. Close times, train numbers
alone, destinations alone, and viewer metadata alone must never establish identity.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
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
CONFIG_TARGETS = [
    "html5/js/book.xml",
    "html5/js/search.xml",
    "html5/js/t.xml",
    "html5/js/html5setting.xml",
    "html5/js/skinoption.xml",
]
OUT = Path("data/transit/fukutoshin/seibu-2026-source-report.json")
ATTR_RE = re.compile(r"(?:href|src)\s*=\s*[\"']([^\"']+)[\"']", re.I)
URL_RE = re.compile(r"url\(\s*[\"']?([^\"')]+)", re.I)
ASSET_RE = re.compile(r"[^\"'\s<>]+\.(?:js|json|txt|xml|css|svg|png|jpe?g|gif|webp|html?|pdf)(?:\?[^\"'\s<>]*)?", re.I)
TRAIN_TOKEN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]?\d{3,5}[A-Z](?![A-Z0-9])")
KEYWORDS = ("時刻", "列車番号", "小竹向原", "飯能", "元町", "中華街", "副都心", "池袋線", "有楽町線")


def curl(url: str) -> bytes:
    proc = subprocess.run(
        [
            "curl", "-fLsS", "--retry", "3", "--retry-delay", "1",
            "--connect-timeout", "15", "--max-time", "60",
            "-A", "Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/1.0)",
            "-H", "Accept: text/html,application/xhtml+xml,application/xml,text/xml,application/javascript,text/javascript,*/*;q=0.8",
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
        "pdfAssets": [u for u in assets if urlparse(u).path.lower().endswith(".pdf")][:20],
        "trainNumberLikeTokenCount": len(train_tokens),
        "trainNumberLikeTokens": train_tokens[:40],
        "keywordHits": [k for k in KEYWORDS if k in text],
    }


def compact_fragments(text: str) -> list[dict]:
    normalized = re.sub(r"\s+", " ", text)
    out = []
    for keyword in KEYWORDS:
        pos = normalized.find(keyword)
        if pos < 0:
            continue
        start = max(0, pos - 100)
        end = min(len(normalized), pos + len(keyword) + 180)
        out.append({"keyword": keyword, "fragment": normalized[start:end]})
        if len(out) >= 8:
            break
    return out


def summarize_config(url: str, raw: bytes) -> dict:
    base = summarize(url, raw)
    text = text_of(raw)
    base["notablePathTokens"] = sorted(set(re.findall(r"[A-Za-z0-9_./{}$-]+\.(?:json|xml|txt|js|jpe?g|png|html?|pdf)", text, re.I)))[:120]
    base["keywordFragments"] = compact_fragments(text)
    base["xml"] = {"parseable": False, "root": "", "elementCount": 0, "tagCounts": {}}
    try:
        root = ET.fromstring(text)
        tags = {}
        count = 0
        for elem in root.iter():
            count += 1
            tag = str(elem.tag).split('}')[-1]
            tags[tag] = tags.get(tag, 0) + 1
        base["xml"] = {
            "parseable": True,
            "root": str(root.tag).split('}')[-1],
            "elementCount": count,
            "tagCounts": dict(sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))[:60]),
        }
    except Exception as exc:
        base["xml"]["error"] = str(exc)[:300]
    return base


def main() -> None:
    fetched = []
    config_rows = []
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

    for rel in CONFIG_TARGETS:
        url = urljoin(BASE, rel)
        try:
            config_rows.append(summarize_config(url, curl(url)))
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
            row["notablePathTokens"] = sorted(set(re.findall(r"[A-Za-z0-9_./{}$-]+\.(?:json|xml|txt|js|jpe?g|png|html?|pdf)", text, re.I)))[:100]
            script_rows.append(row)
        except Exception as exc:
            errors.append({"url": url, "error": str(exc)})

    reachable = len(fetched)
    config_reachable = len(config_rows)
    searchable_config = [row["url"] for row in config_rows if row["keywordHits"] or row["trainNumberLikeTokenCount"]]
    report = {
        "version": 2,
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
        "configTargets": CONFIG_TARGETS,
        "reachableSamplePages": reachable,
        "reachableConfigResources": config_reachable,
        "fetched": fetched,
        "configResources": config_rows,
        "inspectedScripts": script_rows,
        "errors": errors,
        "searchableConfigResources": searchable_config,
        "sourceUsableForFurtherParsing": reachable >= 2 and config_reachable >= 1,
        "note": "Discovery only. No same-train edge is emitted until a single current official published train column is parsed exactly.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "reachableSamplePages": reachable,
        "reachableConfigResources": config_reachable,
        "searchableConfigResources": searchable_config,
        "discoveredScripts": len(seen),
        "inspectedScripts": len(script_rows),
        "errors": len(errors),
        "sourceUsableForFurtherParsing": report["sourceUsableForFurtherParsing"],
    }, ensure_ascii=False, indent=2))
    if reachable < 2 or config_reachable < 1:
        raise SystemExit("Current Seibu official digital timetable could not be structurally inspected from this runner")


if __name__ == "__main__":
    main()
