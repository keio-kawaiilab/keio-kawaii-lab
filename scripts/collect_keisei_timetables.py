#!/usr/bin/env python3
"""Collect Keisei official timetable pages into a resumable snapshot.

The Keisei station timetable HTML contains Vue click handlers with the exact
parameters needed for each official one-train timetable page.  This collector
extracts those parameters, deduplicates trains, then stores each train's real
arrival/departure rows without estimating running times.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

BASE = "https://keisei.ekitan.com"
OUT_DIR = Path("data/transit/keisei")
PROBE_PATH = OUT_DIR / "collector-probe.json"
TEST_PATH = OUT_DIR / "collector-test.json"
UA = "Keio-Kawaii-Lab timetable research/1.0 (+https://github.com/keio-kawaiilab/keio-kawaii-lab)"
REQUEST_INTERVAL = float(os.environ.get("KEISEI_REQUEST_INTERVAL_SECONDS", "0.8"))
SAMPLE_STATION_URL = f"{BASE}/search/timetable/station/254-0/d1?dw=0"

TRAIN_CALL_RE = re.compile(
    r"openOneTrainTimetable\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"
)
TIME_RE = re.compile(r"^(?:[0-2]?\d):[0-5]\d$")


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def get(session: requests.Session, url: str) -> requests.Response:
    last: Exception | None = None
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


def extract_train_refs(html: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for match in TRAIN_CALL_RE.finditer(html):
        tx, sf, date, departure_time, dw = match.groups()
        key = (tx, date, dw)
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            {
                "tx": tx,
                "sf": sf,
                "date": date,
                "time": departure_time,
                "dw": dw,
            }
        )
    return refs


def detail_url(ref: dict[str, str]) -> str:
    query = urlencode({k: ref[k] for k in ("tx", "sf", "date", "time", "dw")})
    return f"{BASE}/search/timetable/onetraintimetable/?{query}"


def clean_cell(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def parse_train_detail(html: str, url: str, ref: dict[str, str]) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    page_title = clean_cell(soup.title) if soup.title else ""

    headings: list[str] = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = clean_cell(tag)
        if text and text not in headings:
            headings.append(text)

    stops: list[dict[str, str | None]] = []
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 3:
            continue
        values = [clean_cell(cell) for cell in cells[:3]]
        station, arrival, departure = values
        if station in {"駅", "駅名", "停車駅"}:
            continue
        if not station or station in {"…", "..."}:
            continue
        # A real timetable row should have at least one clock time.  The
        # terminal/origin side may legitimately be "-" in one column.
        arr_ok = bool(TIME_RE.match(arrival))
        dep_ok = bool(TIME_RE.match(departure))
        if not (arr_ok or dep_ok):
            continue
        stops.append(
            {
                "station": station,
                "arrival": arrival if arr_ok else None,
                "departure": departure if dep_ok else None,
            }
        )

    # Some responsive versions render timetable rows as list items rather than
    # a traditional table. Keep enough diagnostic text to adjust the parser
    # without losing the exact fetched train reference.
    if not stops:
        body_text = clean_cell(soup.body) if soup.body else ""
        diagnostic = body_text[:4000]
    else:
        diagnostic = ""

    return {
        "key": f"{ref['dw']}:{ref['date']}:{ref['tx']}",
        "reference": ref,
        "url": url,
        "pageTitle": page_title,
        "headings": headings[:12],
        "stops": stops,
        "diagnostic": diagnostic,
    }


def run_small_test(session: requests.Session, limit: int, station_url: str) -> dict:
    station = get(session, station_url)
    refs = extract_train_refs(station.text)
    if len(refs) < limit:
        raise RuntimeError(f"station page yielded only {len(refs)} train refs; wanted {limit}")

    by_dw: dict[str, int] = {}
    for ref in refs:
        by_dw[ref["dw"]] = by_dw.get(ref["dw"], 0) + 1

    trains = []
    for index, ref in enumerate(refs[:limit], start=1):
        url = detail_url(ref)
        response = get(session, url)
        parsed = parse_train_detail(response.text, response.url, ref)
        if not parsed["stops"]:
            raise RuntimeError(f"no timetable stop rows parsed for {url}")
        trains.append(parsed)
        print(
            f"detail {index}/{limit}: {ref['tx']} stops={len(parsed['stops'])} "
            f"{parsed['stops'][0]['station']} -> {parsed['stops'][-1]['station']}",
            flush=True,
        )

    result = {
        "version": 1,
        "mode": "small-test",
        "stationUrl": station.url,
        "stationBytes": len(station.content),
        "trainReferenceCount": len(refs),
        "trainReferencesByDw": by_dw,
        "testedCount": len(trains),
        "trains": trains,
    }
    dump_json(TEST_PATH, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


def run_probe(session: requests.Session) -> dict:
    station = get(session, SAMPLE_STATION_URL)
    refs = extract_train_refs(station.text)
    by_dw: dict[str, int] = {}
    for ref in refs:
        by_dw[ref["dw"]] = by_dw.get(ref["dw"], 0) + 1
    result = {
        "version": 2,
        "stationUrl": station.url,
        "stationBytes": len(station.content),
        "trainReferenceCount": len(refs),
        "trainReferencesByDw": by_dw,
        "samples": refs[:10],
    }
    dump_json(PROBE_PATH, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Fetch N train details from a known station page")
    parser.add_argument("--station-url", default=SAMPLE_STATION_URL)
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "ja,en;q=0.5"})

    if args.probe:
        run_probe(session)
        return 0
    if args.limit > 0:
        run_small_test(session, args.limit, args.station_url)
        return 0

    raise SystemExit("Choose --probe or --limit N")


if __name__ == "__main__":
    raise SystemExit(main())
