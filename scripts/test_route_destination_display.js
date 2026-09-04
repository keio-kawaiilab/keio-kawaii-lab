"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const core = require("../route-core.js");

const line = "odpt.Railway:Test.Headsign";
const payload = {
  Station: [
    {"owl:sameAs":"station:a","odpt:stationTitle":{"ja":"A"},"odpt:railway":line,"odpt:operator":"odpt.Operator:Test","geo:lat":35.0,"geo:long":139.0},
    {"owl:sameAs":"station:b","odpt:stationTitle":{"ja":"B"},"odpt:railway":line,"odpt:operator":"odpt.Operator:Test","geo:lat":35.01,"geo:long":139.01},
    {"owl:sameAs":"station:c","odpt:stationTitle":{"ja":"C"},"odpt:railway":line,"odpt:operator":"odpt.Operator:Test","geo:lat":35.02,"geo:long":139.02}
  ],
  Railway: [{"owl:sameAs":line,"odpt:operator":"odpt.Operator:Test","odpt:railwayTitle":{"ja":"テスト線"},"odpt:stationOrder":[{"odpt:index":1,"odpt:station":"station:a"},{"odpt:index":2,"odpt:station":"station:b"},{"odpt:index":3,"odpt:station":"station:c"}]}]
};
const model = core.createModel([payload]);
const from = model.resolveInput("A").group;
const to = model.resolveInput("B").group;
const route = model.shortestPath(from, to);
const timetable = {
  timeBasis:"train-timetable",
  stations:["station:a","station:b"],
  calendars:["odpt.Calendar:Weekday"],
  trainTypes:["odpt.TrainType:Test.Local"],
  trips:[[0,0,"101",[[0,null,480],[1,490,null]],"station:c","train:101","timetable:101"]]
};
const timed = model.timedItinerary(route,{[line]:timetable},475,"weekday",5);
assert.ok(timed);
assert.equal(timed.segments[0].destination,"station:c");
assert.equal(timed.segments[0].trainNumber,"101");

const ui = fs.readFileSync(path.join(__dirname,"..","route.js"),"utf8");
assert.match(ui,/function destinationLabel\(segment\)/);
assert.match(ui,/labels\.join\("・"\)\+"行"/);
assert.match(ui,/if\(destination\)parts\.push\(destination\)/);
console.log("route destination display test passed");
