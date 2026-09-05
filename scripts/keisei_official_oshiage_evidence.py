#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

DETAILS_PATH = Path("data/transit/keisei/official-train-details.json")
ENTITIES_PATH = Path("data/transit/keisei/entities.json")
DEFAULT_FRAGMENT_DIR = Path("data/transit-v2/fragments")
DEFAULT_OUTPUT = Path("data/transit-v2/keisei-official-oshiage-evidence.json")
BOUNDARY_ID = "keisei-toei-oshiage"
BOUNDARY_NAME = "押上"
KEISEI_OSHIAGE = "odpt.Railway:Keisei.Oshiage"
TOEI_ASAKUSA = "odpt.Railway:Toei.Asakusa"
KEISEI_STATION = "odpt.Station:Keisei.Oshiage.Oshiage"
TOEI_STATION = "odpt.Station:Toei.Asakusa.Oshiage"
MARKER = "same-keisei-official-train-page-spans-oshiage-boundary"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return re.sub(r"\s+", "", text)


def localized_title(item: dict[str, Any]) -> str:
    value = item.get("odpt:stationTitle")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("ja") or value.get("en") or "")
    return str(item.get("dc:title") or "")


def keisei_station_names(entities: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for row in entities.get("Station") or []:
        if not isinstance(row, dict):
            continue
        name = norm(localized_title(row))
        if name:
            names.add(name)
    return names


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


def stable_id(*parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "keisei-official-train:" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def extract_candidates(details: dict[str, Any], names: set[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = {}

    def note(reason: str, item: dict[str, Any]) -> None:
        reasons[reason] += 1
        examples.setdefault(reason, [])
        if len(examples[reason]) < 8:
            examples[reason].append(item)

    for train in details.get("trains") or []:
        if not isinstance(train, dict):
            continue
        stops = [row for row in train.get("stops") or [] if isinstance(row, dict)]
        for index, stop in enumerate(stops):
            if norm(stop.get("station")) != BOUNDARY_NAME:
                continue
            sample = {
                "sourceTrainId": str(train.get("sourceTrainId") or ""),
                "calendar": str(train.get("calendar") or ""),
                "index": index,
            }
            if index == 0 or index + 1 >= len(stops):
                note("oshiage-is-endpoint-not-through", sample)
                continue
            before_name = norm(stops[index - 1].get("station"))
            after_name = norm(stops[index + 1].get("station"))
            before_keisei = before_name in names and before_name != BOUNDARY_NAME
            after_keisei = after_name in names and after_name != BOUNDARY_NAME
            if before_keisei == after_keisei:
                note("cannot-classify-boundary-neighbours", {**sample, "before": before_name, "after": after_name})
                continue
            travel_direction = "keisei-to-toei" if before_keisei else "toei-to-keisei"
            arrival = clock_minutes(stop.get("arrival"))
            departure = clock_minutes(stop.get("departure"))
            source_minute = arrival if arrival is not None else departure
            target_minute = departure if departure is not None else arrival
            if source_minute is None or target_minute is None:
                note("missing-oshiage-boundary-time", {**sample, "before": before_name, "after": after_name})
                continue
            if travel_direction == "keisei-to-toei":
                from_railway, to_railway = KEISEI_OSHIAGE, TOEI_ASAKUSA
                from_station, to_station = KEISEI_STATION, TOEI_STATION
            else:
                from_railway, to_railway = TOEI_ASAKUSA, KEISEI_OSHIAGE
                from_station, to_station = TOEI_STATION, KEISEI_STATION
            entry = {
                "status": "official-per-train-boundary-evidence",
                "operator": "keisei",
                "calendar": str(train.get("calendar") or ""),
                "direction": travel_direction,
                "boundaryId": BOUNDARY_ID,
                "boundaryStation": BOUNDARY_NAME,
                "fromRailway": from_railway,
                "toRailway": to_railway,
                "fromStation": from_station,
                "toStation": to_station,
                "sourceBoundaryMinute": int(source_minute),
                "targetBoundaryMinute": int(target_minute),
                "officialArrivalMinute": arrival,
                "officialDepartureMinute": departure,
                "sourceTrainId": str(train.get("sourceTrainId") or ""),
                "sourceUrl": str(train.get("url") or ""),
                "beforeBoundaryStation": before_name,
                "afterBoundaryStation": after_name,
                "evidence": [
                    "operator-official-per-train-timetable",
                    MARKER,
                ],
            }
            entry["id"] = stable_id(
                entry["calendar"],
                entry["direction"],
                entry["sourceTrainId"],
                entry["sourceBoundaryMinute"],
                entry["targetBoundaryMinute"],
            )
            output.append(entry)
    unique = {str(row["id"]): row for row in output}
    return list(unique.values()), {"reasons": dict(reasons), "examples": examples}


def calendar_key(raw: Any) -> str:
    text = norm(raw).lower()
    if "weekday" in text or "平日" in text:
        return "weekday"
    if any(token in text for token in ("saturdayholiday", "holiday", "休日", "土休日")):
        return "holiday"
    return text


def calendar_matches(raw: Any, service: str) -> bool:
    return calendar_key(raw) == calendar_key(service)


def endpoint(fragment: dict[str, Any], first: bool) -> list[Any] | None:
    stops = fragment.get("stops") or []
    if not isinstance(stops, list) or not stops:
        return None
    stop = stops[0] if first else stops[-1]
    return stop if isinstance(stop, list) and len(stop) >= 3 else None


def fragment_matches(
    fragment: dict[str, Any],
    *,
    railway: str,
    service: str,
    first: bool,
    station: str,
    minute: int,
) -> bool:
    if str(fragment.get("railway") or "") != railway:
        return False
    if not calendar_matches(fragment.get("calendar"), service):
        return False
    stop = endpoint(fragment, first)
    if not stop or str(stop[0] or "") != station:
        return False
    times = [int(value) for value in stop[1:3] if isinstance(value, (int, float))]
    return minute in times


def load_fragments(folder: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for name in ("keisei.json", "toei.json"):
        payload = load_json(folder / name)
        output.extend(row for row in payload.get("fragments") or [] if isinstance(row, dict) and row.get("id"))
    return output


def endpoint_index(
    fragments: list[dict[str, Any]],
    *,
    first: bool,
) -> dict[tuple[str, str, str, int], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str, int], list[dict[str, Any]]] = {}
    for fragment in fragments:
        stop = endpoint(fragment, first)
        if not stop:
            continue
        railway = str(fragment.get("railway") or "")
        service = calendar_key(fragment.get("calendar"))
        station = str(stop[0] or "")
        if railway not in (KEISEI_OSHIAGE, TOEI_ASAKUSA):
            continue
        if station not in (KEISEI_STATION, TOEI_STATION):
            continue
        for value in stop[1:3]:
            if not isinstance(value, (int, float)):
                continue
            key = (railway, service, station, int(value))
            bucket = index.setdefault(key, [])
            if fragment not in bucket:
                bucket.append(fragment)
    return index


def match_candidates(candidates: list[dict[str, Any]], fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    source_index = endpoint_index(fragments, first=False)
    target_index = endpoint_index(fragments, first=True)
    for candidate in candidates:
        service = calendar_key(candidate.get("calendar"))
        source_key = (
            str(candidate["fromRailway"]),
            service,
            str(candidate["fromStation"]),
            int(candidate["sourceBoundaryMinute"]),
        )
        target_key = (
            str(candidate["toRailway"]),
            service,
            str(candidate["toStation"]),
            int(candidate["targetBoundaryMinute"]),
        )
        sources = source_index.get(source_key, [])
        targets = target_index.get(target_key, [])
        if len(sources) == 1 and len(targets) == 1:
            status = "matched-singleton"
        elif not sources or not targets:
            status = "unmatched"
        else:
            status = "ambiguous"
        output.append({
            **candidate,
            "matchStatus": status,
            "fromFragment": sources[0].get("id") if len(sources) == 1 else None,
            "toFragment": targets[0].get("id") if len(targets) == 1 else None,
            "sourceMatches": [str(row.get("id") or "") for row in sources],
            "targetMatches": [str(row.get("id") or "") for row in targets],
            "matchPolicy": {
                "sameOfficialPerTrainPageSpansBoundaryRequired": True,
                "verifiedBoundaryRequired": True,
                "singletonFragmentMatchRequired": True,
                "boundaryMinuteTolerance": 0,
                "trainNumberAloneMayEstablishIdentity": False,
                "timeProximityAloneMayEstablishIdentity": False,
            },
        })
    return output


def make_payload(candidates: list[dict[str, Any]], matched: list[dict[str, Any]], extraction: dict[str, Any]) -> dict[str, Any]:
    status_counts = Counter(str(row.get("matchStatus") or "unknown") for row in matched)
    candidate_directions = Counter(str(row.get("direction") or "unknown") for row in candidates)
    matched_directions = Counter(
        str(row.get("direction") or "unknown")
        for row in matched
        if row.get("matchStatus") == "matched-singleton"
    )
    production = [row for row in matched if row.get("matchStatus") == "matched-singleton"]
    return {
        "version": 1,
        "source": {
            "operator": "keisei",
            "kind": "operator-official-per-train-timetable-snapshot",
            "path": str(DETAILS_PATH),
        },
        "policy": {
            "autoPromoteUnknown": False,
            "sameOfficialPerTrainPageSpansBoundaryRequired": True,
            "verifiedOperationalBoundaryRequired": True,
            "singletonFragmentMatchRequired": True,
            "trainNumberAloneMayEstablishIdentity": False,
            "timeProximityAloneMayEstablishIdentity": False,
            "staleFragmentReferenceMustFailClosed": True,
        },
        "summary": {
            "officialBoundaryCandidates": len(candidates),
            "candidateDirections": dict(candidate_directions),
            "matchedSingleton": status_counts.get("matched-singleton", 0),
            "ambiguous": status_counts.get("ambiguous", 0),
            "unmatched": status_counts.get("unmatched", 0),
            "matchedDirections": dict(matched_directions),
            "productionMatchedSingleton": len(production),
        },
        "extractionDiagnostics": extraction,
        "entries": production,
        "allCandidates": matched,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--details", default=str(DETAILS_PATH))
    parser.add_argument("--entities", default=str(ENTITIES_PATH))
    parser.add_argument("--fragment-dir", default=str(DEFAULT_FRAGMENT_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    details = load_json(Path(args.details))
    entities = load_json(Path(args.entities))
    candidates, extraction = extract_candidates(details, keisei_station_names(entities))
    matched = match_candidates(candidates, load_fragments(Path(args.fragment_dir)))
    payload = make_payload(candidates, matched, extraction)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    if not candidates:
        raise RuntimeError("No Keisei official per-train timetable crosses Oshiage boundary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
