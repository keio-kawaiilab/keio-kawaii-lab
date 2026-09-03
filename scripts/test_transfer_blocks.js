"use strict";

const assert=require("node:assert/strict");
const core=require("../route-core.js");

function station(id,name,railway,lat,lon,connectingStation){
  const item={
    "owl:sameAs":id,
    "odpt:stationTitle":{ja:name},
    "odpt:railway":railway,
    "odpt:operator":"odpt.Operator:Test",
    "geo:lat":lat,
    "geo:long":lon
  };
  if(connectingStation)item["odpt:connectingStation"]=connectingStation;
  return item;
}
function railway(id,name,stations){
  return{
    "owl:sameAs":id,
    "odpt:operator":"odpt.Operator:Test",
    "odpt:railwayTitle":{ja:name},
    "odpt:stationOrder":stations.map((stationId,index)=>({"odpt:index":index+1,"odpt:station":stationId}))
  };
}
function payload(explicit){
  return{
    Station:[
      station("station:a0","出発","line:a",35.000,139.000),
      station("station:a1","同名駅","line:a",35.0100,139.0100,explicit?["station:b1"]:undefined),
      station("station:b1","同名駅","line:b",35.0105,139.0105,explicit?["station:a1"]:undefined),
      station("station:b2","到着","line:b",35.020,139.020)
    ],
    Railway:[
      railway("line:a","A線",["station:a0","station:a1"]),
      railway("line:b","B線",["station:b1","station:b2"])
    ]
  };
}
function pairKey(a,b){return[a,b].sort().join("\u0001");}
function route(model){return model.shortestPath(model.resolveInput("出発").group,model.resolveInput("到着").group);}

assert.ok(route(core.createModel([payload(false)])),"nearby same-name stations normally receive a heuristic transfer edge");
const blocked=core.createModel([payload(false)],{blockedStationPairs:[pairKey("station:a1","station:b1")]});
assert.equal(route(blocked),null,"a blocked same-name station pair must not receive the heuristic transfer edge");
const explicit=core.createModel([payload(true)],{blockedStationPairs:[pairKey("station:a1","station:b1")]});
assert.ok(route(explicit),"an explicit connectingStation edge must remain usable even when the heuristic pair is blocked");

console.log("transfer block tests passed");
