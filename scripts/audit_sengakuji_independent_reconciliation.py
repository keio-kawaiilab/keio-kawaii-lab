#!/usr/bin/env python3
"""Audit both local identities behind official Sengakuji same-column evidence.

No runtime output. Same-column evidence is only a candidate inventory and may
include transfers. The explicit continuation-marker audit must gate identity.
Exact boundary events nominate local records. Ambiguous independent
PDF components, duplicate targets and missing cells remain unresolved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from audit_toei_sengakuji_official_columns import audit, load, TOEI_FILE
from build_keikyu_independent_mother_set_audit import build_audit
from verify_keikyu_independent_mother_set_audit import verify
from audit_toei_asakusa_service_day import build_service_day_audit
from verify_toei_asakusa_service_day import verify as verify_toei
from keikyu_official_train_evidence import (
    DEFAULT_WEEKDAY_URL, DEFAULT_HOLIDAY_URL, extract_pdf, fetch_pdf, hhmm,
)


def reconcile(candidates, timetable, stop_times, graph, toei_index):
    toei_mother = build_service_day_audit(toei_index, timetable)
    toei_summary = verify_toei(toei_mother)
    mother = build_audit(stop_times, graph)
    verify(mother)
    toei = audit(candidates, timetable)
    component_for = {f: c["id"] for c in mother["components"] for f in c["fragments"]}
    index = defaultdict(set)
    for fragment in stop_times["fragments"]:
        component = component_for.get(fragment["id"])
        if component is None:
            continue
        for stop in fragment["stopTimes"]:
            if stop["station"] == "泉岳寺":
                index[(fragment["calendar"], stop["event"], hhmm(stop["time"]))].add(component)

    results = []
    for row in toei["results"]:
        matches = []
        if row["toeiMatchStatus"] == "matched-singleton":
            inbound = row["direction"] == "toei-to-keikyu"
            minute = row["targetBoundaryMinute"] if inbound else row["sourceBoundaryMinute"]
            matches = sorted(index.get((row["calendar"], "departure" if inbound else "arrival", minute), set()))
            status = "both-local-singleton-candidate" if len(matches) == 1 else "keikyu-unmatched" if not matches else "keikyu-ambiguous"
        else:
            status = "toei-" + row["toeiMatchStatus"]
        results.append({**row, "keikyuComponentMatches": matches, "reconciliationStatus": status})

    # One local component cannot be consumed by several crossing columns in
    # this audit. Do not select a winner by number, destination or time gap.
    targets = Counter(r["keikyuComponentMatches"][0] for r in results
                      if r["reconciliationStatus"] == "both-local-singleton-candidate")
    conflicts = {key: n for key, n in targets.items() if n > 1}
    for row in results:
        if row["reconciliationStatus"] == "both-local-singleton-candidate" and row["keikyuComponentMatches"][0] in conflicts:
            row["reconciliationStatus"] = "conflicting-keikyu-component"
    return {
        "version": 1, "kind": "sengakuji-independent-local-identity-reconciliation-audit",
        "sourceSha256": mother["sourceSha256"],
        "officialColumnCandidateCount": len(candidates),
        "statusCounts": dict(sorted(Counter(r["reconciliationStatus"] for r in results).items())),
        "toeiStatusCounts": toei["statusCounts"],
        "toeiMotherSetSummary": toei_summary,
        "calendarCounts": dict(Counter(c["calendar"] for c in candidates)),
        "directionCounts": dict(Counter(c["direction"] for c in candidates)),
        "keikyuMotherSetSummary": {k: v for k, v in mother.items()
                                  if k not in ("components", "structuralBlankFragments", "zeroTimeEvidenceBearingFragments")},
        "conflictingKeikyuComponents": conflicts, "issues": toei["issues"],
        "coverageComplete": False,
        "identityPolicy": {
            "crossBoundaryFactComesFromOfficialSamePrintedColumn": False,
            "explicitContinuationMarkerGateStillRequired": True,
            "bothLocalIdentitiesMustResolveSingleton": True,
            "duplicateTargetsMayBeSelectedArbitrarily": False,
            "clockTimeProximityMayEstablishIdentity": False,
            "trainNumberAloneMayEstablishIdentity": False,
            "destinationMayEstablishIdentity": False,
            "runtimeSameTrainPromotions": 0,
        },
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stop_times", type=Path)
    parser.add_argument("identity_graph", type=Path)
    parser.add_argument("--toei", type=Path, default=TOEI_FILE)
    parser.add_argument("--toei-index", type=Path, default=Path("data/transit/toei/timetable-index.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdf-cache-dir", type=Path)
    args = parser.parse_args()
    candidates, sources = [], []
    for calendar, url in (("weekday", DEFAULT_WEEKDAY_URL), ("holiday", DEFAULT_HOLIDAY_URL)):
        cached = args.pdf_cache_dir / f"other_{calendar}.pdf" if args.pdf_cache_dir else None
        content = cached.read_bytes() if cached and cached.exists() else fetch_pdf(url)
        extracted = extract_pdf(content, calendar, url)
        sources.append(dict(calendar=calendar, url=url, sha256=hashlib.sha256(content).hexdigest(),
                            extractedColumns=len(extracted)))
        candidates.extend(extracted)
    payload = reconcile(candidates, load(args.toei), load(args.stop_times), load(args.identity_graph), load(args.toei_index))
    payload["connectionSources"] = sources
    payload["toeiSourceSha256"] = hashlib.sha256(args.toei.read_bytes()).hexdigest()
    payload["toeiIndexSha256"] = hashlib.sha256(args.toei_index.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("officialColumnCandidateCount", "statusCounts", "toeiStatusCounts", "issues")},
                     ensure_ascii=False, indent=2))
    if payload["issues"]:
        raise SystemExit("Sengakuji reconciliation has structural issues; no runtime promotion")


if __name__ == "__main__":
    main()
