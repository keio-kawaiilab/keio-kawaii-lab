import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const root=process.cwd();
const readJson=(file)=>JSON.parse(fs.readFileSync(path.join(root,file),'utf8'));
const exists=(file)=>fs.existsSync(path.join(root,file));
const writeJson=(file,value)=>fs.writeFileSync(path.join(root,file),JSON.stringify(value,null,2)+'\n','utf8');
const asArray=(value)=>Array.isArray(value)?value:(value==null?[]:[value]);
const idOf=(item)=>item&&item['owl:sameAs']||'';
const uniq=(values)=>Array.from(new Set(values.filter(Boolean)));
const collapse=(values)=>{const out=[];for(const value of values||[])if(value&&out[out.length-1]!==value)out.push(value);return out;};
const digest=(value)=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex').slice(0,20);

const manifest=readJson('data/transit/manifest.json');
const registry=readJson('data/transit/through-service-boundaries.json');
const operators=manifest&&manifest.operators||{};

const railwayToSource=new Map();
const stationToRailways=new Map();
const stationSuffixToRailways=new Map();
const sourceRows=[];

function addStationRailway(stationId,railwayId){
  if(!stationId||!railwayId)return;
  if(!stationToRailways.has(stationId))stationToRailways.set(stationId,new Set());
  stationToRailways.get(stationId).add(railwayId);
  const suffix=String(stationId).split('.').pop();
  if(suffix){
    if(!stationSuffixToRailways.has(suffix))stationSuffixToRailways.set(suffix,new Set());
    stationSuffixToRailways.get(suffix).add(railwayId);
  }
}

for(const [slug,meta] of Object.entries(operators)){
  if(!meta||meta.status!=='ok')continue;
  const entitiesFile=`data/transit/${slug}/entities.json`;
  if(exists(entitiesFile)){
    const entities=readJson(entitiesFile);
    for(const station of entities.Station||[]){
      const stationId=idOf(station);
      for(const railwayId of asArray(station['odpt:railway']))addStationRailway(stationId,railwayId);
    }
    for(const railway of entities.Railway||[]){
      const railwayId=idOf(railway);
      for(const row of asArray(railway['odpt:stationOrder']))addStationRailway(row&&row['odpt:station'],railwayId);
    }
  }
  const indexFile=`data/transit/${slug}/timetable-index.json`;
  if(!exists(indexFile))continue;
  const index=readJson(indexFile);
  for(const [railwayId,line] of Object.entries(index.lines||{})){
    if(!line||!line.file)continue;
    railwayToSource.set(railwayId,{slug,line,file:`data/transit/${slug}/${line.file}`,index});
  }
}

function destinationRailways(destinationId){
  if(!destinationId)return[];
  const direct=stationToRailways.get(destinationId);
  if(direct&&direct.size)return Array.from(direct);
  const suffix=String(destinationId).split('.').pop();
  const bySuffix=stationSuffixToRailways.get(suffix);
  return bySuffix&&bySuffix.size?Array.from(bySuffix):[];
}

const verifiedBoundaries=(registry.boundaries||[]).filter((row)=>row&&row.status==='verified');
const graph=new Map();
function addBoundaryEdge(from,to,boundary,reverse){
  if(!graph.has(from))graph.set(from,[]);
  graph.get(from).push({to,boundary,reverse:Boolean(reverse)});
}
for(const boundary of verifiedBoundaries){
  addBoundaryEdge(boundary.fromRailway,boundary.toRailway,boundary,false);
  if(boundary.bidirectional)addBoundaryEdge(boundary.toRailway,boundary.fromRailway,boundary,true);
}

function uniqueBoundaryPath(fromRailway,targetRailways){
  const targets=new Set(targetRailways||[]);
  if(targets.has(fromRailway))return{status:'same-line',railways:[fromRailway],boundaries:[]};
  const queue=[{railway:fromRailway,railways:[fromRailway],boundaries:[]}];
  const solutions=[];
  let bestDepth=Infinity;
  while(queue.length){
    const state=queue.shift();
    if(state.boundaries.length>bestDepth)continue;
    for(const edge of graph.get(state.railway)||[]){
      if(state.railways.includes(edge.to))continue;
      const next={
        railway:edge.to,
        railways:[...state.railways,edge.to],
        boundaries:[...state.boundaries,{id:edge.boundary.id,station:edge.boundary.station,fromRailway:state.railway,toRailway:edge.to,reverse:edge.reverse}]
      };
      if(targets.has(edge.to)){
        if(next.boundaries.length<bestDepth){solutions.length=0;bestDepth=next.boundaries.length;}
        if(next.boundaries.length===bestDepth)solutions.push(next);
      }else if(next.boundaries.length<bestDepth){
        queue.push(next);
      }
    }
  }
  if(!solutions.length)return{status:'unresolved',railways:[],boundaries:[]};
  const signatures=uniq(solutions.map((s)=>s.railways.join('|')));
  if(signatures.length!==1)return{status:'ambiguous',railways:[],boundaries:[]};
  return{status:'unique',railways:solutions[0].railways,boundaries:solutions[0].boundaries};
}

const records=[];
const unresolved=[];
const exactNetworkSeen=new Set();
const processedNetworks=new Set();

// Exact multi-railway timetable networks are authoritative train identities.
for(const [slug,meta] of Object.entries(operators)){
  if(!meta||meta.status!=='ok')continue;
  const indexFile=`data/transit/${slug}/timetable-index.json`;
  if(!exists(indexFile))continue;
  const index=readJson(indexFile);
  const network=index.network;
  if(!network||!network.file||processedNetworks.has(`${slug}:${network.file}`))continue;
  processedNetworks.add(`${slug}:${network.file}`);
  const networkFile=`data/transit/${slug}/${network.file}`;
  if(!exists(networkFile))continue;
  const table=readJson(networkFile);
  if(table.timeBasis!=='train-timetable-network'||!Array.isArray(table.trips))continue;
  const railways=table.railways||[];
  const stations=table.stations||[];
  const calendars=table.calendars||[];
  const trainTypes=table.trainTypes||[];
  for(let tripIndex=0;tripIndex<table.trips.length;tripIndex++){
    const trip=table.trips[tripIndex];
    if(!Array.isArray(trip))continue;
    const stops=trip[3]||[];
    const links=trip[4]||[];
    const used=collapse(links.flatMap((row)=>asArray(row).map((idx)=>railways[idx])));
    if(used.length<2)continue;
    const transitions=[];
    let prior='';
    for(let edgeIndex=0;edgeIndex<links.length;edgeIndex++){
      const onEdge=collapse(asArray(links[edgeIndex]).map((idx)=>railways[idx]));
      for(const current of onEdge){
        if(prior&&current!==prior){
          const stop=stops[edgeIndex]||[];
          transitions.push({fromRailway:prior,toRailway:current,boundaryStation:stations[stop[0]]||'',stopIndex:edgeIndex});
        }
        prior=current;
      }
    }
    const identity=[slug,network.id||network.file,tripIndex,trip[2]||'',trip[0],trip[1]];
    const id=`network:${digest(identity)}`;
    if(exactNetworkSeen.has(id))continue;
    exactNetworkSeen.add(id);
    records.push({
      id,
      identityType:'train-timetable-network',
      sourceOperator:slug,
      sourceNetwork:network.id||network.file,
      sourceTripIndex:tripIndex,
      calendar:calendars[trip[0]]||'',
      trainType:trainTypes[trip[1]]||'',
      trainNumber:String(trip[2]||''),
      routeRailways:used,
      transitions,
      firstStation:stops.length?stations[stops[0][0]]||'':'',
      lastStation:stops.length?stations[stops[stops.length-1][0]]||'':'',
      classification:'through',
      evidence:'exact-network-trip'
    });
  }
}

// Departure-only sources can establish identity without time matching when the
// departure itself publishes a destination beyond the current railway and the
// verified through-boundary path to that destination is unique.
for(const [railwayId,source] of railwayToSource.entries()){
  if(!exists(source.file))continue;
  const table=readJson(source.file);
  const row={railway:railwayId,operator:source.slug,timeBasis:table.timeBasis||'',file:source.file,trips:0,withPublishedDestination:0,externalPublishedDestination:0,classifiedThrough:0,unresolvedExternalDestination:0};
  if(table.timeBasis==='station-departure-only'&&Array.isArray(table.inferredTrips)&&table.inferredTrips.length){
    const destinations=table.destinations||[];
    const calendars=table.calendars||[];
    const directions=table.directions||[];
    const trainTypes=table.trainTypes||[];
    const stations=table.stations||[];
    for(let tripIndex=0;tripIndex<table.inferredTrips.length;tripIndex++){
      const trip=table.inferredTrips[tripIndex];
      if(!Array.isArray(trip))continue;
      row.trips++;
      const destination=destinations[trip[3]]||'';
      if(!destination)continue;
      row.withPublishedDestination++;
      const targetRailways=destinationRailways(destination);
      if(!targetRailways.length||targetRailways.includes(railwayId))continue;
      row.externalPublishedDestination++;
      const route=uniqueBoundaryPath(railwayId,targetRailways);
      if(route.status!=='unique'){
        row.unresolvedExternalDestination++;
        unresolved.push({railway:railwayId,operator:source.slug,sourceTripIndex:tripIndex,destination,targetRailways,reason:`through-boundary-${route.status}`});
        continue;
      }
      const stops=trip[5]||[];
      const id=`destination:${digest([railwayId,trip[0],trip[1],trip[2],trip[3],stops])}`;
      records.push({
        id,
        identityType:'published-destination',
        sourceOperator:source.slug,
        sourceRailway:railwayId,
        sourceTripIndex:tripIndex,
        calendar:calendars[trip[0]]||'',
        direction:directions[trip[1]]||'',
        trainType:trainTypes[trip[2]]||'',
        destination,
        routeRailways:route.railways,
        transitions:route.boundaries,
        localStops:stops.map((stop)=>({station:stations[stop[0]]||'',arrival:stop[1]??null,departure:stop[2]??null})),
        classification:'through',
        evidence:'published-final-destination+verified-unique-boundary-path'
      });
      row.classifiedThrough++;
    }
  }else if(Array.isArray(table.trips)){
    row.trips=table.trips.length;
  }
  sourceRows.push(row);
}

records.sort((a,b)=>a.id.localeCompare(b.id));
unresolved.sort((a,b)=>`${a.operator}:${a.railway}:${a.sourceTripIndex}`.localeCompare(`${b.operator}:${b.railway}:${b.sourceTripIndex}`));

const tripDb={
  version:1,
  generatedAt:new Date().toISOString(),
  policy:{runtimeInference:false,timeGapMayEstablishIdentity:false},
  records
};
writeJson('data/transit/through-service-trips.json',tripDb);

const boundaryRows=(registry.boundaries||[]).map((boundary)=>({
  id:boundary.id,
  station:boundary.station,
  fromRailway:boundary.fromRailway,
  toRailway:boundary.toRailway,
  status:boundary.status,
  source:boundary.source||'',
  fromTimetable:Boolean(railwayToSource.get(boundary.fromRailway)),
  toTimetable:Boolean(railwayToSource.get(boundary.toRailway))
}));
const coverage={
  version:1,
  generatedAt:tripDb.generatedAt,
  summary:{
    boundaries:boundaryRows.length,
    verifiedBoundaries:boundaryRows.filter((r)=>r.status==='verified').length,
    boundarySourceAuditRequired:boundaryRows.filter((r)=>r.status!=='verified').length,
    throughRecords:records.length,
    exactNetworkThroughRecords:records.filter((r)=>r.identityType==='train-timetable-network').length,
    publishedDestinationThroughRecords:records.filter((r)=>r.identityType==='published-destination').length,
    unresolvedExternalDestinationTrips:unresolved.length,
    sourceLines:sourceRows.length,
    sourceLinesWithPublishedDestination:sourceRows.filter((r)=>r.withPublishedDestination>0).length,
    sourceLinesWithoutPublishedDestination:sourceRows.filter((r)=>r.trips>0&&r.withPublishedDestination===0).length
  },
  boundaries:boundaryRows,
  sources:sourceRows,
  unresolved
};
writeJson('data/transit/through-service-coverage.json',coverage);
console.log(JSON.stringify(coverage.summary,null,2));
