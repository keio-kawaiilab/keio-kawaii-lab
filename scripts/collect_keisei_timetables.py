#!/usr/bin/env python3
"""Collect Keisei official timetables into a resumable snapshot.

Keisei's station timetable HTML embeds Vue handlers containing the exact
parameters for each official one-train timetable page.  The collector first
walks every line/station/direction page and deduplicates train references,
then detailed train pages can be collected from that durable state.
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
STATE_PATH = OUT_DIR / "collector-state.json"
UA = "Keio-Kawaii-Lab timetable research/1.0 (+https://github.com/keio-kawaiilab/keio-kawaii-lab)"
REQUEST_INTERVAL = float(os.environ.get("KEISEI_REQUEST_INTERVAL_SECONDS", "0.55"))
SAMPLE_STATION_URL = f"{BASE}/search/timetable/station/254-0/d1?dw=0"

# Current Keisei timetable line IDs.  We do not hard-code the station count:
# each line is scanned from index 0 until three consecutive blank indices, so
# timetable changes or a newly added station do not require a code edit.
LINE_IDS = ("242", "254", "255", "256", "257", "258", "682")
MAX_STATION_INDEX = 64
BLANK_INDEX_STOP = 3

TRAIN_CALL_RE = re.compile(
    r"openOneTrainTimetable\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"
)
TIME_RE = re.compile(r"^(?:[0-2]?\d):[0-5]\d$")


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "ja,en;q=0.5"})
    return session


def get(session: requests.Session, url: str, *, allow_missing: bool = False) -> requests.Response | None:
    last: Exception | None = None
    for attempt in range(5):
        try:
            response = session.get(url, timeout=(15, 90))
            if allow_missing and response.status_code in {404, 410}:
                return None
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
            if allow_missing and isinstance(exc, requests.HTTPError):
                status = exc.response.status_code if exc.response is not None else None
                if status is not None and 400 <= status < 500 and status != 429:
                    return None
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
        refs.append({"tx": tx, "sf": sf, "date": date, "time": departure_time, "dw": dw})
    return refs


def train_key(ref: dict[str, str]) -> str:
    return f"{ref['dw']}:{ref['tx']}"


def service_minutes(raw: str) -> int:
    raw = raw.zfill(4)
    hour = int(raw[:-2])
    minute = int(raw[-2:])
    # Railway service after midnight belongs to the previous service day. This
    # keeps a 23:55 origin ahead of its 00:20 intermediate stop.
    if hour < 3:
        hour += 24
    return hour * 60 + minute


def prefer_reference(old: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    return new if service_minutes(new["time"]) < service_minutes(old["time"]) else old


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
        station, arrival, departure = [clean_cell(cell) for cell in cells[:3]]
        if station in {"駅", "駅名", "停車駅"} or not station or station in {"…", "..."}:
            continue
        arr_ok = bool(TIME_RE.match(arrival))
        dep_ok = bool(TIME_RE.match(departure))
        if not (arr_ok or dep_ok):
            continue
        stops.append({
            "station": station,
            "arrival": arrival if arr_ok else None,
            "departure": departure if dep_ok else None,
        })

    diagnostic = ""
    if not stops:
        diagnostic = clean_cell(soup.body)[:4000] if soup.body else ""

    return {
        "key": train_key(ref),
        "reference": ref,
        "url": url,
        "pageTitle": page_title,
        "headings": headings[:12],
        "stops": stops,
        "diagnostic": diagnostic,
    }


def station_url(line_id: str, station_index: int, direction: int) -> str:
    return f"{BASE}/search/timetable/station/{line_id}-{station_index}/d{direction}?dw=0"


def page_label(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = clean_cell(tag)
        if text and "時刻表" in text:
            return text
    return clean_cell(soup.title) if soup.title else ""


def run_discovery(session: requests.Session) -> dict:
    refs_by_key: dict[str, dict[str, str]] = {}
    pages: list[dict] = []
    valid_station_indices = 0

    for line_id in LINE_IDS:
        blank_indices = 0
        line_valid = 0
        for station_index in range(MAX_STATION_INDEX + 1):
            index_had_refs = False
            for direction in (1, 2):
                url = station_url(line_id, station_index, direction)
                response = get(session, url, allow_missing=True)
                if response is None:
                    continue
                refs = extract_train_refs(response.text)
                if not refs:
                    continue
                index_had_refs = True
                counts: dict[str, int] = {}
                for ref in refs:
                    counts[ref["dw"]] = counts.get(ref["dw"], 0) + 1
                    key = train_key(ref)
                    if key in refs_by_key:
                        refs_by_key[key] = prefer_reference(refs_by_key[key], ref)
                    else:
                        refs_by_key[key] = ref
                pages.append({
                    "lineId": line_id,
                    "stationIndex": station_index,
                    "direction": direction,
                    "url": response.url,
                    "label": page_label(response.text),
                    "referenceCount": len(refs),
                    "byDw": counts,
                })
                print(
                    f"page {len(pages)} line={line_id} station={station_index} d{direction} "
                    f"refs={len(refs)} unique={len(refs_by_key)}",
                    flush=True,
                )

            if index_had_refs:
                if blank_indices:
                    # A small gap is tolerated; reset after a valid index.
                    blank_indices = 0
                line_valid += 1
                valid_station_indices += 1
            else:
                blank_indices += 1
                if line_valid > 0 and blank_indices >= BLANK_INDEX_STOP:
                    break

        print(f"line {line_id}: station-indices={line_valid}", flush=True)

    refs = [refs_by_key[key] for key in sorted(refs_by_key)]
    by_dw: dict[str, int] = {}
    by_date: dict[str, int] = {}
    for ref in refs:
        by_dw[ref["dw"]] = by_dw.get(ref["dw"], 0) + 1
        by_date[ref["date"]] = by_date.get(ref["date"], 0) + 1

    result = {
        "version": 1,
        "source": "Keisei official timetable / keisei.ekitan.com",
        "lineIds": list(LINE_IDS),
        "pageCount": len(pages),
        "validLineStationIndexCount": valid_station_indices,
        "trainReferenceCount": len(refs),
        "trainReferencesByDw": by_dw,
        "trainReferencesByDate": by_date,
        "pages": pages,
        "trainRefs": refs,
    }
    dump_json(STATE_PATH, result)
    print(
        f"DISCOVERY COMPLETE pages={len(pages)} station-indices={valid_station_indices} "
        f"unique-trains={len(refs)} by-dw={by_dw}",
        flush=True,
    )
    return result


def run_small_test(session: requests.Session, limit: int, station_url_value: str) -> dict:
    station = get(session, station_url_value)
    if station is None:
        raise RuntimeError(f"missing station page {station_url_value}")
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
        if response is None:
            raise RuntimeError(f"missing train page {url}")
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
    return result


def run_probe(session: requests.Session) -> dict:
    station = get(session, SAMPLE_STATION_URL)
    if station is None:
        raise RuntimeError("sample station page missing")
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
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Fetch N train details from a known station page")
    parser.add_argument("--station-url", default=SAMPLE_STATION_URL)
    args = parser.parse_args()

    session = new_session()
    if args.probe:
        run_probe(session)
        return 0
    if args.discover:
        run_discovery(session)
        return 0
    if args.limit > 0:
        run_small_test(session, args.limit, args.station_url)
        return 0
    raise SystemExit("Choose --probe, --discover, or --limit N")


if __name__ == "__main__":
    raise SystemExit(main())
