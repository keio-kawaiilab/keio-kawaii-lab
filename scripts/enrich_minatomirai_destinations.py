#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path('data/transit')
MM_INDEX = ROOT / 'yokohama-minatomirai/timetable-index.json'
TOKYU_INDEX = ROOT / 'tokyu/timetable-index.json'
MM_RAILWAY = 'manual.Railway:YokohamaMinatomirai.Minatomirai'
TOKYU_RAILWAY = 'odpt.Railway:Tokyu.Toyoko'
MM_YOKOHAMA = 'manual.Station:yokohama-minatomirai.横浜'
TOKYU_YOKOHAMA = 'odpt.Station:Tokyu.Toyoko.Yokohama'
REPORT = ROOT / 'yokohama-minatomirai/destination-alignment.json'


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


def path_for(index_path: Path, railway: str) -> Path:
    index = load(index_path)
    row = (index.get('lines') or {}).get(railway) or {}
    rel = row.get('file')
    if not rel:
        raise RuntimeError(f'missing timetable for {railway}')
    return index_path.parent / str(rel)


def normalized_destination(value: str) -> str:
    return value.rsplit('.', 1)[-1].lower().replace('-', '').replace('_', '')


def is_minatomirai_southbound_destination(value: str) -> bool:
    key = normalized_destination(value)
    return key in {'motomachichukagai', '元町・中華街'}


def boundary_basis(stop: list[Any]) -> int | None:
    if len(stop) < 3:
        return None
    raw = stop[1] if stop[1] is not None else stop[2]
    return int(raw) if isinstance(raw, (int, float)) else None


def enrich_table(mm: dict[str, Any], tokyu: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    mm = json.loads(json.dumps(mm, ensure_ascii=False))
    mm_stations = mm.get('stations') or []
    tokyu_stations = tokyu.get('stations') or []
    try:
        mm_yokohama = mm_stations.index(MM_YOKOHAMA)
        tokyu_yokohama = tokyu_stations.index(TOKYU_YOKOHAMA)
    except ValueError as exc:
        raise RuntimeError('Yokohama station is missing from one timetable') from exc

    tokyu_calendars = tokyu.get('calendars') or []
    tokyu_destinations = tokyu.get('destinations') or []
    tokyu_types = tokyu.get('trainTypes') or []
    boundary_events: dict[str, list[dict[str, Any]]] = {}
    for board in tokyu.get('boards') or []:
        if not isinstance(board, list) or len(board) < 4 or board[0] != tokyu_yokohama:
            continue
        calendar = tokyu_calendars[board[1]] if isinstance(board[1], int) and board[1] < len(tokyu_calendars) else ''
        for departure in board[3] or []:
            if not isinstance(departure, list) or len(departure) < 3:
                continue
            destination = tokyu_destinations[departure[2]] if isinstance(departure[2], int) and departure[2] < len(tokyu_destinations) else ''
            if not destination or is_minatomirai_southbound_destination(str(destination)):
                continue
            train_type = tokyu_types[departure[1]] if isinstance(departure[1], int) and departure[1] < len(tokyu_types) else ''
            boundary_events.setdefault(str(calendar), []).append({
                'departure': int(departure[0]),
                'destination': str(destination),
                'trainType': str(train_type),
            })
    for rows in boundary_events.values():
        rows.sort(key=lambda row: row['departure'])

    mm_calendars = mm.get('calendars') or []
    mm_destinations = list(mm.get('destinations') or [])
    destination_index = {str(value): i for i, value in enumerate(mm_destinations)}

    def dest_idx(destination: str) -> int:
        if destination not in destination_index:
            destination_index[destination] = len(mm_destinations)
            mm_destinations.append(destination)
        return destination_index[destination]

    assignments: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    assigned_by_trip: dict[int, int] = {}
    for trip_index, trip in enumerate(mm.get('inferredTrips') or []):
        if not isinstance(trip, list) or len(trip) < 6:
            continue
        stops = trip[5] or []
        if not stops or stops[-1][0] != mm_yokohama:
            continue
        calendar = mm_calendars[trip[0]] if isinstance(trip[0], int) and trip[0] < len(mm_calendars) else ''
        arrival = boundary_basis(stops[-1])
        if arrival is None:
            unresolved.append({'tripIndex': trip_index, 'calendar': calendar, 'reason': 'missing-yokohama-time'})
            continue
        candidates = []
        for event in boundary_events.get(str(calendar), []):
            delta = int(event['departure']) - arrival
            while delta < -720:
                delta += 1440
            if 0 <= delta <= 3:
                candidates.append((delta, event))
        if not candidates:
            unresolved.append({'tripIndex': trip_index, 'calendar': calendar, 'arrival': arrival, 'reason': 'no-tokyu-match'})
            continue
        best_delta = min(delta for delta, _ in candidates)
        best = [event for delta, event in candidates if delta == best_delta]
        if len(best) != 1:
            unresolved.append({'tripIndex': trip_index, 'calendar': calendar, 'arrival': arrival, 'reason': 'ambiguous-tokyu-match', 'candidates': best})
            continue
        event = best[0]
        index = dest_idx(event['destination'])
        trip[3] = index
        assigned_by_trip[trip_index] = index
        assignments.append({
            'tripIndex': trip_index,
            'calendar': calendar,
            'yokohamaArrival': arrival,
            'tokyuDeparture': event['departure'],
            'deltaMinutes': best_delta,
            'destination': event['destination'],
            'tokyuTrainType': event['trainType'],
            'evidence': 'Yokohama Minatomirai official timetable + Tokyu official StationTimetable at Yokohama',
        })

    board_destination: dict[tuple[int, int, int], int] = {}
    for trip_index, destination in assigned_by_trip.items():
        trip = mm['inferredTrips'][trip_index]
        calendar_index = trip[0]
        for stop in trip[5] or []:
            station_index = stop[0]
            departure = stop[2] if len(stop) > 2 else None
            if departure is not None:
                board_destination[(station_index, calendar_index, int(departure))] = destination
    for board in mm.get('boards') or []:
        if not isinstance(board, list) or len(board) < 4:
            continue
        station_index, calendar_index = board[0], board[1]
        for departure in board[3] or []:
            if not isinstance(departure, list) or len(departure) < 3:
                continue
            key = (station_index, calendar_index, int(departure[0]))
            if key in board_destination:
                departure[2] = board_destination[key]

    mm['destinations'] = mm_destinations
    mm['destinationAuthoritative'] = True
    mm['destinationBasis'] = 'official-minatomirai-schedule aligned to official Tokyu Toyoko Yokohama StationTimetable'
    mm.setdefault('sourceMetadata', {})['destinationAlignment'] = {
        'boundary': '横浜',
        'sourceRailway': TOKYU_RAILWAY,
        'assignedTrips': len(assignments),
        'unresolvedTrips': len(unresolved),
    }
    report = {
        'version': 1,
        'assignedTrips': len(assignments),
        'unresolvedTrips': len(unresolved),
        'assignments': assignments,
        'unresolved': unresolved,
    }
    return mm, report


def main() -> int:
    mm_path = path_for(MM_INDEX, MM_RAILWAY)
    tokyu_path = path_for(TOKYU_INDEX, TOKYU_RAILWAY)
    mm, report = enrich_table(load(mm_path), load(tokyu_path))
    save(mm_path, mm)
    save(REPORT, report)
    print(json.dumps({'assignedTrips': report['assignedTrips'], 'unresolvedTrips': report['unresolvedTrips']}, ensure_ascii=False))
    if report['assignedTrips'] == 0:
        raise RuntimeError('no Minatomirai destinations were aligned to Tokyu')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
