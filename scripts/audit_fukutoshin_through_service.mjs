#!/usr/bin/env node
import fs from 'node:fs';

const readJson=(file)=>JSON.parse(fs.readFileSync(file,'utf8'));

const F='odpt.Railway:TokyoMetro.Fukutoshin';
const TY='odpt.Railway:Tokyu.Toyoko';
const SI='odpt.Railway:Seibu.SeibuYurakucho';
const TJ='odpt.Railway:Tobu.Tojo';

const PAIRS=[
  {id:'toyoko-fukutoshin-shibuya',label:'東急東横線↔副都心線（渋谷）',a:TY,b:F},
  {id:'fukutoshin-seibuyurakucho-kotakemukaihara',label:'副都心線↔西武有楽町線（小竹向原）',a:F,b:SI},
  {id:'fukutoshin-tojo-wakoshi',label:'副都心線↔東武東上線（和光市）',a:F,b:TJ}
];

const pairKey=(a,b)=>[String(a||''),String(b||'')].sort().join('|');
const wanted=new Map(PAIRS.map((row)=>[pairKey(row.a,row.b),row]));

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

function countIdentityLink(source,targetId,relation){
  const target=byId.get(String(targetId));
  if(!target){unresolvedReferences++;return;}
  const spec=wanted.get(pairKey(source.railway,target.railway));
  if(!spec)return;
  const sourceId=String(source.timetableId||source.id||source.canonicalId||source['owl:sameAs']||'');
  const targetCanonical=String(target.timetableId||target.id||target.canonicalId||target['owl:sameAs']||targetId);
  if(!sourceId||!targetCanonical)throw new Error(`Missing timetable identity on ${spec.label}`);
  const edge=[sourceId,targetCanonical].sort().join('↔');
  sidecarSets.get(spec.id).add(edge);
  const direction=`${source.railway} -> ${target.railway}`;
  const map=sidecarDirections.get(spec.id);
  map.set(direction,(map.get(direction)||0)+1);
  if(relation!=='previous'&&relation!=='next')throw new Error('Unexpected relation');
}

for(const row of rows){
  for(const id of row.previousTrainTimetables||[])countIdentityLink(row,id,'previous');
  for(const id of row.nextTrainTimetables||[])countIdentityLink(row,id,'next');
}

function railwayFromSide(side){
  if(!side)return '';
  if(typeof side==='string')return side.includes('Railway:')?side:'';
  return String(side.railway||side.railwayId||side['odpt:railway']||'');
}
function recordRailways(row){
  return [
    String(row.fromRailway||railwayFromSide(row.from)||''),
    String(row.toRailway||railwayFromSide(row.to)||'')
  ];
}
function evidenceType(row){return String(row.identityType||row.evidenceType||row.evidence?.type||'');}

const generatedSets=new Map(PAIRS.map((row)=>[row.id,new Set()]));
let weakExactBoundaryRecords=0;
for(const row of through.records||[]){
  const [a,b]=recordRailways(row);
  const spec=wanted.get(pairKey(a,b));
  if(!spec)continue;
  const exact=evidenceType(row)==='odpt-train-timetable-link';
  if(!exact){
    // Destination/service-family records may describe a service pattern, but
    // they are not counted as proof that two timetable fragments are one train.
    continue;
  }
  if(row.status!=='verified')throw new Error(`Non-verified exact identity record on ${spec.label}`);
  const required=row.runtimeRule?.requiredMatch||[];
  for(const field of ['identityKey','fromRailway','toRailway']){
    if(!required.includes(field))throw new Error(`Exact identity record lacks ${field} runtime guard on ${spec.label}`);
  }
  const source=String(row.sourceTimetableId||row.from?.timetableId||row.fromTimetableId||'');
  const target=String(row.targetTimetableId||row.to?.timetableId||row.toTimetableId||'');
  const identity=String(row.identityKey||row.id||`${source}↔${target}`);
  generatedSets.get(spec.id).add(identity);
  if(!source||!target)weakExactBoundaryRecords++;
}

const boundaryById=new Map((boundaries.boundaries||[]).map((row)=>[row.id,row]));
const summary={
  identityRecords:rows.length,
  unresolvedIdentityReferences:unresolvedReferences,
  generatedThroughRecords:(through.records||[]).length,
  weakExactBoundaryRecords,
  boundaries:{}
};

for(const spec of PAIRS){
  const boundary=boundaryById.get(spec.id);
  if(!boundary)throw new Error(`Missing boundary: ${spec.id}`);
  if(boundary.status!=='verified'||boundary.bidirectional!==true)throw new Error(`Boundary is not verified bidirectional: ${spec.id}`);
  if(!boundary.source)throw new Error(`Verified boundary has no official source: ${spec.id}`);
  const sidecar=sidecarSets.get(spec.id);
  const generated=generatedSets.get(spec.id);
  if(sidecar.size<1)throw new Error(`No authoritative ODPT timetable identity link found for ${spec.label}`);
  if(generated.size<1)throw new Error(`No generated exact through-service identity found for ${spec.label}`);
  summary.boundaries[spec.id]={
    label:spec.label,
    authoritativeSidecarLinks:sidecar.size,
    generatedExactThroughRecords:generated.size,
    observedReferenceDirections:Object.fromEntries([...sidecarDirections.get(spec.id).entries()].sort())
  };
}

if(weakExactBoundaryRecords!==0)throw new Error(`Exact Fukutoshin boundary records without source/target timetable IDs: ${weakExactBoundaryRecords}`);

console.log('Fukutoshin exact through-service audit passed');
console.log(JSON.stringify(summary,null,2));
