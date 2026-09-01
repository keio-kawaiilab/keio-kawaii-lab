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

const weekdayTimetables = {
  [lineA]: {
    stations: ["station:a1", "station:a2"],
    calendars: ["odpt.Calendar:Weekday", "odpt.Calendar:SaturdayHoliday"],
    trainTypes: ["odpt.TrainType:Test.Local"],
    trips: [
      [0, 0, "101", [[0, null, 480], [1, 490, null]]],
      [0, 0, "103", [[0, null, 500], [1, 510, null]]],
      [1, 0, "休日101", [[0, null, 485], [1, 495, null]]],
    ],
  },
  [lineB]: {
    stations: ["station:b1", "station:b2"],
    calendars: ["odpt.Calendar:Weekday"],
    trainTypes: ["odpt.TrainType:Test.Express"],
    trips: [
      [0, 0, "201", [[0, null, 493], [1, 503, null]]],
      [0, 0, "203", [[0, null, 496], [1, 506, null]]],
    ],
  },
};
const timed = model.timedItinerary(path, weekdayTimetables, 475, "weekday", 5);
assert.ok(timed, "a timetable-aware itinerary must be found");
assert.equal(timed.departure, 480);
assert.equal(timed.arrival, 506, "the five-minute transfer buffer must reject train 201");
assert.deepEqual(timed.segments.map((item) => item.trainNumber), ["101", "203"]);
assert.equal(model.timedItinerary(path, weekdayTimetables, 475, "holiday", 5), null, "missing holiday service on the second line must not invent a time");

const timedOnlyPath = model.shortestPath(origin, destination, { allowedRailways: [lineA, lineB] });
assert.ok(timedOnlyPath, "railway availability filtering must retain supported routes");
assert.equal(model.shortestPath(origin, destination, { allowedRailways: [lineA] }), null, "unsupported lines must be excluded from a timed route");

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

const stationBasedTimetables = {
  ...weekdayTimetables,
  [lineA]: {
    ...weekdayTimetables[lineA],
    timeBasis: "station-departure",
  },
};
const stationBased = model.timedItinerary(path, stationBasedTimetables, 475, "weekday", 5);
assert.equal(stationBased.estimatedArrival, true, "station timetable results must be labelled as an arrival estimate");

const departureOnly = model.nextDeparture(path, {
  [lineA]: {
    timeBasis: "station-departure-only",
    stations: ["station:a1"],
    calendars: ["odpt.Calendar:Weekday"],
    directions: ["direction:ascending"],
    trainTypes: ["odpt.TrainType:Test.Local"],
    order: ["station:a1", "station:a2"],
    ascendingDirection: "direction:ascending",
    descendingDirection: "direction:descending",
    edgeMinutes: [[0, 1, 3, 3]],
    boards: [[0, 0, 0, [[480, 0], [500, 0]]]],
  },
}, 481, "weekday");
assert.equal(departureOnly.departure, 500, "departure-only data must return the next scheduled train");
const lineAPath = model.shortestPath(origin, nearTransfer, { allowedRailways: [lineA] });
const estimated = model.timedItinerary(lineAPath, {
  [lineA]: {
    timeBasis: "station-departure-only",
    stations: ["station:a1", "station:a2"],
    calendars: ["odpt.Calendar:Weekday"],
    directions: ["direction:ascending"],
    trainTypes: ["odpt.TrainType:Test.Local"],
    order: ["station:a1", "station:a2"],
    ascendingDirection: "direction:ascending",
    descendingDirection: "direction:descending",
    edgeMinutes: [[0, 1, 3, 3]],
    boards: [[0, 0, 0, [[480, 0], [500, 0]]]],
  },
}, 481, "weekday", 5);
assert.equal(estimated.departure, 500);
assert.equal(estimated.arrival, 503);
assert.equal(estimated.estimatedArrival, true);

const geographicFallback = model.timedItinerary(lineAPath, {
  [lineA]: {
    timeBasis: "station-departure-only",
    stations: ["station:a1", "station:a2"],
    calendars: ["odpt.Calendar:Weekday"],
    directions: ["direction:ascending"],
    trainTypes: ["odpt.TrainType:Test.Local"],
    order: ["station:a1", "station:a2"],
    ascendingDirection: "direction:ascending",
    descendingDirection: "direction:descending",
    edgeMinutes: [],
    boards: [[0, 0, 0, [[500, 0]]]],
  },
}, 481, "weekday", 5);
assert.ok(geographicFallback.arrival > geographicFallback.departure, "a missing terminal edge must use a conservative geographic estimate");

const fastestEstimated = model.timedItinerary(lineAPath, {
  [lineA]: {
    timeBasis: "station-departure-only",
    stations: ["station:a1", "station:a2"],
    calendars: ["odpt.Calendar:Weekday"],
    directions: ["direction:ascending"],
    trainTypes: ["odpt.TrainType:Test.Express", "odpt.TrainType:Test.Local"],
    destinations: ["station:a2"],
    order: ["station:a1", "station:a2"],
    ascendingDirection: "direction:ascending",
    descendingDirection: "direction:descending",
    edgeMinutes: [[0, 1, 3, 3]],
    typeDurations: [[0, 1, 0, 0, 10, 8]],
    boards: [[0, 0, 0, [[500, 0, 0], [501, 1, 0]]]],
  },
}, 481, "weekday", 5);
assert.equal(fastestEstimated.departure, 501, "estimated routes must prefer the earliest arrival, not merely the first departure");
assert.equal(fastestEstimated.arrival, 504);

const periodicMatches = model.timedItinerary(lineAPath, {
  [lineA]: {
    timeBasis: "station-departure-only",
    stations: ["station:a1", "station:mid1", "station:mid2", "station:a2"],
    calendars: ["odpt.Calendar:Weekday"],
    directions: ["direction:ascending"],
    trainTypes: ["odpt.TrainType:Test.Express"],
    destinations: ["station:after-a2"],
    order: ["station:a1", "station:mid1", "station:mid2", "station:a2"],
    ascendingDirection: "direction:ascending",
    descendingDirection: "direction:descending",
    edgeMinutes: [[0, 1, 3, 3], [1, 2, 3, 3], [2, 3, 3, 3]],
    typeDurations: [
      [0, 1, 0, 0, 4, 100], [0, 1, 0, 0, 24, 70],
      [0, 2, 0, 0, 8, 90], [0, 2, 0, 0, 28, 75],
      [0, 3, 0, 0, 7, 110], [0, 3, 0, 0, 12, 80], [0, 3, 0, 0, 32, 70],
    ],
    boards: [[0, 0, 0, [[500, 0, 0]]]],
  },
}, 481, "weekday", 5);
assert.equal(periodicMatches.arrival, 512, "duration candidates must stay physically consistent across later stations");

console.log("route-core tests passed");
