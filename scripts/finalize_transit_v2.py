#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_transit_v2 as base
import reviewed_train_evidence as reviewed

ROOT = Path('.')
V1 = ROOT / 'data/transit'
V2 = ROOT / 'data/transit-v2'
BOUNDARIES = V2 / 'service-boundaries.json'
IDENTITY = V1 / 'odpt-train-identities.json'


def load_json(path: Path, default: Any = None) -> Any:
    try:
        text = path.read_text(encoding='utf-8').strip()
        return json.loads(text) if text else default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


def load_fragments(index: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slug, rel in (index.get('fragmentFiles') or {}).items():
        payload = load_json(V2 / str(rel), {}) or {}
        for fragment in payload.get('fragments') or []:
            if isinstance(fragment, dict) and fragment.get('id'):
                rows.append(fragment)
    return rows


def strict_indexes(manifest: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    indexes = base.index_entities(manifest)
    graph: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for boundary in registry.get('boundaries') or []:
        if not isinstance(boundary, dict) or boundary.get('status') != 'verified':
            continue
        first = str(boundary.get('fromRailway') or '')
        second = str(boundary.get('toRailway') or '')
        station = str(boundary.get('station') or '')
        if not first or not second or first == second:
            continue
        evidence = '|'.join(str(value) for value in boundary.get('sourceUrls') or [] if value)
        boundary_id = str(boundary.get('id') or '')

        def add(a: str, b: str) -> None:
            key = (a, b, boundary_id)
            if key in seen:
                return
            seen.add(key)
            graph[a].append({
                'fromRailway': a,
                'toRailway': b,
                'station': station,
                'kind': 'verified-operational-junction',
                'evidence': evidence,
                'boundaryId': boundary_id,
            })

        add(first, second)
        if boundary.get('bidirectional', True):
            add(second, first)
    indexes['graph'] = graph
    return indexes


def classify_inferred_routes(
    fragments: list[dict[str, Any]],
    indexes: dict[str, Any],
    unresolved: list[dict[str, Any]],
) -> None:
    for fragment in fragments:
        fragment.pop('throughRailwayPath', None)
        fragment.pop('throughPathEvidence', None)
        fragment.pop('publishedDestinationRailways', None)
        destinations = [str(value) for value in fragment.get('destination') or [] if value]
        if not destinations:
            continue
        current_railway = str(fragment.get('railway') or '')
        target_railways: set[str] = set()
        external_destinations: list[str] = []
        for destination in destinations:
            resolved = base.destination_railways(destination, indexes)
            # If this physical destination exists on the current railway,
            # the fragment terminates there; a different line-scoped ID
            # must not manufacture a through train.
            if current_railway in resolved:
                continue
            external_destinations.append(destination)
            target_railways.update(resolved)
        target_railways.discard(current_railway)
        if not target_railways:
            continue
        fragment['publishedDestinationRailways'] = sorted(target_railways)

        # Exact TrainTimetable fragments already have authoritative train
        # identity evidence. Do not invent a railway path from the destination
        # label; ODPT previous/next links (or an exact network journey) govern
        # whether the physical train continues.
        if fragment.get('sourceKind') != 'station-timetable-reconstruction':
            continue

        path = base.unique_shortest_path(indexes['graph'], str(fragment.get('railway') or ''), target_railways)
        if path.get('status') == 'matched':
            fragment['throughRailwayPath'] = path['railways']
            fragment['throughPathEvidence'] = [
                edge.get('boundaryId') or edge.get('kind') or 'verified-operational-junction'
                for edge in path.get('edges') or []
            ]
        else:
            unresolved.append({
                'kind': 'published-destination-route-' + str(path.get('status') or 'unknown'),
                'fragment': fragment['id'],
                'railway': fragment.get('railway'),
                'destination': external_destinations,
                'targetRailways': sorted(target_railways),
                'matches': path.get('matches') or [],
                'strictOperationalGraph': True,
            })


def identity_adjacency(records: list[dict[str, Any]]) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for row in records:
        timetable = str(row.get('timetableId') or '')
        if not timetable:
            continue
        for nxt in row.get('nextTrainTimetables') or []:
            nxt = str(nxt or '')
            if nxt:
                adjacency[timetable].add(nxt)
        for previous in row.get('previousTrainTimetables') or []:
            previous = str(previous or '')
            if previous:
                adjacency[previous].add(timetable)
    return adjacency


def authoritative_edges(
    fragments: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sidecar = load_json(IDENTITY, {}) or {}
    records = [row for row in sidecar.get('records') or [] if isinstance(row, dict)]
    by_tt = {str(row.get('timetableId') or ''): row for row in records if row.get('timetableId')}
    adjacency = identity_adjacency(records)
    fragment_by_tt = {
        str(fragment.get('timetableId') or ''): fragment
        for fragment in fragments
        if fragment.get('timetableId')
    }

    # Re-apply sidecar metadata because it is the authoritative identity copy.
    for timetable, row in by_tt.items():
        fragment = fragment_by_tt.get(timetable)
        if not fragment:
            continue
        if row.get('origin'):
            fragment['origin'] = [str(value) for value in row.get('origin') or [] if value]
        if row.get('destination'):
            fragment['destination'] = [str(value) for value in row.get('destination') or [] if value]
        fragment['previousTrainTimetables'] = [str(value) for value in row.get('previousTrainTimetables') or [] if value]
        fragment['nextTrainTimetables'] = [str(value) for value in row.get('nextTrainTimetables') or [] if value]
        fragment['identityLevel'] = 'official-train-timetable'

    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str]] = set()
    unresolved_seen: set[tuple[str, str, str]] = set()

    def add_edge(source: dict[str, Any], target: dict[str, Any], evidence: str, via: list[str]) -> None:
        key = (str(source['id']), str(target['id']))
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge: dict[str, Any] = {
            'fromFragment': source['id'],
            'toFragment': target['id'],
            'classification': 'same-train',
            'identityLevel': 'authoritative',
            'evidence': [evidence],
            'boundary': {
                'fromRailway': source.get('railway'),
                'toRailway': target.get('railway'),
            },
        }
        if via:
            edge['viaTimetables'] = via
        edges.append(edge)

    def note(kind: str, source_tt: str, linked_tt: str, **extra: Any) -> None:
        key = (kind, source_tt, linked_tt)
        if key in unresolved_seen:
            return
        unresolved_seen.add(key)
        unresolved.append({'kind': kind, 'fromTimetable': source_tt, 'toTimetable': linked_tt, **extra})

    for source_tt, source in fragment_by_tt.items():
        for first_link in sorted(adjacency.get(source_tt, set())):
            if first_link in fragment_by_tt:
                add_edge(source, fragment_by_tt[first_link], 'odpt:next/previousTrainTimetable', [])
                continue

            # Compact app timetables intentionally omit fragments with fewer
            # than two usable stops. Follow only a deterministic authoritative
            # ODPT chain through such identity-only fragments. Never use train
            # number or time gaps to bridge it.
            current = first_link
            via: list[str] = []
            visited = {source_tt}
            while current and current not in visited and current not in fragment_by_tt:
                visited.add(current)
                via.append(current)
                next_values = sorted(adjacency.get(current, set()))
                if len(next_values) != 1:
                    if len(next_values) > 1:
                        note('ambiguous-authoritative-linked-timetable-chain', source_tt, first_link, viaTimetables=via, nextTimetables=next_values)
                    else:
                        note('missing-authoritative-linked-timetable', source_tt, first_link, viaTimetables=via)
                    current = ''
                    break
                current = next_values[0]
            if current in fragment_by_tt:
                add_edge(source, fragment_by_tt[current], 'odpt:TrainTimetable-link-chain', via)
            elif current in visited:
                note('cyclic-authoritative-linked-timetable-chain', source_tt, first_link, viaTimetables=via)
    return edges


def write_outputs(
    fragments: list[dict[str, Any]],
    networks: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    index: dict[str, Any],
) -> dict[str, Any]:
    generated = datetime.now(timezone.utc).isoformat()
    by_operator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for fragment in fragments:
        slug = str(fragment.get('sourceOperator') or 'unknown')
        by_operator[slug].append(fragment)
        source_counts[slug][str(fragment.get('sourceKind') or 'unknown')] += 1

    fragment_files: dict[str, str] = {}
    for slug, rows in sorted(by_operator.items()):
        filename = f'fragments/{slug}.json'
        fragment_files[slug] = filename
        write_json(V2 / filename, {'version': 1, 'operator': slug, 'fragments': rows})

    write_json(V2 / 'same-train-edges.json', {
        'version': 2,
        'generatedAt': generated,
        'policy': {
            'runtimeInference': False,
            'timeGapMayEstablishTrainIdentity': False,
            'trainNumberMayEstablishTrainIdentity': False,
            'lineNameChangeCountsAsTransfer': False,
            'unresolvedMayBeShownAsThrough': False,
            'genericSameOperatorSharedStationMayEstablishPath': False,
        },
        'edges': edges,
    })

    fragment_by_id = {str(fragment.get('id') or ''): fragment for fragment in fragments if fragment.get('id')}

    def runtime_ref(fragment: dict[str, Any] | None) -> str:
        if not fragment:
            return ''
        if fragment.get('sourceKind') == 'exact-train-timetable':
            timetable_id = str(fragment.get('timetableId') or '')
            return f'tt:{timetable_id}' if timetable_id else ''
        if fragment.get('sourceKind') == 'station-timetable-reconstruction':
            trip_index = fragment.get('sourceTripIndex')
            railway = str(fragment.get('railway') or '')
            if isinstance(trip_index, int) and railway:
                return f'inf:{railway}:{trip_index}'
        return ''

    runtime_edges: list[list[str]] = []
    runtime_seen: set[tuple[str, str, str, str]] = set()
    for edge in edges:
        source = fragment_by_id.get(str(edge.get('fromFragment') or ''))
        target = fragment_by_id.get(str(edge.get('toFragment') or ''))
        source_ref = runtime_ref(source)
        target_ref = runtime_ref(target)
        from_railway = str((source or {}).get('railway') or '')
        to_railway = str((target or {}).get('railway') or '')
        key = (source_ref, target_ref, from_railway, to_railway)
        if not source_ref or not target_ref or not from_railway or not to_railway or key in runtime_seen:
            continue
        runtime_seen.add(key)
        runtime_edges.append(list(key))
    write_json(V2 / 'runtime-same-train.json', {
        'version': 1,
        'generatedAt': generated,
        'policy': {
            'runtimeInference': False,
            'unknownMayBePromotedToSameTrain': False,
            'trainNumberAloneMayResolve': False,
            'timeGapAloneMayResolve': False,
        },
        'edges': runtime_edges,
    })

    coverage = {
        'version': 2,
        'generatedAt': generated,
        'summary': {
            'fragments': len(fragments),
            'exactFragments': sum(1 for f in fragments if f.get('sourceKind') == 'exact-train-timetable'),
            'inferredFragments': sum(1 for f in fragments if f.get('sourceKind') == 'station-timetable-reconstruction'),
            'networkJourneys': len(networks),
            'sameTrainEdges': len(edges),
            'authoritativeSameTrainEdges': sum(1 for e in edges if e.get('identityLevel') == 'authoritative'),
            'evidenceBackedSameTrainEdges': sum(1 for e in edges if e.get('identityLevel') == 'evidence-backed'),
            'fragmentsWithDestination': sum(1 for f in fragments if f.get('destination')),
            'fragmentsWithThroughRailwayPath': sum(1 for f in fragments if len(f.get('throughRailwayPath') or []) > 1),
            'unresolved': len(unresolved),
        },
        'byOperator': {slug: dict(values) for slug, values in sorted(source_counts.items())},
        'unresolved': unresolved,
        'policy': {
            'exactIdentitySource': 'ODPT previous/next TrainTimetable or exact network journey',
            'inferredIdentityRequiresVerifiedOperationalPath': True,
        },
    }
    write_json(V2 / 'coverage.json', coverage)

    updated_index = dict(index)
    updated_index['version'] = 2
    updated_index['generatedAt'] = generated
    updated_index['fragmentFiles'] = fragment_files
    updated_index['finalizer'] = 'strict-train-identity-v2'
    updated_index['runtimeSameTrain'] = 'runtime-same-train.json'
    write_json(V2 / 'index.json', updated_index)
    print(json.dumps(coverage['summary'], ensure_ascii=False, indent=2))
    return coverage


def main() -> int:
    manifest = load_json(V1 / 'manifest.json', {}) or {}
    registry = load_json(BOUNDARIES, {}) or {}
    index = load_json(V2 / 'index.json', {}) or {}
    networks_payload = load_json(V2 / 'network-journeys.json', {}) or {}
    networks = [row for row in networks_payload.get('journeys') or [] if isinstance(row, dict)]
    fragments = load_fragments(index)
    if not fragments:
        raise RuntimeError('No transit-v2 fragments are available to finalize')

    indexes = strict_indexes(manifest, registry)
    unresolved: list[dict[str, Any]] = []
    classify_inferred_routes(fragments, indexes, unresolved)
    edges = authoritative_edges(fragments, unresolved)
    edges = base.align_inferred_edges(fragments, indexes, edges, unresolved)
    edges = reviewed.apply_reviewed_train_evidence(
        fragments,
        edges,
        unresolved,
        indexes,
        V2 / 'reviewed-train-evidence.json',
    )

    coverage = write_outputs(fragments, networks, edges, unresolved, index)
    policy = registry.get('policy') or {}
    if policy.get('genericSameOperatorSharedStationMayEstablishPath') is not False:
        raise RuntimeError('service-boundary registry must explicitly prohibit generic same-operator shared-station paths')
    if any(edge.get('identityLevel') not in {'authoritative', 'evidence-backed'} for edge in edges):
        raise RuntimeError('unexpected same-train identity level')
    if any('train-number' in '|'.join(edge.get('evidence') or []).lower() for edge in edges):
        raise RuntimeError('train number evidence must never establish same-train identity')
    print('strict transit-v2 finalization passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
