#!/usr/bin/env python3
"""Extract compact metadata from the current official Seibu FLIPPER3 timetable XML.

This script is diagnostic only. It never emits same-train identities. It discovers
the publisher's real page-data folders so a later parser can read one official
published train column exactly. No time, train-number, or destination matching is
allowed to establish identity.
"""
from __future__ import annotations

import collections
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

BASE = "https://www.seiburailway.jp/railways/2026digitaltimetable/"
FILES = ("book.xml", "search.xml", "menu.xml")
OUT = Path("data/transit/fukutoshin/seibu-2026-flipper-metadata.json")
KEYWORDS = ("西武有楽町線", "有楽町線", "池袋線", "小竹向原", "練馬", "飯能", "S-TRAIN", "元町", "中華街", "副都心")
PAGE_TOKEN = re.compile(r"(?:page|pagenum|page_no|pageNo|pageno)[^0-9]{0,8}(\d{1,3})", re.I)
PATH_TOKEN = re.compile(r"(?:^|[/_.-])(?:page|p)(\d{1,3})(?:[/_.-]|$)", re.I)
TRAIN_TOKEN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]?\d{3,5}[A-Z](?![A-Z0-9])")
PROBE_PAGES = (9, 11, 37, 63, 64, 80)


def curl(url: str) -> bytes:
    proc = subprocess.run(
        [
            "curl", "-fLsS", "--retry", "2", "--retry-delay", "1",
            "--connect-timeout", "15", "--max-time", "45",
            "-A", "Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/1.0)",
            "-H", "Accept: application/xml,text/xml,*/*;q=0.8",
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"curl failed ({proc.returncode}) for {url}: {proc.stderr.decode('utf-8','replace')[-300:]}")
    return proc.stdout


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "shift_jis", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def tag(elem: ET.Element) -> str:
    return str(elem.tag).split("}")[-1]


def element_record(elem: ET.Element, text_limit: int = 500) -> dict:
    return {
        "tag": tag(elem),
        "attrs": dict(elem.attrib),
        "text": (elem.text or "").strip()[:text_limit],
    }


def find_page_numbers(value: str) -> list[int]:
    out = set()
    for regex in (PAGE_TOKEN, PATH_TOKEN):
        for match in regex.finditer(value or ""):
            n = int(match.group(1))
            if 1 <= n <= 400:
                out.add(n)
    return sorted(out)


def inspect(name: str, raw: bytes) -> dict:
    text = decode(raw)
    root = ET.fromstring(text)
    tag_counts = collections.Counter()
    attr_counts = collections.Counter()
    page_numbers = set()
    path_like_values = set()
    keyword_records = []
    page_like_records = []
    all_records = []

    for elem in root.iter():
        rec = element_record(elem)
        tag_counts[rec["tag"]] += 1
        for key, value in rec["attrs"].items():
            attr_counts[key] += 1
            for n in find_page_numbers(f"{key}={value}"):
                page_numbers.add(n)
            if any(token in value.lower() for token in ("page", ".xml", ".jpg", ".pdf")):
                path_like_values.add(value)
        joined = " ".join([rec["tag"], rec["text"], *[f"{k}={v}" for k,v in rec["attrs"].items()]])
        for n in find_page_numbers(joined):
            page_numbers.add(n)
        if any(k in joined for k in KEYWORDS) and len(keyword_records) < 100:
            keyword_records.append(rec)
        keys_lower = {x.lower() for x in rec["attrs"].keys()}
        if any(k.lower() in keys_lower for k in ("page", "pagenum", "pageno", "page_no")) and len(page_like_records) < 100:
            page_like_records.append(rec)
        if len(all_records) < 30:
            all_records.append(rec)

    train_tokens = sorted(set(TRAIN_TOKEN_RE.findall(text)))
    return {
        "file": name,
        "bytes": len(raw),
        "rootTag": tag(root),
        "rootAttrs": dict(root.attrib),
        "elementCount": sum(tag_counts.values()),
        "tagCounts": dict(tag_counts.most_common(80)),
        "attributeCounts": dict(attr_counts.most_common(80)),
        "firstElements": all_records,
        "pageLikeElements": page_like_records,
        "keywordElements": keyword_records,
        "discoveredPageNumbers": sorted(page_numbers),
        "pathLikeValues": sorted(path_like_values)[:200],
        "trainNumberLikeTokenCount": len(train_tokens),
        "trainNumberLikeTokens": train_tokens[:100],
    }


def text_for_tag(raw: bytes, wanted: str) -> str:
    root = ET.fromstring(decode(raw))
    for elem in root.iter():
        if tag(elem) == wanted:
            return (elem.text or "").strip()
    return ""


def page_data_ids(book_raw: bytes) -> list[str]:
    return [part.strip() for part in text_for_tag(book_raw, "data").split(",") if part.strip()]


def probe_page(page: int, data_id: str) -> dict:
    row = {"page": page, "dataId": data_id, "attempts": [], "resources": []}
    # FLIPPER3 package generators may publish the opaque data id either directly
    # as the page folder or under a page/pages container. Probe only these narrow,
    # deterministic layouts; never crawl recursively.
    prefixes = (f"{data_id}/", f"page/{data_id}/", f"pages/{data_id}/")
    for filename in ("page.xml", "textpoint.xml"):
        found = False
        for prefix in prefixes:
            rel = prefix + filename
            url = urljoin(BASE, rel)
            try:
                raw = curl(url)
                inspected = inspect(rel, raw)
                row["resources"].append({"url": url, **inspected})
                row["attempts"].append({"url": url, "status": "ok", "bytes": len(raw)})
                found = True
                break
            except Exception as exc:
                row["attempts"].append({"url": url, "status": "miss", "error": str(exc)[:260]})
        if not found:
            row.setdefault("missing", []).append(filename)
    row["resolved"] = bool(row["resources"])
    return row


def main() -> None:
    resources = []
    raw_by_name: dict[str, bytes] = {}
    errors = []
    for name in FILES:
        url = urljoin(BASE, name)
        try:
            raw = curl(url)
            raw_by_name[name] = raw
            resources.append(inspect(name, raw))
        except Exception as exc:
            errors.append({"file": name, "url": url, "error": str(exc)})

    if len(raw_by_name) < 3:
        raise SystemExit("Could not fetch all required current Seibu FLIPPER3 metadata files")

    by_name = {row["file"]: row for row in resources}
    menu_entries = []
    for rec in by_name.get("menu.xml", {}).get("pageLikeElements", []):
        attrs = rec.get("attrs", {})
        if attrs.get("name") or attrs.get("pagenum"):
            menu_entries.append({
                "name": attrs.get("name", ""),
                "pagenum": attrs.get("pagenum", attrs.get("page", "")),
                "id": attrs.get("id", ""),
            })

    ids = page_data_ids(raw_by_name["book.xml"])
    id_mapping = [{"page": i + 1, "dataId": data_id} for i, data_id in enumerate(ids)]
    probes = []
    for page in PROBE_PAGES:
        if 1 <= page <= len(ids):
            probes.append(probe_page(page, ids[page - 1]))

    report = {
        "version": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceBase": BASE,
        "sourceFiles": list(FILES),
        "identityPolicy": {
            "metadataMayEstablishIdentity": False,
            "timeProximityMayEstablishIdentity": False,
            "trainNumberAloneMayEstablishIdentity": False,
            "destinationAloneMayEstablishIdentity": False,
            "singlePublishedTrainColumnRequired": True,
        },
        "resources": resources,
        "menuEntries": menu_entries,
        "pageData": {
            "count": len(ids),
            "mapping": id_mapping,
            "probePages": list(PROBE_PAGES),
            "probes": probes,
        },
        "errors": errors,
        "summary": {
            "resourcesFetched": len(resources),
            "errors": len(errors),
            "menuEntries": len(menu_entries),
            "pageDataIds": len(ids),
            "resolvedProbePages": sum(1 for row in probes if row["resolved"]),
            "searchKeywordElements": len(by_name.get("search.xml", {}).get("keywordElements", [])),
            "searchDiscoveredPageNumbers": by_name.get("search.xml", {}).get("discoveredPageNumbers", []),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if len(ids) < 200:
        raise SystemExit(f"Unexpectedly few FLIPPER3 page data ids: {len(ids)}")


if __name__ == "__main__":
    main()
