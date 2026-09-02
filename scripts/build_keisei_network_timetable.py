#!/usr/bin/env python3
"""Build a network-wide exact Keisei timetable for through services.

Line-specific app timetables are ideal for ordinary routing, but an express can
cross a line boundary without stopping at the boundary station.  Inventing that
station as a stop would create false boarding/alighting opportunities.  This
file keeps only observed Keisei stops while recording the topology railway path
between consecutive observed stops, so the browser can verify a genuine
through train without fabricating a stop.
"""

from __future__ import annotations

import heapq
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path("data/transit/keisei")
DETAILS_PATH = ROOT / "official-train-details.json"
ENTITIES_PATH = ROOT / "entities.json"
TOPOLOGY_PATH = Path("data/transit-sources/manual-topology.json")
INDEX_PATH = ROOT / "timetable-index.json"
OUT_PATH = ROOT / "timetables/official-network.json"
REPORT_PATH = ROOT / "official-network-report.json"


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
        "新鎌ケ谷": "新鎌ヶ谷",
    }
    return aliases.get(text, text)


def localized_title(item: dict[str, Any]) -> str:
    value = item.get("odpt:stationTitle")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("ja") or value.get("en") or "")
    return str(item.get("dc:title") or "")


def clock_minutes(value: Any) -> int | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", str(value or "").strip())
    if not match:
        return None
    hour, minute = map(int, match.groups())
    if minute > 59:
        return None
    if hour < 3:
        hour += 24
    return hour * 60 + minute


def monotonic(value: Any, previous: int | None) -> int | None:
    minute = clock_minutes(value)
    if minute is None:
        return None
    if previous is not None:
        while minute + 360 < previous:
            minute += 1440
    return minute


def train_number(source_id: Any) -> str:
    text = str(source_id or "")
    return text.rsplit("-", 1)[-1] if "-" in text else text


def collapse(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and (not result or result[-1] != value):
            result.append(value)
    return result


def build_topology(entities: dict[str, Any], topology: dict[str, Any]):
    station_by_name: dict[str, str] = {}
    for station in entities.get("Station") or []:
        if not isinstance(station, dict):
            continue
        station_id = str(station.get("owl:sameAs") or "")
        name = normalize_name(localized_title(station))
        if station_id and name:
            station_by_name[name] = station_id

    keisei = topology.get("keisei") if isinstance(topology, dict) else None
    if not isinstance(keisei, dict):
        raise RuntimeError("missing keisei manual topology")

    railway_ids: list[str] = []
    graph: dict[str, list[tuple[str, str]]] = defaultdict(list)
    common_lines: dict[tuple[str, str], list[str]] = defaultdict(list)
    line_station_ids: dict[str, list[str]] = {}
    for line in keisei.get("lines") or []:
        railway_id = str(line.get("id") or "")
        names = [normalize_name(value) for value in line.get("stations") or []]
        ids = [station_by_name.get(name, "") for name in names]
        if not railway_id or any(not value for value in ids):
            missing = [name for name, value in zip(names, ids) if not value]
            raise RuntimeError(f"topology mapping failed for {railway_id}: {missing}")
        railway_ids.append(railway_id)
        line_station_ids[railway_id] = ids
        for first, second in zip(ids, ids[1:]):
            graph[first].append((second, railway_id))
            graph[second].append((first, railway_id))
        for i, first in enumerate(ids):
            for second in ids[i + 1 :]:
                common_lines[(first, second)].append(railway_id)
                common_lines[(second, first)].append(railway_id)
    return station_by_name, railway_ids, graph, common_lines


def shortest_line_paths(
    start: str,
    goal: str,
    graph: dict[str, list[tuple[str, str]]],
    common_lines: dict[tuple[str, str], list[str]],
    limit: int = 4,
) -> list[list[str]]:
    direct = common_lines.get((start, goal)) or []
    if direct:
        return [[line] for line in direct]

    queue: list[tuple[int, int, str, str, tuple[str, ...]]] = []
    heapq.heappush(queue, (0, 0, start, "", tuple()))
    best: dict[tuple[str, str], tuple[int, int]] = {(start, ""): (0, 0)}
    found_cost: tuple[int, int] | None = None
    results: list[list[str]] = []
    while queue:
        edges, changes, node, previous_line, route = heapq.heappop(queue)
        cost = (edges, changes)
        if found_cost is not None and cost > found_cost:
            break
        if node == goal:
            found_cost = cost
            collapsed = collapse(list(route))
            if collapsed not in results:
                results.append(collapsed)
            if len(results) >= limit:
                break
            continue
        for neighbour, railway in graph.get(node, []):
            next_edges = edges + 1
            next_changes = changes + (1 if previous_line and previous_line != railway else 0)
            key = (neighbour, railway)
            next_cost = (next_edges, next_changes)
            prior = best.get(key)
            if prior is not None and prior < next_cost:
                continue
            best[key] = next_cost
            heapq.heappush(queue, (next_edges, next_changes, neighbour, railway, route + (railway,)))
    return results


def choose_link_routes(options: list[list[list[str]]]) -> list[list[str]]:
    """Global DP chooses pair routes that minimize line changes across a train."""
    if not options:
        return []
    states: dict[tuple[str, ...], tuple[tuple[int, int], list[list[str]]]] = {}
    for route in options[0]:
        key = tuple(route)
        states[key] = ((len(route), max(0, len(route) - 1)), [route])
    for pair_options in options[1:]:
        next_states: dict[tuple[str, ...], tuple[tuple[int, int], list[list[str]]]] = {}
        for previous_route, (score, chosen) in states.items():
            for route in pair_options:
                boundary_change = 1 if previous_route and route and previous_route[-1] != route[0] else 0
                next_score = (score[0] + len(route), score[1] + max(0, len(route) - 1) + boundary_change)
                key = tuple(route)
                existing = next_states.get(key)
                if existing is None or next_score < existing[0]:
                    next_states[key] = (next_score, chosen + [route])
        states = next_states
        if not states:
            return []
    return min(states.values(), key=lambda item: item[0])[1]


def main() -> int:
    details = load_json(DETAILS_PATH)
    entities = load_json(ENTITIES_PATH)
    topology = load_json(TOPOLOGY_PATH)
    if not isinstance(details, dict) or not isinstance(details.get("trains"), list):
        raise RuntimeError("invalid official Keisei train details")

    station_by_name, railway_values, graph, common_lines = build_topology(entities, topology)
    railway_indexes = {value: index for index, value in enumerate(railway_values)}
    station_values: list[str] = []
    station_indexes: dict[str, int] = {}
    calendar_values: list[str] = []
    calendar_indexes: dict[str, int] = {}
    type_values: list[str] = []
    type_indexes: dict[str, int] = {}

    def idx(value: str, values: list[str], indexes: dict[str, int]) -> int:
        if value not in indexes:
            indexes[value] = len(values)
            values.append(value)
        return indexes[value]

    trips: list[list[Any]] = []
    skipped_under_two = 0
    unresolved_pairs: Counter[tuple[str, str]] = Counter()
    route_counts: Counter[tuple[str, ...]] = Counter()

    for train in details["trains"]:
        if not isinstance(train, dict):
            continue
        observed: list[dict[str, Any]] = []
        previous_minute: int | None = None
        for stop in train.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            name = normalize_name(stop.get("station"))
            station_id = station_by_name.get(name)
            arrival = monotonic(stop.get("arrival"), previous_minute)
            departure = monotonic(stop.get("departure"), arrival if arrival is not None else previous_minute)
            effective = departure if departure is not None else arrival
            if effective is not None:
                previous_minute = effective
            if station_id:
                observed.append({"name": name, "station": station_id, "arrival": arrival, "departure": departure})
        if len(observed) < 2:
            skipped_under_two += 1
            continue

        option_rows: list[list[list[str]]] = []
        unresolved = False
        for first, second in zip(observed, observed[1:]):
            options = shortest_line_paths(first["station"], second["station"], graph, common_lines)
            if not options:
                unresolved_pairs[(first["name"], second["name"])] += 1
                unresolved = True
                break
            option_rows.append(options)
        if unresolved:
            continue
        selected = choose_link_routes(option_rows)
        if len(selected) != len(observed) - 1:
            raise RuntimeError("network route DP returned an invalid link count")

        stops = [
            [idx(row["station"], station_values, station_indexes), row["arrival"], row["departure"]]
            for row in observed
        ]
        links = [[railway_indexes[value] for value in route] for route in selected]
        route_signature = tuple(collapse([value for route in selected for value in route]))
        route_counts[route_signature] += 1
        calendar_index = idx(str(train.get("calendar") or ""), calendar_values, calendar_indexes)
        type_index = idx(str(train.get("trainType") or ""), type_values, type_indexes)
        trips.append([calendar_index, type_index, train_number(train.get("sourceTrainId")), stops, links])

    payload = {
        "version": 1,
        "timeBasis": "train-timetable-network",
        "source": "Keisei official timetable / keisei.ekitan.com",
        "stations": station_values,
        "calendars": calendar_values,
        "trainTypes": type_values,
        "railways": railway_values,
        "trips": trips,
    }
    dump_json(OUT_PATH, payload)

    index = load_json(INDEX_PATH)
    if not isinstance(index, dict):
        raise RuntimeError("invalid timetable-index.json")
    index["network"] = {
        "id": "keisei-official-network",
        "file": "timetables/official-network.json",
        "railways": railway_values,
        "trips": len(trips),
        "timeBasis": "train-timetable-network",
    }
    dump_json(INDEX_PATH, index)

    report = {
        "version": 1,
        "sourceTrainCount": int(details.get("trainCount") or len(details["trains"])),
        "networkTripCount": len(trips),
        "skippedUnderTwoMappedStops": skipped_under_two,
        "unresolvedPairCount": sum(unresolved_pairs.values()),
        "unresolvedPairs": [
            {"from": pair[0], "to": pair[1], "count": count}
            for pair, count in unresolved_pairs.most_common()
        ],
        "routeSignatures": [
            {"railways": list(signature), "trains": count}
            for signature, count in route_counts.most_common()
        ],
    }
    dump_json(REPORT_PATH, report)

    if report["sourceTrainCount"] != 4659:
        raise RuntimeError(f"expected 4659 source trains, got {report['sourceTrainCount']}")
    if report["unresolvedPairCount"]:
        raise RuntimeError(f"unresolved Keisei topology pairs remain: {report['unresolvedPairs'][:10]}")
    if len(trips) < 4500:
        raise RuntimeError(f"unexpectedly few network trips: {len(trips)}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
