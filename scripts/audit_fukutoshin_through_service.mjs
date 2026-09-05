#!/usr/bin/env node
import fs from 'node:fs';

const readJson=(file)=>JSON.parse(fs.readFileSync(file,'utf8'));

const F='odpt.Railway:TokyoMetro.Fukutoshin';
const TY='odpt.Railway:Tokyu.Toyoko';
const SI='odpt.Railway:Seibu.SeibuYurakucho';
const TJ='odpt.Railway:Tobu.Tojo';

const PAIRS=[
  {id:'toyoko-fukutoshin-shibuya',label:'東急東横線↔副都心線（渋谷）',a:TY,b:F,destinationPrefixes:['odpt.Station:Tokyu.Toyoko.','odpt.Station:TokyoMetro.Fukutoshin.']},
  {id:'fukutoshin-seibuyurakucho-kotakemukaihara',label:'副都心線↔西武有楽町線（小竹向原）',a:F,b:SI,destinationPrefixes:['odpt.Station:Seibu.','odpt.Station:TokyoMetro.Fukutoshin.']},
  {id:'fukutoshin-tojo-wakoshi',label:'副都心線↔東武東上線（和光市）',a:F,b:TJ,destinationPrefixes:['odpt.Station:Tobu.Tojo.','odpt.Station:TokyoMetro.Fukutoshin.']}
];

const pairKey=(a,b)=>[String(a||''),String(b||'')].sort().join('|');
const wanted=new Map(PAIRS.map((row)=>[pairKey(row.a,row.b),row]));
const timetableIdentity=(row)=>String(row?.timetableId||row?.id||row?.canonicalId||row?.['owl:sameAs']||'');

const identities=readJson('data/transit/odpt-train-identities.json');
const through=readJson('data/transit/through-service-trips.json');
const boundaries=readJson('data/transit/through-service-boundaries.json');

if(identities?.policy?.runtimeInference!==false)throw new Error('Identity sidecar must forbid runtime inference');
if(identities?.policy?.timeGapMayEstablishTrainIdentity!==false)throw new Error('Identity sidecar must forbid time-gap identity inference');
if(identities?.policy?.trainNumberMayEstablishTrainIdentity!==false)throw new Error('Identity sidecar must forbid train-number identity inference');

const rows=Array.isArray(identities.records)?identities.records:[];
const byId=new Map();
for(const row of rows){
  const ids=[row.timetableId,row.id,row.canonicalId,row['owl:sameAs']].filter(Boolean);
  for(const id of ids)byId.set(String(id),row);
}

const sidecarSets=new Map(PAIRS.map((row)=>[row.id,new Set()]));
const sidecarDirections=new Map(PAIRS.map((row)=>[row.id,new Map()]));
let unresolvedReferences=0;

function countIdentityLink(source,targetId){
  const target=byId.get(String(targetId));
  if(!target){unresolvedReferences++;return;}
  const spec=wanted.get(pairKey(source.railway,target.railway));
  if(!spec)return;
  const sourceId=timetableIdentity(source);
  const targetCanonical=timetableIdentity(target)||String(targetId);
  if(!sourceId||!targetCanonical)throw new Error(`Missing timetable identity on ${spec.label}`);
  sidecarSets.get(spec.id).add([sourceId,targetCanonical].sort().join('↔'));
  const direction=`${source.railway} -> ${target.railway}`;
  const map=sidecarDirections.get(spec.id);
  map.set(direction,(map.get(direction)||0)+1);
}

for(const row of rows){
  for(const id of row.previousTrainTimetables||[])countIdentityLink(row,id);
  for(const id of row.nextTrainTimetables||[])countIdentityLink(row,id);
}

function railwayFromSide(side){
  if(!side)return '';
  if(typeof side==='string')return side.includes('Railway:')?side:'';
  return String(side.railway||side.railwayId||side['odpt:railway']||'');
}
function recordRailways(row){
  return [String(row.fromRailway||railwayFromSide(row.from)||''),String(row.toRailway||railwayFromSide(row.to)||'')];
}
function evidenceType(row){return String(row.identityType||row.evidenceType||row.evidence?.type||'');}

const generatedSets=new Map(PAIRS.map((row)=>[row.id,new Set()]));
let weakExactBoundaryRecords=0;
for(const row of through.records||[]){
  const [a,b]=recordRailways(row);
  const spec=wanted.get(pairKey(a,b));
  if(!spec||evidenceType(row)!=='odpt-train-timetable-link')continue;
  if(row.status!=='verified')throw new Error(`Non-verified exact identity record on ${spec.label}`);
  const required=row.runtimeRule?.requiredMatch||[];
  for(const field of ['identityKey','fromRailway','toRailway']){
    if(!required.includes(field))throw new Error(`Exact identity record lacks ${field} runtime guard on ${spec.label}`);
  }
  const source=String(row.sourceTimetableId||row.from?.timetableId||row.fromTimetableId||'');
  const target=String(row.targetTimetableId||row.to?.timetableId||row.toTimetableId||'');
  generatedSets.get(spec.id).add(String(row.identityKey||row.id||`${source}↔${target}`));
  if(!source||!target)weakExactBoundaryRecords++;
}

function sharedTrainIds(a,b){
  const first=new Set(rows.filter((row)=>row.railway===a&&row.trainId).map((row)=>String(row.trainId)));
  const second=new Set(rows.filter((row)=>row.railway===b&&row.trainId).map((row)=>String(row.trainId)));
  return [...first].filter((id)=>second.has(id));
}
function externalDestinationRows(spec){
  const relevant=rows.filter((row)=>row.railway===spec.a||row.railway===spec.b);
  let count=0;
  const samples=[];
  for(const row of relevant){
    const destinations=Array.isArray(row.destination)?row.destination:[row.destination].filter(Boolean);
    const external=destinations.some((destination)=>spec.destinationPrefixes.some((prefix)=>String(destination).startsWith(prefix)));
    if(!external)continue;
    count++;
    if(samples.length<3)samples.push({railway:row.railway,timetableId:timetableIdentity(row),trainId:String(row.trainId||''),trainNumber:String(row.trainNumber||''),destination:destinations});
  }
  return {count,samples};
}
function generatedMentions(spec){
  let destinationEvidence=0;
  const samples=[];
  for(const row of through.records||[]){
    const text=JSON.stringify(row);
    if(!text.includes(spec.a)||!text.includes(spec.b))continue;
    if(evidenceType(row)==='odpt-exact-published-destination')destinationEvidence++;
    if(samples.length<2)samples.push(row);
  }
  return {destinationEvidence,samples};
}

const boundaryById=new Map((boundaries.boundaries||[]).map((row)=>[row.id,row]));
const summary={identityRecords:rows.length,unresolvedIdentityReferences:unresolvedReferences,generatedThroughRecords:(through.records||[]).length,weakExactBoundaryRecords,boundaries:{}};
const missing=[];

for(const spec of PAIRS){
  const boundary=boundaryById.get(spec.id);
  if(!boundary)throw new Error(`Missing boundary: ${spec.id}`);
  if(boundary.status!=='verified'||boundary.bidirectional!==true)throw new Error(`Boundary is not verified bidirectional: ${spec.id}`);
  if(!boundary.source)throw new Error(`Verified boundary has no official source: ${spec.id}`);
  const sidecar=sidecarSets.get(spec.id);
  const generated=generatedSets.get(spec.id);
  const shared=sharedTrainIds(spec.a,spec.b);
  const destinations=externalDestinationRows(spec);
  const generatedDiagnostic=generatedMentions(spec);
  summary.boundaries[spec.id]={
    label:spec.label,
    authoritativeSidecarLinks:sidecar.size,
    generatedExactThroughRecords:generated.size,
    sharedNonemptyTrainIds:shared.length,
    externalDestinationIdentityRows:destinations.count,
    generatedPublishedDestinationRecordsMentioningPair:generatedDiagnostic.destinationEvidence,
    observedReferenceDirections:Object.fromEntries([...sidecarDirections.get(spec.id).entries()].sort()),
    externalDestinationSamples:destinations.samples,
    generatedRecordSamples:generatedDiagnostic.samples
  };
  if(sidecar.size<1||generated.size<1)missing.push(spec.label);
}

console.log('Fukutoshin through-service identity evidence audit');
console.log(JSON.stringify(summary,null,2));
if(weakExactBoundaryRecords!==0)throw new Error(`Exact Fukutoshin boundary records without source/target timetable IDs: ${weakExactBoundaryRecords}`);
if(missing.length)throw new Error(`Authoritative timetable-fragment identity is still missing for: ${missing.join(' / ')}`);
console.log('Fukutoshin exact through-service audit passed');
