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


def small_fragment(row: dict[str, Any]) -> dict[str, Any]:
    stops = row.get('stops') or []
    return {
        'id': str(row.get('id') or ''),
        'railway': str(row.get('railway') or ''),
        'calendar': str(row.get('calendar') or ''),
        'trainType': str(row.get('trainType') or ''),
        'destination': [str(v) for v in row.get('destination') or []],
        'stopCount': len(stops),
        'firstStops': stops[:4],
        'lastStops': stops[-4:] if len(stops) > 4 else stops,
    }


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
    fragments = [r for r in fragment_payload.get('fragments') or [] if isinstance(r, dict) and r.get('id')]
    by_id = {str(r['id']): r for r in fragments}
    official_by_id = {
        str(r['id']): r
        for r in official.get('fragments') or []
        if isinstance(r, dict) and r.get('id')
    }
    rows = current.unresolved_sources(coverage, by_id, boundary_id=BOUNDARY_ID)
    owners = current.anchor_owner_index(fragments)
    anchors = current.singleton_anchor_cache(fragments, owners)
    official_index = local.official_anchor_index(official)

    provisional: list[dict[str, Any]] = []
    for _unresolved, source, pair in rows:
        source_id = str(source['id'])
        service = base.service_of(source)
        if service not in {'weekday', 'holiday'}:
            continue
        proven: list[tuple[dict[str, Any], int, dict[str, Any]]] = []
        for target, gap in current.candidate_targets(source, pair, fragments):
            proof = local.same_page_section_column_proof(
                source, target, service, anchors, official_index
            )
            if proof:
                proven.append((target, gap, proof))
        if len(proven) != 1:
            continue
        target, gap, proof = proven[0]
        provisional.append({
            'source': source,
            'target': target,
            'gapMinutes': gap,
            'proof': proof,
            'service': service,
            'direction': f"{pair[0].rsplit('.',1)[-1].lower()}-to-{pair[1].rsplit('.',1)[-1].lower()}",
        })

    target_counts = Counter(str(r['target']['id']) for r in provisional)
    groups: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    source_count = 0
    for target_id, count in sorted(target_counts.items()):
        if count <= 1:
            continue
        rows_for_target = [r for r in provisional if str(r['target']['id']) == target_id]
        official_ids = [str(r['proof'].get('officialFragment') or '') for r in rows_for_target]
        distinct_official = sorted(set(official_ids))
        classification = (
            'all-sources-prove-same-official-section-column'
            if len(distinct_official) == 1
            else 'sources-prove-different-official-section-columns'
        )
        class_counts[classification] += 1
        source_count += len(rows_for_target)
        rendered_sources = []
        for row in sorted(rows_for_target, key=lambda r: (int(r['gapMinutes']), str(r['source']['id']))):
            proof = row['proof']
            official_id = str(proof.get('officialFragment') or '')
            official_fragment = official_by_id.get(official_id) or {}
            rendered_sources.append({
                'source': small_fragment(row['source']),
                'gapMinutes': int(row['gapMinutes']),
                'service': row['service'],
                'direction': row['direction'],
                'sourceSingletonAnchors': anchors.get(str(row['source']['id']), []),
                'officialFragment': official_id,
                'officialPage': proof.get('page'),
                'officialSection': proof.get('section'),
                'officialColumn': proof.get('column'),
                'sourceAnchor': proof.get('sourceAnchor'),
                'targetAnchor': proof.get('targetAnchor'),
                'corroboratingAnchorPairs': proof.get('corroboratingAnchorPairs'),
                'officialStopTimes': official_fragment.get('stopTimes') or [],
            })
        groups.append({
            'target': small_fragment(by_id[target_id]),
            'targetSingletonAnchors': anchors.get(target_id, []),
            'sourceCount': len(rows_for_target),
            'classification': classification,
            'distinctOfficialFragments': distinct_official,
            'sources': rendered_sources,
        })

    output = {
        'summary': {
            'provisionalUniqueSourceProofs': len(provisional),
            'sharedTargetGroups': len(groups),
            'sharedTargetSources': source_count,
            'groupClassifications': dict(class_counts),
            'groupSizeHistogram': dict(Counter(str(g['sourceCount']) for g in groups)),
        },
        'groups': groups,
    }
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output['summary'], ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
