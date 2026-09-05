#!/usr/bin/env node
"use strict";

// Prove that equal train numbers and zero-minute boundary alignment are NOT
// enough to suppress a transfer. Only an explicit precomputed identity edge
// may turn the boundary into a through movement.
const core=require("../route-core.js");

const A="test.Station:A";
const X1="test.Station:OperatorA.X";
const X2="test.Station:OperatorB.X";
const B="test.Station:B";
const L1="test.Railway:OperatorA.Line";
const L2="test.Railway:OperatorB.Line";
const TYPE="test.TrainType:Local";

const payload={
  Station:[
    {"owl:sameAs":A,"dc:title":"A","odpt:railway":L1,"odpt:operator":"test.Operator:A"},
    {"owl:sameAs":X1,"dc:title":"X","odpt:railway":L1,"odpt:operator":"test.Operator:A","odpt:connectingStation":[X2]},
    {"owl:sameAs":X2,"dc:title":"X","odpt:railway":L2,"odpt:operator":"test.Operator:B","odpt:connectingStation":[X1]},
    {"owl:sameAs":B,"dc:title":"B","odpt:railway":L2,"odpt:operator":"test.Operator:B"}
  ],
  Railway:[
    {"owl:sameAs":L1,"dc:title":"A線","odpt:operator":"test.Operator:A","odpt:stationOrder":[
      {"odpt:index":1,"odpt:station":A},{"odpt:index":2,"odpt:station":X1}
    ]},
    {"owl:sameAs":L2,"dc:title":"B線","odpt:operator":"test.Operator:B","odpt:stationOrder":[
      {"odpt:index":1,"odpt:station":X2},{"odpt:index":2,"odpt:station":B}
    ]}
  ],
  TrainType:[{"owl:sameAs":TYPE,"dc:title":"普通"}]
};

const model=core.createModel([payload]);
const origin=model.resolveInput("A").group;
const destination=model.resolveInput("B").group;
if(!origin||!destination)throw new Error("Synthetic stations did not resolve");
const path=model.shortestPath(origin,destination);
if(!path)throw new Error("Synthetic transfer path was not built");

function table(stations,identity){
  return {
    timeBasis:"train-timetable",
    stations,
    calendars:["weekday"],
    trainTypes:[TYPE],
    trips:[[0,0,"777",[
      [0,null,300],
      [1,310,310]
    ],stations[1],null,identity]]
  };
}

const tables={};
tables[L1]=table([A,X1],"left-physical-train");
tables[L2]={
  timeBasis:"train-timetable",
  stations:[X2,B],
  calendars:["weekday"],
  trainTypes:[TYPE],
  trips:[[0,0,"777",[
    [0,310,310],
    [1,320,null]
  ],B,null,"right-physical-train"]]
};

// Same displayed train number (777), exactly matching 05:10 boundary time,
// but no authoritative identity relationship: this MUST remain one transfer.
const separate=model.timedItinerary(path,tables,299,"weekday",0,null,()=>new Set());
if(!separate)throw new Error("Synthetic separate-train itinerary was not found");
if(separate.transfers!==1)throw new Error(`Time/train-number inference leaked into identity: transfers=${separate.transfers}`);
if(separate.segments[1].throughFromPrevious)throw new Error("Separate train was incorrectly marked as through");

// The same timetable becomes zero-transfer only when the precomputed resolver
// explicitly maps the first physical identity to the second one.
const verified=model.timedItinerary(path,tables,299,"weekday",0,null,(identity,fromRailway,toRailway)=>{
  if(identity==="tt:left-physical-train"&&fromRailway===L1&&toRailway===L2){
    return new Set(["tt:right-physical-train"]);
  }
  return new Set();
});
if(!verified)throw new Error("Synthetic verified-through itinerary was not found");
if(verified.transfers!==0)throw new Error(`Verified identity did not suppress transfer: transfers=${verified.transfers}`);
if(!verified.segments[1].throughFromPrevious)throw new Error("Verified identity was not marked as through");

console.log("Keisei identity safety regression passed",{
  sameDisplayedTrainNumber:"777",
  sameBoundaryMinute:310,
  withoutIdentityTransfers:separate.transfers,
  withVerifiedIdentityTransfers:verified.transfers
});
