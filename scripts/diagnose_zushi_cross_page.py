#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import keikyu_cross_page_zushi_evidence as cross
import keikyu_internal_official_evidence as base
import keikyu_missing_boundary_evidence as current
import keikyu_schedule_all_zushi_evidence as local


def load(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise RuntimeError(f'expected JSON object: {path}')
    return value


def official_hits(
    fragment_id: str,
    anchors: dict[str, list[dict[str, Any]]],
    index: dict[tuple[str, int], list[dict[str, Any]]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for anchor in anchors.get(fragment_id, []):
        key = (str(anchor.get('suffix') or ''), int(anchor.get('minute') or 0) % 1440)
        for hit in index.get(key, []):
            out.append((anchor, hit))
    return out


def path_components(
    source_id: str,
    target_id: str,
    anchors: dict[str, list[dict[str, Any]]],
    index: dict[tuple[str, int], list[dict[str, Any]]],
    outgoing: dict[str, dict[str, Any]],
    roots: dict[str, str],
) -> tuple[set[str], bool, bool]:
    """Return directed-path components, any same component, any opposite/reverse path.

    This is diagnostic only. Reverse reachability is NEVER identity evidence; it is
    counted only to explain why a current candidate failed the required official
    publication direction.
    """
    directed_components: set[str] = set()
    same_component = False
    reverse_path = False
    for left in anchors.get(source_id, []):
        left_hits = index.get((str(left.get('suffix') or ''), int(left.get('minute') or 0) % 1440), [])
        for right in anchors.get(target_id, []):
            if str(left.get('station') or '') == str(right.get('station') or ''):
                continue
            right_hits = index.get((str(right.get('suffix') or ''), int(right.get('minute') or 0) % 1440), [])
            for a in left_hits:
                af = str(a.get('officialFragment') or '')
                ar = roots.get(af)
                if not ar:
                    continue
                for b in right_hits:
                    bf = str(b.get('officialFragment') or '')
                    if not bf or bf == af or roots.get(bf) != ar:
                        continue
                    same_component = True
                    if cross.directed_path(af, bf, outgoing):
                        directed_components.add(ar)
                    elif cross.directed_path(bf, af, outgoing):
                        reverse_path = True
    return directed_components, same_component, reverse_path


def classify_source(
    source: dict[str, Any],
    pair: tuple[str, str],
    fragments: list[dict[str, Any]],
    anchors: dict[str, list[dict[str, Any]]],
    official_index: dict[tuple[str, int], list[dict[str, Any]]],
    outgoing: dict[str, dict[str, Any]],
    roots: dict[str, str],
) -> tuple[str, dict[str, Any]]:
    source_id = str(source.get('id') or '')
    candidates = current.candidate_targets(source, pair, fragments)
    source_anchors = anchors.get(source_id, [])
    source_hits = official_hits(source_id, anchors, official_index)
    detail: dict[str, Any] = {
        'fragment': source_id,
        'calendar': base.service_of(source),
        'direction': f"{pair[0].rsplit('.', 1)[-1].lower()}-to-{pair[1].rsplit('.', 1)[-1].lower()}",
        'candidateCount': len(candidates),
        'sourceSingletonAnchorCount': len(source_anchors),
        'sourceOfficialHitCount': len(source_hits),
        'targetWithSingletonAnchor': 0,
        'targetWithOfficialHit': 0,
        'candidateWithSameOfficialComponent': 0,
        'candidateWithRequiredDirectedPath': 0,
        'candidateWithReverseOnlyPath': 0,
        'candidateWithAmbiguousDirectedComponents': 0,
        'provenTargetCount': 0,
    }
    if not candidates:
        return 'no-search-candidate', detail
    if not source_anchors:
        return 'source-has-no-singleton-anchor', detail
    if not source_hits:
        return 'source-singleton-anchors-have-no-official-hit', detail

    for target, _gap in candidates:
        target_id = str(target.get('id') or '')
        target_anchors = anchors.get(target_id, [])
        if target_anchors:
            detail['targetWithSingletonAnchor'] += 1
        target_hits = official_hits(target_id, anchors, official_index)
        if target_hits:
            detail['targetWithOfficialHit'] += 1
        components, same_component, reverse_path = path_components(
            source_id, target_id, anchors, official_index, outgoing, roots
        )
        if same_component:
            detail['candidateWithSameOfficialComponent'] += 1
        if components:
            detail['candidateWithRequiredDirectedPath'] += 1
        if reverse_path and not components:
            detail['candidateWithReverseOnlyPath'] += 1
        if len(components) > 1:
            detail['candidateWithAmbiguousDirectedComponents'] += 1
        proof = cross.cross_page_proof(source, target, anchors, official_index, outgoing, roots)
        if proof is not None:
            detail['provenTargetCount'] += 1

    if detail['provenTargetCount'] > 1:
        return 'multiple-current-targets-have-strict-proof', detail
    if detail['provenTargetCount'] == 1:
        return 'strict-proof-exists', detail
    if detail['targetWithSingletonAnchor'] == 0:
        return 'all-search-targets-lack-singleton-anchor', detail
    if detail['targetWithOfficialHit'] == 0:
        return 'all-search-target-singleton-anchors-lack-official-hit', detail
    if detail['candidateWithSameOfficialComponent'] == 0:
        return 'no-candidate-shares-explicit-official-component', detail
    if detail['candidateWithRequiredDirectedPath'] == 0:
        if detail['candidateWithReverseOnlyPath']:
            return 'official-component-found-but-only-reverse-reference-path', detail
        return 'same-official-component-but-no-required-directed-path', detail
    if detail['candidateWithAmbiguousDirectedComponents']:
        return 'directed-proof-ambiguous-across-official-components', detail
    return 'directed-official-path-exists-but-proof-remains-nonunique', detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--coverage', default='data/transit-v2/coverage.json')
    ap.add_argument('--fragments', default='data/transit-v2/fragments/keikyu.json')
    ap.add_argument('--official-stop-times', required=True)
    ap.add_argument('--cross-page-audit', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()

    coverage = load(args.coverage)
    fragment_payload = load(args.fragments)
    stop_times = load(args.official_stop_times)
    audit = load(args.cross_page_audit)
    cross.validate_cross_page_sources(stop_times, audit)

    fragments = [r for r in fragment_payload.get('fragments') or [] if isinstance(r, dict) and r.get('id')]
    by_id = {str(r.get('id') or ''): r for r in fragments}
    rows = current.unresolved_sources(coverage, by_id, boundary_id=base.ZUSHI_BOUNDARY_ID)
    owners = current.anchor_owner_index(fragments)
    anchors = current.singleton_anchor_cache(fragments, owners)
    index = local.official_anchor_index(stop_times)
    official_ids = {str(r.get('id') or '') for r in stop_times.get('fragments') or [] if isinstance(r, dict) and r.get('id')}
    outgoing, incoming = cross.build_graph(audit, official_ids)
    roots = cross.component_roots(official_ids, incoming)

    reason_counts: Counter[str] = Counter()
    by_direction: dict[str, Counter[str]] = defaultdict(Counter)
    by_calendar: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    totals: Counter[str] = Counter()

    for _unresolved, source, pair in rows:
        reason, detail = classify_source(source, pair, fragments, anchors, index, outgoing, roots)
        reason_counts[reason] += 1
        by_direction[str(detail['direction'])][reason] += 1
        by_calendar[str(detail['calendar'])][reason] += 1
        for key in (
            'candidateCount', 'sourceSingletonAnchorCount', 'sourceOfficialHitCount',
            'targetWithSingletonAnchor', 'targetWithOfficialHit',
            'candidateWithSameOfficialComponent', 'candidateWithRequiredDirectedPath',
            'candidateWithReverseOnlyPath', 'candidateWithAmbiguousDirectedComponents',
            'provenTargetCount',
        ):
            totals[key] += int(detail.get(key) or 0)
        if len(examples[reason]) < 5:
            examples[reason].append(detail)

    payload = {
        'kind': 'keikyu-zushi-explicit-cross-page-failure-diagnosis',
        'eligibleUnresolvedSources': len(rows),
        'officialCrossPageEdges': len(outgoing),
        'reasonCounts': dict(reason_counts.most_common()),
        'byDirection': {k: dict(v.most_common()) for k, v in sorted(by_direction.items())},
        'byCalendar': {k: dict(v.most_common()) for k, v in sorted(by_calendar.items())},
        'aggregateGateCounts': dict(totals),
        'examples': dict(examples),
        'safety': {
            'diagnosticOnly': True,
            'runtimeSameTrainPromotions': 0,
            'reverseReferencePathMayEstablishIdentity': False,
            'destinationMayEstablishIdentity': False,
            'timeProximityMayEstablishIdentity': False,
            'trainNumberAloneMayEstablishIdentity': False,
        },
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'eligibleUnresolvedSources': len(rows),
        'officialCrossPageEdges': len(outgoing),
        'reasonCounts': payload['reasonCounts'],
        'byDirection': payload['byDirection'],
        'byCalendar': payload['byCalendar'],
        'aggregateGateCounts': payload['aggregateGateCounts'],
        'runtimeSameTrainPromotions': 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
