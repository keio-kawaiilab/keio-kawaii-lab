#!/usr/bin/env python3
"""Import every audited Yahoo western train into the indexed transit-v2 DB.

The source snapshot has its own stable train, station and calendar keys. Legacy
ODPT/inferred fragments remain intact; exact content matches are a crosswalk,
never permission to invent missing events or unconditional runtime continuations.
"""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re

from transit_network_db import read_json, load_network_journeys

SOURCE = 'western-yahoo'
SOURCE_DIR = 'data/transit/yahoo-western-research'
DB_DIR = 'data/transit-v2/western'


def norm(name):
    return re.sub(r'\([^)]*\)|（[^）]*）|<[^>]*>|〈[^〉]*〉', '', name).replace('ケ', 'ヶ').replace('麴', '麹')


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
    raw = gzip.compress(raw, mtime=0) if path.suffix == '.gz' else raw
    if path.exists() and path.read_bytes() == raw:
        return
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(raw)
    tmp.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def minute(clock):
    if clock is None:
        return None
    n = int(clock)
    hour, mins = n // 100, n % 100
    if not 0 <= hour < 27 or not 0 <= mins < 60:
        raise ValueError('Invalid source clock')
    return (hour + 24 if hour < 3 else hour) * 60 + mins


def legacy_minute(value):
    if value is None:
        return None
    n = int(value)
    return n + 1440 if n < 180 else n


def legacy_day_kinds(calendar):
    text = str(calendar or '').lower()
    if 'weekday' in text or '平日' in text:
        return {1}
    if any(s in text for s in ['saturdayholiday', 'saturdayandholiday', 'weekend', '土休日']):
        return {2, 4}
    if 'saturday' in text:
        return {2}
    if any(s in text for s in ['holiday', 'sunday', '休日']):
        return {4}
    return set()


def entity_aliases(root, names, topology):
    """Resolve only stations actually present in this bounded source inventory."""
    by_name = collections.defaultdict(set)
    by_id = {}
    allowed = {r: {norm(s) for s in ss} for r, ss in topology.items()}
    allowed['JR-East.Saikyo'] = allowed['JR.SaikyoSotetsuThrough']
    allowed['JR-East.SaikyoKawagoe'] = allowed['JR.SaikyoSotetsuThrough'] | allowed['JR.Kawagoe']
    allowed['JR-East.SotetsuDirect'] = allowed['JR.SaikyoSotetsuThrough']
    allowed['JR-East.Yokosuka'] = allowed['JR.SaikyoSotetsuThrough']
    allowed['JR-East.Kawagoe'] = allowed['JR.Kawagoe']
    allowed['JR-East.Musashino'] = {'東川口'}
    for path in sorted((root / 'data/transit').glob('*/entities.json')):
        entities = read_json(path)
        for station in entities.get('Station', []):
            sid = station.get('owl:sameAs')
            title = station.get('odpt:stationTitle', {}).get('ja') or station.get('dc:title')
            if sid and title:
                by_id[sid] = norm(title)
                memberships = station.get('odpt:railway') or []
                memberships = memberships if isinstance(memberships, list) else [memberships]
                if norm(title) in names and any(norm(title) in allowed.get(r.split(':')[-1], set()) for r in memberships):
                    by_name[norm(title)].add(sid)
        for railway in entities.get('Railway', []):
            short = railway.get('owl:sameAs', '').split(':')[-1]
            for station in railway.get('odpt:stationOrder', []):
                sid = station.get('odpt:station')
                title = station.get('odpt:stationTitle', {}).get('ja') or by_id.get(sid)
                if sid and title and norm(title) in names and norm(title) in allowed.get(short, set()):
                    by_name[norm(title)].add(sid)
    return by_name


def build_payloads(root):
    directory = root / SOURCE_DIR
    audit = read_json(directory / 'audit.json')
    if not audit.get('complete') or audit.get('exactDepartureMismatches') or audit.get('routeErrors'):
        raise ValueError('Western source inventory has not passed its complete audit')
    manifest = read_json(directory / 'manifest.json')
    for rel, expected in manifest.items():
        if hashlib.sha256((root / rel).read_bytes()).hexdigest() != expected['sha256']:
            raise ValueError('Audited source hash changed: ' + rel)
    pages = read_json(directory / 'train-pages.json.gz')
    classified = read_json(directory / 'classified-trains.json.gz')
    occurrences = read_json(directory / 'train-occurrences.json.gz')
    if pages.keys() != classified.keys() or pages.keys() != occurrences.keys() or len(pages) != audit['trainIds']:
        raise ValueError('Train mother sets differ')
    versions = {t['engineVersion'] for t in pages.values()}
    if len(versions) != 1:
        raise ValueError('Mixed source timetable editions')
    edition = next(iter(versions))
    names = {}
    for page in pages.values():
        for stop in page['stops']:
            code, name = stop['stationCode'], stop['stationName']
            if code in names and norm(names[code]) != norm(name):
                raise ValueError('Conflicting physical station name')
            names[code] = name
    normalized_names = collections.defaultdict(list)
    for code, name in names.items():
        normalized_names[norm(name)].append(code)
    if any(len(codes) != 1 for codes in normalized_names.values()):
        raise ValueError('Station name is ambiguous within this source inventory')
    targets = read_json(directory / 'target-stations.json')
    topology = read_json(directory / 'line-topology.json')
    aliases = entity_aliases(root, normalized_names, topology)
    railway_ids = {t['railway'].split(':')[-1]: t['railway'] for t in targets}
    railway_ids.update({'JR.SaikyoSotetsuThrough': 'manual.Railway:JR-East.SaikyoSotetsuThrough',
                        'JR.Kawagoe': 'odpt.Railway:JR-East.Kawagoe',
                        'Chichibu.Chichibu': 'manual.Railway:Chichibu.Chichibu'})
    rail_names = {row['railway']: row['railName'] for c in read_json(directory / 'station-index.json').values() for row in c['directions']}
    rail_names.update({'JR.SaikyoSotetsuThrough': 'JR埼京・相鉄直通線', 'JR.Kawagoe': 'JR川越線', 'Chichibu.Chichibu': '秩父鉄道'})
    station_key = lambda code: 'yahoo.Station:' + code
    stations = [{'id': station_key(code), 'sourceStationId': code, 'name': name,
                 'aliases': sorted(aliases[norm(name)]),
                 'railways': sorted(railway_ids[r] for r, ss in topology.items() if norm(name) in {norm(s) for s in ss}),
                 'sourceURL': 'https://transit.yahoo.co.jp/timetable/' + code}
                for code, name in sorted(names.items())]
    railways = [{'id': rid, 'name': rail_names[r], 'sourceRailway': r,
                 'stationOrder': [station_key(normalized_names[norm(s)][0]) for s in topology[r] if norm(s) in normalized_names]}
                for r, rid in sorted(railway_ids.items())]
    calendars = {}
    journeys = []
    for tid, page in sorted(pages.items()):
        row = classified[tid]
        if row['classification'] not in ['line-only', 'through'] or not row['railways']:
            raise ValueError('Unclassified source train')
        condition = {'dayKinds': row['kinds'], 'sourceRule': page['calendarCondition'],
                     'dateRestricted': row['hasDateRestriction']}
        cid = 'yahoo.Calendar:' + edition + ':' + digest(condition)[:16]
        calendars[cid] = dict(id=cid, **condition,
            dayKindLabels={'1': 'weekday', '2': 'saturday', '4': 'sunday-or-public-holiday'},
            dateRuleStatus='source-expression-preserved' if condition['dateRestricted'] else 'weekday-pattern',
            year=None if condition['dateRestricted'] else 'not-applicable',
            requiresDateEvaluation=condition['dateRestricted'])
        stops = [[station_key(s['stationCode']), minute(s['arrivalTime']), minute(s['departureTime'])] for s in page['stops']]
        times = [n for s in stops for n in s[1:] if n is not None]
        if times != sorted(times) or stops[0][2] is None or stops[-1][1] is None:
            raise ValueError('Non-monotonic or incomplete published journey: ' + tid)
        journey = {
            'id': 'yahoo.Train:' + edition + ':' + tid,
            'sourceKind': 'published-one-train-page', 'sourceOperator': SOURCE,
            'sourceProvider': 'Yahoo!乗換案内', 'sourceTrainId': tid, 'sourceEdition': edition,
            'sourceURL': page['url'], 'sourceSha256': page['sha256'],
            'calendar': cid, 'railwayPath': [railway_ids[r] for r in row['railways']],
            'origin': stops[0][0], 'destination': stops[-1][0], 'stops': stops,
            'trainType': '', 'sourceDisplayName': page['displayName'],
            'trainNumber': '', 'sourceTrainNumbers': row['trainNumbers'],
            'sectionComment': page['sectionComment'], 'classification': row['classification'],
            'identityLevel': 'source-exact-network',
            'boardingRulesStatus': 'not-normalized',
            'dateRestricted': row['hasDateRestriction'],
            'sourceOccurrenceCount': len(occurrences[tid]),
        }
        journeys.append(journey)
    catalog = {'version': 1, 'source': SOURCE, 'sourceEdition': edition, 'stations': stations, 'railways': railways}
    rules = {'version': 1, 'source': SOURCE, 'calendars': [calendars[k] for k in sorted(calendars)],
             'policy': {'unknownYearMayBeInferred': False, 'dateRestrictedMayRunOnEveryListedWeekday': False}}
    network = {'version': 2, 'source': SOURCE, 'sourceEdition': edition, 'stationCatalog': 'station-catalog.json',
               'calendarCatalog': 'calendars.json', 'journeys': journeys,
               'policy': {'runtimeInference': False, 'trainNumberMayEstablishIdentity': False,
                          'timeProximityMayEstablishIdentity': False, 'publishedTypeAppliesToEverySection': False}}
    return network, catalog, rules


def match_legacy_fragments(root, network, catalog, calendars):
    """All available events in the entire old fragment must match contiguously."""
    alias = {}
    for station in catalog['stations']:
        for sid in station['aliases']:
            if sid in alias and alias[sid] != station['id']:
                raise ValueError('Conflicting existing station alias')
            alias[sid] = station['id']
    rules = {c['id']: c for c in calendars['calendars']}
    rails = {r['id'] for r in catalog['railways']}
    candidates = collections.defaultdict(list)
    for j in network['journeys']:
        for pos, (sid, arrival, departure) in enumerate(j['stops']):
            if departure is not None:
                candidates[sid, departure].append((j, pos))
    results = []
    for path in sorted((root / 'data/transit-v2/fragments').glob('*.json')):
        for fragment in read_json(path).get('fragments', []):
            rail = fragment.get('railway')
            if rail not in rails:
                continue
            f = fragment.get('stops') or []
            kinds = legacy_day_kinds(fragment.get('calendar'))
            result = {'fragmentId': fragment['id'], 'railway': rail,
                      'sourceFile': str(path.relative_to(root)), 'journeyIds': []}
            if len(f) < 2 or not kinds or any(s[0] not in alias for s in f) or f[0][2] is None:
                result['status'] = 'insufficient-comparable-events'
                results.append(result)
                continue
            normalized = [[alias[sid], legacy_minute(a), legacy_minute(d)] for sid, a, d in f]
            for journey, start in candidates.get((normalized[0][0], normalized[0][2]), []):
                if rail not in journey['railwayPath'] or not kinds.issubset(set(rules[journey['calendar']]['dayKinds'])):
                    continue
                actual = journey['stops'][start:start + len(f)]
                if len(actual) != len(f):
                    continue
                if all(old[0] == new[0] and all(old[i] is None or old[i] == new[i] for i in [1, 2]) for old, new in zip(normalized, actual)):
                    result['journeyIds'].append(journey['id'])
            result['journeyIds'] = sorted(set(result['journeyIds']))
            result['status'] = ('unique-exact-content-match' if len(result['journeyIds']) == 1 else
                                'ambiguous-exact-content-match' if result['journeyIds'] else 'no-exact-content-match')
            results.append(result)
    return {'version': 1, 'matches': results,
            'policy': {'fullFragmentStationOrderRequired': True, 'allAvailableArrivalDepartureEventsRequired': True,
                       'automaticLegacyIdentityPromotion': False, 'dateConditionsMustStillBeEvaluated': True},
            'counts': dict(collections.Counter(r['status'] for r in results))}


def install(root=Path('.')):
    root = Path(root)
    if not (root / SOURCE_DIR / 'audit.json').exists():
        return None
    network, catalog, calendars = build_payloads(root)
    matches = match_legacy_fragments(root, network, catalog, calendars)
    out = root / DB_DIR
    for filename, value in [('network-journeys.json.gz', network), ('station-catalog.json', catalog),
                            ('calendars.json', calendars), ('existing-fragment-matches.json.gz', matches)]:
        write_json(out / filename, value)
    directory = root / 'data/transit-v2'
    index = read_json(directory / 'index.json')
    index.setdefault('networkJourneyFiles', {})[SOURCE] = 'western/network-journeys.json.gz'
    index.setdefault('sourceCatalogs', {})[SOURCE] = {
        'stations': 'western/station-catalog.json', 'calendars': 'western/calendars.json',
        'legacyCrosswalk': 'western/existing-fragment-matches.json.gz', 'audit': 'western/import-audit.json'}
    write_json(directory / 'index.json', index)
    imported = [j for j in load_network_journeys(directory, index) if j.get('sourceOperator') == SOURCE]
    if {j['id'] for j in imported} != {j['id'] for j in network['journeys']}:
        raise ValueError('Registered DB does not expose every imported train')
    coverage_path = directory / 'coverage.json'
    if coverage_path.exists():
        coverage = read_json(coverage_path)
        coverage['summary']['networkJourneys'] = len(load_network_journeys(directory, index))
        coverage['summary']['westernPublishedJourneys'] = len(imported)
        write_json(coverage_path, coverage)
    report = {
        'version': 1, 'complete': True, 'scope': 'database-import', 'sourceEdition': network['sourceEdition'],
        'sourceTrainIds': len(network['journeys']), 'importedTrainIds': len(imported),
        'through': sum(j['classification'] == 'through' for j in imported),
        'lineOnly': sum(j['classification'] == 'line-only' for j in imported),
        'stopEvents': sum(len(j['stops']) for j in imported), 'stations': len(catalog['stations']),
        'stationsWithExistingAliases': sum(bool(s['aliases']) for s in catalog['stations']),
        'calendarRules': len(calendars['calendars']),
        'dateRestrictedTrainIds': sum(j['dateRestricted'] for j in imported),
        'legacyFragmentComparison': matches['counts'],
        'legacyIdentityPromotions': 0, 'runtimeRoutingEnabledByThisImport': False,
        'legacyInputSha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted((root / 'data/transit-v2/fragments').glob('*.json'))},
        'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.name != 'import-audit.json'},
    }
    write_json(out / 'import-audit.json', report)
    return report


if __name__ == '__main__':
    print(json.dumps(install(), ensure_ascii=False, indent=2))
