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

console.log(`transit snapshot tests passed (${model.stations.length} station choices)`);
