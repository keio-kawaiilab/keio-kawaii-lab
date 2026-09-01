#!/usr/bin/env python3
"""Import ODPT railway timetable data into compact app-facing JSON files.

The script intentionally does not scrape railway websites. It uses the official
ODPT API and expects the access token in ODPT_API_KEY.

JR East data is imported from the Challenge 2026 feed. It covers only part of
the conventional-line network around the Tokyo area and does not include the
Shinkansen. Set ALLOW_JR_EAST_CHALLENGE_DATA=0 to pause the import if the
challenge feed or its applicable terms change.
"""

from __future__ import annotations

import json
import hashlib
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.odpt.org/api/v4"
CHALLENGE_BASE_URL = "https://api-challenge.odpt.org/api/v4"
OUT_ROOT = Path("data/transit")
MANUAL_TOPOLOGY_PATH = Path("data/transit-sources/manual-topology.json")
JST = timezone(timedelta(hours=9))

# The first-version scope discussed for the site. Aliases are used to discover
# the actual ODPT operator URI from odpt:Operator instead of hard-coding it.
TARGETS = {
    "jr-east": {
        "label": "JR東日本",
        "aliases": ["JR東日本", "東日本旅客鉄道", "JR East", "East Japan Railway"],
        "fallback": "odpt.Operator:JR-East",
        "license": "challenge-2026",
        "restricted": True,
    },
    "tokyo-metro": {
        "label": "東京メトロ",
        "aliases": ["東京メトロ", "Tokyo Metro"],
        "fallback": "odpt.Operator:TokyoMetro",
        "license": "basic",
    },
    "toei": {
        "label": "東京都交通局",
        "aliases": ["東京都交通局", "Toei", "Bureau of Transportation, Tokyo Metropolitan Government"],
        "fallback": "odpt.Operator:Toei",
        "license": "basic",
    },
    "tobu": {
        "label": "東武鉄道",
        "aliases": ["東武鉄道", "Tobu"],
        "fallback": "odpt.Operator:Tobu",
        "license": "challenge-2026",
    },
    "seibu": {
        "label": "西武鉄道",
        "aliases": ["西武鉄道", "Seibu"],
        "fallback": "odpt.Operator:Seibu",
        "license": "challenge-2026",
    },
    "keisei": {
        "label": "京成電鉄",
        "aliases": ["京成電鉄", "Keisei"],
        "fallback": "odpt.Operator:Keisei",
        "license": "unknown",
    },
    "keio": {
        "label": "京王電鉄",
        "aliases": ["京王電鉄", "Keio"],
        "fallback": "odpt.Operator:Keio",
        "license": "challenge-2026",
    },
    "odakyu": {
        "label": "小田急電鉄",
        "aliases": ["小田急電鉄", "Odakyu"],
        "fallback": "odpt.Operator:Odakyu",
        "license": "challenge-2026",
    },
    "tokyu": {
        "label": "東急電鉄",
        "aliases": ["東急電鉄", "Tokyu"],
        "fallback": "odpt.Operator:Tokyu",
        "license": "challenge-2026",
    },
    "keikyu": {
        "label": "京急電鉄",
        "aliases": ["京急電鉄", "京浜急行電鉄", "Keikyu"],
        "fallback": "odpt.Operator:Keikyu",
        "license": "challenge-2026",
    },
    "sotetsu": {
        "label": "相模鉄道",
        "aliases": ["相模鉄道", "相鉄", "Sotetsu", "Sagami Railway"],
        "fallback": "odpt.Operator:Sotetsu",
        "license": "challenge-2026",
    },
    "tx": {
        "label": "つくばエクスプレス",
        "aliases": ["首都圏新都市鉄道", "つくばエクスプレス", "Metropolitan Intercity Railway", "Tsukuba Express"],
        "fallback": "odpt.Operator:MIR",
        "license": "basic",
    },
    "rinkai": {
        "label": "りんかい線",
        "aliases": ["東京臨海高速鉄道", "りんかい線", "Tokyo Waterfront Area Rapid Transit", "TWR Rinkai"],
        "fallback": "odpt.Operator:TWR",
        "license": "basic",
    },
    "yurikamome": {
        "label": "ゆりかもめ",
        "aliases": ["ゆりかもめ", "Yurikamome"],
        "fallback": "odpt.Operator:Yurikamome",
        "license": "basic",
    },
    "yokohama-subway": {
        "label": "横浜市営地下鉄",
        "aliases": ["横浜市交通局", "横浜市営地下鉄", "Transportation Bureau, City of Yokohama", "Yokohama Municipal"],
        "fallback": "odpt.Operator:YokohamaMunicipal",
        "license": "basic",
    },
    "yokohama-minatomirai": {
        "label": "横浜高速鉄道（みなとみらい線）",
        "aliases": ["横浜高速鉄道", "みなとみらい線", "Yokohama Minatomirai Railway"],
        "fallback": "manual.Operator:YokohamaMinatomirai",
        "license": "official-site-reference",
        "manual_only": True,
    },
}

ENTITY_TYPES = ["odpt:Station", "odpt:Railway", "odpt:TrainType"]
MIN_REQUEST_INTERVAL = float(os.environ.get("ODPT_REQUEST_INTERVAL_SECONDS", "0.75"))
_last_request_at = 0.0


def jr_east_import_enabled() -> bool:
    """Include JR East unless an operator explicitly pauses the limited feed."""
    value = os.environ.get("ALLOW_JR_EAST_CHALLENGE_DATA", "").strip().lower()
    return value not in {"0", "false", "no", "off"}


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def title_values(obj: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("dc:title", "odpt:operatorTitle", "odpt:stationTitle", "odpt:railwayTitle", "odpt:trainTypeTitle", "odpt:railDirectionTitle"):
        val = obj.get(key)
        if isinstance(val, str):
            values.append(val)
        elif isinstance(val, dict):
            values.extend(str(v) for v in val.values() if v)
    return values


def api_get(
    session: requests.Session,
    rdf_type: str,
    key: str,
    operator: str | None = None,
    base_url: str = BASE_URL,
    extra_params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    global _last_request_at
    url = f"{base_url}/{rdf_type}"
    params = {"acl:consumerKey": key}
    if operator:
        params["odpt:operator"] = operator
    if extra_params:
        params.update(extra_params)
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            wait_for_slot = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
            if wait_for_slot > 0:
                time.sleep(wait_for_slot)
            response = session.get(url, params=params, timeout=(15, 180))
            _last_request_at = time.monotonic()
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = max(float(retry_after), min(60.0, 3.0 * (2 ** attempt)))
                except ValueError:
                    delay = min(60.0, 3.0 * (2 ** attempt))
                print(f"ODPT rate limit for {rdf_type}; retrying in {delay:.0f}s", file=sys.stderr)
                last_error = RuntimeError(f"ODPT rate limit persisted for {rdf_type}")
                time.sleep(delay)
                continue
            if response.status_code == 403:
                print(f"ODPT access denied for {base_url} / {rdf_type} / {operator}", file=sys.stderr)
                return []
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise ValueError(f"Unexpected {rdf_type} response: {type(data).__name__}")
            if operator:
                with_operator = [item for item in data if item.get("odpt:operator")]
                if with_operator:
                    data = [
                        item for item in data
                        if operator in (
                            item.get("odpt:operator")
                            if isinstance(item.get("odpt:operator"), list)
                            else [item.get("odpt:operator")]
                        )
                    ]
            return data
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < 5:
                time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"ODPT request failed for {rdf_type} / {operator}: {last_error}")


def api_base_for(config: dict[str, Any]) -> str:
    """Route challenge-only operators to the Challenge 2026 API host."""
    return CHALLENGE_BASE_URL if config.get("license") == "challenge-2026" else BASE_URL


def api_key_for(config: dict[str, Any], standard_key: str, challenge_key: str) -> str:
    return challenge_key if config.get("license") == "challenge-2026" else standard_key


def localized_title(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("ja") or value.get("en") or "")
    return ""


def load_manual_topology() -> dict[str, Any]:
    if not MANUAL_TOPOLOGY_PATH.exists():
        return {}
    data = json.loads(MANUAL_TOPOLOGY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manual-topology.json must contain an object")
    return data


def merge_manual_topology(
    slug: str,
    operator_uri: str,
    entities: dict[str, list[dict[str, Any]]],
    topology: dict[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    """Merge small, reviewed official-site topology supplements into ODPT data."""
    if not topology:
        return entities

    stations = {
        str(item.get("owl:sameAs")): dict(item)
        for item in entities.get("Station", [])
        if item.get("owl:sameAs")
    }
    railways = {
        str(item.get("owl:sameAs")): dict(item)
        for item in entities.get("Railway", [])
        if item.get("owl:sameAs")
    }
    station_ids_by_name: dict[str, str] = {}
    for station_id, station in stations.items():
        name = localized_title(station, "odpt:stationTitle") or str(station.get("dc:title") or "")
        if name:
            station_ids_by_name[name] = station_id

    railway_ids_by_name: dict[str, str] = {}
    for railway_id, railway in railways.items():
        name = localized_title(railway, "odpt:railwayTitle") or str(railway.get("dc:title") or "")
        if name:
            railway_ids_by_name[name] = railway_id

    configured_lines: list[tuple[str, dict[str, Any]]] = []
    for line in topology.get("lines") or []:
        if not isinstance(line, dict) or not line.get("name") or not line.get("stations"):
            continue
        name = str(line["name"])
        railway_id = str(line.get("id") or railway_ids_by_name.get(name) or f"manual.Railway:{slug}.{name}")
        configured_lines.append((railway_id, line))

    station_railways: dict[str, list[str]] = defaultdict(list)
    for railway_id, line in configured_lines:
        for name in line["stations"]:
            station_railways[str(name)].append(railway_id)

    station_meta = topology.get("stationMetadata") or {}
    for name, railway_ids in station_railways.items():
        station_id = station_ids_by_name.get(name) or f"manual.Station:{slug}.{name}"
        existing = stations.get(station_id, {})
        meta = station_meta.get(name) if isinstance(station_meta, dict) else None
        meta = meta if isinstance(meta, dict) else {}
        railway_value: str | list[str] = railway_ids[0] if len(railway_ids) == 1 else railway_ids
        station = {
            **existing,
            "dc:title": name,
            "owl:sameAs": station_id,
            "odpt:operator": operator_uri,
            "odpt:railway": railway_value,
            "odpt:stationTitle": {"ja": name},
        }
        if "lat" in meta and "lon" in meta:
            station["geo:lat"] = meta["lat"]
            station["geo:long"] = meta["lon"]
        if meta.get("connectingStation"):
            station["odpt:connectingStation"] = meta["connectingStation"]
        if meta.get("connectingRailway"):
            station["odpt:connectingRailway"] = meta["connectingRailway"]
        stations[station_id] = station
        station_ids_by_name[name] = station_id

    # ODPT sometimes exposes one physical station as separate line-specific
    # records. A reviewed supplement uses one shared node, so remove the stale
    # duplicates to keep station-name resolution unambiguous.
    for station_id, station in list(stations.items()):
        name = localized_title(station, "odpt:stationTitle") or str(station.get("dc:title") or "")
        if name in station_railways and station_id != station_ids_by_name[name]:
            del stations[station_id]

    for railway_id, line in configured_lines:
        name = str(line["name"])
        existing = railways.get(railway_id, {})
        railways[railway_id] = {
            **existing,
            "dc:title": name,
            "owl:sameAs": railway_id,
            "odpt:operator": operator_uri,
            "odpt:railwayTitle": {"ja": name},
            "odpt:color": str(line.get("color") or existing.get("odpt:color") or ""),
            "odpt:stationOrder": [
                {"odpt:index": index, "odpt:station": station_ids_by_name[str(name)]}
                for index, name in enumerate(line["stations"], start=1)
            ],
        }

    return {**entities, "Station": list(stations.values()), "Railway": list(railways.values())}


def discover_operators(session: requests.Session, key: str) -> tuple[dict[str, str], list[dict[str, Any]]]:
    operators = api_get(session, "odpt:Operator", key)
    operator_uris = {
        item.get("owl:sameAs")
        for item in operators
        if isinstance(item.get("owl:sameAs"), str)
    }
    found: dict[str, str] = {}
    for slug, config in TARGETS.items():
        fallback = str(config["fallback"])
        if fallback in operator_uris:
            found[slug] = fallback
            continue
        aliases = {" ".join(str(a).casefold().split()) for a in config["aliases"]}
        for item in operators:
            titles = {" ".join(value.casefold().split()) for value in title_values(item)}
            if aliases.intersection(titles):
                uri = item.get("owl:sameAs")
                if isinstance(uri, str):
                    found[slug] = uri
                    break
        if slug not in found:
            # Keep a standards-based fallback so a newly-added operator can be
            # attempted even if its title is not present in the Operator list.
            found[slug] = fallback
    return found, operators


def compact_entity(item: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "owl:sameAs", "dc:title", "dc:date", "odpt:operator", "odpt:railway",
        "odpt:stationTitle", "odpt:railwayTitle", "odpt:trainTypeTitle",
        "odpt:railDirectionTitle", "odpt:stationCode", "odpt:lineCode",
        "odpt:ascendingRailDirection", "odpt:descendingRailDirection",
        "odpt:stationOrder", "geo:lat", "geo:long",
        "odpt:connectingRailway", "odpt:connectingStation", "odpt:color",
    }
    return {k: v for k, v in item.items() if k in keep}


def compact_station_timetable(item: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for row in item.get("odpt:stationTimetableObject") or []:
        if not isinstance(row, dict):
            continue
        out = {}
        for key in (
            "odpt:departureTime", "odpt:arrivalTime", "odpt:destinationStation",
            "odpt:trainType", "odpt:trainNumber", "odpt:train", "odpt:isOrigin",
            "odpt:note", "odpt:platformNumber", "odpt:platformName",
        ):
            if key in row:
                out[key] = row[key]
        rows.append(out)
    return {
        "id": item.get("owl:sameAs"),
        "operator": item.get("odpt:operator"),
        "station": item.get("odpt:station"),
        "railway": item.get("odpt:railway"),
        "direction": item.get("odpt:railDirection"),
        "calendar": item.get("odpt:calendar"),
        "issued": item.get("dct:issued"),
        "updatedAt": item.get("dc:date"),
        "trains": rows,
    }


def compact_train_timetable(item: dict[str, Any]) -> dict[str, Any]:
    stops = []
    for row in item.get("odpt:trainTimetableObject") or []:
        if not isinstance(row, dict):
            continue
        out = {}
        for key in (
            "odpt:index", "odpt:station", "odpt:arrivalStation", "odpt:departureStation",
            "odpt:arrivalTime", "odpt:departureTime",
            "odpt:platformNumber", "odpt:platformName",
        ):
            if key in row:
                out[key] = row[key]
        stops.append(out)
    return {
        "id": item.get("owl:sameAs"),
        "operator": item.get("odpt:operator"),
        "railway": item.get("odpt:railway"),
        "train": item.get("odpt:train"),
        "trainType": item.get("odpt:trainType"),
        "trainNumber": item.get("odpt:trainNumber"),
        "direction": item.get("odpt:railDirection"),
        "calendar": item.get("odpt:calendar"),
        "origin": item.get("odpt:originStation"),
        "destination": item.get("odpt:destinationStation"),
        "stops": stops,
    }


def timetable_import_enabled() -> bool:
    """Import scheduled train times unless an operator explicitly pauses it."""
    value = os.environ.get("ODPT_IMPORT_TIMETABLES", "").strip().lower()
    return value not in {"0", "false", "no", "off"}


def clock_minutes(value: Any) -> int | None:
    """Convert ODPT service-day times such as 24:18 to integer minutes."""
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if hour < 0 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def canonical_station_aliases(
    original_stations: list[dict[str, Any]],
    merged_stations: list[dict[str, Any]],
) -> dict[str, str]:
    """Map line-specific ODPT station IDs to the canonical topology node."""
    canonical_by_name: dict[str, str] = {}
    for station in merged_stations:
        station_id = str(station.get("owl:sameAs") or "")
        name = localized_title(station, "odpt:stationTitle") or str(station.get("dc:title") or "")
        if station_id and name:
            canonical_by_name[name] = station_id

    aliases: dict[str, str] = {}
    for station in original_stations:
        station_id = str(station.get("owl:sameAs") or "")
        name = localized_title(station, "odpt:stationTitle") or str(station.get("dc:title") or "")
        if station_id:
            aliases[station_id] = canonical_by_name.get(name, station_id)
    for station_id in canonical_by_name.values():
        aliases[station_id] = station_id
    return aliases


def compact_line_timetable(
    railway_id: str,
    items: list[dict[str, Any]],
    station_aliases: dict[str, str] | None = None,
) -> tuple[dict[str, Any], int]:
    """Build a compact client-side timetable for one railway."""
    station_aliases = station_aliases or {}
    station_values: list[str] = []
    station_indexes: dict[str, int] = {}
    calendar_values: list[str] = []
    calendar_indexes: dict[str, int] = {}
    train_type_values: list[str] = []
    train_type_indexes: dict[str, int] = {}
    trips: list[list[Any]] = []
    connections = 0

    def index_of(value: str, values: list[str], indexes: dict[str, int]) -> int:
        if value not in indexes:
            indexes[value] = len(values)
            values.append(value)
        return indexes[value]

    for item in items:
        raw_calendars = item.get("odpt:calendar")
        if isinstance(raw_calendars, list):
            calendars = [str(value) for value in raw_calendars if value]
        elif raw_calendars:
            calendars = [str(raw_calendars)]
        else:
            calendars = [""]
        train_type = str(item.get("odpt:trainType") or "")
        train_number = str(item.get("odpt:trainNumber") or "")
        stops: list[list[int | None]] = []

        def add_stop(station_value: Any, arrival: int | None, departure: int | None) -> None:
            original_station = str(station_value or "")
            station_id = station_aliases.get(original_station, original_station)
            if not station_id or (arrival is None and departure is None):
                return
            station_index = index_of(station_id, station_values, station_indexes)
            if stops and stops[-1][0] == station_index:
                if arrival is not None:
                    stops[-1][1] = arrival
                if departure is not None:
                    stops[-1][2] = departure
                return
            stops.append([station_index, arrival, departure])

        for row in item.get("odpt:trainTimetableObject") or []:
            if not isinstance(row, dict):
                continue
            arrival = clock_minutes(row.get("odpt:arrivalTime"))
            departure = clock_minutes(row.get("odpt:departureTime"))
            generic_station = row.get("odpt:station")
            arrival_station = row.get("odpt:arrivalStation") or generic_station
            departure_station = row.get("odpt:departureStation") or generic_station
            if arrival_station and departure_station and str(arrival_station) == str(departure_station):
                add_stop(arrival_station, arrival, departure)
            else:
                add_stop(arrival_station, arrival, None)
                add_stop(departure_station, None, departure)
        if len(stops) < 2:
            continue
        usable_connections = sum(
            1
            for current, following in zip(stops, stops[1:])
            if (current[2] if current[2] is not None else current[1]) is not None
            and (following[1] if following[1] is not None else following[2]) is not None
        )
        if not usable_connections:
            continue
        connections += usable_connections * len(calendars)
        type_index = index_of(train_type, train_type_values, train_type_indexes)
        for calendar in calendars:
            calendar_index = index_of(calendar, calendar_values, calendar_indexes)
            trips.append([calendar_index, type_index, train_number, stops])

    return {
        "version": 1,
        "railway": railway_id,
        "timeBasis": "train-timetable",
        "stations": station_values,
        "calendars": calendar_values,
        "trainTypes": train_type_values,
        "trips": trips,
    }, connections


def compact_station_timetables(
    items: list[dict[str, Any]],
    station_aliases: dict[str, str] | None = None,
    railways: list[dict[str, Any]] | None = None,
) -> dict[str, tuple[dict[str, Any], int, int]]:
    """Build compact departure boards and any joinable trips per line.

    Challenge operators often omit train identifiers and arrival times from
    odpt:StationTimetable. Their exact departures remain useful, but must not
    be presented as a fabricated arrival itinerary. The compact file therefore
    retains station departure boards and only joins trips when ODPT supplies a
    stable train URI or number.
    """
    station_aliases = station_aliases or {}
    grouped: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = defaultdict(dict)
    raw_boards: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in items:
        railway_id = str(item.get("odpt:railway") or "")
        raw_station = str(item.get("odpt:station") or "")
        station_id = station_aliases.get(raw_station, raw_station)
        direction = str(item.get("odpt:railDirection") or "")
        raw_calendars = item.get("odpt:calendar")
        calendars = raw_calendars if isinstance(raw_calendars, list) else [raw_calendars or ""]
        if not railway_id or not station_id:
            continue

        board_departures: list[tuple[int, str]] = []

        for row in item.get("odpt:stationTimetableObject") or []:
            if not isinstance(row, dict):
                continue
            arrival = clock_minutes(row.get("odpt:arrivalTime"))
            departure = clock_minutes(row.get("odpt:departureTime"))
            if arrival is None and departure is None:
                continue
            train_type = str(row.get("odpt:trainType") or "")
            if departure is not None:
                board_departures.append((departure, train_type))
            train_ref = str(row.get("odpt:train") or "")
            train_number = str(row.get("odpt:trainNumber") or "")
            train_key = train_ref or train_number
            if not train_key:
                continue
            for calendar_value in calendars:
                calendar = str(calendar_value or "")
                key = (calendar, direction, train_key)
                trip = grouped[railway_id].setdefault(key, {
                    "calendar": calendar,
                    "trainType": train_type,
                    "trainNumber": train_number,
                    "stops": {},
                })
                if not trip["trainType"] and train_type:
                    trip["trainType"] = train_type
                if not trip["trainNumber"] and train_number:
                    trip["trainNumber"] = train_number
                stop = trip["stops"].setdefault(station_id, [arrival, departure])
                if arrival is not None:
                    stop[0] = arrival
                if departure is not None:
                    stop[1] = departure

        if board_departures:
            for calendar_value in calendars:
                raw_boards[railway_id].append({
                    "station": station_id,
                    "calendar": str(calendar_value or ""),
                    "direction": direction,
                    "departures": board_departures,
                })

    railway_meta = {
        str(item.get("owl:sameAs") or ""): item
        for item in railways or []
        if item.get("owl:sameAs")
    }
    results: dict[str, tuple[dict[str, Any], int, int]] = {}
    for railway_id in set(grouped) | set(raw_boards):
        trains = grouped.get(railway_id, {})
        station_values: list[str] = []
        station_indexes: dict[str, int] = {}
        calendar_values: list[str] = []
        calendar_indexes: dict[str, int] = {}
        train_type_values: list[str] = []
        train_type_indexes: dict[str, int] = {}
        direction_values: list[str] = []
        direction_indexes: dict[str, int] = {}
        trips: list[list[Any]] = []
        boards: list[list[Any]] = []
        connections = 0
        departure_count = 0

        def index_of(value: str, values: list[str], indexes: dict[str, int]) -> int:
            if value not in indexes:
                indexes[value] = len(values)
                values.append(value)
            return indexes[value]

        for trip in trains.values():
            raw_stops = []
            times = []
            for station_id, values in trip["stops"].items():
                arrival, departure = values
                basis = departure if departure is not None else arrival
                if basis is None:
                    continue
                times.append(basis)
                raw_stops.append([station_id, arrival, departure, basis])
            crosses_midnight = bool(times and max(times) >= 18 * 60 and min(times) < 6 * 60)
            if crosses_midnight:
                for stop in raw_stops:
                    if stop[3] < 6 * 60:
                        stop[3] += 24 * 60
                        if stop[1] is not None:
                            stop[1] += 24 * 60
                        if stop[2] is not None:
                            stop[2] += 24 * 60
            raw_stops.sort(key=lambda stop: stop[3])
            if len(raw_stops) < 2:
                continue

            stops: list[list[int | None]] = []
            for station_id, arrival, departure, _basis in raw_stops:
                station_index = index_of(station_id, station_values, station_indexes)
                # Station timetables normally expose departures only. Using
                # that same scheduled instant for arrival keeps the result
                # factual and conservative by at most the platform dwell.
                effective_arrival = arrival if arrival is not None else departure
                effective_departure = departure if departure is not None else arrival
                stops.append([station_index, effective_arrival, effective_departure])
            if len(stops) < 2:
                continue
            calendar_index = index_of(trip["calendar"], calendar_values, calendar_indexes)
            type_index = index_of(trip["trainType"], train_type_values, train_type_indexes)
            trips.append([calendar_index, type_index, trip["trainNumber"], stops])
            connections += len(stops) - 1

        for board in raw_boards.get(railway_id, []):
            station_index = index_of(board["station"], station_values, station_indexes)
            calendar_index = index_of(board["calendar"], calendar_values, calendar_indexes)
            direction_index = index_of(board["direction"], direction_values, direction_indexes)
            departures = []
            for departure, train_type in sorted(board["departures"]):
                type_index = index_of(train_type, train_type_values, train_type_indexes)
                departures.append([departure, type_index])
            if departures:
                boards.append([station_index, calendar_index, direction_index, departures])
                departure_count += len(departures)

        meta = railway_meta.get(railway_id, {})
        order = []
        for row in sorted(meta.get("odpt:stationOrder") or [], key=lambda value: int(value.get("odpt:index") or 0)):
            raw_station = str(row.get("odpt:station") or "")
            station_id = station_aliases.get(raw_station, raw_station)
            if station_id:
                order.append(station_id)

        results[railway_id] = ({
            "version": 1,
            "railway": railway_id,
            "timeBasis": "station-departure-only" if not trips else "station-departure",
            "stations": station_values,
            "calendars": calendar_values,
            "directions": direction_values,
            "trainTypes": train_type_values,
            "trips": trips,
            "boards": boards,
            "order": order,
            "ascendingDirection": str(meta.get("odpt:ascendingRailDirection") or ""),
            "descendingDirection": str(meta.get("odpt:descendingRailDirection") or ""),
        }, connections, departure_count)
    return results


def timetable_filename(railway_id: str) -> str:
    digest = hashlib.sha1(railway_id.encode("utf-8"), usedforsecurity=False).hexdigest()[:14]
    return f"{digest}.json"


def main() -> int:
    standard_key = os.environ.get("ODPT_API_KEY", "").strip()
    challenge_key = os.environ.get("ODPT_CHALLENGE_API_KEY", "").strip() or standard_key
    if not standard_key:
        print("ODPT_API_KEY is not set. Register at developer.odpt.org and store the token as a GitHub Actions secret.", file=sys.stderr)
        return 2

    include_jr = jr_east_import_enabled()
    include_timetables = timetable_import_enabled()
    session = requests.Session()
    session.headers.update({"User-Agent": "keio-kawaii-lab-transit-preview/0.1"})

    operator_ids, operators = discover_operators(session, standard_key)
    manual_topology = load_manual_topology()
    fetched_at = datetime.now(JST).isoformat(timespec="seconds")
    manifest: dict[str, Any] = {
        "fetchedAt": fetched_at,
        "source": "Public Transportation Open Data Center (ODPT)",
        "api": BASE_URL,
        "challengeApi": CHALLENGE_BASE_URL,
        "scope": "Tokyo/Kanagawa/Saitama/Chiba first-version operator set; operator networks may extend outside the four prefectures",
        "operators": {},
        "notes": [
            "Static timetable data must be refreshed after ODPT data updates in accordance with the applicable license/guideline.",
            "JR East data is provided under the Challenge 2026 limited license and covers only part of the conventional-line network around Tokyo; Shinkansen is not included.",
            "Keisei availability is detected at runtime; it may be unavailable from ODPT.",
            "Reviewed official-site topology supplements are merged only where ODPT does not provide a complete station order.",
            "Scheduled train times are refreshed weekly and are not real-time delay or cancellation information.",
        ],
    }

    # Keep only the operator metadata needed by the app.
    selected_operator_uris = set(operator_ids.values())
    dump_json(OUT_ROOT / "operators.json", [compact_entity(o) for o in operators if o.get("owl:sameAs") in selected_operator_uris])

    for slug, config in TARGETS.items():
        operator_uri = operator_ids[slug]
        info: dict[str, Any] = {
            "label": config["label"],
            "operator": operator_uri,
            "license": config["license"],
            "status": "pending",
        }
        manifest["operators"][slug] = info

        if slug == "jr-east" and not include_jr:
            info["status"] = "disabled"
            info["reason"] = "JR East Challenge 2026 import was paused with ALLOW_JR_EAST_CHALLENGE_DATA=0."
            continue

        try:
            entities: dict[str, list[dict[str, Any]]] = {}
            original_stations: list[dict[str, Any]] = []
            base_url = api_base_for(config)
            key = api_key_for(config, standard_key, challenge_key)
            if not config.get("manual_only"):
                for rdf_type in ENTITY_TYPES:
                    raw = api_get(session, rdf_type, key, operator_uri, base_url=base_url)
                    if rdf_type == "odpt:Station":
                        original_stations = raw
                    entities[rdf_type.split(":", 1)[1]] = [compact_entity(x) for x in raw]
                info["api"] = base_url

            supplement = manual_topology.get(slug)
            entities = merge_manual_topology(slug, operator_uri, entities, supplement)
            if supplement:
                info["topologySource"] = supplement.get("source")

            stations = entities.get("Station") or []
            railways = entities.get("Railway") or []
            if not stations or not railways:
                info["status"] = "not-available"
                info["stations"] = len(stations)
                info["railways"] = len(railways)
                info["stationTimetables"] = 0
                info["trainTimetables"] = 0
                continue

            op_dir = OUT_ROOT / slug
            dump_json(op_dir / "entities.json", entities)
            dump_json(op_dir / "station-timetables.json", [])
            dump_json(op_dir / "train-timetables.json", [])

            timetable_index: dict[str, Any] = {"version": 1, "lines": {}}
            total_station_timetables = 0
            total_station_departures = 0
            total_train_timetables = 0
            total_connections = 0
            timetable_dir = op_dir / "timetables"
            if timetable_dir.exists():
                for old_file in timetable_dir.glob("*.json"):
                    old_file.unlink()
            station_aliases = canonical_station_aliases(original_stations, stations)
            if include_timetables and not config.get("manual_only"):
                for railway in railways:
                    railway_id = str(railway.get("owl:sameAs") or "")
                    if not railway_id:
                        continue
                    train_raw = api_get(
                        session,
                        "odpt:TrainTimetable",
                        key,
                        operator_uri,
                        base_url=base_url,
                        extra_params={"odpt:railway": railway_id},
                    )
                    total_train_timetables += len(train_raw)
                    compact_timetable, connection_count = compact_line_timetable(
                        railway_id, train_raw, station_aliases
                    )
                    if not compact_timetable["trips"]:
                        continue
                    filename = timetable_filename(railway_id)
                    dump_json(timetable_dir / filename, compact_timetable)
                    timetable_index["lines"][railway_id] = {
                        "file": f"timetables/{filename}",
                        "trips": len(compact_timetable["trips"]),
                        "connections": connection_count,
                    }
                    total_connections += connection_count
                if not total_connections:
                    station_raw = api_get(
                        session,
                        "odpt:StationTimetable",
                        key,
                        operator_uri,
                        base_url=base_url,
                    )
                    total_station_timetables = len(station_raw)
                    station_lines = compact_station_timetables(station_raw, station_aliases, railways)
                    for railway_id, (compact_timetable, connection_count, departure_count) in station_lines.items():
                        if not compact_timetable["trips"] and not compact_timetable["boards"]:
                            continue
                        filename = timetable_filename(railway_id)
                        dump_json(timetable_dir / filename, compact_timetable)
                        timetable_index["lines"][railway_id] = {
                            "file": f"timetables/{filename}",
                            "trips": len(compact_timetable["trips"]),
                            "connections": connection_count,
                            "departures": departure_count,
                            "source": "station-timetable",
                        }
                        total_connections += connection_count
                        total_station_departures += departure_count
            dump_json(op_dir / "timetable-index.json", timetable_index)

            unique_stations = {x.get("owl:sameAs") for x in stations if x.get("owl:sameAs")}
            topology_edges = sum(max(0, len(x.get("odpt:stationOrder") or []) - 1) for x in railways)
            info.update({
                "status": "ok" if topology_edges else "topology-unavailable",
                "topologyStatus": "ok" if topology_edges else "unavailable",
                "topologyEdges": topology_edges,
                "timetableStatus": "ok" if total_connections else ("departure-only" if total_station_departures else ("not-available" if include_timetables else "not-requested")),
                "stations": len(unique_stations),
                "railways": len(railways),
                "stationTimetables": total_station_timetables,
                "trainTimetables": total_train_timetables,
                "timetableLines": len(timetable_index["lines"]),
                "timetableConnections": total_connections,
                "departures": total_connections + total_station_departures,
            })
            print(f"{slug}: {len(unique_stations)} stations / {topology_edges} topology edges / {total_connections} timetable connections / {total_station_departures} station departures / {total_train_timetables} train timetables")
        except Exception as exc:  # continue other operators and expose failure in manifest
            info["status"] = "error"
            info["error"] = str(exc)
            print(f"{slug}: ERROR {exc}", file=sys.stderr)

    dump_json(OUT_ROOT / "manifest.json", manifest)
    ok_count = sum(1 for x in manifest["operators"].values() if x.get("status") == "ok")
    print(f"Imported {ok_count}/{len(TARGETS)} target operators")
    return 0 if ok_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
