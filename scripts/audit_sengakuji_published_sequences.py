#!/usr/bin/env python3
"""Reconcile local candidates using reciprocal pages and exact published sequences.

This diagnostic does not edit the mother sets or runtime DB. A shared printed
column alone does NOT prove through service: some columns print transfers.
An explicit continuation arrow with no intervening branch train is required.
Reciprocal publication
references account for duplicate physical-train publication; station sequences
only identify which local candidate that column describes. No nearest-time or
number-based tie-breaking, and no arbitrary merging of candidate trains.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from audit_keikyu_reciprocal_publication import resolve_links
from audit_sengakuji_independent_reconciliation import reconcile
from audit_toei_sengakuji_official_columns import load
from diagnose_sengakuji_toei_sequence_match import (
    build_page_cache, build_trip_index, extract_pdf_fingerprint, page_words, score_trip, PDF_TO_ODPT_SUFFIX,
)
from keikyu_official_train_evidence import (
    DEFAULT_WEEKDAY_URL, DEFAULT_HOLIDAY_URL, extract_pdf, fetch_pdf,
    hhmm, norm, rows, time_cells, column_tolerance, cx, cy, calendar_matches, NUMBER_RE,
)
from verify_keikyu_independent_mother_set_audit import verify as verify_mother


KEIKYU_STATIONS = ("泉岳寺", "品川", "羽田空港第1・第2ターミナル", "羽田空港第3ターミナル")
CANONICAL = {norm(name): name for name in ("泉岳寺", "品川", "羽田空港第１・第２ターミナル", "羽田空港第３ターミナル")}


def classify_boundary(cache, candidate):
    """Inspect the actual boundary marker and intervening Nishimagome row.

    A literal train number plus Nishimagome departure is a different train,
    even when arrival/departure at Sengakuji coincide. CID decorations are
    preserved in evidence but cannot count as a continuation arrow.
    """
    geometry = candidate["rowGeometry"]
    x, y = candidate["columnX"], geometry["boundaryTrainNumberY"]
    def tokens_at(row_y):
        return [norm(w["text"]) for w in cache["words"]
                if abs(cx(w) - x) < 5 and abs(cy(w) - row_y) < 3.7]
    markers = tokens_at(y)
    meaningful = [s for s in markers if not re.fullmatch(r"\(cid:\d+\)", s)]
    branch_rows = [r for r in cache["rows"] if "西馬込" in r["text"]
                   and geometry["sourceBoundaryY"] < r["y"] < geometry["targetBoundaryY"]]
    branch = [dict(rowY=round(r["y"], 3), tokens=tokens_at(r["y"])) for r in branch_rows]
    times = [hhmm(s) for r in branch for s in r["tokens"] if hhmm(s) is not None]
    branch_meaningful = [s for r in branch for s in r["tokens"] if not re.fullmatch(r"\(cid:\d+\)", s)]
    numbers = [s for s in meaningful if NUMBER_RE.fullmatch(s)]
    status = "unresolved-boundary-marker"
    north = candidate["direction"] == "keikyu-to-toei"
    if north and len(branch) == 1 and len(times) == 1 and len(numbers) == 1 and "↓" not in meaningful:
        status = "official-transfer-via-nishimagome"
    elif meaningful == ["↓"] and branch_meaningful == ["..."] and len(branch) == 1:
        status = "official-continuation-arrow"
    return dict(status=status, markerTokens=markers, markerRowY=y,
                branchRows=branch, nishimagomeDepartureMinutes=times)


def keikyu_page_cache(words, time_cache=None):
    page_rows = rows(words)
    return {"words": words, "rows": page_rows, "timeByY": (time_cache or build_page_cache(words))["timeByY"],
            "numberRows": [r["y"] for r in page_rows if "列車番号" in r["text"]]}


def keikyu_fingerprint(words, candidate):
    """Use only labelled Keikyu-side rows inside the boundary's own panel.

    The relevant strip is bounded by its nearest printed train-number rows;
    no rows from the other stacked direction may enter this fingerprint.
    """
    cache = words if isinstance(words, dict) else keikyu_page_cache(words)
    page_rows = cache["rows"]
    geometry = candidate["rowGeometry"]
    inbound = candidate["direction"] == "toei-to-keikyu"
    boundary_y = geometry["targetBoundaryY"] if inbound else geometry["sourceBoundaryY"]
    number_rows = cache["numberRows"]
    lower = max((y for y in number_rows if y < boundary_y), default=float("-inf"))
    upper = min((y for y in number_rows if y > boundary_y), default=float("inf"))
    relevant = []
    for row in page_rows:
        y = row["y"]
        if not lower < y < upper:
            continue
        if (inbound and y < boundary_y - 2) or (not inbound and y > boundary_y + 2):
            continue
        names = [name for name in KEIKYU_STATIONS if norm(name) in norm(row["text"])]
        if len(names) != 1:
            continue
        values = cache["timeByY"].get(y, [])
        tolerance = column_tolerance(values)
        hits = [v for v in values if abs(v["x"] - candidate["columnX"]) <= tolerance]
        if len(hits) != 1:
            continue
        cell = hits[0]
        relevant.append(dict(station=CANONICAL[norm(names[0])], minute=cell["minute"],
                             rowY=round(y, 3), columnX=cell["x"]))
    return sorted(relevant, key=lambda p: p["rowY"])


def sequence_matches(fingerprint, fragment):
    """All published points must occur in printed order in one local column."""
    if len({p["station"] for p in fingerprint}) < 2:
        return False
    stops = fragment.get("stopTimes", [])
    cursor = 0
    for point in fingerprint:
        while cursor < len(stops):
            stop = stops[cursor]
            cursor += 1
            minute = hhmm(stop["time"])
            if stop["station"] == point["station"] and minute is not None and minute % 1440 == point["minute"] % 1440:
                break
        else:
            return False
    return True


def publication_groups(mother, reciprocal):
    verify_mother(mother)
    if mother["sourceSha256"] != reciprocal.get("sourceSha256"):
        raise RuntimeError("mother/reciprocal PDF hashes differ")
    if reciprocal.get("identityPolicy", {}).get("runtimeSameTrainPromotions") != 0:
        raise RuntimeError("reciprocal audit contains runtime promotion")
    # Rebuild from metadata, so a modified link list or misleading count cannot
    # bypass the reciprocal-page and singleton checks.
    links, _ = resolve_links(reciprocal["metadata"])
    if links != reciprocal.get("links") or len(links) != reciprocal.get("candidateLinkCount"):
        raise RuntimeError("reciprocal link inventory does not match its metadata")
    member_of = {f: c["id"] for c in mother["components"] for f in c["fragments"]}
    parent = {c["id"]: c["id"] for c in mother["components"]}
    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node
    for link in links:
        if link["fromFragment"] not in member_of or link["toFragment"] not in member_of:
            raise RuntimeError("reciprocal link references missing mother fragment")
        a, b = find(member_of[link["fromFragment"]]), find(member_of[link["toFragment"]])
        if a != b:
            parent[max(a, b)] = min(a, b)
    roots = {c: find(c) for c in parent}
    groups = defaultdict(list)
    for component in mother["components"]:
        groups[roots[component["id"]]].extend(component["fragments"])
    return roots, dict(groups)


def verify_metadata_matches_stops(reciprocal, stops):
    by_id = {f["id"]: f for f in stops["fragments"]}
    metadata = reciprocal["metadata"]
    if len(metadata) != len(by_id) or {r["id"] for r in metadata} != set(by_id):
        raise RuntimeError("reciprocal metadata omits or duplicates a local column")
    for row in metadata:
        for key in ("page", "section", "column", "calendar", "printedTrainNumber"):
            if row[key] != by_id[row["id"]][key]:
                raise RuntimeError(f"reciprocal metadata disagrees with source column: {row['id']} {key}")


def ordered_toei_score(fingerprint, trip):
    result = score_trip(fingerprint, trip)
    stations = list(trip["stops"])
    positions = [stations.index(PDF_TO_ODPT_SUFFIX[p["station"]])
                 if PDF_TO_ODPT_SUFFIX[p["station"]] in stations else -1 for p in fingerprint]
    result["printedOrderMatches"] = bool(positions) and min(positions) >= 0 and all(a < b for a, b in zip(positions, positions[1:]))
    return result


def refine(base, candidates, fingerprints, toei_fingerprints, timetable, stops, mother, reciprocal, boundaries):
    if base["sourceSha256"] != mother["sourceSha256"] or base["sourceSha256"] != stops["source"]["sha256"]:
        raise RuntimeError("input PDF hashes differ")
    verify_metadata_matches_stops(reciprocal, stops)
    roots, groups = publication_groups(mother, reciprocal)
    fragments = {f["id"]: f for f in stops["fragments"]}
    boundary_index = defaultdict(set)
    for group, members in groups.items():
        for fid in members:
            f = fragments[fid]
            for stop in f["stopTimes"]:
                if stop["station"] == "泉岳寺":
                    boundary_index[(f["calendar"], stop["event"], hhmm(stop["time"]))].add(group)
    trips = build_trip_index(timetable)
    results = []
    for row in base["results"]:
        cid = row["candidateId"]
        if cid not in candidates:
            raise RuntimeError("official candidate missing from source re-extraction")
        fp = fingerprints[cid]
        toei_fp = toei_fingerprints[cid]
        boundary = boundaries[cid]
        transfer_trips = []
        if boundary["status"] == "official-transfer-via-nishimagome":
            for tid, trip in trips.items():
                if not calendar_matches(trip["calendar"], row["calendar"]) or next(iter(trip["stops"]), None) != "NishiMagome":
                    continue
                score = ordered_toei_score(toei_fp, trip)
                if (score["allMatched"] and score["printedOrderMatches"] and score["totalPoints"] >= 3
                        and trip["stops"]["NishiMagome"][1] in boundary["nishimagomeDepartureMinutes"]):
                    transfer_trips.append(tid)
        original_toei = row["toeiMatches"]
        toei_scored = [{"timetableId": tid, **ordered_toei_score(toei_fp, trips[tid])} for tid in original_toei]
        exact_toei = [r["timetableId"] for r in toei_scored if r["allMatched"] and r["printedOrderMatches"] and r["totalPoints"] >= 3]
        # The baseline deliberately stopped before the Keikyu lookup whenever
        # Toei was ambiguous. Repeat the SAME exact-event local lookup for all
        # source-verified columns, so a newly unique Toei sequence can proceed.
        inbound = row["direction"] == "toei-to-keikyu"
        minute = row["targetBoundaryMinute"] if inbound else row["sourceBoundaryMinute"]
        candidate_groups = sorted(boundary_index.get((row["calendar"], "departure" if inbound else "arrival", minute), set()))
        supports = {g: [f for f in groups[g] if sequence_matches(fp, fragments[f])] for g in candidate_groups}
        exact_groups = [g for g in candidate_groups if supports[g]]
        if boundary["status"] != "official-continuation-arrow":
            status = boundary["status"]
        elif row["toeiMatchStatus"] not in ("matched-singleton", "ambiguous"):
            status = "toei-" + row["toeiMatchStatus"]
        elif len(exact_toei) != 1:
            status = "toei-sequence-unmatched" if not exact_toei else "toei-sequence-ambiguous"
        elif len({p["station"] for p in fp}) < 2:
            status = "keikyu-insufficient-published-sequence"
        elif len(exact_groups) == 1:
            status = "both-local-published-sequence-singleton"
        elif not exact_groups:
            status = "keikyu-sequence-unmatched"
        else:
            status = "keikyu-sequence-ambiguous"
        results.append({**row, "publishedSequenceStatus": status,
                        "officialBoundaryClassification": boundary,
                        "transferToeiSequenceMatches": transfer_trips,
                        "keikyuFingerprint": fp, "toeiFingerprint": toei_fp,
                        "toeiSequenceComparisons": toei_scored, "toeiSequenceMatches": exact_toei,
                        "reciprocalCandidateGroups": candidate_groups,
                        "keikyuSequenceMatches": exact_groups, "supportingOfficialColumns": supports})
    # Recheck uniqueness after disambiguation; new singleton results must not
    # consume another candidate's local identity in either direction.
    singletons = [r for r in results if r["publishedSequenceStatus"] == "both-local-published-sequence-singleton"]
    toei_counts = Counter(r["toeiSequenceMatches"][0] for r in singletons)
    keikyu_counts = Counter(r["keikyuSequenceMatches"][0] for r in singletons)
    for row in singletons:
        if toei_counts[row["toeiSequenceMatches"][0]] != 1 or keikyu_counts[row["keikyuSequenceMatches"][0]] != 1:
            row["publishedSequenceStatus"] = "conflicting-local-targets"
    return {
        "version": 2, "kind": "sengakuji-reciprocal-publication-sequence-audit",
        "sourceSha256": base["sourceSha256"], "officialColumnCandidateCount": len(results),
        "statusCounts": dict(Counter(r["publishedSequenceStatus"] for r in results)),
        "boundaryStatusCounts": dict(Counter(r["officialBoundaryClassification"]["status"] for r in results)),
        "previousStatusCounts": base["statusCounts"], "reciprocalLinkCount": len(reciprocal["links"]),
        "publicationGroupCount": len(groups), "coverageComplete": False,
        "identityPolicy": {
            "samePrintedColumnAloneProvesThroughService": False,
            "crossingRequiresExplicitContinuationArrowAndNoBranchTrain": True,
            "bothLocalPublishedSequencesRequired": True,
            "allPublishedSequencePointsMustMatchInOrder": True, "reciprocalPageEvidenceRequiredForPublicationGrouping": True,
            "clockTimeProximityMayEstablishIdentity": False, "trainNumberAloneMayEstablishIdentity": False,
            "overlappingPublishedStopsMayBeConcatenated": False, "runtimeSameTrainPromotions": 0,
        },
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stops", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--mother", type=Path, required=True)
    parser.add_argument("--reciprocal", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=Path("docs/transit/sengakuji-independent-reconciliation-audit.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdf-cache-dir", type=Path)
    args = parser.parse_args()
    stops, graph, mother, reciprocal = (load(p) for p in (args.stops, args.graph, args.mother, args.reciprocal))
    baseline = load(args.baseline)
    candidates, k_fps, t_fps, boundaries, source_rows = {}, {}, {}, {}, []
    for calendar, url in (("weekday", DEFAULT_WEEKDAY_URL), ("holiday", DEFAULT_HOLIDAY_URL)):
        cached = args.pdf_cache_dir / f"other_{calendar}.pdf" if args.pdf_cache_dir else None
        content = cached.read_bytes() if cached and cached.exists() else fetch_pdf(url)
        digest = hashlib.sha256(content).hexdigest()
        recorded = [r for r in baseline["connectionSources"] if r["calendar"] == calendar and r["url"] == url]
        if len(recorded) != 1 or recorded[0]["sha256"] != digest:
            raise RuntimeError("official connection PDF changed; rebuild the baseline first")
        if cached and not cached.exists():
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(content)
        print(f"{calendar}: source hash verified", flush=True)
        extracted = extract_pdf(content, calendar, url)
        words = page_words(content, {c["pdfPage"] for c in extracted})
        caches = {p: build_page_cache(w) for p, w in words.items()}
        k_caches = {p: keikyu_page_cache(w, caches[p]) for p, w in words.items()}
        for c in extracted:
            candidates[c["id"]] = c
            k_fps[c["id"]] = keikyu_fingerprint(k_caches[c["pdfPage"]], c)
            t_fps[c["id"]] = extract_pdf_fingerprint(caches[c["pdfPage"]], c)
            boundaries[c["id"]] = classify_boundary(k_caches[c["pdfPage"]], c)
        source_rows.append(dict(calendar=calendar, url=url, sha256=digest))
        print(f"{calendar}: {len(extracted)} official columns fingerprinted", flush=True)
    timetable_path = Path("data/transit/toei/timetables/899209dea5fc3a.json")
    timetable = load(timetable_path)
    base = reconcile(list(candidates.values()), timetable, stops, graph, load(Path("data/transit/toei/timetable-index.json")))
    if base["statusCounts"] != baseline["statusCounts"]:
        raise RuntimeError("baseline local candidate population changed")
    payload = refine(base, candidates, k_fps, t_fps, timetable, stops, mother, reciprocal, boundaries)
    payload["connectionSources"] = source_rows
    payload["toeiSourceSha256"] = hashlib.sha256(timetable_path.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("officialColumnCandidateCount", "statusCounts", "reciprocalLinkCount", "publicationGroupCount")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
