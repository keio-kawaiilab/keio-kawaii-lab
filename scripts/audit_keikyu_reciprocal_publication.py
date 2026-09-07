#!/usr/bin/env python3
"""Audit explicit reciprocal publication references, never runtime continuations.

The connection panels put 前の掲載ページ BELOW their own train-number header.
The existing preceding-header extractor intentionally does not consume these.
Here a source column's 次の掲載ページ and a destination column's 前の掲載ページ
must point to each other's uniquely identified printed pages, with one literal
train number and one printed calendar on both sides. Numbers alone, times,
destinations and page adjacency cannot create a link. A link identifies repeat
publication; it must not cause overlapping stop rows to be concatenated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from audit_keikyu_previous_publication_refs import (
    _assign_tokens, _parse_printed_page, _row_y, detect_printed_page_number,
)
from build_keikyu_independent_mother_set_audit import build_audit as mother_audit
from build_keikyu_cross_page_identity_audit import _find_cycles
from keikyu_official_pdf import bbox_words, cluster_by_y, detect_train_column_sections, _label_span
from verify_keikyu_independent_mother_set_audit import verify as verify_mother


def extract_section_reference_rows(words, sections):
    rows = cluster_by_y(words)
    output = {}
    for i, section in enumerate(sections):
        next_header = sections[i + 1].grid.header_y if i + 1 < len(sections) else float("inf")
        previous = [r for r in rows if section.grid.header_y < _row_y(r) < section.y_max
                    and _label_span(r, "前の掲載ページ") is not None]
        following = [r for r in rows if section.y_max <= _row_y(r) < next_header
                     and _label_span(r, "次の掲載ページ") is not None]
        entry = {}
        for kind, candidates, label in (("previous", previous, "前の掲載ページ"),
                                        ("next", following, "次の掲載ページ")):
            entry[kind + "RowCount"] = len(candidates)
            entry[kind + "RowY"] = round(_row_y(candidates[0]), 3) if len(candidates) == 1 else None
            entry[kind + "Pages"] = (_assign_tokens(candidates[0], section.grid, label=label, parser=_parse_printed_page)
                                      if len(candidates) == 1 else [None] * len(section.grid.centers))
        output[section.section_index] = entry
    return output


def resolve_links(metadata):
    by_id = {r["id"]: r for r in metadata}
    if len(by_id) != len(metadata):
        raise RuntimeError("duplicate local identity in reciprocal metadata")
    printed_to_pdf = defaultdict(set)
    targets = defaultdict(list)
    for row in metadata:
        if row.get("printedPage") is not None:
            printed_to_pdf[row["printedPage"]].add(row["page"])
        if row.get("printedTrainNumber"):
            targets[(row.get("printedPage"), row["printedTrainNumber"])].append(row)
    results, links = [], []
    for row in metadata:
        if row.get("previousPrintedPage") is None:
            continue
        previous_page, number = row["previousPrintedPage"], row.get("printedTrainNumber")
        hits = targets.get((previous_page, number), []) if number else []
        status = "unresolved"
        if row.get("calendar") not in ("weekday", "holiday"):
            status = "missing-literal-calendar"
        elif len(printed_to_pdf[previous_page]) != 1 or len(printed_to_pdf[row.get("printedPage")]) != 1:
            status = "unmapped-or-ambiguous-printed-page"
        elif not number:
            status = "missing-literal-train-number"
        elif len(hits) != 1:
            status = "missing-or-ambiguous-previous-column"
        elif hits[0]["id"] == row["id"]:
            status = "self-reference"
        elif hits[0].get("calendar") != row["calendar"]:
            status = "calendar-mismatch"
        elif hits[0].get("nextPrintedPage") != row.get("printedPage"):
            status = "missing-reciprocal-next-page"
        else:
            status = "reciprocal-publication-candidate"
            source = hits[0]
            links.append({
                "fromFragment": source["id"], "toFragment": row["id"],
                "calendar": row["calendar"], "printedTrainNumber": number,
                "sourcePrintedPage": source["printedPage"], "targetPrintedPage": row["printedPage"],
                "sourceNextPrintedPage": source["nextPrintedPage"],
                "targetPreviousPrintedPage": row["previousPrintedPage"],
                "sourceNextRowY": source["nextRowY"], "targetPreviousRowY": row["previousRowY"],
                "evidence": "official-reciprocal-publication-pages-and-unique-literal-train-number",
            })
        results.append({"fragment": row["id"], "previousPrintedPage": previous_page,
                        "previousColumnCandidates": [r["id"] for r in hits], "status": status})
    # A reciprocal repeat-publication relation must be one-to-one. Preserve
    # conflicts in diagnostics and exclude every involved link, never choose.
    outgoing = Counter(e["fromFragment"] for e in links)
    incoming = Counter(e["toFragment"] for e in links)
    conflicted = {e["toFragment"] for e in links if outgoing[e["fromFragment"]] != 1 or incoming[e["toFragment"]] != 1}
    for result in results:
        if result["fragment"] in conflicted:
            result["status"] = "conflicting-reciprocal-columns"
    links = [e for e in links if e["toFragment"] not in conflicted]
    outgoing_graph = defaultdict(list)
    for e in links:
        outgoing_graph[e["fromFragment"]].append(e["toFragment"])
    cycles = _find_cycles({n for e in links for n in (e["fromFragment"], e["toFragment"])}, outgoing_graph)
    cyclic_nodes = {n for cycle in cycles for n in cycle}
    if cyclic_nodes:
        for result in results:
            if result["fragment"] in cyclic_nodes:
                result["status"] = "cyclic-publication-reference"
        links = [e for e in links if e["fromFragment"] not in cyclic_nodes and e["toFragment"] not in cyclic_nodes]
    return links, results


def build_audit(pdf, stops, graph):
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if digest != (stops.get("source") or {}).get("sha256"):
        raise RuntimeError("PDF and stop dataset source hashes differ")
    mother = mother_audit(stops, graph)
    verify_mother(mother)
    by_page = defaultdict(list)
    for fragment in stops["fragments"]:
        by_page[fragment["page"]].append(fragment)
    metadata = []
    for page, fragments in sorted(by_page.items()):
        width, height, words = bbox_words(pdf, page)
        printed_page = detect_printed_page_number(width, height, words)
        sections = detect_train_column_sections(words)
        by_section = {s.section_index: s for s in sections}
        refs = extract_section_reference_rows(words, sections)
        for fragment in fragments:
            section, column = fragment["section"], fragment["column"]
            detected = by_section.get(section)
            if (detected is None or column >= len(detected.grid.centers)
                    or abs(detected.grid.centers[column] - fragment["columnCenterX"]) > .001
                    or detected.grid.explicit_numbers[column] != fragment["printedTrainNumber"]):
                raise RuntimeError(f"stale section grid: {fragment['id']}")
            row = refs[section]
            metadata.append({
                **{key: fragment[key] for key in ("id", "page", "section", "column", "calendar", "printedTrainNumber")},
                "printedPage": printed_page,
                "previousPrintedPage": row["previousPages"][column], "nextPrintedPage": row["nextPages"][column],
                **{key: row[key] for key in ("previousRowY", "nextRowY", "previousRowCount", "nextRowCount")},
            })
    links, results = resolve_links(metadata)
    return {
        "version": 1, "kind": "keikyu-reciprocal-publication-audit", "sourceSha256": digest,
        "metadataFragmentCount": len(metadata), "candidateLinkCount": len(links),
        "calendarLinkCounts": dict(Counter(e["calendar"] for e in links)),
        "referenceStatusCounts": dict(Counter(r["status"] for r in results)),
        "identityPolicy": {
            "bothOfficialPageReferencesRequired": True, "uniquePrintedPageAndTrainColumnRequired": True,
            "literalPrintedCalendarsMustMatch": True, "repeatedPublicationIsNotAdditionalTrain": True,
            "clockTimeUsedForIdentity": False, "destinationUsedForIdentity": False,
            "trainNumberAloneMayEstablishIdentity": False, "runtimeSameTrainPromotions": 0,
        },
        "links": links, "results": results, "metadata": metadata,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--stops", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_audit(args.pdf, json.loads(args.stops.read_text()), json.loads(args.graph.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k not in ("links", "results", "metadata")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
