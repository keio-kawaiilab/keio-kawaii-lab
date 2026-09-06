#!/usr/bin/env python3
"""Fail-closed verifier for generated Keikyu official page-local stop times."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from keikyu_connected_station_catalog import station_titles

TIME_RE = re.compile(r"^(?:[0-2]?\d)[0-5]\d$")
ID_RE = re.compile(r"^keikyu-official-pdf:p(\d{3}):c(\d{2})$")
EVENTS = {"arrival", "departure"}
RESOLUTIONS = {
    "same-row-station-title",
    "arrival-row-to-following-station-title",
    "departure-row-to-preceding-station-title",
}


def verify(payload: dict) -> dict:
    errors: list[str] = []
    if payload.get("version") != 1:
        errors.append("version must be 1")
    if payload.get("kind") != "keikyu-official-page-local-stop-times":
        errors.append("unexpected dataset kind")

    policy = payload.get("identityPolicy") or {}
    required_false = (
        "printedTrainNumberMayJoinPages",
        "anonymousColumnMayJoinPages",
        "clockTimeProximityMayJoinFragments",
        "destinationMayJoinFragments",
        "crossPageIdentityEstablished",
    )
    if policy.get("pageColumnIsExactLocalIdentity") is not True:
        errors.append("pageColumnIsExactLocalIdentity must be true")
    for key in required_false:
        if policy.get(key) is not False:
            errors.append(f"{key} must be false")
    if policy.get("runtimeSameTrainPromotions") != 0:
        errors.append("runtimeSameTrainPromotions must remain zero")

    canonical = set(station_titles())
    ids: set[str] = set()
    fragment_counts_by_page: dict[int, int] = {}
    source_count = 0
    resolved_count = 0
    unresolved_count = 0
    explicit_count = 0
    anonymous_count = 0

    for fragment in payload.get("fragments") or []:
        fragment_id = fragment.get("id")
        if not isinstance(fragment_id, str) or not ID_RE.fullmatch(fragment_id):
            errors.append(f"invalid fragment id: {fragment_id!r}")
            continue
        if fragment_id in ids:
            errors.append(f"duplicate fragment id: {fragment_id}")
        ids.add(fragment_id)
        match = ID_RE.fullmatch(fragment_id)
        assert match is not None
        page = fragment.get("page")
        column = fragment.get("column")
        if page != int(match.group(1)) or column != int(match.group(2)):
            errors.append(f"id/page/column mismatch: {fragment_id}")
        fragment_counts_by_page[int(page)] = fragment_counts_by_page.get(int(page), 0) + 1

        number = fragment.get("printedTrainNumber")
        anonymous = fragment.get("anonymousColumn")
        if anonymous is not (number is None):
            errors.append(f"anonymous flag mismatch: {fragment_id}")
        if anonymous:
            anonymous_count += 1
        else:
            explicit_count += 1

        previous_y = None
        for stop in fragment.get("stopTimes") or []:
            if stop.get("station") not in canonical:
                errors.append(f"non-canonical station in {fragment_id}: {stop.get('station')!r}")
            if stop.get("event") not in EVENTS:
                errors.append(f"invalid event in {fragment_id}: {stop.get('event')!r}")
            if not isinstance(stop.get("time"), str) or not TIME_RE.fullmatch(stop["time"]):
                errors.append(f"invalid time in {fragment_id}: {stop.get('time')!r}")
            if stop.get("resolution") not in RESOLUTIONS:
                errors.append(f"invalid resolution in {fragment_id}: {stop.get('resolution')!r}")
            row_y = stop.get("rowY")
            if not isinstance(row_y, (int, float)):
                errors.append(f"missing rowY in {fragment_id}")
            elif previous_y is not None and row_y < previous_y:
                errors.append(f"stopTimes out of printed row order: {fragment_id}")
            if isinstance(row_y, (int, float)):
                previous_y = row_y
            resolved_count += 1

        for cell in fragment.get("unresolvedCells") or []:
            if not isinstance(cell.get("time"), str) or not TIME_RE.fullmatch(cell["time"]):
                errors.append(f"invalid unresolved time in {fragment_id}: {cell.get('time')!r}")
            unresolved_count += 1

    page_rows = payload.get("pages") or []
    for page_row in page_rows:
        page = int(page_row["page"])
        expected_fragments = int(page_row["fragmentCount"])
        if fragment_counts_by_page.get(page, 0) != expected_fragments:
            errors.append(f"fragment count mismatch on page {page}")
        if int(page_row["resolvedTimeCells"]) + int(page_row["unresolvedTimeCells"]) != int(page_row["sourceTimeCells"]):
            errors.append(f"cell accounting mismatch on page {page}")
        source_count += int(page_row["sourceTimeCells"])

    totals = payload.get("totals") or {}
    expected = {
        "sourceTimeCells": source_count,
        "resolvedTimeCells": resolved_count,
        "unresolvedTimeCells": unresolved_count,
        "trainColumnFragments": len(ids),
        "explicitTrainNumberFragments": explicit_count,
        "anonymousFragments": anonymous_count,
    }
    for key, value in expected.items():
        if totals.get(key) != value:
            errors.append(f"total mismatch {key}: expected {value}, got {totals.get(key)!r}")
    if resolved_count + unresolved_count != source_count:
        errors.append("global cell accounting mismatch")

    if errors:
        raise RuntimeError("Keikyu stop-time verification failed:\n- " + "\n- ".join(errors[:100]))
    return {
        "verified": True,
        "pages": len(page_rows),
        "fragments": len(ids),
        "resolvedTimeCells": resolved_count,
        "unresolvedTimeCells": unresolved_count,
        "runtimeSameTrainPromotions": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    print(json.dumps(verify(payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
