#!/usr/bin/env python3
"""Import ODPT railway timetable data into compact app-facing JSON files.

The script intentionally does not scrape railway websites. It uses the official
ODPT API and expects the access token in ODPT_API_KEY.

By default JR East challenge data is NOT imported because the 2026 challenge
license has JR-East-specific restrictions on competing services. Set
ALLOW_JR_EAST_CHALLENGE_DATA=1 only after confirming the intended use complies
with the applicable license/terms.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.odpt.org/api/v4"
OUT_ROOT = Path("data/transit")
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
}

ENTITY_TYPES = ["odpt:Station", "odpt:Railway", "odpt:TrainType", "odpt:RailDirection"]
TIMETABLE_TYPES = ["odpt:StationTimetable", "odpt:TrainTimetable"]


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


def api_get(session: requests.Session, rdf_type: str, key: str, operator: str | None = None) -> list[dict[str, Any]]:
    url = f"{BASE_URL}/{rdf_type}"
    params = {"acl:consumerKey": key}
    if operator:
        params["odpt:operator"] = operator
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.get(url, params=params, timeout=(15, 180))
            if response.status_code in (403, 404):
                return []
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise ValueError(f"Unexpected {rdf_type} response: {type(data).__name__}")
            return data
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"ODPT request failed for {rdf_type} / {operator}: {last_error}")


def discover_operators(session: requests.Session, key: str) -> tuple[dict[str, str], list[dict[str, Any]]]:
    operators = api_get(session, "odpt:Operator", key)
    found: dict[str, str] = {}
    for slug, config in TARGETS.items():
        aliases = [a.casefold() for a in config["aliases"]]
        for item in operators:
            haystack = " | ".join(title_values(item)).casefold()
            if any(alias in haystack for alias in aliases):
                uri = item.get("owl:sameAs")
                if isinstance(uri, str):
                    found[slug] = uri
                    break
        if slug not in found:
            # Keep a standards-based fallback so a newly-added operator can be
            # attempted even if its title is not present in the Operator list.
            found[slug] = str(config["fallback"])
    return found, operators


def compact_entity(item: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "owl:sameAs", "dc:title", "dc:date", "odpt:operator", "odpt:railway",
        "odpt:stationTitle", "odpt:railwayTitle", "odpt:trainTypeTitle",
        "odpt:railDirectionTitle", "odpt:stationCode", "odpt:lineCode",
        "odpt:ascendingRailDirection", "odpt:descendingRailDirection",
        "odpt:stationOrder", "geo:lat", "geo:long",
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
            "odpt:index", "odpt:station", "odpt:arrivalTime", "odpt:departureTime",
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


def main() -> int:
    key = os.environ.get("ODPT_API_KEY", "").strip()
    if not key:
        print("ODPT_API_KEY is not set. Register at developer.odpt.org and store the token as a GitHub Actions secret.", file=sys.stderr)
        return 2

    include_jr = os.environ.get("ALLOW_JR_EAST_CHALLENGE_DATA", "").strip() == "1"
    session = requests.Session()
    session.headers.update({"User-Agent": "keio-kawaii-lab-transit-preview/0.1"})

    operator_ids, operators = discover_operators(session, key)
    fetched_at = datetime.now(JST).isoformat(timespec="seconds")
    manifest: dict[str, Any] = {
        "fetchedAt": fetched_at,
        "source": "Public Transportation Open Data Center (ODPT)",
        "api": BASE_URL,
        "scope": "Tokyo/Kanagawa/Saitama/Chiba first-version operator set; operator networks may extend outside the four prefectures",
        "operators": {},
        "notes": [
            "Static timetable data must be refreshed after ODPT data updates in accordance with the applicable license/guideline.",
            "JR East challenge data is disabled by default because of JR-East-specific Challenge 2026 usage restrictions.",
            "Keisei availability is detected at runtime; it may be unavailable from ODPT.",
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
            info["status"] = "skipped-license-review"
            info["reason"] = "Set ALLOW_JR_EAST_CHALLENGE_DATA=1 only after confirming the intended use complies with JR East Challenge 2026 specific terms."
            continue

        try:
            entities: dict[str, list[dict[str, Any]]] = {}
            for rdf_type in ENTITY_TYPES:
                raw = api_get(session, rdf_type, key, operator_uri)
                entities[rdf_type.split(":", 1)[1]] = [compact_entity(x) for x in raw]

            station_raw = api_get(session, "odpt:StationTimetable", key, operator_uri)
            train_raw = api_get(session, "odpt:TrainTimetable", key, operator_uri)

            if not station_raw:
                info["status"] = "not-available"
                info["stationTimetables"] = 0
                info["trainTimetables"] = len(train_raw)
                continue

            op_dir = OUT_ROOT / slug
            dump_json(op_dir / "entities.json", entities)
            station_compact = [compact_station_timetable(x) for x in station_raw]
            train_compact = [compact_train_timetable(x) for x in train_raw]
            dump_json(op_dir / "station-timetables.json", station_compact)
            dump_json(op_dir / "train-timetables.json", train_compact)

            unique_stations = {x.get("station") for x in station_compact if x.get("station")}
            departures = sum(len(x.get("trains") or []) for x in station_compact)
            info.update({
                "status": "ok",
                "stations": len(unique_stations),
                "stationTimetables": len(station_compact),
                "trainTimetables": len(train_compact),
                "departures": departures,
            })
            print(f"{slug}: {len(unique_stations)} stations / {departures} departures / {len(train_compact)} train timetables")
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
