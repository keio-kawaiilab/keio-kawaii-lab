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
const boundaryRegistry=readJson('data/transit/through-service-boundaries.json');
const familyRegistry=readJson('data/transit/through-service-families.json');
const operators=manifest&&manifest.operators||{};

if(familyRegistry?.policy?.runtimeInference!==false)throw new Error('through-service families must forbid runtime inference');
if(familyRegistry?.policy?.timeGapMayEstablishTrainIdentity!==false)throw new Error('time gap must never establish train identity');
if(familyRegistry?.policy?.genericBoundaryChaining!==false)throw new Error('generic boundary chaining must be disabled');

const railwayToSource=new Map();
const stationToRailways=new Map();
const stationSuffixToRailways=new Map();
const knownRailways=new Set();
const sourceRows=[];

function addStationRailway(stationId,railwayId){
  if(!stationId||!railwayId)return;
  knownRailways.add(railwayId);
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
      if(railwayId)knownRailways.add(railwayId);
      for(const row of asArray(railway['odpt:stationOrder']))addStationRailway(row&&row['odpt:station'],railwayId);
    }
  }
  const indexFile=`data/transit/${slug}/timetable-index.json`;
  if(!exists(indexFile))continue;
  const index=readJson(indexFile);
  for(const [railwayId,line] of Object.entries(index.lines||{})){
    if(!line||!line.file)continue;
    knownRailways.add(railwayId);
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

const verifiedFamilies=(familyRegistry.families||[]).filter((family)=>family&&family.status==='verified');
const familyPathRows=[];
const unknownFamilyRailways=[];
for(const family of verifiedFamilies){
  for(let pathIndex=0;pathIndex<(family.paths||[]).length;pathIndex++){
    const route=family.paths[pathIndex];
    if(!Array.isArray(route)||route.length<2)continue;
    for(const railway of route)if(!knownRailways.has(railway))unknownFamilyRailways.push({family:family.id,pathIndex,railway});
    familyPathRows.push({familyId:family.id,pathIndex,route,sourceUrls:family.sourceUrls||[],exclusions:family.exclusions||[]});
  }
}

function allSubpaths(route,fromRailway,toRailway){
  const results=[];
  for(let i=0;i<route.length;i++){
    if(route[i]!==fromRailway)continue;
    for(let j=i+1;j<route.length;j++){
      if(route[j]===toRailway)results.push(route.slice(i,j+1));
    }
  }
  return results;
}

function matchServiceFamily(fromRailway,targetRailways){
  const targetSet=new Set(targetRailways||[]);
  const matches=[];
  for(const row of familyPathRows){
    const orientations=[row.route,[...row.route].reverse()];
    for(const oriented of orientations){
      for(const target of targetSet){
        for(const subpath of allSubpaths(oriented,fromRailway,target)){
          if(subpath.some((railway)=>row.exclusions.includes(railway)))continue;
          matches.push({familyId:row.familyId,pathIndex:row.pathIndex,route:subpath,sourceUrls:row.sourceUrls});
        }
      }
    }
  }
  const uniqueByRoute=new Map();
  for(const match of matches){
    const signature=match.route.join('|');
    if(!uniqueByRoute.has(signature))uniqueByRoute.set(signature,match);
    else{
      const existing=uniqueByRoute.get(signature);
      existing.familyIds=uniq([...(existing.familyIds||[existing.familyId]),match.familyId]);
    }
  }
  const unique=Array.from(uniqueByRoute.values());
  if(!unique.length)return{status:'no-family'};
  if(unique.length>1)return{status:'ambiguous-family',matches:unique.map((row)=>({familyId:row.familyId,route:row.route}))};
  return{status:'matched',...unique[0]};
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

// Departure-only rows may be classified only from their own published final
// destination AND a verified, explicit service-family path. No timetable-gap
// matching and no generic boundary chaining are permitted.
for(const [railwayId,source] of railwayToSource.entries()){
  if(!exists(source.file))continue;
  const table=readJson(source.file);
  const row={railway:railwayId,operator:source.slug,timeBasis:table.timeBasis||'',file:source.file,trips:0,withPublishedDestination:0,externalPublishedDestination:0,classifiedThrough:0,noFamily:0,ambiguousFamily:0};
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
      const family=matchServiceFamily(railwayId,targetRailways);
      if(family.status!=='matched'){
        if(family.status==='no-family')row.noFamily++;
        if(family.status==='ambiguous-family')row.ambiguousFamily++;
        unresolved.push({railway:railwayId,operator:source.slug,sourceTripIndex:tripIndex,destination,targetRailways,reason:family.status,matches:family.matches||[]});
        continue;
      }
      const stops=trip[5]||[];
      const id=`destination:${digest([railwayId,trip[0],trip[1],trip[2],trip[3],stops,family.route])}`;
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
        serviceFamily:family.familyId,
        serviceFamilies:family.familyIds||[family.familyId],
        routeRailways:family.route,
        localStops:stops.map((stop)=>({station:stations[stop[0]]||'',arrival:stop[1]??null,departure:stop[2]??null})),
        classification:'through',
        evidence:'published-final-destination+verified-service-family'
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
  version:2,
  generatedAt:new Date().toISOString(),
  policy:{runtimeInference:false,timeGapMayEstablishIdentity:false,genericBoundaryChaining:false},
  records
};
writeJson('data/transit/through-service-trips.json',tripDb);

const boundaryRows=(boundaryRegistry.boundaries||[]).map((boundary)=>({
  id:boundary.id,station:boundary.station,fromRailway:boundary.fromRailway,toRailway:boundary.toRailway,status:boundary.status,source:boundary.source||''
}));
const familyRows=(familyRegistry.families||[]).map((family)=>({
  id:family.id,status:family.status,paths:(family.paths||[]).length,sourceUrls:family.sourceUrls||[],exclusions:family.exclusions||[]
}));
const coverage={
  version:2,
  generatedAt:tripDb.generatedAt,
  summary:{
    boundaries:boundaryRows.length,
    verifiedBoundaries:boundaryRows.filter((r)=>r.status==='verified').length,
    serviceFamilies:familyRows.length,
    verifiedServiceFamilies:familyRows.filter((r)=>r.status==='verified').length,
    familyPaths:familyPathRows.length,
    unknownFamilyRailways:unknownFamilyRailways.length,
    throughRecords:records.length,
    exactNetworkThroughRecords:records.filter((r)=>r.identityType==='train-timetable-network').length,
    publishedDestinationThroughRecords:records.filter((r)=>r.identityType==='published-destination').length,
    unresolvedExternalDestinationTrips:unresolved.length,
    noFamilyForExternalDestination:unresolved.filter((r)=>r.reason==='no-family').length,
    ambiguousFamilyForExternalDestination:unresolved.filter((r)=>r.reason==='ambiguous-family').length,
    sourceLines:sourceRows.length,
    sourceLinesWithPublishedDestination:sourceRows.filter((r)=>r.withPublishedDestination>0).length,
    sourceLinesWithoutPublishedDestination:sourceRows.filter((r)=>r.trips>0&&r.withPublishedDestination===0).length
  },
  families:familyRows,
  unknownFamilyRailways,
  boundaries:boundaryRows,
  sources:sourceRows,
  unresolved
};
writeJson('data/transit/through-service-coverage.json',coverage);
console.log(JSON.stringify(coverage.summary,null,2));
