#!/usr/bin/env python3
"""Independent, full-record verification of the registered western DB import."""
import hashlib
import json
from pathlib import Path

from transit_network_db import read_json, load_network_journeys


def verify(root=Path('.')):
    root = Path(root)
    source = root / 'data/transit/yahoo-western-research'
    db = root / 'data/transit-v2'
    pages = read_json(source / 'train-pages.json.gz')
    routes = read_json(source / 'classified-trains.json.gz')
    index = read_json(db / 'index.json')
    assert index['networkJourneyFiles']['western-yahoo'] == 'western/network-journeys.json.gz'
    journeys = [j for j in load_network_journeys(db, index) if j.get('sourceOperator') == 'western-yahoo']
    by_tid = {j['sourceTrainId']: j for j in journeys}
    assert len(journeys) == len(by_tid) == len(pages) == 7898, 'missing/duplicate train'
    assert by_tid.keys() == pages.keys(), 'source mother set differs'
    catalog = read_json(db / index['sourceCatalogs']['western-yahoo']['stations'])
    calendar_data = read_json(db / index['sourceCatalogs']['western-yahoo']['calendars'])
    stations = {s['id']: s for s in catalog['stations']}
    calendars = {c['id']: c for c in calendar_data['calendars']}
    rails = {r['sourceRailway']: r['id'] for r in catalog['railways']}
    assert len(stations) == 248 and len(calendars) == 36
    checked = 0
    for tid, page in pages.items():
        j = by_tid[tid]
        assert j['railwayPath'] == [rails[r] for r in routes[tid]['railways']], ('route', tid)
        assert j['classification'] == routes[tid]['classification']
        assert j['identityLevel'] == 'source-exact-network'
        assert j['sourceSha256'] == page['sha256'] and j['sourceURL'] == page['url']
        assert j['sourceDisplayName'] == page['displayName'] and j['sectionComment'] == page['sectionComment']
        rule = calendars[j['calendar']]
        assert rule['dayKinds'] == routes[tid]['kinds'] and rule['sourceRule'] == page['calendarCondition']
        assert rule['dateRestricted'] == j['dateRestricted'] == routes[tid]['hasDateRestriction']
        if rule['dateRestricted']:
            assert rule['requiresDateEvaluation'] and rule['year'] is None
        assert len(j['stops']) == len(page['stops'])
        for actual, expected in zip(j['stops'], page['stops']):
            assert stations[actual[0]]['sourceStationId'] == expected['stationCode'], ('station', tid)
            for position, field in [(1, 'arrivalTime'), (2, 'departureTime')]:
                value = expected[field]
                if value is None:
                    assert actual[position] is None, ('invented time', tid)
                else:
                    h, m = divmod(int(value), 100)
                    minutes = h * 60 + m
                    if minutes < 180:
                        minutes += 1440
                    assert actual[position] == minutes, ('time', tid, expected['stationName'])
            checked += 1
        assert j['origin'] == j['stops'][0][0] and j['destination'] == j['stops'][-1][0]
    # Same-named physical stations must not acquire aliases on unrelated lines.
    ogawa = next(s for s in stations.values() if s['name'] == '小川町(埼玉県)')
    assert not any('Toei.Shinjuku' in alias for alias in ogawa['aliases'])
    assert by_tid['118449']['railwayPath'] == ['odpt.Railway:Tobu.Tojo']
    assert by_tid['119302']['railwayPath'] == ['odpt.Railway:Tobu.Tojo', 'odpt.Railway:TokyoMetro.Yurakucho']
    assert by_tid['111161']['railwayPath'][-1] == 'odpt.Railway:Tokyu.Meguro'
    assert by_tid['128823']['railwayPath'][-1] == 'odpt.Railway:Tokyu.Toyoko'
    assert by_tid['111140']['dateRestricted'] and by_tid['111141']['dateRestricted']
    assert len(by_tid['175818']['railwayPath']) == 6  # S-TRAIN crosses a line with no platform stop.
    receipt = read_json(db / 'western/import-audit.json')
    for path, expected in receipt['legacyInputSha256'].items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == expected, ('legacy input changed', path)
    for filename, expected in receipt['files'].items():
        assert hashlib.sha256((db / 'western' / filename).read_bytes()).hexdigest() == expected, ('import file changed', filename)
    assert receipt['legacyIdentityPromotions'] == 0
    assert receipt['importedTrainIds'] == len(journeys) and receipt['stopEvents'] == checked
    result = {'complete': True, 'indexedTrainIds': len(journeys), 'verifiedStopEvents': checked,
              'through': sum(j['classification'] == 'through' for j in journeys),
              'lineOnly': sum(j['classification'] == 'line-only' for j in journeys),
              'dateRestricted': sum(j['dateRestricted'] for j in journeys), 'missingReferences': 0}
    return result


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
