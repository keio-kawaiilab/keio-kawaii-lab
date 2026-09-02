#!/usr/bin/env python3
"""Convert the collected Keisei official train pages into app timetable files.

The collector keeps the complete official train snapshot for provenance.  This
script derives the compact per-railway format consumed by route-core.js without
throwing away the original data.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path("data/transit/keisei")
DETAILS_PATH = ROOT / "official-train-details.json"
ENTITIES_PATH = ROOT / "entities.json"
TOPOLOGY_PATH = Path("data/transit-sources/manual-topology.json")
INDEX_PATH = ROOT / "timetable-index.json"
REPORT_PATH = ROOT / "official-conversion-report.json"
MANIFEST_PATH = Path("data/transit/manifest.json")
TIMETABLE_DIR = ROOT / "timetables"
JST = timezone(timedelta(hours=9))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"\s+", "", text)
    aliases = {
        "成田空港(成田第1ターミナル)": "成田空港",
        "空港第2ビル(成田第2・第3ターミナル)": "空港第2ビル",
        "空港第2ビル(成田第2・3ターミナル)": "空港第2ビル",
    }
    return aliases.get(text, text)


def title(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("ja") or value.get("en") or "")
    return ""


def clock_minutes(value: Any) -> int | None:
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hour, minute = map(int, match.groups())
    if minute > 59:
        return None
    if hour < 3:
        hour += 24
    return hour * 60 + minute


def monotonic_time(value: Any, previous: int | None) -> int | None:
    minute = clock_minutes(value)
    if minute is None:
        return None
    if previous is not None:
        while minute + 360 < previous:
            minute += 1440
    return minute


def train_number(source_train_id: Any) -> str:
    text = str(source_train_id or "")
    return text.rsplit("-", 1)[-1] if "-" in text else text


def build_station_maps(entities: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    by_name: dict[str, str] = {}
    names_by_id: dict[str, str] = {}
    for station in entities.get("Station") or []:
        if not isinstance(station, dict):
            continue
        station_id = str(station.get("owl:sameAs") or "")
        name = title(station, "odpt:stationTitle") or str(station.get("dc:title") or "")
        if station_id and name:
            by_name[normalize_name(name)] = station_id
            names_by_id[station_id] = name
    return by_name, names_by_id


def build_lines(topology: dict[str, Any], station_by_name: dict[str, str]) -> dict[str, dict[str, Any]]:
    keisei = topology.get("keisei") if isinstance(topology, dict) else None
    if not isinstance(keisei, dict):
        raise RuntimeError("manual topology has no keisei section")
    lines: dict[str, dict[str, Any]] = {}
    for row in keisei.get("lines") or []:
        if not isinstance(row, dict):
            continue
        railway_id = str(row.get("id") or "")
        raw_names = [normalize_name(name) for name in row.get("stations") or []]
        station_ids = [station_by_name.get(name, "") for name in raw_names]
        if not railway_id or not raw_names or any(not station_id for station_id in station_ids):
            missing = [name for name, station_id in zip(raw_names, station_ids) if not station_id]
            raise RuntimeError(f"topology station mapping failed for {railway_id}: {missing}")
        lines[railway_id] = {
            "id": railway_id,
            "name": str(row.get("name") or railway_id),
            "names": raw_names,
            "stations": station_ids,
            "order": {station_id: index for index, station_id in enumerate(station_ids)},
        }
    if len(lines) != 8:
        raise RuntimeError(f"expected 8 Keisei railway lines, found {len(lines)}")
    return lines


def pair_candidates(first: str, second: str, lines: dict[str, dict[str, Any]]) -> list[str]:
    candidates: list[str] = []
    for railway_id, line in lines.items():
        order = line["order"]
        if first in order and second in order and order[first] != order[second]:
            candidates.append(railway_id)
    return candidates


def choose_pair_lines(candidate_rows: list[list[str]]) -> list[str | None]:
    """Choose ambiguous shared-track pairs while minimizing railway changes."""
    result: list[str | None] = [None] * len(candidate_rows)
    # First lock unambiguous pairs.
    for index, candidates in enumerate(candidate_rows):
        if len(candidates) == 1:
            result[index] = candidates[0]
    # Propagate a neighbouring known railway into ambiguous pairs.
    changed = True
    while changed:
        changed = False
        for index, candidates in enumerate(candidate_rows):
            if result[index] is not None or not candidates:
                continue
            neighbours = []
            if index > 0 and result[index - 1] in candidates:
                neighbours.append(result[index - 1])
            if index + 1 < len(result) and result[index + 1] in candidates:
                neighbours.append(result[index + 1])
            neighbours = [value for value in neighbours if value]
            if neighbours and all(value == neighbours[0] for value in neighbours):
                result[index] = neighbours[0]
                changed = True
    # A remaining ambiguous pair is normally the shared Airport T2/T1 edge.
    # Prefer Narita Sky Access only when an adjacent pair proves that path;
    # otherwise Main is the conservative physical-line default.
    for index, candidates in enumerate(candidate_rows):
        if result[index] is None and candidates:
            if "odpt.Railway:Keisei.Main" in candidates:
                result[index] = "odpt.Railway:Keisei.Main"
            else:
                result[index] = candidates[0]
    return result


def compact_line(railway_id: str, segments: list[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    station_values: list[str] = []
    station_indexes: dict[str, int] = {}
    calendar_values: list[str] = []
    calendar_indexes: dict[str, int] = {}
    type_values: list[str] = []
    type_indexes: dict[str, int] = {}
    trips: list[list[Any]] = []
    connections = 0

    def idx(value: str, values: list[str], indexes: dict[str, int]) -> int:
        if value not in indexes:
            indexes[value] = len(values)
            values.append(value)
        return indexes[value]

    for segment in segments:
        stops: list[list[int | None]] = []
        previous_minute: int | None = None
        for row in segment["stops"]:
            arrival = monotonic_time(row.get("arrival"), previous_minute)
            departure = monotonic_time(row.get("departure"), arrival if arrival is not None else previous_minute)
            effective = departure if departure is not None else arrival
            if effective is not None:
                previous_minute = effective
            station_index = idx(row["stationId"], station_values, station_indexes)
            stops.append([station_index, arrival, departure])
        if len(stops) < 2:
            continue
        usable = sum(
            1
            for current, following in zip(stops, stops[1:])
            if (current[2] if current[2] is not None else current[1]) is not None
            and (following[1] if following[1] is not None else following[2]) is not None
        )
        if usable < 1:
            continue
        calendar_index = idx(str(segment["calendar"]), calendar_values, calendar_indexes)
        type_index = idx(str(segment.get("trainType") or ""), type_values, type_indexes)
        trips.append([calendar_index, type_index, str(segment.get("trainNumber") or ""), stops])
        connections += usable

    return {
        "version": 1,
        "railway": railway_id,
        "timeBasis": "train-timetable",
        "source": "Keisei official timetable / keisei.ekitan.com",
        "stations": station_values,
        "calendars": calendar_values,
        "trainTypes": type_values,
        "trips": trips,
    }, connections


def main() -> int:
    if not DETAILS_PATH.exists():
        raise RuntimeError("official-train-details.json is missing; finish the collector first")
    details = load_json(DETAILS_PATH)
    entities = load_json(ENTITIES_PATH)
    topology = load_json(TOPOLOGY_PATH)
    if not isinstance(details, dict) or not isinstance(details.get("trains"), list):
        raise RuntimeError("invalid Keisei official train detail snapshot")
    station_by_name, names_by_id = build_station_maps(entities)
    lines = build_lines(topology, station_by_name)

    segments_by_line: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmapped_stops: Counter[str] = Counter()
    cross_line_pairs: Counter[tuple[str, str]] = Counter()
    mapped_stop_rows = 0
    source_trains_with_keisei_segment = 0

    for train in details["trains"]:
        if not isinstance(train, dict):
            continue
        mapped: list[dict[str, Any]] = []
        for stop in train.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            raw_name = normalize_name(stop.get("station"))
            station_id = station_by_name.get(raw_name)
            if not station_id:
                # Through services may start/end on Toei/Keikyu/etc. Those rows
                # are intentionally kept in the source snapshot but excluded
                # from the Keisei-only app files.
                unmapped_stops[raw_name] += 1
                mapped.append({"stationId": None, "name": raw_name, "arrival": stop.get("arrival"), "departure": stop.get("departure")})
                continue
            mapped_stop_rows += 1
            mapped.append({"stationId": station_id, "name": raw_name, "arrival": stop.get("arrival"), "departure": stop.get("departure")})

        # Work on each contiguous Keisei block separately so external through
        # portions cannot create false Keisei edges.
        blocks: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for row in mapped:
            if row["stationId"]:
                current.append(row)
            else:
                if len(current) >= 2:
                    blocks.append(current)
                current = []
        if len(current) >= 2:
            blocks.append(current)

        train_had_segment = False
        for block in blocks:
            candidates = [pair_candidates(block[i]["stationId"], block[i + 1]["stationId"], lines) for i in range(len(block) - 1)]
            chosen = choose_pair_lines(candidates)
            for i, railway_id in enumerate(chosen):
                if railway_id is None:
                    cross_line_pairs[(block[i]["name"], block[i + 1]["name"])] += 1

            start = 0
            while start < len(chosen):
                railway_id = chosen[start]
                if railway_id is None:
                    start += 1
                    continue
                end = start + 1
                while end < len(chosen) and chosen[end] == railway_id:
                    end += 1
                rows = block[start : end + 1]
                if len(rows) >= 2:
                    segments_by_line[railway_id].append({
                        "calendar": str(train.get("calendar") or ""),
                        "trainType": str(train.get("trainType") or ""),
                        "trainNumber": train_number(train.get("sourceTrainId")),
                        "sourceTrainId": str(train.get("sourceTrainId") or ""),
                        "stops": rows,
                    })
                    train_had_segment = True
                start = end
        if train_had_segment:
            source_trains_with_keisei_segment += 1

    TIMETABLE_DIR.mkdir(parents=True, exist_ok=True)
    line_index: dict[str, Any] = {}
    line_report: dict[str, Any] = {}
    total_connections = 0
    total_trips = 0
    filenames = {
        "odpt.Railway:Keisei.Main": "official-main.json",
        "odpt.Railway:Keisei.Oshiage": "official-oshiage.json",
        "odpt.Railway:Keisei.Kanamachi": "official-kanamachi.json",
        "odpt.Railway:Keisei.Chiba": "official-chiba.json",
        "odpt.Railway:Keisei.Chihara": "official-chihara.json",
        "odpt.Railway:Keisei.HigashiNarita": "official-higashinarita.json",
        "odpt.Railway:Keisei.NaritaSkyAccess": "official-narita-sky-access.json",
        "odpt.Railway:Keisei.Matsudo": "official-matsudo.json",
    }
    for railway_id, line in lines.items():
        compact, connections = compact_line(railway_id, segments_by_line.get(railway_id, []))
        filename = filenames[railway_id]
        dump_json(TIMETABLE_DIR / filename, compact)
        trips = len(compact["trips"])
        total_trips += trips
        total_connections += connections
        line_index[railway_id] = {"file": f"timetables/{filename}", "trips": trips, "connections": connections}
        line_report[railway_id] = {"name": line["name"], "trips": trips, "connections": connections, "stations": len(compact["stations"])}

    dump_json(INDEX_PATH, {"version": 1, "source": "Keisei official timetable / keisei.ekitan.com", "lines": line_index})
    report = {
        "version": 1,
        "builtAt": datetime.now(JST).isoformat(timespec="seconds"),
        "sourceTrainCount": int(details.get("trainCount") or len(details["trains"])),
        "sourceTrainsWithKeiseiSegment": source_trains_with_keisei_segment,
        "mappedStopRows": mapped_stop_rows,
        "unmappedExternalStopRows": sum(unmapped_stops.values()),
        "unmappedExternalStations": dict(unmapped_stops.most_common()),
        "crossLineSkippedPairCount": sum(cross_line_pairs.values()),
        "crossLineSkippedPairs": [
            {"from": pair[0], "to": pair[1], "count": count}
            for pair, count in cross_line_pairs.most_common()
        ],
        "compactTripCount": total_trips,
        "compactConnectionCount": total_connections,
        "lines": line_report,
    }
    dump_json(REPORT_PATH, report)

    manifest = load_json(MANIFEST_PATH)
    operator = manifest.get("operators", {}).get("keisei") if isinstance(manifest, dict) else None
    if isinstance(operator, dict):
        operator.update({
            "timetableStatus": "ok",
            "timetableSource": "Keisei official timetable / keisei.ekitan.com",
            "trainTimetables": report["sourceTrainCount"],
            "timetableLines": len(line_index),
            "timetableConnections": total_connections,
            "inferredConnections": 0,
            "departures": total_connections,
        })
        manifest["fetchedAt"] = datetime.now(JST).isoformat(timespec="seconds")
        notes = manifest.setdefault("notes", [])
        note = "Keisei scheduled train times are built from the official Keisei timetable pages; the complete source snapshot is retained for validation."
        if note not in notes:
            notes.append(note)
        dump_json(MANIFEST_PATH, manifest)

    if report["sourceTrainCount"] != 4659:
        raise RuntimeError(f"expected 4659 source trains, got {report['sourceTrainCount']}")
    if len(line_index) != 8 or any(not row["trips"] for row in line_report.values()):
        raise RuntimeError(f"not all Keisei lines received timetable trips: {line_report}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
