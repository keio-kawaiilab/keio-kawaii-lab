import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const root=process.cwd();
const p=(file)=>path.join(root,file);
const exists=(file)=>fs.existsSync(p(file));
const readJson=(file)=>JSON.parse(fs.readFileSync(p(file),'utf8'));
const writeJson=(file,value)=>fs.writeFileSync(p(file),JSON.stringify(value,null,2)+'\n','utf8');
const asArray=(value)=>Array.isArray(value)?value:(value==null?[]:[value]);
const uniq=(values)=>Array.from(new Set((values||[]).filter(Boolean)));
const digest=(value)=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex').slice(0,20);

const identityFile='data/transit/odpt-train-identities.json';
const tripsFile='data/transit/through-service-trips.json';
const coverageFile='data/transit/through-service-coverage.json';
const familiesFile='data/transit/through-service-families.json';

if(!exists(identityFile)){
  console.log('No ODPT train-identity sidecar; leaving through-service DB unchanged.');
  process.exit(0);
}
for(const required of [tripsFile,coverageFile,familiesFile]){
  if(!exists(required))throw new Error(`Missing required file: ${required}`);
}

const identity=readJson(identityFile);
const tripDb=readJson(tripsFile);
const coverage=readJson(coverageFile);
const familyRegistry=readJson(familiesFile);

if(identity?.policy?.runtimeInference!==false)throw new Error('identity sidecar must forbid runtime inference');
if(identity?.policy?.timeGapMayEstablishTrainIdentity!==false)throw new Error('identity sidecar must forbid timetable-gap identity');
if(identity?.policy?.trainNumberMayEstablishTrainIdentity!==false)throw new Error('identity sidecar must forbid train-number identity');
if(familyRegistry?.policy?.runtimeInference!==false)throw new Error('through-service families must forbid runtime inference');
if(familyRegistry?.policy?.timeGapMayEstablishTrainIdentity!==false)throw new Error('through-service families must forbid timetable-gap identity');
if(familyRegistry?.policy?.genericBoundaryChaining!==false)throw new Error('generic boundary chaining must stay disabled');

const stationToRailways=new Map();
const suffixToRailways=new Map();
function addStationRailway(station,railway){
  if(!station||!railway)return;
  if(!stationToRailways.has(station))stationToRailways.set(station,new Set());
  stationToRailways.get(station).add(railway);
  const suffix=String(station).split('.').pop();
  if(suffix){
    if(!suffixToRailways.has(suffix))suffixToRailways.set(suffix,new Set());
    suffixToRailways.get(suffix).add(railway);
  }
}

const transitRoot=p('data/transit');
if(fs.existsSync(transitRoot)){
  for(const entry of fs.readdirSync(transitRoot,{withFileTypes:true})){
    if(!entry.isDirectory())continue;
    const entitiesPath=path.join(transitRoot,entry.name,'entities.json');
    if(!fs.existsSync(entitiesPath))continue;
    let entities;
    try{entities=JSON.parse(fs.readFileSync(entitiesPath,'utf8'));}catch{continue;}
    for(const station of entities.Station||[]){
      const stationId=station&&station['owl:sameAs']||'';
      for(const railway of asArray(station&&station['odpt:railway']))addStationRailway(stationId,railway);
    }
    for(const railway of entities.Railway||[]){
      const railwayId=railway&&railway['owl:sameAs']||'';
      for(const order of asArray(railway&&railway['odpt:stationOrder']))addStationRailway(order&&order['odpt:station'],railwayId);
    }
  }
}

function destinationRailways(station){
  if(!station)return[];
  const direct=stationToRailways.get(station);
  if(direct&&direct.size)return Array.from(direct);
  const suffix=String(station).split('.').pop();
  const bySuffix=suffixToRailways.get(suffix);
  return bySuffix&&bySuffix.size?Array.from(bySuffix):[];
}

const familyPaths=[];
for(const family of familyRegistry.families||[]){
  if(!family||family.status!=='verified')continue;
  for(let pathIndex=0;pathIndex<(family.paths||[]).length;pathIndex++){
    const route=family.paths[pathIndex];
    if(Array.isArray(route)&&route.length>=2){
      familyPaths.push({familyId:family.id,pathIndex,route,exclusions:family.exclusions||[],sourceUrls:family.sourceUrls||[]});
    }
  }
}

function allSubpaths(route,fromRailway,toRailway){
  const results=[];
  for(let i=0;i<route.length;i++){
    if(route[i]!==fromRailway)continue;
    for(let j=i+1;j<route.length;j++)if(route[j]===toRailway)results.push(route.slice(i,j+1));
  }
  return results;
}

function matchServiceFamily(fromRailway,targetRailways){
  const targetSet=new Set(targetRailways||[]);
  const matches=[];
  for(const row of familyPaths){
    for(const oriented of [row.route,[...row.route].reverse()]){
      for(const target of targetSet){
        for(const route of allSubpaths(oriented,fromRailway,target)){
          if(route.some((railway)=>row.exclusions.includes(railway)))continue;
          matches.push({familyId:row.familyId,pathIndex:row.pathIndex,route,sourceUrls:row.sourceUrls});
        }
      }
    }
  }
  const byRoute=new Map();
  for(const match of matches){
    const signature=match.route.join('|');
    if(!byRoute.has(signature))byRoute.set(signature,{...match,familyIds:[match.familyId]});
    else byRoute.get(signature).familyIds=uniq([...byRoute.get(signature).familyIds,match.familyId]);
  }
  const unique=Array.from(byRoute.values());
  if(!unique.length)return{status:'no-family'};
  if(unique.length>1)return{status:'ambiguous-family',matches:unique.map((row)=>({familyId:row.familyId,route:row.route}))};
  return{status:'matched',...unique[0]};
}

function sameBoundaryStation(left,right){
  const a=left&&left.lastStop&&left.lastStop.station||'';
  const b=right&&right.firstStop&&right.firstStop.station||'';
  if(!a||!b)return a||b||'';
  if(a===b)return a;
  return String(a).split('.').pop()===String(b).split('.').pop()?a:'';
}

const identities=Array.isArray(identity.records)?identity.records:[];
const byTimetable=new Map(identities.filter((row)=>row&&row.timetableId).map((row)=>[row.timetableId,row]));
const baseRecords=Array.isArray(tripDb.records)?tripDb.records:[];
const recordMap=new Map(baseRecords.map((row)=>[row.id,row]));
const unresolved=[];
let exactLinkRecords=0;
let exactDestinationRecords=0;

function addRecord(record){
  if(recordMap.has(record.id))return false;
  recordMap.set(record.id,record);
  return true;
}

function considerLink(from,to,linkType){
  if(!from||!to||!from.railway||!to.railway||from.railway===to.railway)return;
  const family=matchServiceFamily(from.railway,[to.railway]);
  if(family.status!=='matched'){
    unresolved.push({type:'authoritative-link',fromTimetableId:from.timetableId,toTimetableId:to.timetableId,fromRailway:from.railway,toRailway:to.railway,reason:family.status,matches:family.matches||[]});
    return;
  }
  const id=`odpt-link:${digest([from.timetableId,to.timetableId,family.route])}`;
  if(addRecord({
    id,
    identityType:'odpt-train-timetable-link',
    sourceOperator:from.sourceOperator||'',
    targetOperator:to.sourceOperator||'',
    sourceTimetableId:from.timetableId,
    targetTimetableId:to.timetableId,
    sourceTrainId:from.trainId||'',
    targetTrainId:to.trainId||'',
    calendars:uniq([...(from.calendars||[]),...(to.calendars||[])]),
    trainType:from.trainType||to.trainType||'',
    trainNumber:from.trainNumber||to.trainNumber||'',
    serviceFamily:family.familyId,
    serviceFamilies:family.familyIds||[family.familyId],
    routeRailways:family.route,
    transitions:[{fromRailway:from.railway,toRailway:to.railway,boundaryStation:sameBoundaryStation(from,to)}],
    classification:'through',
    evidence:'odpt-previous-next-train-timetable+verified-service-family',
    authoritativeLink:linkType
  }))exactLinkRecords++;
}

for(const row of identities){
  if(!row||!row.timetableId)continue;
  for(const nextId of row.nextTrainTimetables||[]){
    const next=byTimetable.get(nextId);
    if(next)considerLink(row,next,'nextTrainTimetable');
    else unresolved.push({type:'missing-linked-timetable',fromTimetableId:row.timetableId,toTimetableId:nextId,fromRailway:row.railway,reason:'linked-timetable-not-collected'});
  }
  for(const previousId of row.previousTrainTimetables||[]){
    const previous=byTimetable.get(previousId);
    if(previous)considerLink(previous,row,'previousTrainTimetable');
    else unresolved.push({type:'missing-linked-timetable',fromTimetableId:previousId,toTimetableId:row.timetableId,toRailway:row.railway,reason:'linked-timetable-not-collected'});
  }
}

for(const row of identities){
  if(!row||!row.timetableId||!row.railway||!row.externalDestination)continue;
  const targetRailways=uniq((row.destination||[]).flatMap(destinationRailways)).filter((railway)=>railway!==row.railway);
  if(!targetRailways.length){
    unresolved.push({type:'exact-published-destination',timetableId:row.timetableId,railway:row.railway,destination:row.destination||[],reason:'destination-railway-unknown'});
    continue;
  }
  const family=matchServiceFamily(row.railway,targetRailways);
  if(family.status!=='matched'){
    unresolved.push({type:'exact-published-destination',timetableId:row.timetableId,railway:row.railway,destination:row.destination||[],targetRailways,reason:family.status,matches:family.matches||[]});
    continue;
  }
  const id=`odpt-destination:${digest([row.timetableId,row.destination,family.route])}`;
  if(addRecord({
    id,
    identityType:'odpt-exact-published-destination',
    sourceOperator:row.sourceOperator||'',
    sourceRailway:row.railway,
    sourceTimetableId:row.timetableId,
    trainId:row.trainId||'',
    calendars:row.calendars||[],
    trainType:row.trainType||'',
    trainNumber:row.trainNumber||'',
    direction:row.direction||'',
    origin:row.origin||[],
    destination:row.destination||[],
    serviceFamily:family.familyId,
    serviceFamilies:family.familyIds||[family.familyId],
    routeRailways:family.route,
    classification:'through',
    evidence:'odpt-published-final-destination+verified-service-family'
  }))exactDestinationRecords++;
}

const records=Array.from(recordMap.values()).sort((a,b)=>String(a.id).localeCompare(String(b.id)));
tripDb.version=Math.max(Number(tripDb.version)||0,3);
tripDb.policy={...(tripDb.policy||{}),runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,genericBoundaryChaining:false};
tripDb.identitySource={file:identityFile,generatedAt:identity.generatedAt||'',authoritativeLinks:identity.policy?.authoritativeLinks||[]};
tripDb.records=records;
writeJson(tripsFile,tripDb);

coverage.version=Math.max(Number(coverage.version)||0,3);
coverage.generatedAt=tripDb.generatedAt||coverage.generatedAt||new Date().toISOString();
coverage.summary={...(coverage.summary||{}),throughRecords:records.length,odptAuthoritativeLinkThroughRecords:records.filter((r)=>r.identityType==='odpt-train-timetable-link').length,odptExactPublishedDestinationThroughRecords:records.filter((r)=>r.identityType==='odpt-exact-published-destination').length,odptIdentityUnresolved:unresolved.length};
coverage.odptIdentity={sourceFile:identityFile,sourceGeneratedAt:identity.generatedAt||'',sourceRecords:identities.length,addedAuthoritativeLinkRecords:exactLinkRecords,addedPublishedDestinationRecords:exactDestinationRecords,unresolved};
writeJson(coverageFile,coverage);

console.log(JSON.stringify({identityRecords:identities.length,addedAuthoritativeLinkRecords:exactLinkRecords,addedPublishedDestinationRecords:exactDestinationRecords,throughRecords:records.length,unresolved:unresolved.length},null,2));
