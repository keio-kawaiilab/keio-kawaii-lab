import fs from 'node:fs';

const TOEI = 'odpt.Railway:Toei.Asakusa';
const KEIKYU = 'odpt.Railway:Keikyu.Main';
const TOEI_SENGAKUJI = 'odpt.Station:Toei.Asakusa.Sengakuji';
const KEIKYU_SENGAKUJI = 'odpt.Station:Keikyu.Main.Sengakuji';
const MAX_DIAGNOSTIC_GAP = 2;

function rowsOf(value) {
  if (Array.isArray(value)) return value;
  for (const key of ['fragments', 'items', 'rows', 'data']) {
    if (Array.isArray(value?.[key])) return value[key];
  }
  return [];
}

function loadRows(path) {
  return rowsOf(JSON.parse(fs.readFileSync(path, 'utf8')));
}

function stopStation(stop) {
  return Array.isArray(stop) ? String(stop[0] || '') : '';
}

function stopArrival(stop) {
  if (!Array.isArray(stop)) return null;
  const value = stop[1] ?? stop[2];
  return Number.isFinite(Number(value)) ? Number(value) : null;
}

function stopDeparture(stop) {
  if (!Array.isArray(stop)) return null;
  const value = stop[2] ?? stop[1];
  return Number.isFinite(Number(value)) ? Number(value) : null;
}

function startsAt(row, station) {
  const stops = row?.stops || [];
  return stops.length > 0 && stopStation(stops[0]) === station;
}

function endsAt(row, station) {
  const stops = row?.stops || [];
  return stops.length > 0 && stopStation(stops[stops.length - 1]) === station;
}

function boundaryMinute(row, side) {
  const stops = row?.stops || [];
  if (!stops.length) return null;
  return side === 'start' ? stopDeparture(stops[0]) : stopArrival(stops[stops.length - 1]);
}

function calendar(row) {
  return String(row?.calendar || '');
}

function references(row, key) {
  return (row?.[key] || []).map((value) => String(value || '')).filter(Boolean);
}

function stationRailway(station) {
  const match = String(station || '').match(/^odpt\.Station:([^.]+)\.([^.]+)\./);
  return match ? `odpt.Railway:${match[1]}.${match[2]}` : '';
}

function foreignReferences(row, key) {
  const own = String(row?.railway || '');
  return references(row, key).filter((station) => {
    if (/\.Sengakuji$/.test(station)) return false;
    const railway = stationRailway(station);
    return railway && railway !== own;
  });
}

function intersection(left, right) {
  const rightSet = new Set(right);
  return [...new Set(left.filter((value) => rightSet.has(value)))];
}

function crossBoundaryHint(source, target) {
  const sourceDestinations = references(source, 'destination').filter((station) => !/\.Sengakuji$/.test(station));
  const targetDestinations = references(target, 'destination').filter((station) => !/\.Sengakuji$/.test(station));
  const sourceOrigins = references(source, 'origin').filter((station) => !/\.Sengakuji$/.test(station));
  const targetOrigins = references(target, 'origin').filter((station) => !/\.Sengakuji$/.test(station));
  const sharedDestination = intersection(sourceDestinations, targetDestinations);
  const sharedOrigin = intersection(sourceOrigins, targetOrigins);
  const sourceForeignDestination = foreignReferences(source, 'destination');
  const targetForeignOrigin = foreignReferences(target, 'origin');
  return {
    sharedPublishedDestination: sharedDestination,
    sharedPublishedOrigin: sharedOrigin,
    sourceDestinationBeyondOwnRailway: sourceForeignDestination,
    targetOriginBeyondOwnRailway: targetForeignOrigin,
    sourceAdvertisesBeyondBoundary: sourceForeignDestination.length > 0,
    sharedDestinationProvesContinuation: sourceForeignDestination.some((value) => sharedDestination.includes(value)),
  };
}

function candidateRows(sources, targets, direction) {
  const candidates = [];
  for (const source of sources) {
    const sourceMinute = boundaryMinute(source, 'end');
    if (sourceMinute == null) continue;
    for (const target of targets) {
      if (calendar(source) !== calendar(target)) continue;
      const targetMinute = boundaryMinute(target, 'start');
      if (targetMinute == null) continue;
      const gap = targetMinute - sourceMinute;
      if (gap < 0 || gap > MAX_DIAGNOSTIC_GAP) continue;
      const hint = crossBoundaryHint(source, target);
      candidates.push({
        direction,
        calendar: calendar(source),
        sourceMinute,
        targetMinute,
        gap,
        sourceId: String(source.id || ''),
        targetId: String(target.id || ''),
        sourceKind: String(source.sourceKind || ''),
        targetKind: String(target.sourceKind || ''),
        sourceOperator: String(source.sourceOperator || source.operator || ''),
        targetOperator: String(target.sourceOperator || target.operator || ''),
        sourceConfidence: Number(source.confidence || 0),
        targetConfidence: Number(target.confidence || 0),
        sourceTrainNumber: String(source.trainNumber || ''),
        targetTrainNumber: String(target.trainNumber || ''),
        sourceOrigin: references(source, 'origin'),
        sourceDestination: references(source, 'destination'),
        targetOrigin: references(target, 'origin'),
        targetDestination: references(target, 'destination'),
        hint,
      });
    }
  }
  return candidates;
}

function countsBy(rows, keyFn) {
  const values = {};
  for (const row of rows) {
    const key = String(keyFn(row));
    values[key] = (values[key] || 0) + 1;
  }
  return Object.fromEntries(Object.entries(values).sort(([a], [b]) => a.localeCompare(b)));
}

function summarizeCandidates(candidates) {
  const sourceCounts = new Map();
  const targetCounts = new Map();
  for (const row of candidates) {
    sourceCounts.set(row.sourceId, (sourceCounts.get(row.sourceId) || 0) + 1);
    targetCounts.set(row.targetId, (targetCounts.get(row.targetId) || 0) + 1);
  }
  const unique = candidates.filter((row) => sourceCounts.get(row.sourceId) === 1 && targetCounts.get(row.targetId) === 1);
  const destinationProven = unique.filter((row) => row.hint.sharedDestinationProvesContinuation);
  const sharedDestinationButNotBeyond = unique.filter((row) => row.hint.sharedPublishedDestination.length > 0 && !row.hint.sharedDestinationProvesContinuation);
  const noSharedDestination = unique.filter((row) => row.hint.sharedPublishedDestination.length === 0);
  return {
    candidatePairs: candidates.length,
    uniqueOneToOneByBoundaryWindow: unique.length,
    destinationProvenUnique: destinationProven.length,
    destinationProvenByGap: countsBy(destinationProven, (row) => row.gap),
    destinationProvenByCalendar: countsBy(destinationProven, (row) => row.calendar),
    sharedDestinationButNotBeyond: sharedDestinationButNotBeyond.length,
    noSharedDestinationUnique: noSharedDestination.length,
    ambiguousPairs: candidates.length - unique.length,
    examplesDestinationProven: destinationProven.slice(0, 20),
    examplesNoSharedDestination: noSharedDestination.slice(0, 10),
  };
}

function boundarySummary(rows, railway, station) {
  const selected = rows.filter((row) => String(row.railway || '') === railway);
  const starts = selected.filter((row) => startsAt(row, station));
  const ends = selected.filter((row) => endsAt(row, station));
  const calendars = {};
  for (const row of [...starts, ...ends]) {
    const key = calendar(row) || '(unknown)';
    calendars[key] ||= { starts: 0, ends: 0 };
  }
  for (const row of starts) calendars[calendar(row) || '(unknown)'].starts += 1;
  for (const row of ends) calendars[calendar(row) || '(unknown)'].ends += 1;
  return {
    railway,
    totalFragments: selected.length,
    startsAtSengakuji: starts.length,
    endsAtSengakuji: ends.length,
    calendars,
    startsWithForeignOrigin: starts.filter((row) => foreignReferences(row, 'origin').length > 0).length,
    endsWithForeignDestination: ends.filter((row) => foreignReferences(row, 'destination').length > 0).length,
  };
}

const toei = loadRows('data/transit-v2/fragments/toei.json');
const keikyu = loadRows('data/transit-v2/fragments/keikyu.json');

const toeiStarts = toei.filter((row) => String(row.railway || '') === TOEI && startsAt(row, TOEI_SENGAKUJI));
const toeiEnds = toei.filter((row) => String(row.railway || '') === TOEI && endsAt(row, TOEI_SENGAKUJI));
const keikyuStarts = keikyu.filter((row) => String(row.railway || '') === KEIKYU && startsAt(row, KEIKYU_SENGAKUJI));
const keikyuEnds = keikyu.filter((row) => String(row.railway || '') === KEIKYU && endsAt(row, KEIKYU_SENGAKUJI));

const toeiToKeikyu = candidateRows(toeiEnds, keikyuStarts, 'toei-to-keikyu');
const keikyuToToei = candidateRows(keikyuEnds, toeiStarts, 'keikyu-to-toei');

const report = {
  policy: {
    purpose: 'diagnostic-only: quantify exact Sengakuji boundary candidates without promoting same-train identity',
    maxBoundaryGapMinutes: MAX_DIAGNOSTIC_GAP,
    timeProximityAloneMayEstablishIdentity: false,
    publishedEndpointHintAloneMayEstablishIdentity: false,
    proposedSafeSignal: 'source advertises a destination beyond its own railway; target advertises the exact same destination; boundary pairing is unique within the diagnostic window',
    productionMutation: false,
  },
  fragments: {
    toei: boundarySummary(toei, TOEI, TOEI_SENGAKUJI),
    keikyu: boundarySummary(keikyu, KEIKYU, KEIKYU_SENGAKUJI),
  },
  candidates: {
    toeiToKeikyu: summarizeCandidates(toeiToKeikyu),
    keikyuToToei: summarizeCandidates(keikyuToToei),
  },
};

console.log(JSON.stringify(report, null, 2));