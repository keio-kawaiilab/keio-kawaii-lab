const core=require('../route-core.js');

const S=(id,name,railways)=>({'owl:sameAs':id,'odpt:stationTitle':{ja:name},'odpt:railway':railways});
const R=(id,name,operator,stations)=>({'owl:sameAs':id,'odpt:railwayTitle':{ja:name},'odpt:operator':operator,'odpt:stationOrder':stations.map((station,index)=>({'odpt:index':index,'odpt:station':station}))});

const A='odpt.Railway:Test.A';
const B='odpt.Railway:Test.B';
const C='odpt.Railway:Test.C';
const A0='odpt.Station:Test.A.A0';
const X='odpt.Station:Test.X.X';
const Y='odpt.Station:Test.Y.Y';
const D='odpt.Station:Test.C.D';

const payload={
  Station:[S(A0,'A0',[A]),S(X,'X',[A,B]),S(Y,'Y',[B,C]),S(D,'D',[C])],
  Railway:[R(A,'A線','op:A',[A0,X]),R(B,'B線','op:B',[X,Y]),R(C,'C線','op:C',[Y,D])],
  TrainType:[]
};

const model=core.createModel([payload]);
const origin=model.resolveInput('A0').group;
const destination=model.resolveInput('D').group;
const path=model.shortestPath(origin,destination);
if(!path)throw new Error('Synthetic path was not created');

const stationTable=(railway,order,destinationId,departure)=>({
  version:2,
  railway,
  timeBasis:'station-departure-only',
  stations:order,
  order,
  calendars:['weekday'],
  directions:['out'],
  trainTypes:['odpt.TrainType:Test.Local'],
  destinations:[destinationId],
  ascendingDirection:'out',
  descendingDirection:'in',
  boards:[[0,0,0,[[departure,0,0]]]],
  inferredTrips:[],
  edgeMinutes:[[0,1,5]],
  typeDurations:[]
});

const tables={};
tables[A]=stationTable(A,[A0,X],D,600);
tables[B]={
  version:1,
  railway:B,
  timeBasis:'train-timetable',
  stations:[X,Y],
  calendars:['weekday'],
  trainTypes:['odpt.TrainType:Test.Local'],
  trips:[[0,0,'B1',[[0,null,605],[1,610,null]]]]
};
tables[C]=stationTable(C,[Y,D],D,610);

const timed=model.timedItinerary(path,tables,600,'weekday',5);
if(!timed)throw new Error('No itinerary returned');
if(timed.transfers!==0)throw new Error(`Expected 0 transfers, got ${timed.transfers}`);
if(timed.segments.length!==3)throw new Error(`Expected 3 railway segments, got ${timed.segments.length}`);
if(!timed.segments[1].throughFromPrevious||!timed.segments[2].throughFromPrevious)throw new Error('Cross-operator boundaries were not marked through');
if(timed.segments[1].destination!==D)throw new Error('Destination was not propagated across destination-less train timetable');

console.log('cross-operator through-service test passed');
