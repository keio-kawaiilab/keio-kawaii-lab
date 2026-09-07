#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import keikyu_internal_official_evidence as base
import keikyu_missing_boundary_evidence as current
from keikyu_official_pdf import OFFICIAL_PDF_URL

BOUNDARY_ID = base.ZUSHI_BOUNDARY_ID
MARKER = 'schedule-all-page-column-v1'


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def validate_official_dataset(payload: dict[str, Any]) -> None:
    if payload.get('kind') != 'keikyu-official-page-local-stop-times':
        raise RuntimeError('unexpected official stop-time dataset kind')
    policy = payload.get('identityPolicy') or {}
    required_true = {
        'pageColumnIsExactLocalIdentity',
    }
    required_false = {
        'printedTrainNumberMayJoinPages',
        'anonymousColumnMayJoinPages',
        'clockTimeProximityMayJoinFragments',
        'destinationMayJoinFragments',
        'crossPageIdentityEstablished',
    }
    if any(policy.get(key) is not True for key in required_true):
        raise RuntimeError('unsafe official stop-time local-identity policy')
    if any(policy.get(key) is not False for key in required_false):
        raise RuntimeError('unsafe official stop-time cross-fragment policy')
    if int(policy.get('runtimeSameTrainPromotions') or 0) != 0:
        raise RuntimeError('official stop-time dataset already contains runtime promotions')
    source = payload.get('source') or {}
    if str(source.get('url') or '') != OFFICIAL_PDF_URL:
        raise RuntimeError('unexpected official timetable source URL')


def station_suffix_map() -> dict[str, str]:
    output: dict[str, str] = {}
    duplicate: set[str] = set()
    for suffix, labels in base.STATION_LABELS.items():
        for label in labels:
            key = base.parser.norm(label)
            if not key:
                continue
            if key in output and output[key] != suffix:
                duplicate.add(key)
            else:
                output[key] = suffix
    for key in duplicate:
        output.pop(key, None)
    return output


def minute_of_hhmm(value: Any) -> int | None:
    minute = base.parser.hhmm(base.parser.norm(value))
    return int(minute) % 1440 if minute is not None else None


def official_anchor_index(payload: dict[str, Any]) -> dict[tuple[str, int], list[dict[str, Any]]]:
    validate_official_dataset(payload)
    suffixes = station_suffix_map()
    index: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    seen_fragment_ids: set[str] = set()
    for fragment in payload.get('fragments') or []:
        if not isinstance(fragment, dict):
            continue
        fid = str(fragment.get('id') or '')
        if not fid:
            continue
        if fid in seen_fragment_ids:
            raise RuntimeError(f'duplicate official page-column fragment: {fid}')
        seen_fragment_ids.add(fid)
        page = int(fragment.get('page') or 0)
        column = int(fragment.get('column') or 0)
        seen_local: set[tuple[str, int, str]] = set()
        for stop in fragment.get('stopTimes') or []:
            if not isinstance(stop, dict):
                continue
            suffix = suffixes.get(base.parser.norm(stop.get('station')))
            minute = minute_of_hhmm(stop.get('time'))
            if not suffix or minute is None:
                continue
            local_key = (suffix, minute, str(stop.get('event') or ''))
            if local_key in seen_local:
                continue
            seen_local.add(local_key)
            index[(suffix, minute)].append({
                'officialFragment': fid,
                'page': page,
                'column': column,
                'event': str(stop.get('event') or ''),
                'time': str(stop.get('time') or ''),
                'station': str(stop.get('station') or ''),
            })
    return dict(index)


def same_page_column_proof(
    source: dict[str, Any],
    target: dict[str, Any],
    anchors: dict[str, list[dict[str, Any]]],
    official_index: dict[tuple[str, int], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    source_id = str(source.get('id') or '')
    target_id = str(target.get('id') or '')
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for left in anchors.get(source_id, []):
        left_hits = official_index.get((str(left.get('suffix') or ''), int(left.get('minute') or 0) % 1440), [])
        if not left_hits:
            continue
        for right in anchors.get(target_id, []):
            if str(left.get('station') or '') == str(right.get('station') or ''):
                continue
            right_hits = official_index.get((str(right.get('suffix') or ''), int(right.get('minute') or 0) % 1440), [])
            if not right_hits:
                continue
            right_by_fragment: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for hit in right_hits:
                right_by_fragment[str(hit['officialFragment'])].append(hit)
            for a in left_hits:
                fid = str(a['officialFragment'])
                for b in right_by_fragment.get(fid, []):
                    groups[fid].append({
                        'officialFragment': fid,
                        'page': int(a['page']),
                        'column': int(a['column']),
                        'sourceAnchor': left,
                        'targetAnchor': right,
                        'sourceOfficialHit': a,
                        'targetOfficialHit': b,
                    })
    if len(groups) != 1:
        return None
    group = next(iter(groups.values()))
    chosen = sorted(
        group,
        key=lambda row: (
            str(row['sourceAnchor'].get('suffix') or ''),
            int(row['sourceAnchor'].get('minute') or 0),
            str(row['targetAnchor'].get('suffix') or ''),
            int(row['targetAnchor'].get('minute') or 0),
        ),
    )[0]
    chosen['corroboratingAnchorPairs'] = len(group)
    return chosen


def build_entries(
    coverage: dict[str, Any],
    fragments: list[dict[str, Any]],
    official_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_id = {str(row.get('id') or ''): row for row in fragments if row.get('id')}
    rows = current.unresolved_sources(coverage, by_id, boundary_id=BOUNDARY_ID)
    owners = current.anchor_owner_index(fragments)
    anchors = current.singleton_anchor_cache(fragments, owners)
    official_index = official_anchor_index(official_payload)

    provisional: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    candidate_count = 0
    for _unresolved, source, pair in rows:
        source_id = str(source.get('id') or '')
        candidates = current.candidate_targets(source, pair, fragments)
        candidate_count += len(candidates)
        proven: list[tuple[dict[str, Any], int, dict[str, Any]]] = []
        for target, gap in candidates:
            proof = same_page_column_proof(source, target, anchors, official_index)
            if proof:
                proven.append((target, gap, proof))
        if len(proven) != 1:
            reasons['no-unique-official-page-column-proof' if not proven else 'multiple-official-page-column-proofs'] += 1
            continue

        target, gap, proof = proven[0]
        spec = base.BOUNDARIES[pair]
        shared_destinations = sorted(current.published_destinations(source) & current.published_destinations(target))
        source_anchor = proof['sourceAnchor']
        target_anchor = proof['targetAnchor']
        provisional.append({
            'status': 'official-column-evidence',
            'matchStatus': 'matched-singleton',
            'id': current.stable_id(
                'schedule-all', base.service_of(source), spec['id'], proof['officialFragment'],
                source_id, target['id'], source_anchor, target_anchor,
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
            'officialAnchors': [source_anchor, target_anchor],
            'officialPageLocalFragment': proof['officialFragment'],
            'pdfPage': proof['page'],
            'pdfColumn': proof['column'],
            'corroboratingAnchorPairs': proof['corroboratingAnchorPairs'],
            'candidateFragmentGapMinutes': gap,
            'sharedPublishedDestination': shared_destinations,
            'evidence': ['operator-official-full-timetable', base.MARKER, MARKER],
            'sourceUrl': OFFICIAL_PDF_URL,
            'matchPolicy': {
                'officialSamePrintedColumnRequired': True,
                'twoExactPublishedStationTimesRequired': True,
                'singletonFragmentMatchRequiredAtBothPoints': True,
                'officialPageColumnIsExactLocalIdentity': True,
                'crossPageIdentityUsed': False,
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
    reasons['matched-current-missing-boundary'] += len(entries)
    summary = {
        'proofSource': OFFICIAL_PDF_URL,
        'proofMode': 'exact-page-local-column-two-point',
        'eligibleUnresolvedSources': len(rows),
        'candidatePairsAfterDestinationAndTimeSearch': candidate_count,
        'matchedSingleton': len(entries),
        'reasons': dict(reasons),
        'boundaries': dict(Counter(str(row['boundaryId']) for row in entries)),
        'directions': dict(Counter(str(row['direction']) for row in entries)),
        'calendars': dict(Counter(str(row['calendar']) for row in entries)),
        'policy': {
            'officialSamePrintedColumnRequired': True,
            'twoExactPublishedStationTimesRequired': True,
            'singletonFragmentMatchRequiredAtBothPoints': True,
            'officialPageColumnIsExactLocalIdentity': True,
            'crossPageIdentityUsed': False,
            'sharedPublishedDestinationIsSearchOnly': True,
            'candidateTimeWindowIsSearchOnly': True,
            'uniqueTargetRequired': True,
            'trainNumberAloneMayEstablishIdentity': False,
            'timeProximityAloneMayEstablishIdentity': False,
        },
    }
    return entries, summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--coverage', default='data/transit-v2/coverage.json')
    ap.add_argument('--fragments', default='data/transit-v2/fragments/keikyu.json')
    ap.add_argument('--official-stop-times', required=True)
    ap.add_argument('--entries-output', required=True)
    ap.add_argument('--report', required=True)
    args = ap.parse_args()

    coverage = load_json(Path(args.coverage), {}) or {}
    fragment_payload = load_json(Path(args.fragments), {}) or {}
    fragments = [row for row in fragment_payload.get('fragments') or [] if isinstance(row, dict) and row.get('id')]
    official_payload = load_json(Path(args.official_stop_times), {}) or {}
    entries, summary = build_entries(coverage, fragments, official_payload)

    Path(args.entries_output).write_text(json.dumps({
        'calendar': 'all-current-services',
        'boundaryId': BOUNDARY_ID,
        'entries': entries,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    Path(args.report).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
