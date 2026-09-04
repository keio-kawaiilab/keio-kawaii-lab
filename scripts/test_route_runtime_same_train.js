// Permanent regression guard: only evidence-backed same-physical-train edges may suppress a transfer.
const assert = require('assert');
const fs = require('fs');

const runtime = JSON.parse(fs.readFileSync('data/transit-v2/runtime-same-train.json', 'utf8'));
const policy = runtime.policy || {};
const edges = Array.isArray(runtime.edges) ? runtime.edges : [];

assert.equal(policy.runtimeInference, false, 'runtime must not infer same-train identity');
assert.equal(policy.unknownMayBePromotedToSameTrain, false, 'unknown identity must remain unresolved');
assert.equal(policy.trainNumberAloneMayResolve, false, 'train number alone must never establish same-train identity');
assert.equal(policy.timeGapAloneMayResolve, false, 'time gap alone must never establish same-train identity');
assert.ok(edges.length > 100, `runtime same-train DB unexpectedly small: ${edges.length}`);
assert.ok(edges.every((row) => Array.isArray(row) && row.length === 4 && row.every(Boolean)), 'runtime edges must be complete four-field rows');

const expectedSotetsu = [
  'tt:odpt.TrainTimetable:Sotetsu.Izumino.6752.Weekday',
  'tt:odpt.TrainTimetable:Sotetsu.Main.6752.Weekday',
  'odpt.Railway:Sotetsu.Izumino',
  'odpt.Railway:Sotetsu.Main',
];
assert.ok(
  edges.some((row) => expectedSotetsu.every((value, index) => row[index] === value)),
  'authoritative Sotetsu 6752 Izumino -> Main continuation is missing from runtime DB'
);

const routeJs = fs.readFileSync('route.js', 'utf8');
assert.ok(routeJs.includes('data/transit-v2/runtime-same-train.json'), 'route UI must load the strict runtime same-train DB');
assert.ok(routeJs.includes('resolveSameTrain'), 'route UI must pass a same-train resolver into route search');
assert.ok(routeJs.includes('model.timedItinerary(path,timetables,earliest,service,5,resolveTransferRule,resolveSameTrain)'), 'timed route search must receive the strict same-train resolver');

console.log(`route runtime same-train test passed: ${edges.length} strict edges`);
