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

BOUNDARY_ID = base.ZUSHI_BOUNDARY_ID


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise RuntimeError(f'expected JSON object: {path}')
    return value


def hit_fragments(
    anchors: list[dict[str, Any]],
    official_index: dict[tuple[str, int], list[dict[str, Any]]],
) -> set[str]:
    out: set[str] = set()
    for anchor in anchors:
        key = (str(anchor.get('suffix') or ''), int(anchor.get('minute') or 0) % 1440)
        for hit in official_index.get(key, []):
            fid = str(hit.get('officialFragment') or '')
            if fid:
                out.add(fid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--coverage', default='data/transit-v2/coverage.json')
    ap.add_argument('--fragments', default='data/transit-v2/fragments/keikyu.json')
    ap.add_argument('--official-stop-times', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()

    coverage = load(Path(args.coverage))
    fragment_payload = load(Path(args.fragments))
    official = load(Path(args.official_stop_times))
    fragments = [row for row in fragment_payload.get('fragments') or [] if isinstance(row, dict) and row.get('id')]
    by_id = {str(row['id']): row for row in fragments}
    rows = current.unresolved_sources(coverage, by_id, boundary_id=BOUNDARY_ID)
    owners = current.anchor_owner_index(fragments)
    anchors = current.singleton_anchor_cache(fragments, owners)
    official_index = local.official_anchor_index(official)

    first_gate = Counter()
    by_calendar: dict[str, Counter] = defaultdict(Counter)
    by_direction: dict[str, Counter] = defaultdict(Counter)
    provisional: list[tuple[str, str]] = []
    details: list[dict[str, Any]] = []

    for _unresolved, source, pair in rows:
        source_id = str(source['id'])
        service = base.service_of(source) or 'unknown'
        direction = f"{pair[0].rsplit('.', 1)[-1].lower()}-to-{pair[1].rsplit('.', 1)[-1].lower()}"
        candidates = current.candidate_targets(source, pair, fragments)
        source_anchors = anchors.get(source_id, [])
        source_hits = hit_fragments(source_anchors, official_index)

        proven: list[tuple[str, dict[str, Any]]] = []
        any_target_anchor = False
        any_target_hit = False
        shared_counts: list[int] = []
        target_rows: list[dict[str, Any]] = []
        for target, gap in candidates:
            target_id = str(target['id'])
            target_anchors = anchors.get(target_id, [])
            target_hits = hit_fragments(target_anchors, official_index)
            any_target_anchor = any_target_anchor or bool(target_anchors)
            any_target_hit = any_target_hit or bool(target_hits)
            shared = source_hits & target_hits
            shared_counts.append(len(shared))
            proof = local.same_page_column_proof(source, target, anchors, official_index)
            if proof:
                proven.append((target_id, proof))
            target_rows.append({
                'targetFragment': target_id,
                'gapMinutes': gap,
                'singletonAnchors': len(target_anchors),
                'officialFragments': len(target_hits),
                'sharedOfficialFragments': len(shared),
            })

        if not candidates:
            gate = 'no-candidate-target'
        elif not source_anchors:
            gate = 'no-source-singleton-anchor'
        elif not source_hits:
            gate = 'no-source-official-hit'
        elif not any_target_anchor:
            gate = 'no-target-singleton-anchor'
        elif not any_target_hit:
            gate = 'no-target-official-hit'
        elif len(proven) > 1:
            gate = 'multiple-runtime-targets-with-local-proof'
        elif len(proven) == 1:
            gate = 'locally-proven-before-target-conflict-check'
            provisional.append((source_id, proven[0][0]))
        elif max(shared_counts, default=0) == 0:
            gate = 'official-hits-exist-but-no-shared-section-column'
        elif max(shared_counts, default=0) > 1:
            gate = 'shared-multiple-official-section-columns'
        else:
            gate = 'shared-single-official-fragment-but-proof-not-unique'

        first_gate[gate] += 1
        by_calendar[service][gate] += 1
        by_direction[direction][gate] += 1
        details.append({
            'sourceFragment': source_id,
            'calendar': service,
            'direction': direction,
            'candidateTargets': len(candidates),
            'sourceSingletonAnchors': len(source_anchors),
            'sourceOfficialFragments': len(source_hits),
            'provenTargets': [target for target, _proof in proven],
            'gate': gate,
            'targets': target_rows[:20],
        })

    target_counts = Counter(target for _source, target in provisional)
    shared_target_sources = {
        source for source, target in provisional
        if target_counts[target] > 1
    }
    final_local = len(provisional) - len(shared_target_sources)

    summary = {
        'eligibleRemainingSources': len(rows),
        'firstGateCounts': dict(first_gate),
        'byCalendar': {key: dict(value) for key, value in sorted(by_calendar.items())},
        'byDirection': {key: dict(value) for key, value in sorted(by_direction.items())},
        'locallyProvenBeforeTargetConflict': len(provisional),
        'sharedTargetRejectedSources': len(shared_target_sources),
        'finalLocalProofsIfRecomputedNow': final_local,
        'officialAnchorKeys': len(official_index),
        'officialFragments': len(official.get('fragments') or []),
    }
    payload = {'summary': summary, 'details': details}
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
