"use strict";

const assert = require("node:assert/strict");
const core = require("../route-core.js");

function station(id, name, railway, lat, lon, operator = "odpt.Operator:Test") {
  return {
    "owl:sameAs": id,
    "odpt:stationTitle": { ja: name },
    "odpt:railway": railway,
    "odpt:operator": operator,
    "geo:lat": lat,
    "geo:long": lon,
  };
}

function railway(id, name, color, stations) {
  return {
    "owl:sameAs": id,
    "odpt:railwayTitle": { ja: name },
    "odpt:color": color,
    "odpt:stationOrder": stations.map((stationId, index) => ({
      "odpt:index": index + 1,
      "odpt:station": stationId,
    })),
  };
}

const lineA = "odpt.Railway:Test.A";
const lineB = "odpt.Railway:Test.B";
const farLine = "odpt.Railway:Test.Far";
const payload = {
  Station: [
    station("station:a1", "出発", lineA, 35.000, 139.000),
    station("station:a2", "乗換", lineA, 35.010, 139.010),
    station("station:b1", "乗換", lineB, 35.0102, 139.0102),
    station("station:b2", "到着", lineB, 35.020, 139.020),
    station("station:far1", "乗換", farLine, 36.000, 140.000, "odpt.Operator:Far"),
    station("station:far2", "遠方", farLine, 36.010, 140.010, "odpt.Operator:Far"),
  ],
  Railway: [
    railway(lineA, "A線", "#ff0000", ["station:a1", "station:a2"]),
    railway(lineB, "B線", "#0000ff", ["station:b1", "station:b2"]),
    railway(farLine, "遠方線", "#00aa00", ["station:far1", "station:far2"]),
  ],
};

const model = core.createModel([payload]);
assert.equal(model.stations.length, 5, "far-away same-name stations must be separate choices");
assert.equal(model.resolveInput("乗換").ambiguous, true, "a bare duplicate station name must be rejected");

const nearTransfer = model.stations.find((item) => item.label.includes("乗換") && item.railways.includes("A線"));
const farTransfer = model.stations.find((item) => item.label.includes("乗換") && item.railways.includes("遠方線"));
assert.ok(nearTransfer.label.includes("A線"));
assert.ok(farTransfer.label.includes("遠方線"));

const origin = model.resolveInput("出発").group;
const destination = model.resolveInput("到着").group;
const path = model.shortestPath(origin, destination);
assert.ok(path, "a route through a nearby transfer must be found");
const segments = model.segmentsFrom(path);
assert.deepEqual(segments.map((item) => item.label), ["A線", "B線"]);
assert.deepEqual(segments.map((item) => item.stops), [1, 1]);

const impossible = model.shortestPath(origin, model.resolveInput("遠方").group);
assert.equal(impossible, null, "same-name stations that are far apart must not become a transfer shortcut");

const bridgeModel = core.createModel([{
  Station: [
    station("station:bridge-a", "接続駅", "line:a"),
    station("station:bridge-b", "接続駅", "line:b"),
    {
      ...station("station:bridge", "接続駅", "line:bridge"),
      "odpt:connectingStation": ["station:bridge-a", "station:bridge-b"],
    },
  ],
  Railway: [],
}]);
assert.equal(bridgeModel.resolveInput("接続駅").ambiguous, false, "a connector node must merge every matching station cluster");
assert.equal(bridgeModel.resolveInput("接続駅").group.nodes.length, 3);

console.log("route-core tests passed");
