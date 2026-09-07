"""Synthetic printed-calendar fixtures; never production timetable evidence."""
from collections import Counter, defaultdict

from build_keikyu_official_stop_times import fragment_id
from build_keikyu_cross_page_identity_audit import _components

SHA = "a" * 64


def fragment(page, col, number, resolved, unresolved=0, *, anonymous=None,
             section=0, calendar="weekday"):
    return {
        "id": fragment_id(page, section, col), "page": page, "section": section,
        "column": col, "calendar": calendar, "headerOrdinal": section,
        "sectionYMin": 100.0, "sectionYMax": 600.0, "columnCenterX": 100.0 + col * 15,
        "printedTrainNumber": number, "anonymousColumn": number is None if anonymous is None else anonymous,
        "stopTimes": [{"station": "品川", "event": "departure", "time": "1000",
                       "rowY": 200.0 + i * 10, "resolution": "same-row-station-title"}
                      for i in range(resolved)],
        "unresolvedCells": [{"time": "1001", "rowY": 300.0 + i * 10} for i in range(unresolved)],
    }


def stop_payload(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["page"], row["section"])].append(row)
    pages = {}
    for (page, section), members in sorted(groups.items()):
        first = members[0]
        resolved = sum(len(f["stopTimes"]) for f in members)
        unresolved = sum(len(f["unresolvedCells"]) for f in members)
        summary = dict(section=section, calendar=first["calendar"], headerOrdinal=section,
                       yMin=100.0, yMax=600.0, fragmentCount=len(members),
                       resolvedTimeCells=resolved, unresolvedTimeCells=unresolved,
                       sourceTimeCells=resolved + unresolved)
        parent = pages.setdefault(page, dict(page=page, calendar=first["calendar"], sections=[]))
        parent["sections"].append(summary)
    for page in pages.values():
        page["sectionCount"] = len(page["sections"])
        for field in ("fragmentCount", "resolvedTimeCells", "unresolvedTimeCells", "sourceTimeCells"):
            page[field] = sum(s[field] for s in page["sections"])
    page_rows = list(pages.values())
    return {
        "version": 4, "kind": "keikyu-official-section-local-stop-times",
        "source": {"sha256": SHA}, "pages": page_rows, "fragments": rows,
        "excludedPages": [], "calendarExcludedPages": [],
        "calendarCounts": {
            "pages": dict(Counter(p["calendar"] for p in page_rows)),
            "sections": dict(Counter(s["calendar"] for p in page_rows for s in p["sections"])),
            "fragments": dict(Counter(f["calendar"] for f in rows)),
        },
        "totals": {
            **{field: sum(p[field] for p in page_rows)
               for field in ("resolvedTimeCells", "unresolvedTimeCells", "sourceTimeCells")},
            "trainColumnFragments": len(rows), "timetableSections": len(groups),
            "explicitTrainNumberFragments": sum(f["printedTrainNumber"] is not None for f in rows),
            "anonymousFragments": sum(f["printedTrainNumber"] is None for f in rows),
        },
        "identityPolicy": {
            **{key: True for key in ("pageSectionColumnIsExactLocalIdentity",
               "literalTrainNumberRowsAreHardSectionBoundaries", "literalPrintedCalendarRequired",
               "unclassifiedCalendarPagesExcludedFromIdentity")},
            **{key: False for key in ("printedTrainNumberMayJoinSectionsOrPages",
               "anonymousColumnMayJoinSectionsOrPages", "calendarMayBeInferredFromPageNumber",
               "calendarMayBeInferredFromNeighboringPages", "clockTimeProximityMayJoinFragments",
               "destinationMayJoinFragments", "crossPageIdentityEstablished")},
            "minimumDistinctTimedRowsPerIdentitySection": 3, "runtimeSameTrainPromotions": 0,
        },
    }


def graph(edges, rows=()):
    by_id = {r["id"]: r for r in rows}
    nodes = {n for pair in edges for n in pair}
    groups = _components(nodes, edges) if nodes else []
    evidence = []
    for source, target in edges:
        previous, current = by_id.get(source, {}), by_id.get(target, {})
        evidence.append({
            "fromFragment": source, "toFragment": target,
            "evidence": "keikyu-official-previous-publication-page-and-train-number",
            "previousPrintedPage": int(source.split(":p")[1][:3]),
            "previousPdfPage": int(source.split(":p")[1][:3]),
            "currentPdfPage": int(target.split(":p")[1][:3]),
            "previousSection": int(source.split(":s")[1][:2]),
            "currentSection": int(target.split(":s")[1][:2]),
            "previousTrainNumber": previous.get("printedTrainNumber", "100A"),
            "currentTrainNumber": current.get("printedTrainNumber"),
            "calendar": previous.get("calendar", "weekday"),
        })
    return {
        "version": 3, "kind": "keikyu-official-section-cross-page-identity-audit",
        "sourceSha256": SHA, "candidateReferenceCount": len(edges),
        "materializedCandidateEdgeCount": len(edges), "nodeCount": len(nodes),
        "identityComponentCount": len(groups),
        "componentSizeHistogram": dict(Counter(str(len(g)) for g in groups)),
        "branchingTargets": {}, "multiplePreviousSources": {}, "cycles": [], "issues": [],
        "calendarEdgeCounts": {c: sum(e["calendar"] == c for e in evidence) for c in ("weekday", "holiday")},
        "edges": evidence,
        "identityPolicy": {
            **{key: True for key in ("officialPreviousPublicationPageRequired",
               "officialPreviousTrainNumberRequired", "uniqueTargetFragmentRequired",
               "pageSectionLocalFragmentMetadataMustMatch", "officialSectionIdentityRequired",
               "literalPrintedCalendarRequired", "unclassifiedCalendarPagesExcludedFromIdentity",
               "crossPageEdgesStayWithinPrintedCalendar")},
            **{key: False for key in ("clockTimeUsedForIdentity", "destinationUsedForIdentity",
               "branchingAllowedForPromotion", "cyclesAllowedForPromotion", "crossPageIdentityEstablished",
               "calendarMayBeInferredFromPageNumber", "calendarMayBeInferredFromNeighboringPages")},
            "runtimeSameTrainPromotions": 0,
        },
    }
