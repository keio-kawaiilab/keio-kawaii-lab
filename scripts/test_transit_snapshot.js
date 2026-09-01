"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const core = require("../route-core.js");

const root = path.join(__dirname, "..", "data", "transit");
const manifest = JSON.parse(fs.readFileSync(path.join(root, "manifest.json"), "utf8"));
const required = ["jr-east", "keio", "keisei", "tokyo-metro", "yokohama-minatomirai"];

required.forEach((slug) => {
  assert.equal(manifest.operators[slug]?.status, "ok", `${slug} topology must be available`);
  assert.ok(manifest.operators[slug]?.topologyEdges > 0, `${slug} must contain connected station order`);
});

["jr-east", "keio"].forEach((slug) => {
  assert.equal(manifest.operators[slug]?.timetableStatus, "ok", `${slug} timetable must be available`);
  assert.ok(manifest.operators[slug]?.timetableConnections > 0, `${slug} must contain scheduled connections`);
});

["seibu", "odakyu", "tokyu", "keikyu", "yurikamome"].forEach((slug) => {
  assert.equal(manifest.operators[slug]?.timetableStatus, "departure-only", `${slug} station timetable must be available`);
  assert.ok(manifest.operators[slug]?.stationTimetables > 0, `${slug} must contain station timetable objects`);
  assert.ok(manifest.operators[slug]?.departures > 0, `${slug} must contain scheduled departures`);
});

const payloads = Object.entries(manifest.operators)
  .filter(([, info]) => info?.status === "ok")
  .map(([slug]) => JSON.parse(fs.readFileSync(path.join(root, slug, "entities.json"), "utf8")));
const model = core.createModel(payloads);

function assertRoute(from, to, expectedLine) {
  const origin = model.resolveInput(from);
  const destination = model.resolveInput(to);
  assert.ok(origin.group && !origin.ambiguous, `${from} must resolve to one station group`);
  assert.ok(destination.group && !destination.ambiguous, `${to} must resolve to one station group`);
  const route = model.shortestPath(origin.group, destination.group);
  assert.ok(route, `${from} to ${to} must have a route`);
  const labels = model.segmentsFrom(route).map((segment) => segment.label);
  if (expectedLine) {
    assert.ok(labels.includes(expectedLine), `${from} to ${to} must use ${expectedLine}`);
  }
}

assertRoute("京成上野", "成田空港", "京成本線");
assertRoute("新宿", "京王八王子", "京王線");
assertRoute("渋谷", "吉祥寺");
assertRoute("神泉", "駒場東大前", "井の頭線");
assertRoute("横浜", "元町・中華街", "みなとみらい線");

const airportRoute = model.shortestPath(
  model.resolveInput("品川").group,
  model.resolveInput("羽田空港第1・第2ターミナル").group,
);
const airportLines = model.segmentsFrom(airportRoute).map((segment) => segment.label);
assert.ok(airportLines.includes("京急本線") && airportLines.includes("空港線"), "品川 to 羽田空港 must use Keikyu directly");
assert.ok(!airportLines.includes("東海道線"), "品川 to 羽田空港 must not detour through Kawasaki on JR");

function assertEstimatedRoute(slug, railwayId, from, to, minimum, maximum) {
  const origin = model.resolveInput(from);
  const destination = model.resolveInput(to);
  const route = model.shortestPath(origin.group, destination.group, { allowedRailways: [railwayId] });
  assert.ok(route, `${from} to ${to} must have a ${railwayId} route`);
  const timetableIndex = JSON.parse(fs.readFileSync(path.join(root, slug, "timetable-index.json"), "utf8"));
  const entry = timetableIndex.lines[railwayId];
  assert.ok(entry?.file, `${railwayId} must have a timetable file`);
  const timetable = JSON.parse(fs.readFileSync(path.join(root, slug, entry.file), "utf8"));
  const timed = model.timedItinerary(route, { [railwayId]: timetable }, 480, "weekday", 5);
  assert.ok(timed?.estimatedArrival, `${from} to ${to} must have an estimated arrival`);
  assert.ok(
    timed.duration >= minimum && timed.duration <= maximum,
    `${from} to ${to} duration ${timed.duration} must be between ${minimum} and ${maximum} minutes`,
  );
}

assertEstimatedRoute("seibu", "odpt.Railway:Seibu.Ikebukuro", "池袋", "所沢", 18, 40);
assertEstimatedRoute("odakyu", "odpt.Railway:Odakyu.Odawara", "新宿", "町田", 25, 50);
assertEstimatedRoute("tokyu", "odpt.Railway:Tokyu.Toyoko", "渋谷", "横浜", 25, 45);
assertEstimatedRoute("keikyu", "odpt.Railway:Keikyu.Main", "品川", "横浜", 15, 35);
assertEstimatedRoute("yurikamome", "odpt.Railway:Yurikamome.Yurikamome", "新橋", "豊洲", 25, 40);
assertEstimatedRoute("seibu", "odpt.Railway:Seibu.Toshima", "練馬", "豊島園", 2, 5);
assertEstimatedRoute("seibu", "odpt.Railway:Seibu.Seibuen", "東村山", "西武園", 2, 6);

console.log(`transit snapshot tests passed (${model.stations.length} station choices)`);
