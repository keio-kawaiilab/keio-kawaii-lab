#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import keikyu_internal_official_evidence as base
import keikyu_internal_official_evidence_selective as focused

# Search window only. It is never accepted as train-identity evidence.
MAX_CANDIDATE_GAP_MINUTES = 90
CURRENT_KIND = 'missing-boundary-train-identity-evidence'
MARKER = 'current-missing-boundary-official-column-v1'

BOUNDARY_SUFFIXES: dict[tuple[str, str], str] = {
    (base.MAIN, base.AIRPORT): '.KeikyuKamata',
    (base.AIRPORT, base.MAIN): '.KeikyuKamata',
    (base.MAIN, base.KURIHAMA): '.Horinouchi',
    (base.KURIHAMA, base.MAIN): '.Horinouchi',
    (base.MAIN, base.ZUSHI): '.KanazawaHakkei',
    (base.ZUSHI, base.MAIN): '.KanazawaHakkei',
}


def load_json(path: Path, default: Any = None) -> Any:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def stable_id(*parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return 'keikyu-current-boundary:' + hashlib.sha256(raw.encode()).hexdigest()[:24]


def endpoint_minute(fragment: dict[str, Any], side: str) -> int | None:
    stops = fragment.get('stops') or []
    if not stops:
        return None
    stop = stops[0] if side == 'start' else stops[-1]
    if not isinstance(stop, list):
        return None
    if side == 'start':
        values = [stop[2] if len(stop) > 2 else None, stop[1] if len(stop) > 1 else None]
    else:
        values = [stop[1] if len(stop) > 1 else None, stop[2] if len(stop) > 2 else None]
    for value in values:
        if isinstance(value, (int, float)):
            return int(value)
    return None


def forward_gap(source_minute: int, target_minute: int) -> int:
    gap = target_minute - source_minute
    if gap < 0:
        gap += 1440
    return gap


def published_destinations(fragment: dict[str, Any]) -> set[str]:
    return {str(value) for value in fragment.get('destination') or [] if value}


def unresolved_sources(
    coverage: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    *,
    boundary_id: str | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any], tuple[str, str]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any], tuple[str, str]]] = []
    for unresolved in coverage.get('unresolved') or []:
        if not isinstance(unresolved, dict) or unresolved.get('kind') != CURRENT_KIND:
            continue
        source = by_id.get(str(unresolved.get('fragment') or ''))
        if not source or not (source.get('stops') or []):
            continue
        pair = (str(source.get('railway') or ''), str(unresolved.get('nextRailway') or ''))
        spec = base.BOUNDARIES.get(pair)
        if not spec or pair not in BOUNDARY_SUFFIXES:
            continue
        if boundary_id and str(spec.get('id') or '') != boundary_id:
            continue
        rows.append((unresolved, source, pair))
    return rows


def candidate_targets(
    source: dict[str, Any],
    pair: tuple[str, str],
    fragments: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], int]]:
    """Find plausible next fragments only to limit official-PDF proof work.

    Current reconstructed fragments frequently stop before the physical junction
    (for example Zushi fragments stop at Mutsuura rather than Kanazawa-Hakkei).
    Therefore candidate discovery must not require the boundary station itself.
    Same calendar, exact published destination and chronology are search filters
    only. Identity is established later only by independent official same-column
    exact-time proof.
    """
    service = base.service_of(source)
    source_minute = endpoint_minute(source, 'end')
    source_destinations = published_destinations(source)
    if not service or source_minute is None or not source_destinations:
        return []
    output: list[tuple[dict[str, Any], int]] = []
    for target in fragments:
        if str(target.get('railway') or '') != pair[1] or base.service_of(target) != service:
            continue
        if not (source_destinations & published_destinations(target)):
            continue
        target_minute = endpoint_minute(target, 'start')
        if target_minute is None:
            continue
        gap = forward_gap(source_minute, target_minute)
        if 0 <= gap <= MAX_CANDIDATE_GAP_MINUTES:
            output.append((target, gap))
    return output


def anchor_owner_index(fragments: list[dict[str, Any]]) -> dict[tuple[str, str, str, int], set[str]]:
    owners: dict[tuple[str, str, str, int], set[str]] = defaultdict(set)
    for fragment in fragments:
        fid = str(fragment.get('id') or '')
        railway = str(fragment.get('railway') or '')
        service = base.service_of(fragment)
        if not fid or not railway or not service:
            continue
        seen: set[tuple[str, int]] = set()
        for anchor in base.fragment_anchors(fragment):
            key2 = (str(anchor.get('suffix') or ''), int(anchor.get('minute') or 0))
            if key2 in seen:
                continue
            seen.add(key2)
            owners[(railway, service, key2[0], key2[1])].add(fid)
    return owners


def singleton_anchor_cache(
    fragments: list[dict[str, Any]],
    owners: dict[tuple[str, str, str, int], set[str]],
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for fragment in fragments:
        fid = str(fragment.get('id') or '')
        railway = str(fragment.get('railway') or '')
        service = base.service_of(fragment)
        anchors: list[dict[str, Any]] = []
        if fid and railway and service:
            for anchor in base.fragment_anchors(fragment):
                suffix = str(anchor.get('suffix') or '')
                minute = int(anchor.get('minute') or 0)
                if owners.get((railway, service, suffix, minute)) == {fid}:
                    anchors.append(anchor)
        output[fid] = anchors
    return output


def needed_station_times(
    rows: list[tuple[dict[str, Any], dict[str, Any], tuple[str, str]]],
    fragments: list[dict[str, Any]],
) -> tuple[dict[str, set[tuple[str, int]]], dict[str, list[tuple[dict[str, Any], int]]]]:
    needed: dict[str, set[tuple[str, int]]] = defaultdict(set)
    candidate_map: dict[str, list[tuple[dict[str, Any], int]]] = {}
    for _unresolved, source, pair in rows:
        source_id = str(source.get('id') or '')
        targets = candidate_targets(source, pair, fragments)
        candidate_map[source_id] = targets
        service = base.service_of(source)
        for fragment in [source, *(target for target, _gap in targets)]:
            for anchor in base.fragment_anchors(fragment):
                suffix = str(anchor.get('suffix') or '')
                minute = anchor.get('minute')
                if suffix and isinstance(minute, int):
                    needed[service].add((suffix, minute % 1440))
    return dict(needed), candidate_map


def build_official_indexes(needed: dict[str, set[tuple[str, int]]]) -> dict[str, dict[tuple[str, int], list[dict[str, Any]]]]:
    indexes: dict[str, dict[tuple[str, int], list[dict[str, Any]]]] = {}
    if needed.get('weekday'):
        indexes['weekday'] = focused.focused_official_station_time_index('weekday', base.MAINLINE_WEEKDAY_URL, needed)
    if needed.get('holiday'):
        indexes['holiday'] = focused.focused_official_station_time_index('holiday', base.MAINLINE_HOLIDAY_URL, needed)
    return indexes


def exact_same_column_proof(
    source: dict[str, Any],
    target: dict[str, Any],
    anchors: dict[str, list[dict[str, Any]]],
    official_index: dict[tuple[str, int], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    source_id = str(source.get('id') or '')
    target_id = str(target.get('id') or '')
    matches: list[dict[str, Any]] = []
    for left in anchors.get(source_id, []):
        left_positions = official_index.get((str(left['suffix']), int(left['minute']) % 1440), [])
        for right in anchors.get(target_id, []):
            if str(left.get('station') or '') == str(right.get('station') or ''):
                continue
            right_positions = official_index.get((str(right['suffix']), int(right['minute']) % 1440), [])
            for a in left_positions:
                for b in right_positions:
                    if int(a['page']) != int(b['page']):
                        continue
                    delta = abs(float(a['x']) - float(b['x']))
                    if delta > 3.0:
                        continue
                    matches.append({
                        'page': int(a['page']),
                        'x': round((float(a['x']) + float(b['x'])) / 2, 2),
                        'deltaX': round(delta, 3),
                        'sourceAnchor': left,
                        'targetAnchor': right,
                        'sourceRowText': a.get('rowText'),
                        'targetRowText': b.get('rowText'),
                        'sourceUrl': a.get('sourceUrl') or b.get('sourceUrl'),
                    })
    if not matches:
        return None
    groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for match in matches:
        groups[(int(match['page']), int(round(float(match['x']))))].append(match)
    if len(groups) != 1:
        return None
    group = next(iter(groups.values()))
    chosen = min(group, key=lambda row: (float(row['deltaX']), str(row['sourceAnchor']), str(row['targetAnchor'])))
    chosen['corroboratingAnchorPairs'] = len(group)
    return chosen


def build_entries(
    coverage: dict[str, Any],
    fragments: list[dict[str, Any]],
    *,
    boundary_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_id = {str(row.get('id') or ''): row for row in fragments if row.get('id')}
    rows = unresolved_sources(coverage, by_id, boundary_id=boundary_id)
    needed, candidate_map = needed_station_times(rows, fragments)
    official_indexes = build_official_indexes(needed)
    owners = anchor_owner_index(fragments)
    anchors = singleton_anchor_cache(fragments, owners)

    provisional: list[dict[str, Any]] = []
    reasons: Counter = Counter()
    candidate_count = 0
    for _unresolved, source, pair in rows:
        source_id = str(source.get('id') or '')
        service = base.service_of(source)
        index = official_indexes.get(service) or {}
        candidates = candidate_map.get(source_id) or []
        candidate_count += len(candidates)
        proven: list[tuple[dict[str, Any], int, dict[str, Any]]] = []
        for target, gap in candidates:
            proof = exact_same_column_proof(source, target, anchors, index)
            if proof:
                proven.append((target, gap, proof))
        if len(proven) != 1:
            reasons['no-independent-official-column-proof' if not proven else 'multiple-independent-official-column-proofs'] += 1
            continue
        target, gap, proof = proven[0]
        spec = base.BOUNDARIES[pair]
        source_anchor = proof['sourceAnchor']
        target_anchor = proof['targetAnchor']
        shared_destinations = sorted(published_destinations(source) & published_destinations(target))
        provisional.append({
            'status': 'official-column-evidence',
            'matchStatus': 'matched-singleton',
            'id': stable_id(service, spec['id'], proof['page'], proof['x'], source_id, target['id'], source_anchor, target_anchor),
            'operator': 'keikyu',
            'calendar': service,
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
            'pdfPage': proof['page'],
            'columnX': proof['x'],
            'corroboratingAnchorPairs': proof['corroboratingAnchorPairs'],
            'candidateFragmentGapMinutes': gap,
            'sharedPublishedDestination': shared_destinations,
            'evidence': ['operator-official-mainline-timetable', base.MARKER, MARKER],
            'sourceUrl': proof['sourceUrl'],
            'matchPolicy': {
                'officialSamePrintedColumnRequired': True,
                'twoExactPublishedStationTimesRequired': True,
                'singletonFragmentMatchRequiredAtBothPoints': True,
                'sharedPublishedDestinationUsedOnlyForSearch': True,
                'candidateFragmentGapUsedOnlyForSearch': True,
                'candidateFragmentGapMaximumMinutes': MAX_CANDIDATE_GAP_MINUTES,
                'trainNumberAloneMayEstablishIdentity': False,
                'timeProximityAloneMayEstablishIdentity': False,
            },
        })

    target_counts = Counter(str(row['toFragment']) for row in provisional)
    entries = [row for row in provisional if target_counts[str(row['toFragment'])] == 1]
    reasons['rejected-shared-target'] += len(provisional) - len(entries)
    reasons['matched-current-missing-boundary'] += len(entries)
    summary = {
        'eligibleUnresolvedSources': len(rows),
        'candidatePairsAfterDestinationAndTimeSearch': candidate_count,
        'matchedSingleton': len(entries),
        'reasons': dict(reasons),
        'boundaries': dict(Counter(str(row['boundaryId']) for row in entries)),
        'directions': dict(Counter(str(row['direction']) for row in entries)),
        'calendars': dict(Counter(str(row['calendar']) for row in entries)),
        'policy': {
            'sharedPublishedDestinationIsSearchOnly': True,
            'candidateTimeWindowIsSearchOnly': True,
            'officialSamePrintedColumnRequired': True,
            'twoExactPublishedStationTimesRequired': True,
            'singletonFragmentMatchRequiredAtBothPoints': True,
            'uniqueTargetRequired': True,
            'trainNumberAloneMayEstablishIdentity': False,
            'timeProximityAloneMayEstablishIdentity': False,
        },
    }
    return entries, summary


def merge_payload(existing: dict[str, Any], new_entries: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    output = dict(existing or {})
    old_entries = [row for row in output.get('entries') or [] if isinstance(row, dict)]
    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for row in old_entries + new_entries:
        key = (str(row.get('fromFragment') or ''), str(row.get('toFragment') or ''))
        if all(key):
            by_pair[key] = row
    entries = list(by_pair.values())
    policy = dict(output.get('policy') or {})
    policy.update({
        'officialSamePrintedColumnRequired': True,
        'twoExactPublishedStationTimesRequired': True,
        'singletonFragmentMatchRequiredAtBothPoints': True,
        'trainNumberAloneMayEstablishIdentity': False,
        'timeProximityAloneMayEstablishIdentity': False,
    })
    output.update({
        'version': max(2, int(output.get('version') or 0)),
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'operator': 'keikyu',
        'policy': policy,
        'entries': entries,
    })
    old_summary = dict(output.get('summary') or {})
    old_summary['currentMissingBoundaryResolver'] = summary
    old_summary['matchedSingleton'] = len(entries)
    old_summary['boundaries'] = dict(Counter(str(row.get('boundaryId') or '') for row in entries))
    old_summary['directions'] = dict(Counter(str(row.get('direction') or '') for row in entries))
    output['summary'] = old_summary
    output['boundaryIds'] = sorted({str(row.get('boundaryId') or '') for row in entries if row.get('boundaryId')})
    return output


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--coverage', default='data/transit-v2/coverage.json')
    ap.add_argument('--fragments', default='data/transit-v2/fragments/keikyu.json')
    ap.add_argument('--existing', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    ap.add_argument('--output', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    ap.add_argument('--boundary-id')
    ap.add_argument('--report')
    args = ap.parse_args()

    coverage = load_json(Path(args.coverage), {}) or {}
    fragment_payload = load_json(Path(args.fragments), {}) or {}
    fragments = [row for row in fragment_payload.get('fragments') or [] if isinstance(row, dict) and row.get('id')]
    existing = load_json(Path(args.existing), {}) or {}
    entries, summary = build_entries(coverage, fragments, boundary_id=args.boundary_id)
    payload = merge_payload(existing, entries, summary)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.report:
        Path(args.report).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
