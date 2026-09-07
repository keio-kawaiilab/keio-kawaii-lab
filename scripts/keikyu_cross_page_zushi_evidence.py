#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import keikyu_internal_official_evidence as base
import keikyu_missing_boundary_evidence as current
import keikyu_schedule_all_zushi_evidence as local
from keikyu_official_pdf import OFFICIAL_PDF_URL

BOUNDARY_ID = base.ZUSHI_BOUNDARY_ID
MARKER = 'official-previous-publication-chain-two-exact-station-times-v1'
REFERENCE_EVIDENCE = 'keikyu-official-previous-publication-page-and-train-number'


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def validate_cross_page_sources(stop_times: dict[str, Any], audit: dict[str, Any]) -> None:
    local.validate_official_dataset(stop_times)
    if audit.get('kind') != 'keikyu-official-cross-page-identity-audit':
        raise RuntimeError('unexpected cross-page audit kind')
    source_sha = str((stop_times.get('source') or {}).get('sha256') or '')
    audit_sha = str(audit.get('sourceSha256') or '')
    if not source_sha or source_sha != audit_sha:
        raise RuntimeError('cross-page audit source SHA does not match official stop-time source')
    if audit.get('issues') not in ([], None):
        raise RuntimeError('cross-page audit contains safety issues')
    policy = audit.get('identityPolicy') or {}
    required_true = {
        'officialPreviousPublicationPageRequired',
        'officialPreviousTrainNumberRequired',
        'uniqueTargetFragmentRequired',
        'pageLocalFragmentMetadataMustMatch',
    }
    required_false = {
        'clockTimeUsedForIdentity',
        'destinationUsedForIdentity',
        'branchingAllowedForPromotion',
        'cyclesAllowedForPromotion',
    }
    if any(policy.get(key) is not True for key in required_true):
        raise RuntimeError('unsafe explicit previous-publication policy')
    if any(policy.get(key) is not False for key in required_false):
        raise RuntimeError('unsafe cross-page identity policy')
    if int(policy.get('runtimeSameTrainPromotions') or 0) != 0:
        raise RuntimeError('cross-page audit unexpectedly contains runtime promotions')
    if audit.get('branchingTargets') not in ({}, None):
        raise RuntimeError('cross-page graph branches')
    if audit.get('multiplePreviousSources') not in ({}, None):
        raise RuntimeError('cross-page graph has multiple previous sources')
    if audit.get('cycles') not in ([], None):
        raise RuntimeError('cross-page graph contains cycles')


def build_graph(audit: dict[str, Any], official_ids: set[str]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    outgoing: dict[str, dict[str, Any]] = {}
    incoming: dict[str, str] = {}
    for edge in audit.get('edges') or []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get('fromFragment') or '')
        target = str(edge.get('toFragment') or '')
        if source not in official_ids or target not in official_ids:
            raise RuntimeError('stale official fragment in cross-page edge')
        if str(edge.get('evidence') or '') != REFERENCE_EVIDENCE:
            raise RuntimeError('cross-page edge lacks explicit official reference evidence')
        if not edge.get('previousTrainNumber') or edge.get('previousPrintedPage') is None:
            raise RuntimeError('cross-page edge lacks required printed previous-page metadata')
        if source in outgoing and str(outgoing[source].get('toFragment') or '') != target:
            raise RuntimeError('cross-page graph has branching source')
        if target in incoming and incoming[target] != source:
            raise RuntimeError('cross-page graph has multiple previous sources')
        outgoing[source] = edge
        incoming[target] = source
    return outgoing, incoming


def component_roots(official_ids: set[str], incoming: dict[str, str]) -> dict[str, str]:
    roots: dict[str, str] = {}
    for node in official_ids:
        seen: set[str] = set()
        cursor = node
        while cursor in incoming:
            if cursor in seen:
                raise RuntimeError('cycle while resolving cross-page component root')
            seen.add(cursor)
            cursor = incoming[cursor]
        roots[node] = cursor
    return roots


def directed_path(source: str, target: str, outgoing: dict[str, dict[str, Any]]) -> list[dict[str, Any]] | None:
    if source == target:
        return []
    path: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor = source
    while cursor in outgoing:
        if cursor in seen:
            raise RuntimeError('cycle while traversing cross-page continuation')
        seen.add(cursor)
        edge = outgoing[cursor]
        path.append(edge)
        cursor = str(edge.get('toFragment') or '')
        if cursor == target:
            return path
    return None


def cross_page_proof(
    source: dict[str, Any],
    target: dict[str, Any],
    anchors: dict[str, list[dict[str, Any]]],
    official_index: dict[tuple[str, int], list[dict[str, Any]]],
    outgoing: dict[str, dict[str, Any]],
    roots: dict[str, str],
) -> dict[str, Any] | None:
    source_id = str(source.get('id') or '')
    target_id = str(target.get('id') or '')
    matches_by_component: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for left in anchors.get(source_id, []):
        left_hits = official_index.get((str(left.get('suffix') or ''), int(left.get('minute') or 0) % 1440), [])
        for right in anchors.get(target_id, []):
            if str(left.get('station') or '') == str(right.get('station') or ''):
                continue
            right_hits = official_index.get((str(right.get('suffix') or ''), int(right.get('minute') or 0) % 1440), [])
            for a in left_hits:
                left_fragment = str(a.get('officialFragment') or '')
                left_root = roots.get(left_fragment)
                if not left_root:
                    continue
                for b in right_hits:
                    right_fragment = str(b.get('officialFragment') or '')
                    if not right_fragment or right_fragment == left_fragment:
                        continue
                    if roots.get(right_fragment) != left_root:
                        continue
                    path = directed_path(left_fragment, right_fragment, outgoing)
                    if not path:
                        continue
                    matches_by_component[left_root].append({
                        'componentRoot': left_root,
                        'sourceOfficialFragment': left_fragment,
                        'targetOfficialFragment': right_fragment,
                        'sourceAnchor': left,
                        'targetAnchor': right,
                        'sourceOfficialHit': a,
                        'targetOfficialHit': b,
                        'referencePath': path,
                    })

    if len(matches_by_component) != 1:
        return None
    group = next(iter(matches_by_component.values()))
    if not group:
        return None
    chosen = min(
        group,
        key=lambda row: (
            len(row['referencePath']),
            str(row['sourceOfficialFragment']),
            str(row['targetOfficialFragment']),
            str(row['sourceAnchor']),
            str(row['targetAnchor']),
        ),
    )
    chosen['corroboratingAnchorPaths'] = len(group)
    return chosen


def build_entries(
    coverage: dict[str, Any],
    fragments: list[dict[str, Any]],
    stop_times: dict[str, Any],
    cross_page_audit: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validate_cross_page_sources(stop_times, cross_page_audit)
    official_fragments = [row for row in stop_times.get('fragments') or [] if isinstance(row, dict) and row.get('id')]
    official_ids = {str(row.get('id') or '') for row in official_fragments}
    outgoing, incoming = build_graph(cross_page_audit, official_ids)
    roots = component_roots(official_ids, incoming)
    official_index = local.official_anchor_index(stop_times)

    by_id = {str(row.get('id') or ''): row for row in fragments if row.get('id')}
    rows = current.unresolved_sources(coverage, by_id, boundary_id=BOUNDARY_ID)
    owners = current.anchor_owner_index(fragments)
    anchors = current.singleton_anchor_cache(fragments, owners)

    provisional: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    candidate_count = 0
    for _unresolved, source, pair in rows:
        source_id = str(source.get('id') or '')
        candidates = current.candidate_targets(source, pair, fragments)
        candidate_count += len(candidates)
        proven: list[tuple[dict[str, Any], int, dict[str, Any]]] = []
        for target, gap in candidates:
            proof = cross_page_proof(source, target, anchors, official_index, outgoing, roots)
            if proof:
                proven.append((target, gap, proof))
        if len(proven) != 1:
            reasons['no-unique-explicit-cross-page-proof' if not proven else 'multiple-explicit-cross-page-proofs'] += 1
            continue

        target, gap, proof = proven[0]
        spec = base.BOUNDARIES[pair]
        path = proof['referencePath']
        shared_destinations = sorted(current.published_destinations(source) & current.published_destinations(target))
        provisional.append({
            'status': 'official-explicit-cross-page-evidence',
            'matchStatus': 'matched-singleton',
            'id': current.stable_id(
                'schedule-all-cross-page', base.service_of(source), spec['id'],
                proof['componentRoot'], source_id, target['id'],
                proof['sourceOfficialFragment'], proof['targetOfficialFragment'],
            ),
            'operator': 'keikyu',
            'calendar': base.service_of(source),
            'direction': f"{pair[0].rsplit('.', 1)[-1].lower()}-to-{pair[1].rsplit('.', 1)[-1].lower()}",
            'boundaryId': spec['id'],
            'boundaryStation': spec['station'],
            'fromRailway': pair[0],
            'toRailway': pair[1],
            'fromFragment': source_id,
            'toFragment': str(target['id']),
            'sourceMatches': [source_id],
            'targetMatches': [str(target['id'])],
            'officialAnchors': [proof['sourceAnchor'], proof['targetAnchor']],
            'officialPhysicalComponentRoot': proof['componentRoot'],
            'sourceOfficialFragment': proof['sourceOfficialFragment'],
            'targetOfficialFragment': proof['targetOfficialFragment'],
            'officialPreviousPublicationPath': [
                {
                    'fromFragment': str(edge.get('fromFragment') or ''),
                    'toFragment': str(edge.get('toFragment') or ''),
                    'previousPrintedPage': edge.get('previousPrintedPage'),
                    'previousTrainNumber': str(edge.get('previousTrainNumber') or ''),
                    'currentPrintedPage': edge.get('currentPrintedPage'),
                    'currentTrainNumber': str(edge.get('currentTrainNumber') or ''),
                    'evidence': str(edge.get('evidence') or ''),
                }
                for edge in path
            ],
            'corroboratingAnchorPaths': proof['corroboratingAnchorPaths'],
            'candidateFragmentGapMinutes': gap,
            'sharedPublishedDestination': shared_destinations,
            'evidence': ['operator-official-full-timetable', MARKER],
            'sourceUrl': OFFICIAL_PDF_URL,
            'matchPolicy': {
                'crossPageIdentityUsed': True,
                'officialPreviousPublicationPageAndTrainNumberRequired': True,
                'uniquePreviousPublicationTargetRequired': True,
                'pageLocalFragmentMetadataMustMatch': True,
                'crossPageGraphMustBeNonBranchingAcyclic': True,
                'directedOfficialContinuationPathRequired': True,
                'twoExactPublishedStationTimesRequired': True,
                'singletonFragmentMatchRequiredAtBothPoints': True,
                'sharedPublishedDestinationUsedOnlyForSearch': True,
                'candidateFragmentGapUsedOnlyForSearch': True,
                'candidateFragmentGapMaximumMinutes': current.MAX_CANDIDATE_GAP_MINUTES,
                'trainNumberAloneMayEstablishIdentity': False,
                'timeProximityAloneMayEstablishIdentity': False,
            },
        })

    target_counts = Counter(str(row['toFragment']) for row in provisional)
    entries = [row for row in provisional if target_counts[str(row['toFragment'])] == 1]
    reasons['rejected-shared-target'] += len(provisional) - len(entries)
    reasons['matched-explicit-cross-page'] += len(entries)
    summary = {
        'proofSource': OFFICIAL_PDF_URL,
        'proofMode': 'explicit-previous-publication-chain-two-point',
        'eligibleUnresolvedSources': len(rows),
        'candidatePairsAfterDestinationAndTimeSearch': candidate_count,
        'officialCrossPageEdges': len(outgoing),
        'matchedSingleton': len(entries),
        'reasons': dict(reasons),
        'directions': dict(Counter(str(row['direction']) for row in entries)),
        'calendars': dict(Counter(str(row['calendar']) for row in entries)),
        'policy': {
            'crossPageIdentityUsed': True,
            'officialPreviousPublicationPageAndTrainNumberRequired': True,
            'uniquePreviousPublicationTargetRequired': True,
            'pageLocalFragmentMetadataMustMatch': True,
            'crossPageGraphMustBeNonBranchingAcyclic': True,
            'directedOfficialContinuationPathRequired': True,
            'twoExactPublishedStationTimesRequired': True,
            'singletonFragmentMatchRequiredAtBothPoints': True,
            'sharedPublishedDestinationIsSearchOnly': True,
            'candidateTimeWindowIsSearchOnly': True,
            'uniqueTargetRequired': True,
            'trainNumberAloneMayEstablishIdentity': False,
            'timeProximityAloneMayEstablishIdentity': False,
        },
    }
    return entries, summary


def merge_payload(existing: dict[str, Any], entries: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    output = dict(existing or {})
    old_entries = [row for row in output.get('entries') or [] if isinstance(row, dict)]
    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for row in old_entries + entries:
        key = (str(row.get('fromFragment') or ''), str(row.get('toFragment') or ''))
        if all(key):
            by_pair[key] = row
    policy = dict(output.get('policy') or {})
    policy.update({
        'singletonFragmentMatchRequiredAtBothPoints': True,
        'trainNumberAloneMayEstablishIdentity': False,
        'timeProximityAloneMayEstablishIdentity': False,
        'officialPreviousPublicationPageAndTrainNumberRequiredForCrossPage': True,
        'uniquePreviousPublicationTargetRequiredForCrossPage': True,
        'pageLocalFragmentMetadataMustMatchForCrossPage': True,
        'crossPageGraphMustBeNonBranchingAcyclic': True,
        'directedOfficialContinuationPathRequired': True,
    })
    output.update({
        'entries': list(by_pair.values()),
        'policy': policy,
        'latestCrossPageSummary': summary,
    })
    return output


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--coverage', default='data/transit-v2/coverage.json')
    ap.add_argument('--fragments', default='data/transit-v2/fragments/keikyu.json')
    ap.add_argument('--official-stop-times', required=True)
    ap.add_argument('--cross-page-audit', required=True)
    ap.add_argument('--existing', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    ap.add_argument('--output', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    ap.add_argument('--report', required=True)
    args = ap.parse_args()

    coverage = load_json(Path(args.coverage), {}) or {}
    fragment_payload = load_json(Path(args.fragments), {}) or {}
    fragments = [row for row in fragment_payload.get('fragments') or [] if isinstance(row, dict) and row.get('id')]
    stop_times = load_json(Path(args.official_stop_times), {}) or {}
    audit = load_json(Path(args.cross_page_audit), {}) or {}
    entries, summary = build_entries(coverage, fragments, stop_times, audit)
    existing = load_json(Path(args.existing), {}) or {}
    output = merge_payload(existing, entries, summary)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    Path(args.report).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
