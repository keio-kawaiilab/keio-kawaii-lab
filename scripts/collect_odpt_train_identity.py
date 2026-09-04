#!/usr/bin/env python3
"""Collect authoritative ODPT train-identity evidence for through-service routing.

This is intentionally a sidecar to the compact timetable importer. Compact
line timetables stay backwards compatible, while this file preserves the ODPT
fields that prove a timetable fragment belongs to the same physical train.

Only identity-relevant rows are stored: a TrainTimetable with an explicit
previous/next TrainTimetable link, or a published destination outside its
source railway. Train numbers and timetable gaps are retained as labels only;
they are never used to establish train identity.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path("data/transit")
MANIFEST = ROOT / "manifest.json"
OUT = ROOT / "odpt-train-identities.json"
REQUEST_INTERVAL = float(os.environ.get("ODPT_REQUEST_INTERVAL_SECONDS", "0.75"))


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def strings(value: Any) -> list[str]:
    return [str(item) for item in as_list(value) if item]


def station_from_stop(row: dict[str, Any]) -> str:
    return str(
        row.get("odpt:station")
        or row.get("odpt:departureStation")
        or row.get("odpt:arrivalStation")
        or ""
    )


def compact_endpoint(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    station = station_from_stop(row)
    if not station:
        return None
    return {
        "station": station,
        "arrival": row.get("odpt:arrivalTime"),
        "departure": row.get("odpt:departureTime"),
    }


def load_station_railways() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    direct: dict[str, set[str]] = {}
    suffix: dict[str, set[str]] = {}
    for entities_path in ROOT.glob("*/entities.json"):
        try:
            entities = json.loads(entities_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for station in entities.get("Station") or []:
            if not isinstance(station, dict):
                continue
            station_id = str(station.get("owl:sameAs") or "")
            railways = strings(station.get("odpt:railway"))
            if station_id and railways:
                direct.setdefault(station_id, set()).update(railways)
                suffix.setdefault(station_id.split(".")[-1], set()).update(railways)
        for railway in entities.get("Railway") or []:
            if not isinstance(railway, dict):
                continue
            railway_id = str(railway.get("owl:sameAs") or "")
            if not railway_id:
                continue
            for order in as_list(railway.get("odpt:stationOrder")):
                if not isinstance(order, dict):
                    continue
                station_id = str(order.get("odpt:station") or "")
                if station_id:
                    direct.setdefault(station_id, set()).add(railway_id)
                    suffix.setdefault(station_id.split(".")[-1], set()).add(railway_id)
    return direct, suffix


def destination_railways(
    station_id: str, direct: dict[str, set[str]], suffix: dict[str, set[str]]
) -> set[str]:
    if station_id in direct:
        return set(direct[station_id])
    return set(suffix.get(station_id.split(".")[-1], set()))


def is_external_destination(
    railway: str,
    destinations: list[str],
    direct: dict[str, set[str]],
    suffix: dict[str, set[str]],
) -> bool:
    for destination in destinations:
        targets = destination_railways(destination, direct, suffix)
        if targets and any(target != railway for target in targets):
            return True
        # Keep a visibly cross-railway ODPT destination even when topology
        # aliases are incomplete. The deterministic builder still requires a
        # verified service family before classifying it as through service.
        if destination.startswith("odpt.Station:"):
            station_parts = destination.removeprefix("odpt.Station:").split(".")
            railway_parts = railway.removeprefix("odpt.Railway:").split(".")
            if len(station_parts) >= 2 and len(railway_parts) >= 2:
                if station_parts[:2] != railway_parts[:2]:
                    return True
    return False


def api_get(url: str, key: str, operator: str) -> list[dict[str, Any]]:
    params = {"acl:consumerKey": key, "odpt:operator": operator}
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = requests.get(url, params=params, timeout=90)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise RuntimeError(f"ODPT returned non-list payload for {operator}")
            return [item for item in payload if isinstance(item, dict)]
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt == 3:
                break
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch TrainTimetable for {operator}: {last_error}")


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    basic_key = os.environ.get("ODPT_API_KEY", "").strip()
    challenge_key = os.environ.get("ODPT_CHALLENGE_API_KEY", "").strip()
    direct, suffix = load_station_railways()

    records: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    operators = manifest.get("operators") or {}
    for slug, meta in operators.items():
        if not isinstance(meta, dict) or meta.get("status") != "ok":
            continue
        if meta.get("timetableStatus") != "ok" or int(meta.get("trainTimetables") or 0) <= 0:
            continue
        # Keisei uses its own official timetable collector/network builder.
        if meta.get("timetableSource") or slug == "keisei":
            continue
        operator = str(meta.get("operator") or "")
        base_url = str(meta.get("api") or manifest.get("api") or "").rstrip("/")
        if not operator or not base_url:
            continue
        challenge = "challenge" in base_url
        key = challenge_key if challenge else basic_key
        if not key:
            sources.append({"slug": slug, "operator": operator, "status": "missing-key", "records": 0})
            continue
        rows = api_get(f"{base_url}/odpt:TrainTimetable", key, operator)
        kept = 0
        for item in rows:
            railway = str(item.get("odpt:railway") or "")
            timetable_id = str(item.get("owl:sameAs") or "")
            previous = strings(item.get("odpt:previousTrainTimetable"))
            following = strings(item.get("odpt:nextTrainTimetable"))
            destinations = strings(item.get("odpt:destinationStation"))
            if not timetable_id or not railway:
                continue
            external = is_external_destination(railway, destinations, direct, suffix)
            if not previous and not following and not external:
                continue
            stops = [row for row in as_list(item.get("odpt:trainTimetableObject")) if isinstance(row, dict)]
            records.append({
                "timetableId": timetable_id,
                "trainId": str(item.get("odpt:train") or ""),
                "operator": operator,
                "sourceOperator": slug,
                "railway": railway,
                "calendars": strings(item.get("odpt:calendar")),
                "trainType": str(item.get("odpt:trainType") or ""),
                "trainNumber": str(item.get("odpt:trainNumber") or ""),
                "direction": str(item.get("odpt:railDirection") or ""),
                "origin": strings(item.get("odpt:originStation")),
                "destination": destinations,
                "previousTrainTimetables": previous,
                "nextTrainTimetables": following,
                "firstStop": compact_endpoint(stops[0] if stops else None),
                "lastStop": compact_endpoint(stops[-1] if stops else None),
                "externalDestination": external,
            })
            kept += 1
        sources.append({"slug": slug, "operator": operator, "status": "ok", "fetched": len(rows), "records": kept})
        time.sleep(REQUEST_INTERVAL)

    records.sort(key=lambda row: (row["sourceOperator"], row["railway"], row["timetableId"]))
    payload = {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "ODPT TrainTimetable",
        "policy": {
            "runtimeInference": False,
            "timeGapMayEstablishTrainIdentity": False,
            "trainNumberMayEstablishTrainIdentity": False,
            "authoritativeLinks": ["odpt:previousTrainTimetable", "odpt:nextTrainTimetable"],
        },
        "sources": sources,
        "records": records,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"sources": len(sources), "identityRecords": len(records)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
