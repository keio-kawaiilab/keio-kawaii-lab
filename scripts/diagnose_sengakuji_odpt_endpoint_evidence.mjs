#!/usr/bin/env node
import fs from 'node:fs';

const identityFile = 'data/transit/odpt-train-identities.json';
const KEIKYU = 'odpt.Railway:Keikyu.Main';
const TOEI = 'odpt.Railway:Toei.Asakusa';
const KEIKYU_SENGAKUJI = 'odpt.Station:Keikyu.Main.Sengakuji';
const TOEI_SENGAKUJI = 'odpt.Station:Toei.Asakusa.Sengakuji';
const KEIKYU_PREFIX = 'odpt.Station:Keikyu.Main.';
const TOEI_PREFIX = 'odpt.Station:Toei.Asakusa.';

const read = (f) => JSON.parse(fs.readFileSync(f, 'utf8'));
const arr = (v) => Array.isArray(v) ? v.map(String) : [];
const station = (x) => String(x?.station || '');
const side = (value, prefix) => arr(value).filter((x) => x.startsWith(prefix));
const sample = (r, direction, externalStations, endpointRole) => ({
  timetableId: r.timetableId || '',
  trainId: r.trainId || '',
  railway: r.railway || '',
  direction,
  endpointRole,
  firstStop: station(r.firstStop),
  lastStop: station(r.lastStop),
  origin: arr(r.origin),
  destination: arr(r.destination),
  externalStations,
  calendars: arr(r.calendars),
  trainNumber: r.trainNumber || '',
  trainType: r.trainType || ''
});

const identities = read(identityFile);
if (identities?.policy?.runtimeInference !== false ||
    identities?.policy?.timeGapMayEstablishTrainIdentity !== false ||
    identities?.policy?.trainNumberMayEstablishTrainIdentity !== false) {
  throw new Error('Identity sidecar must remain fail-closed');
}

const rows = Array.isArray(identities?.records) ? identities.records : [];
const counts = {
  total: rows.length,
  keikyuRows: 0,
  toeiRows: 0,
  keikyuToToei: 0,
  toeiToKeikyu: 0,
  keikyuToToeiExactSengakujiEndpoint: 0,
  toeiToKeikyuExactSengakujiEndpoint: 0,
  byCalendar: {},
  byDirection: {}
};
const samples = [];

function bump(map, values, label) {
  const xs = values.length ? values : ['(none)'];
  for (const x of xs) map[`${label}:${x}`] = (map[`${label}:${x}`] || 0) + 1;
}
function recordEvidence(r, direction, externalStations, endpointRole, exact) {
  if (direction === 'keikyu-to-toei') {
    counts.keikyuToToei++;
    if (exact) counts.keikyuToToeiExactSengakujiEndpoint++;
  } else {
    counts.toeiToKeikyu++;
    if (exact) counts.toeiToKeikyuExactSengakujiEndpoint++;
  }
  bump(counts.byCalendar, arr(r.calendars), direction);
  bump(counts.byDirection, [String(r.railDirection || r.direction || '(none)')], direction);
  if (samples.length < 20) samples.push(sample(r, direction, externalStations, endpointRole));
}

for (const r of rows) {
  const railway = String(r?.railway || '');
  const first = station(r.firstStop);
  const last = station(r.lastStop);
  if (railway === KEIKYU) {
    counts.keikyuRows++;
    const originToei = side(r.origin, TOEI_PREFIX);
    const destinationToei = side(r.destination, TOEI_PREFIX);
    if (first === KEIKYU_SENGAKUJI && originToei.length) {
      recordEvidence(r, 'toei-to-keikyu', originToei, 'firstStop', true);
    }
    if (last === KEIKYU_SENGAKUJI && destinationToei.length) {
      recordEvidence(r, 'keikyu-to-toei', destinationToei, 'lastStop', true);
    }
  } else if (railway === TOEI) {
    counts.toeiRows++;
    const originKeikyu = side(r.origin, KEIKYU_PREFIX);
    const destinationKeikyu = side(r.destination, KEIKYU_PREFIX);
    if (first === TOEI_SENGAKUJI && originKeikyu.length) {
      recordEvidence(r, 'keikyu-to-toei', originKeikyu, 'firstStop', true);
    }
    if (last === TOEI_SENGAKUJI && destinationKeikyu.length) {
      recordEvidence(r, 'toei-to-keikyu', destinationKeikyu, 'lastStop', true);
    }
  }
}

const result = {
  sourceFile: identityFile,
  policy: identities.policy || null,
  counts,
  safeExactEvidenceCount:
    counts.keikyuToToeiExactSengakujiEndpoint + counts.toeiToKeikyuExactSengakujiEndpoint,
  samples
};
console.log(JSON.stringify(result, null, 2));

if (!counts.keikyuRows || !counts.toeiRows) {
  throw new Error(`Expected both Keikyu.Main and Toei.Asakusa identity rows; got ${JSON.stringify({keikyuRows: counts.keikyuRows, toeiRows: counts.toeiRows})}`);
}
