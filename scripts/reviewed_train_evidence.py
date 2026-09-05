#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import keikyu_generated_evidence as keikyu_generated
import keisei_generated_evidence as keisei_generated


def load_json(path: Path, default: Any = None) -> Any:
    try:
        text = path.read_text(encoding='utf-8').strip()
        return json.loads(text) if text else default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def stop_departure(stop: Any) -> int | None:
    if not isinstance(stop, list) or len(stop) < 3:
        return None
    raw = stop[2] if stop[2] is not None else stop[1]
    return int(raw) if isinstance(raw, (int, float)) else None


def matches_stop(stop: Any, selector: dict[str, Any]) -> bool:
    if not isinstance(stop, list) or not stop:
        return False
    station = str(selector.get('station') or '')
    if station and str(stop[0] or '') != station:
        return False
    departure = selector.get('departure')
    if departure is not None and stop_departure(stop) != int(departure):
        return False
    return True


def matches_fragment(fragment: dict[str, Any], selector: dict[str, Any]) -> bool:
    for key in ('railway', 'calendar', 'trainType'):
        expected = str(selector.get(key) or '')
        if expected and str(fragment.get(key) or '') != expected:
            return False
    destination = str(selector.get('destination') or '')
    if destination and destination not in [str(value) for value in fragment.get('destination') or []]:
        return False
    stops = fragment.get('stops') or []
    contains = selector.get('containsStop')
    if isinstance(contains, dict) and not any(matches_stop(stop, contains) for stop in stops):
        return False
    first = selector.get('firstStop')
    if isinstance(first, dict) and (not stops or not matches_stop(stops[0], first)):
        return False
    return True


def apply_reviewed_train_evidence(
    fragments: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    indexes: dict[str, Any],
    registry_path: Path,
) -> list[dict[str, Any]]:
    registry = load_json(registry_path, {}) or {}
    entries = [row for row in registry.get('entries') or [] if isinstance(row, dict) and row.get('status') == 'verified-current']
    output = list(edges)
    seen = {(str(edge.get('fromFragment') or ''), str(edge.get('toFragment') or '')) for edge in output}
    resolved_sources: set[str] = set()

    for entry in entries:
        entry_id = str(entry.get('id') or '')
        sources = [fragment for fragment in fragments if matches_fragment(fragment, entry.get('from') or {})]
        targets = [fragment for fragment in fragments if matches_fragment(fragment, entry.get('to') or {})]
        if len(sources) != 1 or len(targets) != 1:
            unresolved.append({
                'kind': 'reviewed-train-evidence-selector-mismatch',
                'evidenceId': entry_id,
                'sourceMatches': [fragment.get('id') for fragment in sources],
                'targetMatches': [fragment.get('id') for fragment in targets],
            })
            continue
        source, target = sources[0], targets[0]
        from_railway = str(source.get('railway') or '')
        to_railway = str(target.get('railway') or '')
        boundary_id = str(entry.get('boundaryId') or '')
        boundary = next((
            edge for edge in indexes.get('graph', {}).get(from_railway, [])
            if str(edge.get('toRailway') or '') == to_railway
            and (not boundary_id or str(edge.get('boundaryId') or '') == boundary_id)
        ), None)
        if not boundary:
            unresolved.append({
                'kind': 'reviewed-train-evidence-unverified-boundary',
                'evidenceId': entry_id,
                'fromFragment': source.get('id'),
                'toFragment': target.get('id'),
                'fromRailway': from_railway,
                'toRailway': to_railway,
                'boundaryId': boundary_id,
            })
            continue
        key = (str(source['id']), str(target['id']))
        if key not in seen:
            seen.add(key)
            output.append({
                'fromFragment': source['id'],
                'toFragment': target['id'],
                'classification': 'same-train',
                'identityLevel': 'evidence-backed',
                'evidence': ['operator-official-per-train-timetable', entry_id],
                'sourceUrls': [str(url) for url in entry.get('sourceUrls') or [] if url],
                'boundary': {
                    'station': boundary.get('station') or '',
                    'fromRailway': from_railway,
                    'toRailway': to_railway,
                },
            })
        resolved_sources.add(str(source['id']))

    if resolved_sources:
        unresolved[:] = [
            row for row in unresolved
            if not (
                row.get('kind') == 'ambiguous-boundary-fragment-alignment'
                and str(row.get('fragment') or '') in resolved_sources
            )
        ]

    output = keikyu_generated.apply_generated_evidence(
        fragments,
        output,
        unresolved,
        indexes,
        registry_path.parent / 'keikyu-official-train-evidence.json',
    )
    return keisei_generated.apply_generated_evidence(
        fragments,
        output,
        unresolved,
        indexes,
        registry_path.parent / 'keisei-official-oshiage-evidence.json',
    )
