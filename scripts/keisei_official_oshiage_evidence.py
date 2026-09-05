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
KEISEI_ENTITIES_PATH = Path("data/transit/keisei/entities.json")
TOEI_ENTITIES_PATH = Path("data/transit/toei/entities.json")
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
    text = re.sub(r"\s+", "", text)
    aliases = {
        "新鎌ケ谷": "新鎌ヶ谷",
        "空港第2ビル(成田第2・第3ターミナル)": "空港第2ビル",
        "空港第2ビル(成田第2・3ターミナル)": "空港第2ビル",
        "成田空港(成田第1ターミナル)": "成田空港",
    }
    return aliases.get(text, text)


def localized_title(item: dict[str, Any]) -> str:
    value = item.get("odpt:stationTitle")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("ja") or value.get("en") or "")
    return str(item.get("dc:title") or "")


def station_map(entities: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for row in entities.get("Station") or []:
        if not isinstance(row, dict):
            continue
        station_id = str(row.get("owl:sameAs") or "")
        name = norm(localized_title(row))
        if station_id and name:
            output[name] = station_id
    return output


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


def official_train_number(source_train_id: Any) -> str:
    text = str(source_train_id or "")
    return text.rsplit("-", 1)[-1] if "-" in text else text


def official_stop_anchor(stop: dict[str, Any], station_id: str) -> dict[str, Any]:
    arrival = clock_minutes(stop.get("arrival"))
    departure = clock_minutes(stop.get("departure"))
    return {
        "stationName": norm(stop.get("station")),
        "station": station_id,
        "arrivalMinute": arrival,
        "departureMinute": departure,
        "minutes": sorted({minute for minute in (arrival, departure) if minute is not None}),
    }


def stable_id(*parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "keisei-official-train:" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def extract_candidates(
    details: dict[str, Any],
    keisei_stations: dict[str, str],
    toei_stations: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = {}

    def note(reason: str, item: dict[str, Any]) -> None:
        reasons[reason] += 1
        examples.setdefault(reason, [])
        if len(examples[reason]) < 8:
            examples[reason].append(item)

    keisei_names = set(keisei_stations)
    for train in details.get("trains") or []:
        if not isinstance(train, dict):
            continue
        stops = [row for row in train.get("stops") or [] if isinstance(row, dict)]
        for index, stop in enumerate(stops):
            if norm(stop.get("station")) != BOUNDARY_NAME:
                continue
            source_train_id = str(train.get("sourceTrainId") or "")
            sample = {"sourceTrainId": source_train_id, "calendar": str(train.get("calendar") or ""), "index": index}
            if index == 0 or index + 1 >= len(stops):
                note("oshiage-is-endpoint-not-through", sample)
                continue
            before_stop, after_stop = stops[index - 1], stops[index + 1]
            before_name = norm(before_stop.get("station"))
            after_name = norm(after_stop.get("station"))
            before_keisei = before_name in keisei_names and before_name != BOUNDARY_NAME
            after_keisei = after_name in keisei_names and after_name != BOUNDARY_NAME
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
                source_anchor_id = keisei_stations.get(before_name, "")
                target_anchor_id = toei_stations.get(after_name, "")
            else:
                from_railway, to_railway = TOEI_ASAKUSA, KEISEI_OSHIAGE
                from_station, to_station = TOEI_STATION, KEISEI_STATION
                source_anchor_id = toei_stations.get(before_name, "")
                target_anchor_id = keisei_stations.get(after_name, "")

            source_anchor = official_stop_anchor(before_stop, source_anchor_id)
            target_anchor = official_stop_anchor(after_stop, target_anchor_id)
            if not source_anchor_id:
                note("missing-source-adjacent-station-mapping", {**sample, "station": before_name, "direction": travel_direction})
            if not target_anchor_id:
                note("missing-target-adjacent-station-mapping", {**sample, "station": after_name, "direction": travel_direction})

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
                "sourceAdjacentAnchor": source_anchor,
                "targetAdjacentAnchor": target_anchor,
                "sourceTrainId": source_train_id,
                "officialTrainNumber": official_train_number(source_train_id),
                "sourceUrl": str(train.get("url") or ""),
                "beforeBoundaryStation": before_name,
                "afterBoundaryStation": after_name,
                "evidence": ["operator-official-per-train-timetable", MARKER],
            }
            entry["id"] = stable_id(
                entry["calendar"], entry["direction"], source_train_id,
                entry["sourceBoundaryMinute"], entry["targetBoundaryMinute"],
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


def endpoint(fragment: dict[str, Any], first: bool) -> list[Any] | None:
    stops = fragment.get("stops") or []
    if not isinstance(stops, list) or not stops:
        return None
    stop = stops[0] if first else stops[-1]
    return stop if isinstance(stop, list) and len(stop) >= 3 else None


def load_fragments(folder: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for name in ("keisei.json", "toei.json"):
        payload = load_json(folder / name)
        output.extend(row for row in payload.get("fragments") or [] if isinstance(row, dict) and row.get("id"))
    return output


def endpoint_index(
    fragments: list[dict[str, Any]], *, first: bool,
) -> dict[tuple[str, str, str, int], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str, int], list[dict[str, Any]]] = {}
    for fragment in fragments:
        stop = endpoint(fragment, first)
        if not stop:
            continue
        railway = str(fragment.get("railway") or "")
        service = calendar_key(fragment.get("calendar"))
        station = str(stop[0] or "")
        if railway not in (KEISEI_OSHIAGE, TOEI_ASAKUSA) or station not in (KEISEI_STATION, TOEI_STATION):
            continue
        for value in stop[1:3]:
            if not isinstance(value, (int, float)):
                continue
            key = (railway, service, station, int(value))
            bucket = index.setdefault(key, [])
            if fragment not in bucket:
                bucket.append(fragment)
    return index


def fragment_has_exact_anchor(fragment: dict[str, Any], anchor: dict[str, Any]) -> bool:
    station_id = str(anchor.get("station") or "")
    official_minutes = {int(value) for value in anchor.get("minutes") or [] if isinstance(value, (int, float))}
    if not station_id or not official_minutes:
        return False
    for stop in fragment.get("stops") or []:
        if not isinstance(stop, list) or len(stop) < 3 or str(stop[0] or "") != station_id:
            continue
        fragment_minutes = {int(value) for value in stop[1:3] if isinstance(value, (int, float))}
        if official_minutes & fragment_minutes:
            return True
    return False


def refine_if_ambiguous(
    matches: list[dict[str, Any]],
    anchor: dict[str, Any],
    *,
    official_number: str,
    may_use_official_number: bool,
) -> tuple[list[dict[str, Any]], str, bool]:
    if len(matches) <= 1:
        return matches, ("boundary-singleton" if len(matches) == 1 else "boundary-missing"), False
    if not str(anchor.get("station") or "") or not anchor.get("minutes"):
        return matches, "adjacent-anchor-unavailable", False

    refined = [fragment for fragment in matches if fragment_has_exact_anchor(fragment, anchor)]
    if len(refined) == 1:
        return refined, "resolved-by-adjacent-official-anchor", False
    if not refined:
        return matches, "adjacent-anchor-no-exact-match", False

    # Train number is never an identity source by itself.  It is allowed only
    # as the final selector after the same official train page already supplied
    # an exact Oshiage boundary anchor AND an exact adjacent-station anchor.
    if may_use_official_number and official_number:
        numbered = [
            fragment for fragment in refined
            if fragment.get("sourceKind") == "exact-train-timetable"
            and str(fragment.get("trainNumber") or "") == official_number
        ]
        if len(numbered) == 1:
            return numbered, "resolved-by-adjacent-anchor-and-official-train-number", True
        if len(numbered) > 1:
            return numbered, "still-ambiguous-after-adjacent-anchor-and-train-number", False
        return refined, "official-train-number-no-exact-fragment-match", False
    return refined, "still-ambiguous-after-adjacent-anchor", False


def match_candidates(candidates: list[dict[str, Any]], fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    source_index = endpoint_index(fragments, first=False)
    target_index = endpoint_index(fragments, first=True)
    for candidate in candidates:
        service = calendar_key(candidate.get("calendar"))
        source_key = (
            str(candidate["fromRailway"]), service, str(candidate["fromStation"]), int(candidate["sourceBoundaryMinute"]),
        )
        target_key = (
            str(candidate["toRailway"]), service, str(candidate["toStation"]), int(candidate["targetBoundaryMinute"]),
        )
        boundary_sources = list(source_index.get(source_key, []))
        boundary_targets = list(target_index.get(target_key, []))
        number = str(candidate.get("officialTrainNumber") or "")
        sources, source_method, source_number = refine_if_ambiguous(
            boundary_sources,
            candidate.get("sourceAdjacentAnchor") or {},
            official_number=number,
            may_use_official_number=str(candidate.get("fromRailway") or "") == KEISEI_OSHIAGE,
        )
        targets, target_method, target_number = refine_if_ambiguous(
            boundary_targets,
            candidate.get("targetAdjacentAnchor") or {},
            official_number=number,
            may_use_official_number=str(candidate.get("toRailway") or "") == KEISEI_OSHIAGE,
        )

        if len(sources) == 1 and len(targets) == 1:
            status = "matched-singleton"
        elif not boundary_sources or not boundary_targets:
            status = "unmatched"
        else:
            status = "ambiguous"
        resolved_by_anchor = (
            source_method.startswith("resolved-by-adjacent-official-anchor")
            or target_method.startswith("resolved-by-adjacent-official-anchor")
        )
        resolved_by_number = source_number or target_number
        output.append({
            **candidate,
            "matchStatus": status,
            "fromFragment": sources[0].get("id") if len(sources) == 1 else None,
            "toFragment": targets[0].get("id") if len(targets) == 1 else None,
            "sourceMatches": [str(row.get("id") or "") for row in sources],
            "targetMatches": [str(row.get("id") or "") for row in targets],
            "boundarySourceMatches": [str(row.get("id") or "") for row in boundary_sources],
            "boundaryTargetMatches": [str(row.get("id") or "") for row in boundary_targets],
            "sourceMatchMethod": source_method,
            "targetMatchMethod": target_method,
            "resolvedByAdjacentOfficialAnchor": resolved_by_anchor,
            "resolvedByOfficialTrainNumberAfterExactAnchors": resolved_by_number,
            "matchPolicy": {
                "sameOfficialPerTrainPageSpansBoundaryRequired": True,
                "exactBoundaryAnchorRequired": True,
                "ambiguousBoundaryEndpointRequiresExactAdjacentOfficialAnchor": True,
                "officialTrainNumberMayDisambiguateOnlyAfterExactBoundaryAndAdjacentAnchor": True,
                "verifiedBoundaryRequired": True,
                "singletonFragmentMatchRequired": True,
                "boundaryMinuteTolerance": 0,
                "adjacentMinuteTolerance": 0,
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
        for row in matched if row.get("matchStatus") == "matched-singleton"
    )
    anchor_resolved = [
        row for row in matched
        if row.get("matchStatus") == "matched-singleton" and row.get("resolvedByAdjacentOfficialAnchor")
    ]
    number_resolved = [row for row in anchor_resolved if row.get("resolvedByOfficialTrainNumberAfterExactAnchors")]
    boundary_singletons = [
        row for row in matched
        if row.get("matchStatus") == "matched-singleton" and not row.get("resolvedByAdjacentOfficialAnchor")
    ]
    still_ambiguous = [row for row in matched if row.get("matchStatus") == "ambiguous"]
    production = [row for row in matched if row.get("matchStatus") == "matched-singleton"]
    return {
        "version": 3,
        "source": {"operator": "keisei", "kind": "operator-official-per-train-timetable-snapshot", "path": str(DETAILS_PATH)},
        "policy": {
            "autoPromoteUnknown": False,
            "sameOfficialPerTrainPageSpansBoundaryRequired": True,
            "exactBoundaryAnchorRequired": True,
            "ambiguousBoundaryEndpointRequiresExactAdjacentOfficialAnchor": True,
            "officialTrainNumberMayDisambiguateOnlyAfterExactBoundaryAndAdjacentAnchor": True,
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
            "boundarySingleton": len(boundary_singletons),
            "resolvedByAdjacentOfficialAnchor": len(anchor_resolved),
            "resolvedByOfficialTrainNumberAfterExactAnchors": len(number_resolved),
            "resolvedByOfficialTrainNumberDirections": dict(Counter(str(row.get("direction") or "unknown") for row in number_resolved)),
            "stillAmbiguousAfterStrictDisambiguation": len(still_ambiguous),
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
    parser.add_argument("--keisei-entities", default=str(KEISEI_ENTITIES_PATH))
    parser.add_argument("--toei-entities", default=str(TOEI_ENTITIES_PATH))
    parser.add_argument("--fragment-dir", default=str(DEFAULT_FRAGMENT_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    details = load_json(Path(args.details))
    candidates, extraction = extract_candidates(
        details,
        station_map(load_json(Path(args.keisei_entities))),
        station_map(load_json(Path(args.toei_entities))),
    )
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
