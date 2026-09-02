#!/usr/bin/env python3
"""Collect Keisei official timetables into resumable local snapshots.

Station timetable HTML embeds Vue handlers containing the exact parameters for
Keisei's official one-train timetable pages. Discovery stores a durable list of
all trains. Detail collection is chunked, parallel, and restartable so a failed
runner never forces the network to be scanned from zero again.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

BASE = "https://keisei.ekitan.com"
OUT_DIR = Path("data/transit/keisei")
CHUNK_DIR = OUT_DIR / "train-detail-chunks"
PROBE_PATH = OUT_DIR / "collector-probe.json"
TEST_PATH = OUT_DIR / "collector-test.json"
STATE_PATH = OUT_DIR / "collector-state.json"
UA = "Keio-Kawaii-Lab timetable research/1.0 (+https://github.com/keio-kawaiilab/keio-kawaii-lab)"
REQUEST_INTERVAL = float(os.environ.get("KEISEI_REQUEST_INTERVAL_SECONDS", "0.35"))
DEFAULT_WORKERS = int(os.environ.get("KEISEI_WORKERS", "6"))
SAMPLE_STATION_URL = f"{BASE}/search/timetable/station/254-0/d1?dw=0"

LINE_IDS = ("242", "254", "255", "256", "257", "258", "682")
MAX_STATION_INDEX = 64
BLANK_INDEX_STOP = 3
TRAIN_CALL_RE = re.compile(
    r"openOneTrainTimetable\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"
)
TIME_RE = re.compile(r"^(?:[0-2]?\d):[0-5]\d$")
DETAIL_LABEL_RE = re.compile(r"^(.*?)行き\s+(.+?)\s+[（(]([^）)]+)[）)]")
_thread_local = threading.local()


def dump_json(path: Path, value: object, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    kwargs = {"ensure_ascii": False}
    if compact:
        kwargs["separators"] = (",", ":")
    else:
        kwargs["indent"] = 2
    tmp.write_text(json.dumps(value, **kwargs), encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "ja,en;q=0.5"})
    return session


def worker_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = new_session()
        _thread_local.session = session
    return session


def get(session: requests.Session, url: str, *, allow_missing: bool = False) -> requests.Response | None:
    last: Exception | None = None
    for attempt in range(6):
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

    service_label = headings[2] if len(headings) > 2 else ""
    destination = ""
    train_type = ""
    calendar_label = "平日" if ref.get("dw") == "0" else "土休日"
    match = DETAIL_LABEL_RE.match(service_label)
    if match:
        destination, train_type, calendar_label = (part.strip() for part in match.groups())
    if not destination and stops:
        destination = str(stops[-1]["station"])

    journey_origin = str(stops[0]["station"]) if stops else ""
    journey_destination = str(stops[-1]["station"]) if stops else destination
    return {
        "key": train_key(ref),
        "sourceTrainId": ref["tx"],
        "calendar": "weekday" if ref["dw"] == "0" else "holiday",
        "calendarLabel": calendar_label,
        "trainType": train_type,
        "destination": destination,
        "origin": journey_origin,
        "journeyDestination": journey_destination,
        "reference": ref,
        "url": url,
        "pageTitle": page_title,
        "headings": headings[:8],
        "stops": stops,
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
                    refs_by_key[key] = prefer_reference(refs_by_key[key], ref) if key in refs_by_key else ref
                pages.append({
                    "lineId": line_id,
                    "stationIndex": station_index,
                    "direction": direction,
                    "url": response.url,
                    "label": page_label(response.text),
                    "referenceCount": len(refs),
                    "byDw": counts,
                })
                print(f"page {len(pages)} line={line_id} station={station_index} d{direction} refs={len(refs)} unique={len(refs_by_key)}", flush=True)
            if index_had_refs:
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
    print(f"DISCOVERY COMPLETE pages={len(pages)} station-indices={valid_station_indices} unique-trains={len(refs)} by-dw={by_dw}", flush=True)
    return result


def fetch_one_detail(ref: dict[str, str]) -> tuple[str, dict | None, str | None]:
    key = train_key(ref)
    try:
        response = get(worker_session(), detail_url(ref))
        if response is None:
            return key, None, "missing detail page"
        parsed = parse_train_detail(response.text, response.url, ref)
        if len(parsed["stops"]) < 2:
            return key, None, "fewer than two parsed stops"
        return key, parsed, None
    except Exception as exc:  # one bad train must not erase a completed chunk
        return key, None, f"{type(exc).__name__}: {exc}"


def chunk_path(index: int) -> Path:
    return CHUNK_DIR / f"chunk-{index:03d}.json"


def run_detail_chunk(index: int, chunk_size: int, workers: int) -> dict:
    if not STATE_PATH.exists():
        raise RuntimeError("collector-state.json is missing; run --discover first")
    state = load_json(STATE_PATH)
    if not isinstance(state, dict) or not isinstance(state.get("trainRefs"), list):
        raise RuntimeError("collector-state.json has an invalid trainRefs list")
    all_refs = state["trainRefs"]
    start = index * chunk_size
    end = min(len(all_refs), start + chunk_size)
    refs = all_refs[start:end]
    if not refs:
        raise RuntimeError(f"chunk {index} is outside 0..{(len(all_refs)-1)//chunk_size}")

    path = chunk_path(index)
    successful: dict[str, dict] = {}
    previous_errors: dict[str, str] = {}
    if path.exists():
        existing = load_json(path)
        if isinstance(existing, dict):
            for train in existing.get("trains") or []:
                if isinstance(train, dict) and train.get("key") and len(train.get("stops") or []) >= 2:
                    successful[str(train["key"])] = train
            for row in existing.get("errors") or []:
                if isinstance(row, dict) and row.get("key"):
                    previous_errors[str(row["key"])] = str(row.get("error") or "")

    pending = [ref for ref in refs if train_key(ref) not in successful]
    print(f"CHUNK {index}: range={start}:{end} total={len(refs)} existing={len(successful)} pending={len(pending)} workers={workers}", flush=True)
    current_errors: dict[str, str] = dict(previous_errors)

    def persist() -> None:
        ordered = [successful[train_key(ref)] for ref in refs if train_key(ref) in successful]
        errors = [
            {"key": train_key(ref), "reference": ref, "error": current_errors.get(train_key(ref), "not fetched")}
            for ref in refs if train_key(ref) not in successful
        ]
        payload = {
            "version": 1,
            "chunkIndex": index,
            "chunkSize": chunk_size,
            "start": start,
            "end": end,
            "expectedCount": len(refs),
            "complete": len(ordered) == len(refs),
            "trains": ordered,
            "errors": errors,
        }
        dump_json(path, payload, compact=True)

    completed_since_save = 0
    if pending:
        with ThreadPoolExecutor(max_workers=max(1, min(8, workers))) as executor:
            futures = {executor.submit(fetch_one_detail, ref): ref for ref in pending}
            for ordinal, future in enumerate(as_completed(futures), start=1):
                key, train, error = future.result()
                if train is not None:
                    successful[key] = train
                    current_errors.pop(key, None)
                    completed_since_save += 1
                    if completed_since_save >= 25:
                        persist()
                        completed_since_save = 0
                else:
                    current_errors[key] = error or "unknown error"
                print(f"chunk {index}: {len(successful)}/{len(refs)} key={key}{' ERROR' if error else ''}", flush=True)
    persist()
    result = load_json(path)
    if not isinstance(result, dict):
        raise RuntimeError(f"failed to persist chunk {index}")
    print(f"CHUNK COMPLETE index={index} success={len(result.get('trains') or [])}/{len(refs)} errors={len(result.get('errors') or [])}", flush=True)
    if result.get("errors"):
        raise RuntimeError(f"chunk {index} still has {len(result['errors'])} unresolved trains")
    return result


def run_merge_chunks(chunk_size: int) -> dict:
    state = load_json(STATE_PATH)
    refs = state.get("trainRefs") if isinstance(state, dict) else None
    if not isinstance(refs, list):
        raise RuntimeError("invalid collector state")
    expected = {train_key(ref) for ref in refs}
    trains_by_key: dict[str, dict] = {}
    chunk_count = (len(refs) + chunk_size - 1) // chunk_size
    for index in range(chunk_count):
        path = chunk_path(index)
        if not path.exists():
            raise RuntimeError(f"missing detail chunk {index}")
        chunk = load_json(path)
        if not isinstance(chunk, dict) or not chunk.get("complete") or chunk.get("errors"):
            raise RuntimeError(f"incomplete detail chunk {index}")
        for train in chunk.get("trains") or []:
            if isinstance(train, dict) and train.get("key"):
                trains_by_key[str(train["key"])] = train
    missing = sorted(expected - trains_by_key.keys())
    extra = sorted(trains_by_key.keys() - expected)
    if missing or extra or len(trains_by_key) != len(expected):
        raise RuntimeError(f"detail merge mismatch expected={len(expected)} actual={len(trains_by_key)} missing={len(missing)} extra={len(extra)}")
    ordered = [trains_by_key[train_key(ref)] for ref in refs]
    stats = {
        "version": 1,
        "source": "Keisei official timetable / keisei.ekitan.com",
        "trainCount": len(ordered),
        "weekdayCount": sum(1 for train in ordered if train.get("calendar") == "weekday"),
        "holidayCount": sum(1 for train in ordered if train.get("calendar") == "holiday"),
        "stopRowCount": sum(len(train.get("stops") or []) for train in ordered),
        "trains": ordered,
    }
    dump_json(OUT_DIR / "official-train-details.json", stats, compact=True)
    print(f"MERGE COMPLETE trains={stats['trainCount']} stops={stats['stopRowCount']}", flush=True)
    return stats


def run_small_test(session: requests.Session, limit: int, station_url_value: str) -> dict:
    station = get(session, station_url_value)
    if station is None:
        raise RuntimeError(f"missing station page {station_url_value}")
    refs = extract_train_refs(station.text)
    if len(refs) < limit:
        raise RuntimeError(f"station page yielded only {len(refs)} train refs; wanted {limit}")
    trains = []
    for index, ref in enumerate(refs[:limit], start=1):
        response = get(session, detail_url(ref))
        if response is None:
            raise RuntimeError(f"missing train page {detail_url(ref)}")
        parsed = parse_train_detail(response.text, response.url, ref)
        if len(parsed["stops"]) < 2:
            raise RuntimeError(f"no timetable rows parsed for {response.url}")
        trains.append(parsed)
        print(f"detail {index}/{limit}: {ref['tx']} stops={len(parsed['stops'])}", flush=True)
    result = {"version": 1, "mode": "small-test", "stationUrl": station.url, "trainReferenceCount": len(refs), "testedCount": len(trains), "trains": trains}
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
    result = {"version": 2, "stationUrl": station.url, "stationBytes": len(station.content), "trainReferenceCount": len(refs), "trainReferencesByDw": by_dw, "samples": refs[:10]}
    dump_json(PROBE_PATH, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--station-url", default=SAMPLE_STATION_URL)
    parser.add_argument("--collect-chunk", type=int)
    parser.add_argument("--chunk-size", type=int, default=300)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--merge-chunks", action="store_true")
    args = parser.parse_args()

    if args.collect_chunk is not None:
        run_detail_chunk(args.collect_chunk, args.chunk_size, args.workers)
        return 0
    if args.merge_chunks:
        run_merge_chunks(args.chunk_size)
        return 0

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
    raise SystemExit("Choose --probe, --discover, --limit N, --collect-chunk N, or --merge-chunks")


if __name__ == "__main__":
    raise SystemExit(main())
