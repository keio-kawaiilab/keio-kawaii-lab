// Generates transfer candidates from the current transit dataset.
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const TRANSIT = path.join(ROOT, 'data', 'transit');

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function asArray(value) {
  return Array.isArray(value) ? value : value ? [value] : [];
}

function title(value) {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object') return value.ja || value.en || Object.values(value)[0] || '';
  return '';
}

function normalize(value) {
  let text = String(value || '').normalize('NFKC').replace(/[\s　]/g, '');
  if (text.endsWith('駅')) text = text.slice(0, -1);
  return text.toLowerCase();
}

function stationName(item) {
  return title(item?.['odpt:stationTitle']) || item?.['dc:title'] || String(item?.['owl:sameAs'] || '').split('.').pop() || '駅';
}

function railwayName(item) {
  return title(item?.['odpt:railwayTitle']) || item?.['dc:title'] || String(item?.['owl:sameAs'] || '').split('.').pop() || '路線';
}

function distanceMeters(a, b) {
  const lat1 = Number(a?.['geo:lat']);
  const lon1 = Number(a?.['geo:long']);
  const lat2 = Number(b?.['geo:lat']);
  const lon2 = Number(b?.['geo:long']);
  if (![lat1, lon1, lat2, lon2].every(Number.isFinite)) return null;
  const r = 6371000;
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

function operatorIds(item) {
  return asArray(item?.['odpt:operator']);
}

function sameOperator(a, b) {
  const right = new Set(operatorIds(b));
  return operatorIds(a).some(id => right.has(id));
}

const manifest = readJson(path.join(TRANSIT, 'manifest.json'));
const operatorEntries = Object.entries(manifest.operators || {}).filter(([, info]) => info?.status === 'ok');

const supportedRailways = new Set();
const stationById = new Map();
const railwayById = new Map();
const railwaysByStation = new Map();
const operatorLabelById = new Map();

for (const [, info] of operatorEntries) {
  if (info?.operator) operatorLabelById.set(info.operator, info.label || info.operator);
}

for (const [slug] of operatorEntries) {
  const base = path.join(TRANSIT, slug);
  const indexFile = path.join(base, 'timetable-index.json');
  const entitiesFile = path.join(base, 'entities.json');
  if (!fs.existsSync(indexFile) || !fs.existsSync(entitiesFile)) continue;

  const index = readJson(indexFile);
  for (const [railwayId, row] of Object.entries(index.lines || {})) {
    if (row?.file) supportedRailways.add(railwayId);
  }

  const entities = readJson(entitiesFile);
  for (const station of entities.Station || []) {
    const id = station?.['owl:sameAs'];
    if (!id) continue;
    stationById.set(id, station);
    const lines = asArray(station?.['odpt:railway']);
    if (!railwaysByStation.has(id)) railwaysByStation.set(id, new Set());
    for (const railwayId of lines) railwaysByStation.get(id).add(railwayId);
  }
  for (const railway of entities.Railway || []) {
    const id = railway?.['owl:sameAs'];
    if (!id) continue;
    railwayById.set(id, railway);
    for (const row of asArray(railway?.['odpt:stationOrder'])) {
      const stationId = row?.['odpt:station'];
      if (!stationId) continue;
      if (!railwaysByStation.has(stationId)) railwaysByStation.set(stationId, new Set());
      railwaysByStation.get(stationId).add(id);
    }
  }
}

function samePlace(aId, bId) {
  const a = stationById.get(aId);
  const b = stationById.get(bId);
  const meters = distanceMeters(a, b);
  if (meters !== null) return meters <= 850;
  return asArray(a?.['odpt:connectingStation']).includes(bId) || asArray(b?.['odpt:connectingStation']).includes(aId);
}

function supportedLinesForStation(stationId) {
  return [...(railwaysByStation.get(stationId) || [])].filter(id => supportedRailways.has(id));
}

const pairMap = new Map();
function addCandidate(placeKey, placeLabel, stationIdsA, stationIdsB, railwayA, railwayB, source) {
  if (!railwayA || !railwayB || railwayA === railwayB) return;
  if (!supportedRailways.has(railwayA) || !supportedRailways.has(railwayB)) return;

  const [line1, line2] = railwayA < railwayB ? [railwayA, railwayB] : [railwayB, railwayA];
  const key = `${placeKey}\u0001${line1}\u0001${line2}`;
  const line1Obj = railwayById.get(line1);
  const line2Obj = railwayById.get(line2);
  const aStations = railwayA === line1 ? stationIdsA : stationIdsB;
  const bStations = railwayB === line2 ? stationIdsB : stationIdsA;

  let fallbackMinutes = 5;
  let distance = null;
  for (const aId of aStations) {
    for (const bId of bStations) {
      const d = distanceMeters(stationById.get(aId), stationById.get(bId));
      if (d !== null && (distance === null || d < distance)) distance = d;
    }
  }
  if (distance !== null) fallbackMinutes = Math.max(5, Math.min(15, Math.ceil(distance / 75) + 2));

  const existing = pairMap.get(key);
  const candidate = {
    placeKey,
    placeLabel,
    railwayA: line1,
    railwayAName: railwayName(line1Obj),
    railwayB: line2,
    railwayBName: railwayName(line2Obj),
    sameOperator: sameOperator(line1Obj, line2Obj),
    stationIdsA: [...new Set(aStations)].sort(),
    stationIdsB: [...new Set(bStations)].sort(),
    fallbackMinutes,
    distanceMeters: distance === null ? null : Math.round(distance),
    sources: [source]
  };

  if (!existing) {
    pairMap.set(key, candidate);
    return;
  }
  existing.stationIdsA = [...new Set([...existing.stationIdsA, ...candidate.stationIdsA])].sort();
  existing.stationIdsB = [...new Set([...existing.stationIdsB, ...candidate.stationIdsB])].sort();
  existing.sources = [...new Set([...existing.sources, source])].sort();
  if (candidate.distanceMeters !== null && (existing.distanceMeters === null || candidate.distanceMeters < existing.distanceMeters)) {
    existing.distanceMeters = candidate.distanceMeters;
    existing.fallbackMinutes = candidate.fallbackMinutes;
  }
}

// 1) Replicate route-planner same-name / <=850m station grouping.
const buckets = new Map();
for (const [stationId, station] of stationById) {
  const key = normalize(stationName(station));
  if (!key) continue;
  if (!buckets.has(key)) buckets.set(key, { name: stationName(station), nodes: [] });
  buckets.get(key).nodes.push(stationId);
}

const groupInfoByStation = new Map();
for (const [nameKey, bucket] of buckets) {
  const clusters = [];
  for (const node of bucket.nodes) {
    const matches = clusters.filter(candidate => candidate.some(other => samePlace(node, other)));
    if (!matches.length) {
      clusters.push([node]);
      continue;
    }
    const primary = matches[0];
    primary.push(node);
    for (const extra of matches.slice(1)) {
      for (const other of extra) if (!primary.includes(other)) primary.push(other);
      clusters.splice(clusters.indexOf(extra), 1);
    }
  }

  clusters.forEach((nodes, index) => {
    const placeKey = `group:${nameKey}:${index}`;
    for (const node of nodes) groupInfoByStation.set(node, { placeKey, placeLabel: bucket.name });
    const lines = [...new Set(nodes.flatMap(supportedLinesForStation))].sort();
    for (let i = 0; i < lines.length; i++) {
      for (let j = i + 1; j < lines.length; j++) {
        const aNodes = nodes.filter(id => supportedLinesForStation(id).includes(lines[i]));
        const bNodes = nodes.filter(id => supportedLinesForStation(id).includes(lines[j]));
        addCandidate(placeKey, bucket.name, aNodes, bNodes, lines[i], lines[j], 'same-place-group');
      }
    }
  });
}

// 2) Add explicit ODPT connectingStation edges, including differently named stations.
for (const [fromId, fromStation] of stationById) {
  for (const toId of asArray(fromStation?.['odpt:connectingStation'])) {
    if (!stationById.has(toId)) continue;
    const fromLines = supportedLinesForStation(fromId);
    const toLines = supportedLinesForStation(toId);
    if (!fromLines.length || !toLines.length) continue;

    const fromGroup = groupInfoByStation.get(fromId);
    const toGroup = groupInfoByStation.get(toId);
    const sameGroup = fromGroup && toGroup && fromGroup.placeKey === toGroup.placeKey;
    const fromName = stationName(fromStation);
    const toName = stationName(stationById.get(toId));
    const canonicalStations = [fromId, toId].sort();
    const placeKey = sameGroup ? fromGroup.placeKey : `explicit:${canonicalStations.join('|')}`;
    const placeLabel = sameGroup ? fromGroup.placeLabel : (fromName === toName ? fromName : `${fromName} ↔ ${toName}`);

    for (const a of fromLines) {
      for (const b of toLines) addCandidate(placeKey, placeLabel, [fromId], [toId], a, b, 'connecting-station');
    }
  }
}

const candidates = [...pairMap.values()].sort((a, b) =>
  a.placeLabel.localeCompare(b.placeLabel, 'ja') ||
  a.railwayAName.localeCompare(b.railwayAName, 'ja') ||
  a.railwayBName.localeCompare(b.railwayBName, 'ja')
);

const placeKeys = new Set(candidates.map(row => row.placeKey));
const sameOperatorCount = candidates.filter(row => row.sameOperator).length;
const crossOperatorCount = candidates.length - sameOperatorCount;
const operatorPairCounts = new Map();
for (const row of candidates) {
  const aOps = operatorIds(railwayById.get(row.railwayA));
  const bOps = operatorIds(railwayById.get(row.railwayB));
  const a = aOps.map(id => operatorLabelById.get(id) || id).sort().join('/');
  const b = bOps.map(id => operatorLabelById.get(id) || id).sort().join('/');
  const pair = [a, b].sort().join(' × ');
  operatorPairCounts.set(pair, (operatorPairCounts.get(pair) || 0) + 1);
}

const output = {
  generatedAt: new Date().toISOString(),
  sourceManifestFetchedAt: manifest.fetchedAt || null,
  methodology: 'Replicates route-planner same-name/850m grouping and explicit odpt:connectingStation edges; only timetable-supported railways are retained. Duplicate sources for the same place/railway pair are merged.',
  summary: {
    supportedRailways: supportedRailways.size,
    transferPlaces: placeKeys.size,
    transferRailwayPairs: candidates.length,
    sameOperatorPairs: sameOperatorCount,
    crossOperatorPairs: crossOperatorCount
  },
  operatorPairCounts: Object.fromEntries([...operatorPairCounts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'ja'))),
  candidates
};

fs.writeFileSync(path.join(TRANSIT, 'transfer-candidates.json'), JSON.stringify(output, null, 2) + '\n');
console.log(JSON.stringify(output.summary));
