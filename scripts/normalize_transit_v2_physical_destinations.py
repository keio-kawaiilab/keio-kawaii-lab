#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_transit_v2 as base

ROOT = Path('.')
V1 = ROOT / 'data/transit'
V2 = ROOT / 'data/transit-v2'


def load_json(path: Path, default: Any = None) -> Any:
    try:
        text = path.read_text(encoding='utf-8').strip()
        return json.loads(text) if text else default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


def destination_title(destination: str, indexes: dict[str, Any]) -> str:
    exact = str(indexes.get('stationTitle', {}).get(destination) or '')
    if exact:
        return exact
    suffix = destination.rsplit('.', 1)[-1] if destination else ''
    titles = {
        str(title)
        for sid, title in indexes.get('stationTitle', {}).items()
        if str(sid).rsplit('.', 1)[-1] == suffix and title
    }
    return next(iter(titles)) if len(titles) == 1 else ''


def main() -> int:
    manifest = load_json(V1 / 'manifest.json', {}) or {}
    index = load_json(V2 / 'index.json', {}) or {}
    coverage = load_json(V2 / 'coverage.json', {}) or {}
    indexes = base.index_entities(manifest)

    fragment_by_id: dict[str, dict[str, Any]] = {}
    file_payloads: dict[Path, dict[str, Any]] = {}
    for rel in (index.get('fragmentFiles') or {}).values():
        path = V2 / str(rel)
        payload = load_json(path, {}) or {}
        file_payloads[path] = payload
        for fragment in payload.get('fragments') or []:
            if isinstance(fragment, dict) and fragment.get('id'):
                fragment_by_id[str(fragment['id'])] = fragment

    kept: list[dict[str, Any]] = []
    resolved = 0
    resolved_by_railway: dict[str, int] = {}
    for row in coverage.get('unresolved') or []:
        if not isinstance(row, dict) or row.get('kind') != 'published-destination-route-no-path':
            kept.append(row)
            continue
        fragment = fragment_by_id.get(str(row.get('fragment') or ''))
        if not fragment or fragment.get('sourceKind') != 'station-timetable-reconstruction':
            kept.append(row)
            continue
        railway = str(fragment.get('railway') or '')
        current_names = set(indexes.get('railwayStationTitles', {}).get(railway, set()))
        destinations = [str(value) for value in fragment.get('destination') or [] if value]
        names = [destination_title(value, indexes) for value in destinations]
        # A destination station ID may be owned by a different line even when
        # the physical station is also on this train's current line. In that
        # case the destination label does not imply any through service.
        if destinations and all(name and name in current_names for name in names):
            fragment.pop('throughRailwayPath', None)
            fragment.pop('throughPathEvidence', None)
            fragment.pop('publishedDestinationRailways', None)
            fragment['destinationPhysicalScope'] = 'current-railway-terminal'
            resolved += 1
            resolved_by_railway[railway] = resolved_by_railway.get(railway, 0) + 1
            continue
        kept.append(row)

    coverage['unresolved'] = kept
    coverage.setdefault('summary', {})['unresolved'] = len(kept)
    coverage['physicalDestinationNormalization'] = {
        'resolvedFalseThroughCandidates': resolved,
        'byRailway': dict(sorted(resolved_by_railway.items(), key=lambda item: (-item[1], item[0]))),
        'rule': 'A destination ID on another railway does not imply through service when the same physical station title is part of the current railway.',
    }

    for path, payload in file_payloads.items():
        write_json(path, payload)
    write_json(V2 / 'coverage.json', coverage)

    print(json.dumps({
        'resolvedFalseThroughCandidates': resolved,
        'remainingUnresolved': len(kept),
        'topRailways': list(coverage['physicalDestinationNormalization']['byRailway'].items())[:12],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
