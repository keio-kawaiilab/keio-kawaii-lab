#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path('data/transit-v2')
KIND = 'missing-boundary-train-identity-evidence'


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    return value if isinstance(value, dict) else {}


def stop_station(stop: Any) -> str:
    return str(stop[0] or '') if isinstance(stop, list) and stop else ''


def stop_times(stop: Any) -> list[int]:
    if not isinstance(stop, list):
        return []
    return [int(value) for value in stop[1:3] if isinstance(value, (int, float))]


def short_station(value: str) -> str:
    return value.rsplit('.', 1)[-1] if value else ''


def fragment_summary(fragment: dict[str, Any]) -> dict[str, Any]:
    stops = fragment.get('stops') or []
    return {
        'id': fragment.get('id'),
        'railway': fragment.get('railway'),
        'calendar': fragment.get('calendar'),
        'sourceKind': fragment.get('sourceKind'),
        'origin': fragment.get('origin') or [],
        'destination': fragment.get('destination') or [],
        'stopCount': len(stops),
        'first': [stop_station(stops[0]), stop_times(stops[0])] if stops else None,
        'last': [stop_station(stops[-1]), stop_times(stops[-1])] if stops else None,
        'firstStations': [stop_station(stop) for stop in stops[:4]],
        'lastStations': [stop_station(stop) for stop in stops[-4:]],
    }


def main() -> int:
    coverage = load(ROOT / 'coverage.json')
    fragments_payload = load(ROOT / 'fragments/keikyu.json')
    fragments = [row for row in fragments_payload.get('fragments') or [] if isinstance(row, dict) and row.get('id')]
    by_id = {str(row['id']): row for row in fragments}

    rows = [
        row for row in coverage.get('unresolved') or []
        if isinstance(row, dict)
        and row.get('kind') == KIND
        and ((row.get('_context') or {}).get('operator') == 'keikyu' or str(row.get('railway') or '').startswith('odpt.Railway:Keikyu.'))
    ]

    pair_counts = Counter((str(row.get('railway') or ''), str(row.get('nextRailway') or '')) for row in rows)
    report: dict[str, Any] = {
        'totalKeikyuMissingBoundary': len(rows),
        'pairs': {},
    }

    for pair, count in sorted(pair_counts.items(), key=lambda item: (-item[1], item[0])):
        pair_rows = [row for row in rows if (str(row.get('railway') or ''), str(row.get('nextRailway') or '')) == pair]
        first_counter = Counter()
        last_counter = Counter()
        stop_counts = Counter()
        calendars = Counter()
        destinations = Counter()
        missing_fragments = 0
        examples: list[dict[str, Any]] = []
        for row in pair_rows:
            fragment = by_id.get(str(row.get('fragment') or ''))
            if not fragment:
                missing_fragments += 1
                continue
            stops = fragment.get('stops') or []
            first_counter[short_station(stop_station(stops[0])) if stops else '(none)'] += 1
            last_counter[short_station(stop_station(stops[-1])) if stops else '(none)'] += 1
            stop_counts[len(stops)] += 1
            calendars[str(fragment.get('calendar') or '')] += 1
            for destination in fragment.get('destination') or []:
                destinations[short_station(str(destination))] += 1
            if len(examples) < 8:
                examples.append({
                    'unresolved': {
                        'fragment': row.get('fragment'),
                        'railway': row.get('railway'),
                        'nextRailway': row.get('nextRailway'),
                        'destination': row.get('destination'),
                    },
                    'fragment': fragment_summary(fragment),
                })
        report['pairs'][f'{pair[0]} -> {pair[1]}'] = {
            'count': count,
            'missingFragmentRefs': missing_fragments,
            'firstStationTop': first_counter.most_common(12),
            'lastStationTop': last_counter.most_common(12),
            'stopCountTop': stop_counts.most_common(12),
            'calendars': dict(calendars),
            'destinationTop': destinations.most_common(12),
            'examples': examples,
        }

    zushi_pairs = {
        key: value for key, value in report['pairs'].items()
        if 'Keikyu.Zushi' in key
    }
    compact = {
        'totalKeikyuMissingBoundary': report['totalKeikyuMissingBoundary'],
        'zushiPairs': zushi_pairs,
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
