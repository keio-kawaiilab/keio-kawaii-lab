#!/usr/bin/env python3
"""Verify printed-calendar, section-local identity and every retained time cell."""
from __future__ import annotations

import argparse
import json
import re
import math
from collections import Counter, defaultdict
from pathlib import Path

from keikyu_connected_station_catalog import station_titles

TIME_RE = re.compile(r"^(?:[0-2]?\d)[0-5]\d$")
ID_RE = re.compile(r"^keikyu-official-pdf:p(\d{3}):s(\d{2}):c(\d{2})$")
EVENTS = {"arrival", "departure"}
RESOLUTIONS = {
    "same-row-station-title",
    "arrival-row-to-following-station-title",
    "departure-row-to-preceding-station-title",
}


def verify(payload: dict) -> dict:
    errors: list[str] = []
    if payload.get("version") != 4:
        errors.append("version must be 4")
    if payload.get("kind") != "keikyu-official-section-local-stop-times":
        errors.append("unexpected dataset kind")
    if not re.fullmatch(r"[0-9a-f]{64}", str((payload.get("source") or {}).get("sha256", ""))):
        errors.append("missing or invalid source SHA256")

    policy = payload.get("identityPolicy") or {}
    required_false = (
        "printedTrainNumberMayJoinSectionsOrPages",
        "anonymousColumnMayJoinSectionsOrPages",
        "calendarMayBeInferredFromPageNumber",
        "calendarMayBeInferredFromNeighboringPages",
        "clockTimeProximityMayJoinFragments",
        "destinationMayJoinFragments",
        "crossPageIdentityEstablished",
    )
    for key in ("pageSectionColumnIsExactLocalIdentity", "literalTrainNumberRowsAreHardSectionBoundaries",
                "literalPrintedCalendarRequired", "unclassifiedCalendarPagesExcludedFromIdentity"):
        if policy.get(key) is not True:
            errors.append(f"{key} must be true")
    if policy.get("minimumDistinctTimedRowsPerIdentitySection") != 3:
        errors.append("minimumDistinctTimedRowsPerIdentitySection must be 3")
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
    section_fragments = defaultdict(list)
    calendar_fragments = Counter()

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
        section = fragment.get("section")
        column = fragment.get("column")
        if (page, section, column) != tuple(map(int, match.groups())):
            errors.append(f"id/page/section/column mismatch: {fragment_id}")
            continue
        fragment_counts_by_page[page] = fragment_counts_by_page.get(page, 0) + 1
        section_fragments[(page, section)].append(fragment)
        calendar = fragment.get("calendar")
        if calendar not in ("weekday", "holiday"):
            errors.append(f"missing literal calendar: {fragment_id}")
        calendar_fragments[calendar] += 1
        y_min, y_max = fragment.get("sectionYMin"), fragment.get("sectionYMax")
        valid_bounds = all(isinstance(y, (int, float)) and math.isfinite(y) for y in (y_min, y_max))
        if not valid_bounds or y_min >= y_max:
            errors.append(f"invalid section bounds: {fragment_id}")
        for cell in (fragment.get("stopTimes") or []) + (fragment.get("unresolvedCells") or []):
            y = cell.get("rowY")
            if (not isinstance(y, (int, float)) or not math.isfinite(y)
                    or not valid_bounds or not y_min - 0.001 <= y <= y_max + 0.001):
                errors.append(f"cell outside printed section: {fragment_id}")

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
            resolution = stop.get('resolution', '')
            recovered_marker = isinstance(resolution, str) and resolution.startswith('exact-nearby-printed-marker-and-')
            base_resolution = resolution.removeprefix('exact-nearby-printed-marker-and-') if recovered_marker else resolution
            if base_resolution not in RESOLUTIONS:
                errors.append(f"invalid resolution in {fragment_id}: {stop.get('resolution')!r}")
            row_y = stop.get("rowY")
            if recovered_marker:
                evidence_y = stop.get('markerEvidenceY')
                if (not isinstance(evidence_y, (int, float)) or not math.isfinite(evidence_y)
                        or not isinstance(row_y, (int, float)) or not math.isfinite(row_y)
                        or not 0 < abs(evidence_y-row_y) <= 1.91):
                    errors.append(f"missing/out-of-bounds printed marker proof: {fragment_id}")
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
    seen_pages = set()
    seen_sections = set()
    calendar_pages = Counter()
    calendar_sections = Counter()
    for page_row in page_rows:
        page = int(page_row["page"])
        if page in seen_pages:
            errors.append(f"duplicate page: {page}")
        seen_pages.add(page)
        calendar = page_row.get("calendar")
        calendar_pages[calendar] += 1
        sections = page_row.get("sections") or []
        if page_row.get("sectionCount") != len(sections):
            errors.append(f"section count mismatch on page {page}")
        sums = Counter()
        for row in sections:
            key = (page, row.get("section"))
            if key in seen_sections:
                errors.append(f"duplicate section: {key}")
            seen_sections.add(key)
            calendar_sections[row.get("calendar")] += 1
            members = section_fragments.get(key, [])
            resolved = sum(len(f.get("stopTimes") or []) for f in members)
            unresolved = sum(len(f.get("unresolvedCells") or []) for f in members)
            actual = dict(fragmentCount=len(members), resolvedTimeCells=resolved,
                          unresolvedTimeCells=unresolved, sourceTimeCells=resolved + unresolved)
            for field, value in actual.items():
                sums[field] += value
                if row.get(field) != value:
                    errors.append(f"section {key} {field} mismatch")
            if row.get("calendar") != calendar or calendar not in ("weekday", "holiday"):
                errors.append(f"section calendar mismatch: {key}")
            for member in members:
                for field, parent_field in (("calendar", "calendar"), ("headerOrdinal", "headerOrdinal"),
                                           ("sectionYMin", "yMin"), ("sectionYMax", "yMax")):
                    if member.get(field) != row.get(parent_field):
                        errors.append(f"fragment/section {field} mismatch: {member['id']}")
        for field, value in sums.items():
            if page_row.get(field) != value:
                errors.append(f"page {page} {field} mismatch")
        expected_fragments = int(page_row["fragmentCount"])
        if fragment_counts_by_page.get(page, 0) != expected_fragments:
            errors.append(f"fragment count mismatch on page {page}")
        if int(page_row["resolvedTimeCells"]) + int(page_row["unresolvedTimeCells"]) != int(page_row["sourceTimeCells"]):
            errors.append(f"cell accounting mismatch on page {page}")
        source_count += int(page_row["sourceTimeCells"])

    if seen_pages != set(fragment_counts_by_page) or seen_sections != set(section_fragments):
        errors.append("page/section manifest does not cover every fragment exactly once")
    excluded_pages = {row["page"] if isinstance(row, dict) else row for row in payload.get("excludedPages", [])}
    calendar_excluded = {row["page"] if isinstance(row, dict) else row for row in payload.get("calendarExcludedPages", [])}
    if seen_pages & (excluded_pages | calendar_excluded):
        errors.append("excluded page materialized as identity")
    for field, counts in (("pages", calendar_pages), ("sections", calendar_sections), ("fragments", calendar_fragments)):
        if (payload.get("calendarCounts") or {}).get(field) != dict(counts):
            errors.append(f"calendar {field} accounting mismatch")

    totals = payload.get("totals") or {}
    expected = {
        "sourceTimeCells": source_count,
        "resolvedTimeCells": resolved_count,
        "unresolvedTimeCells": unresolved_count,
        "trainColumnFragments": len(ids),
        "explicitTrainNumberFragments": explicit_count,
        "anonymousFragments": anonymous_count,
        "timetableSections": len(seen_sections),
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
