#!/usr/bin/env python3
"""Build an exact Keisei-led network timetable, including verified through service.

The Keisei official one-train pages contain the same physical train beyond
Keisei's own infrastructure (notably the Toei Asakusa and Keikyu networks).
This builder keeps that per-train identity intact. Railway paths are derived
from published station order and verified cross-operator boundaries; train
number or time proximity never establishes identity.

No boundary station is fabricated as a stop. Only stops printed on the
official one-train page are stored.
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
KEISEI_ENTITIES_PATH = ROOT / "entities.json"
TOEI_ENTITIES_PATH = Path("data/transit/toei/entities.json")
KEIKYU_ENTITIES_PATH = Path("data/transit/keikyu/entities.json")
TOPOLOGY_PATH = Path("data/transit-sources/manual-topology.json")
BOUNDARIES_PATH = Path("data/transit-v2/service-boundaries.json")
INDEX_PATH = ROOT / "timetable-index.json"
OUT_PATH = ROOT / "timetables/official-network.json"
REPORT_PATH = ROOT / "official-network-report.json"

TOEI_ALLOWED = {"odpt.Railway:Toei.Asakusa"}
KEIKYU_PREFIX = "odpt.Railway:Keikyu."


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
        "羽田空港第1・第2ターミナル駅": "羽田空港第1・第2ターミナル",
        "羽田空港第3ターミナル駅": "羽田空港第3ターミナル",
        "逗子・葉山駅": "逗子・葉山",
    }
    return aliases.get(text, text)


def localized(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("ja") or value.get("en") or "")
    return ""


def station_title(item: dict[str, Any]) -> str:
    return localized(item.get("odpt:stationTitle")) or str(item.get("dc:title") or "")


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


def railway_operator(railway_id: str) -> str:
    value = str(railway_id or "")
    if ":" in value:
        value = value.split(":", 1)[1]
    return value.split(".", 1)[0]


def entity_station_maps(entities: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    by_name: dict[str, str] = {}
    by_id: dict[str, str] = {}
    for station in entities.get("Station") or []:
        if not isinstance(station, dict):
            continue
        station_id = str(station.get("owl:sameAs") or "")
        name = normalize_name(station_title(station))
        if station_id and name:
            by_name.setdefault(name, station_id)
            by_id[station_id] = name
    return by_name, by_id


def station_order_from_entities(
    entities: dict[str, Any],
    railway_id: str,
    station_names_by_id: dict[str, str],
) -> tuple[list[str], list[str]]:
    railway = next(
        (
            row
            for row in entities.get("Railway") or []
            if isinstance(row, dict) and str(row.get("owl:sameAs") or "") == railway_id
        ),
        None,
    )
    if not railway:
        return [], []
    names: list[str] = []
    ids: list[str] = []
    for row in railway.get("odpt:stationOrder") or []:
        if not isinstance(row, dict):
            continue
        station_id = str(row.get("odpt:station") or "")
        name = station_names_by_id.get(station_id) or normalize_name(localized(row.get("odpt:stationTitle")))
        if station_id and name:
            ids.append(station_id)
            names.append(normalize_name(name))
    return names, ids


def build_lines(
    keisei_entities: dict[str, Any],
    toei_entities: dict[str, Any],
    keikyu_entities: dict[str, Any],
    topology: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    lines: dict[str, dict[str, Any]] = {}
    ids_by_name: dict[str, list[str]] = defaultdict(list)

    keisei_by_name, _ = entity_station_maps(keisei_entities)
    toei_by_name, toei_names_by_id = entity_station_maps(toei_entities)
    keikyu_by_name, keikyu_names_by_id = entity_station_maps(keikyu_entities)

    def register(railway_id: str, names: list[str], ids: list[str]) -> None:
        if not railway_id or not names or len(names) != len(ids):
            return
        mapping: dict[str, str] = {}
        for name, station_id in zip(names, ids):
            if not name or not station_id:
                continue
            mapping[name] = station_id
            if station_id not in ids_by_name[name]:
                ids_by_name[name].append(station_id)
        if len(mapping) < 2:
            return
        lines[railway_id] = {
            "id": railway_id,
            "operator": railway_operator(railway_id),
            "names": names,
            "stationIds": ids,
            "stationIdByName": mapping,
        }

    keisei = topology.get("keisei") if isinstance(topology, dict) else None
    if not isinstance(keisei, dict):
        raise RuntimeError("missing keisei manual topology")
    for line in keisei.get("lines") or []:
        if not isinstance(line, dict):
            continue
        railway_id = str(line.get("id") or "")
        names = [normalize_name(value) for value in line.get("stations") or []]
        ids = [keisei_by_name.get(name, "") for name in names]
        if not railway_id or any(not value for value in ids):
            missing = [name for name, value in zip(names, ids) if not value]
            raise RuntimeError(f"topology mapping failed for {railway_id}: {missing}")
        register(railway_id, names, ids)

    for railway_id in sorted(TOEI_ALLOWED):
        names, ids = station_order_from_entities(toei_entities, railway_id, toei_names_by_id)
        if len(names) < 2:
            raise RuntimeError(f"missing station order for {railway_id}")
        register(railway_id, names, ids)

    keikyu_ids = sorted(
        str(row.get("owl:sameAs") or "")
        for row in keikyu_entities.get("Railway") or []
        if isinstance(row, dict) and str(row.get("owl:sameAs") or "").startswith(KEIKYU_PREFIX)
    )
    if not keikyu_ids:
        raise RuntimeError("no Keikyu railways available")
    for railway_id in keikyu_ids:
        names, ids = station_order_from_entities(keikyu_entities, railway_id, keikyu_names_by_id)
        if len(names) >= 2:
            register(railway_id, names, ids)

    # Preserve all IDs discovered in the entities, including a physical station
    # represented by more than one line-local Station ID.
    for source in (keisei_by_name, toei_by_name, keikyu_by_name):
        for name, station_id in source.items():
            if station_id and station_id not in ids_by_name[name]:
                ids_by_name[name].append(station_id)

    return lines, dict(ids_by_name)


def verified_cross_operator_transitions(boundaries: dict[str, Any]) -> set[tuple[str, str, str]]:
    allowed: set[tuple[str, str, str]] = set()
    for row in boundaries.get("boundaries") or []:
        if not isinstance(row, dict) or row.get("status") != "verified":
            continue
        first = str(row.get("fromRailway") or "")
        second = str(row.get("toRailway") or "")
        station = normalize_name(row.get("station"))
        if not first or not second or not station or first == second:
            continue
        if railway_operator(first) == railway_operator(second):
            continue
        allowed.add((first, second, station))
        if row.get("bidirectional", True):
            allowed.add((second, first, station))
    return allowed


def build_graph(lines: dict[str, dict[str, Any]]) -> tuple[dict[str, list[tuple[str, str]]], dict[tuple[str, str], list[str]]]:
    graph: dict[str, list[tuple[str, str]]] = defaultdict(list)
    common_lines: dict[tuple[str, str], list[str]] = defaultdict(list)
    for railway_id, line in lines.items():
        names = line["names"]
        for first, second in zip(names, names[1:]):
            graph[first].append((second, railway_id))
            graph[second].append((first, railway_id))
        for i, first in enumerate(names):
            for second in names[i + 1 :]:
                common_lines[(first, second)].append(railway_id)
                common_lines[(second, first)].append(railway_id)
    return graph, common_lines


def transition_allowed(
    previous_line: str,
    next_line: str,
    station: str,
    allowed_cross_operator: set[tuple[str, str, str]],
) -> bool:
    if not previous_line or previous_line == next_line:
        return True
    if railway_operator(previous_line) == railway_operator(next_line):
        return True
    return (previous_line, next_line, normalize_name(station)) in allowed_cross_operator


def shortest_line_paths(
    start: str,
    goal: str,
    graph: dict[str, list[tuple[str, str]]],
    common_lines: dict[tuple[str, str], list[str]],
    allowed_cross_operator: set[tuple[str, str, str]],
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
            if not transition_allowed(previous_line, railway, node, allowed_cross_operator):
                continue
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
    """Globally choose pair routes while minimizing route count and changes."""
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
                next_score = (
                    score[0] + len(route),
                    score[1] + max(0, len(route) - 1) + boundary_change,
                )
                key = tuple(route)
                existing = next_states.get(key)
                if existing is None or next_score < existing[0]:
                    next_states[key] = (next_score, chosen + [route])
        states = next_states
        if not states:
            return []
    return min(states.values(), key=lambda item: item[0])[1]


def preferred_station_id(
    name: str,
    stop_index: int,
    selected: list[list[str]],
    lines: dict[str, dict[str, Any]],
    ids_by_name: dict[str, list[str]],
) -> str:
    preferred: list[str] = []
    if stop_index < len(selected):
        preferred.extend(selected[stop_index])
    if stop_index > 0:
        preferred.extend(reversed(selected[stop_index - 1]))
    for railway in preferred:
        station_id = str(lines.get(railway, {}).get("stationIdByName", {}).get(name) or "")
        if station_id:
            return station_id
    values = ids_by_name.get(name) or []
    return str(values[0]) if values else ""


def main() -> int:
    details = load_json(DETAILS_PATH)
    keisei_entities = load_json(KEISEI_ENTITIES_PATH)
    toei_entities = load_json(TOEI_ENTITIES_PATH)
    keikyu_entities = load_json(KEIKYU_ENTITIES_PATH)
    topology = load_json(TOPOLOGY_PATH)
    boundaries = load_json(BOUNDARIES_PATH)
    if not isinstance(details, dict) or not isinstance(details.get("trains"), list):
        raise RuntimeError("invalid official Keisei train details")

    lines, ids_by_name = build_lines(keisei_entities, toei_entities, keikyu_entities, topology)
    graph, common_lines = build_graph(lines)
    allowed_cross_operator = verified_cross_operator_transitions(boundaries)

    required_boundaries = {
        ("odpt.Railway:Keisei.Oshiage", "odpt.Railway:Toei.Asakusa", "押上"),
        ("odpt.Railway:Toei.Asakusa", "odpt.Railway:Keikyu.Main", "泉岳寺"),
    }
    for boundary in required_boundaries:
        if boundary not in allowed_cross_operator:
            raise RuntimeError(f"required verified through boundary is missing: {boundary}")

    railway_values = list(lines)
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
    crossing_counts: Counter[tuple[str, str]] = Counter()
    unsupported_stop_rows: Counter[str] = Counter()

    supported_names = set(ids_by_name)

    for train in details["trains"]:
        if not isinstance(train, dict):
            continue
        observed: list[dict[str, Any]] = []
        previous_minute: int | None = None
        for stop in train.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            name = normalize_name(stop.get("station"))
            arrival = monotonic(stop.get("arrival"), previous_minute)
            departure = monotonic(stop.get("departure"), arrival if arrival is not None else previous_minute)
            effective = departure if departure is not None else arrival
            if effective is not None:
                previous_minute = effective
            if name not in supported_names:
                if name:
                    unsupported_stop_rows[name] += 1
                continue
            observed.append({"name": name, "arrival": arrival, "departure": departure})

        if len(observed) < 2:
            skipped_under_two += 1
            continue

        option_rows: list[list[list[str]]] = []
        unresolved = False
        for first, second in zip(observed, observed[1:]):
            options = shortest_line_paths(
                first["name"],
                second["name"],
                graph,
                common_lines,
                allowed_cross_operator,
            )
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

        stop_rows: list[list[int | None]] = []
        for stop_index, row in enumerate(observed):
            station_id = preferred_station_id(
                row["name"],
                stop_index,
                selected,
                lines,
                ids_by_name,
            )
            if not station_id:
                raise RuntimeError(f"no station ID for mapped station {row['name']}")
            stop_rows.append(
                [
                    idx(station_id, station_values, station_indexes),
                    row["arrival"],
                    row["departure"],
                ]
            )

        links = [[railway_indexes[value] for value in route] for route in selected]
        route_signature = tuple(collapse([value for route in selected for value in route]))
        route_counts[route_signature] += 1
        for first, second in zip(route_signature, route_signature[1:]):
            if first != second:
                crossing_counts[(first, second)] += 1

        calendar_index = idx(str(train.get("calendar") or ""), calendar_values, calendar_indexes)
        type_index = idx(str(train.get("trainType") or ""), type_values, type_indexes)
        trips.append(
            [
                calendar_index,
                type_index,
                train_number(train.get("sourceTrainId")),
                stop_rows,
                links,
            ]
        )

    payload = {
        "version": 2,
        "timeBasis": "train-timetable-network",
        "identityBasis": "Keisei official one-train timetable page",
        "identityPolicy": {
            "officialTrainPageEstablishesIdentity": True,
            "trainNumberAloneMayEstablishIdentity": False,
            "timeProximityAloneMayEstablishIdentity": False,
            "crossOperatorTransitionRequiresVerifiedBoundary": True,
        },
        "source": "Keisei official one-train timetable / keisei.ekitan.com",
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
        "id": "keisei-official-through-network",
        "file": "timetables/official-network.json",
        "railways": railway_values,
        "trips": len(trips),
        "timeBasis": "train-timetable-network",
        "identityBasis": "official-one-train-page",
    }
    dump_json(INDEX_PATH, index)

    report = {
        "version": 2,
        "sourceTrainCount": int(details.get("trainCount") or len(details["trains"])),
        "networkTripCount": len(trips),
        "skippedUnderTwoMappedStops": skipped_under_two,
        "unresolvedPairCount": sum(unresolved_pairs.values()),
        "unresolvedPairs": [
            {"from": pair[0], "to": pair[1], "count": count}
            for pair, count in unresolved_pairs.most_common()
        ],
        "supportedRailwayCount": len(railway_values),
        "supportedRailways": railway_values,
        "unsupportedStopRows": sum(unsupported_stop_rows.values()),
        "unsupportedStations": dict(unsupported_stop_rows.most_common()),
        "crossOperatorTransitions": [
            {"fromRailway": first, "toRailway": second, "trains": count}
            for (first, second), count in crossing_counts.most_common()
            if railway_operator(first) != railway_operator(second)
        ],
        "routeSignatures": [
            {"railways": list(signature), "trains": count}
            for signature, count in route_counts.most_common()
        ],
        "identityPolicy": payload["identityPolicy"],
    }
    dump_json(REPORT_PATH, report)

    if not 3000 <= report["sourceTrainCount"] <= 7000:
        raise RuntimeError(f"unexpected Keisei source train count: {report['sourceTrainCount']}")
    if report["unresolvedPairCount"]:
        raise RuntimeError(f"unresolved supported topology pairs remain: {report['unresolvedPairs'][:10]}")
    if len(trips) + skipped_under_two != report["sourceTrainCount"]:
        raise RuntimeError(
            f"network trip coverage mismatch: trips={len(trips)} "
            f"skipped={skipped_under_two} source={report['sourceTrainCount']}"
        )

    crossing_pairs = {
        (row["fromRailway"], row["toRailway"]): int(row["trains"])
        for row in report["crossOperatorTransitions"]
    }
    if not (
        crossing_pairs.get(("odpt.Railway:Keisei.Oshiage", "odpt.Railway:Toei.Asakusa"), 0)
        or crossing_pairs.get(("odpt.Railway:Toei.Asakusa", "odpt.Railway:Keisei.Oshiage"), 0)
    ):
        raise RuntimeError("no Keisei/Toei exact through journeys were materialized")
    if not (
        crossing_pairs.get(("odpt.Railway:Toei.Asakusa", "odpt.Railway:Keikyu.Main"), 0)
        or crossing_pairs.get(("odpt.Railway:Keikyu.Main", "odpt.Railway:Toei.Asakusa"), 0)
    ):
        raise RuntimeError("no Toei/Keikyu exact through journeys were materialized")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
