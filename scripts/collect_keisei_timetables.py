#!/usr/bin/env python3
"""Collect Keisei official timetable pages into a resumable local snapshot.

This collector is intentionally separate from the ODPT importer. It reads the
Keisei/Ekitan official timetable pages at a conservative request rate and can
be resumed from files already written under data/transit/keisei.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://keisei.ekitan.com"
SEARCH_URL = f"{BASE}/search/timetable"
OUT_DIR = Path("data/transit/keisei")
PROBE_PATH = OUT_DIR / "collector-probe.json"
UA = "Keio-Kawaii-Lab timetable research/1.0 (+https://github.com/keio-kawaiilab/keio-kawaii-lab)"
REQUEST_INTERVAL = float(os.environ.get("KEISEI_REQUEST_INTERVAL_SECONDS", "1.0"))


def get(session: requests.Session, url: str) -> requests.Response:
    last = None
    for attempt in range(5):
        try:
            response = session.get(url, timeout=(15, 90))
            if response.status_code in {429, 500, 502, 503, 504}:
                delay = min(30, 2 ** attempt)
                print(f"retry {response.status_code} {url} in {delay}s", flush=True)
                time.sleep(delay)
                continue
            response.raise_for_status()
            time.sleep(REQUEST_INTERVAL)
            return response
        except requests.RequestException as exc:
            last = exc
            delay = min(30, 2 ** attempt)
            print(f"retry error {type(exc).__name__} {url} in {delay}s", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"failed to fetch {url}: {last}")


def hrefs_from_html(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for tag in soup.find_all("a", href=True):
        href = str(tag.get("href") or "").strip()
        if href:
            urls.append(urljoin(base_url, href))
    return urls


def probe(session: requests.Session) -> dict:
    root = get(session, SEARCH_URL)
    root_hrefs = hrefs_from_html(root.text, root.url)
    station_hrefs = sorted({u for u in root_hrefs if "/search/timetable/station/" in u})

    sample_station = f"{BASE}/search/timetable/station/254-0/d1?dw=0"
    station = get(session, sample_station)
    station_hrefs_all = hrefs_from_html(station.text, station.url)
    train_hrefs = sorted({u for u in station_hrefs_all if "onetraintimetable" in u})

    raw_station_matches = sorted(set(re.findall(r"/search/timetable/station/[0-9]+-[0-9]+/d[12][^\"'<> ]*", root.text)))
    raw_train_matches = sorted(set(re.findall(r"[^\"'<> ]*onetraintimetable[^\"'<> ]*", station.text)))

    result = {
        "root_status": root.status_code,
        "root_bytes": len(root.content),
        "station_anchor_count": len(station_hrefs),
        "station_anchor_samples": station_hrefs[:10],
        "station_raw_match_count": len(raw_station_matches),
        "station_raw_samples": raw_station_matches[:10],
        "sample_station_status": station.status_code,
        "sample_station_bytes": len(station.content),
        "train_anchor_count": len(train_hrefs),
        "train_anchor_samples": train_hrefs[:10],
        "train_raw_match_count": len(raw_train_matches),
        "train_raw_samples": raw_train_matches[:10],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PROBE_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "ja,en;q=0.5"})

    if args.probe:
        probe(session)
        return 0

    # Full resumable collection is enabled after the official-page structure
    # probe has been verified in GitHub Actions.
    probe(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
