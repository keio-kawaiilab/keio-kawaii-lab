import fs from 'node:fs';

const paths = [
  'data/transit-v2/fragments/toei.json',
  'data/transit-v2/fragments/keikyu.json',
];

function rowsOf(value) {
  if (Array.isArray(value)) return value;
  for (const key of ['fragments', 'items', 'rows', 'data']) {
    if (Array.isArray(value?.[key])) return value[key];
  }
  return [];
}

function compact(value, depth = 0) {
  if (depth > 3) return '[…]';
  if (Array.isArray(value)) return value.slice(0, 4).map((v) => compact(v, depth + 1));
  if (!value || typeof value !== 'object') return value;
  const out = {};
  for (const [k, v] of Object.entries(value)) {
    if (/stop|station|railway|train|id|calendar|direction|origin|destination|time/i.test(k)) {
      out[k] = compact(v, depth + 1);
    }
  }
  return out;
}

for (const path of paths) {
  const raw = JSON.parse(fs.readFileSync(path, 'utf8'));
  const rows = rowsOf(raw);
  console.log(`FILE ${path}`);
  console.log(`count=${rows.length}`);
  console.log('firstKeys=', rows[0] ? Object.keys(rows[0]) : []);
  console.log('first=', JSON.stringify(compact(rows[0]), null, 2));

  const matches = rows.filter((row) => {
    const s = JSON.stringify(row);
    return /Sengakuji/i.test(s) && /(Toei\.Asakusa|Keikyu\.Main)/i.test(s);
  });
  console.log(`sengakujiMatches=${matches.length}`);
  for (const row of matches.slice(0, 8)) {
    console.log(JSON.stringify(compact(row), null, 2));
  }
}
