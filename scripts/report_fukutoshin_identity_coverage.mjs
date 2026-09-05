#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const root=process.cwd();
const readJson=(file)=>JSON.parse(fs.readFileSync(path.join(root,file),'utf8'));
const writeJson=(file,value)=>{
  const target=path.join(root,file);
  fs.mkdirSync(path.dirname(target),{recursive:true});
  fs.writeFileSync(target,JSON.stringify(value,null,2)+'\n','utf8');
};

const MM='manual.Railway:YokohamaMinatomirai.Minatomirai';
const TY='odpt.Railway:Tokyu.Toyoko';
const TSH='odpt.Railway:Tokyu.TokyuShinYokohama';
const SSH='odpt.Railway:Sotetsu.SotetsuShinYokohama';
const SM='odpt.Railway:Sotetsu.Main';
const SIZ='odpt.Railway:Sotetsu.Izumino';
const F='odpt.Railway:TokyoMetro.Fukutoshin';
const SY='odpt.Railway:Seibu.SeibuYurakucho';
const SI='odpt.Railway:Seibu.Ikebukuro';
const TJ='odpt.Railway:Tobu.Tojo';

const PAIRS=[
  {id:'minatomirai-toyoko-yokohama',label:'みなとみらい線↔東急東横線（横浜）',a:MM,b:TY},
  {id:'toyoko-tokyushinyokohama-hiyoshi',label:'東急東横線↔東急新横浜線（日吉）',a:TY,b:TSH},
  {id:'tokyushinyokohama-sotetsushinyokohama-shinyokohama',label:'東急新横浜線↔相鉄新横浜線（新横浜）',a:TSH,b:SSH},
  {id:'sotetsushinyokohama-main-nishiya',label:'相鉄新横浜線↔相鉄本線（西谷）',a:SSH,b:SM},
  {id:'sotetsu-main-izumino-futamatagawa',label:'相鉄本線↔相鉄いずみ野線（二俣川）',a:SM,b:SIZ},
  {id:'toyoko-fukutoshin-shibuya',label:'東急東横線↔副都心線（渋谷）',a:TY,b:F},
  {id:'fukutoshin-seibuyurakucho-kotakemukaihara',label:'副都心線↔西武有楽町線（小竹向原）',a:F,b:SY},
  {id:'fukutoshin-tojo-wakoshi',label:'副都心線↔東武東上線（和光市）',a:F,b:TJ},
];
const pairKey=(a,b)=>[String(a||''),String(b||'')].sort().join('|');
const wanted=new Map(PAIRS.map((row)=>[pairKey(row.a,row.b),row]));

const manifest=readJson('data/transit/manifest.json');
const identities=readJson('data/transit/odpt-train-identities.json');
const through=readJson('data/transit/through-service-trips.json');
const boundaries=readJson('data/transit/through-service-boundaries.json');

for(const [name,policy] of [['identity',identities.policy],['through',through.policy]]){
  if(policy?.runtimeInference!==false)throw new Error(`${name}: runtime inference must be disabled`);
  if(policy?.timeGapMayEstablishTrainIdentity!==false)throw new Error(`${name}: time-gap identity inference must be disabled`);
}
if(identities.policy?.trainNumberMayEstablishTrainIdentity!==false)throw new Error('train-number identity inference must be disabled');

const rows=Array.isArray(identities.records)?identities.records:[];
const byTimetable=new Map(rows.map((row)=>[String(row.timetableId||''),row]).filter(([id])=>id));
const railwayCounts={};
for(const row of rows){
  const railway=String(row.railway||'');
  if(railway)railwayCounts[railway]=(railwayCounts[railway]||0)+1;
}

function railwayFromTimetableId(id){
  const text=String(id||'');
  const prefix='odpt.TrainTimetable:';
  if(!text.startsWith(prefix))return '';
  const parts=text.slice(prefix.length).split('.');
  if(parts.length<2)return '';
  return `odpt.Railway:${parts[0]}.${parts[1]}`;
}

const pairStats=new Map(PAIRS.map((row)=>[row.id,{
  ...row,
  resolvedOdptLinks:new Set(),
  unresolvedOdptReferences:new Set(),
  referenceDirections:{},
  officialSingleTrainPageEvidence:new Set(),
  generatedExactRecords:new Set(),
  generatedPublishedDestinationRecords:new Set(),
}]));

function noteDirection(stats,a,b){
  const key=`${a} -> ${b}`;
  stats.referenceDirections[key]=(stats.referenceDirections[key]||0)+1;
}

function inspectReference(source,targetId){
  const sourceRailway=String(source.railway||'');
  const target=byTimetable.get(String(targetId||''));
  const targetRailway=target?String(target.railway||''):railwayFromTimetableId(targetId);
  const spec=wanted.get(pairKey(sourceRailway,targetRailway));
  if(!spec)return;
  const stats=pairStats.get(spec.id);
  const sourceId=String(source.timetableId||'');
  const signature=[sourceId,String(targetId||'')].sort().join('↔');
  if(target)stats.resolvedOdptLinks.add(signature);
  else stats.unresolvedOdptReferences.add(signature);
  noteDirection(stats,sourceRailway,targetRailway);
}

for(const row of rows){
  for(const id of row.previousTrainTimetables||[])inspectReference(row,id);
  for(const id of row.nextTrainTimetables||[])inspectReference(row,id);
}

function adjacentPair(route,a,b){
  for(let i=0;i+1<route.length;i++)if(pairKey(route[i],route[i+1])===pairKey(a,b))return true;
  return false;
}

for(const record of through.records||[]){
  const route=Array.isArray(record.routeRailways)?record.routeRailways:[];
  for(const spec of PAIRS){
    if(!adjacentPair(route,spec.a,spec.b))continue;
    const stats=pairStats.get(spec.id);
    const type=String(record.identityType||record.evidenceType||'');
    const id=String(record.identityKey||record.id||JSON.stringify(record));
    if(type==='odpt-train-timetable-link'||type==='train-timetable-network'||type==='official-single-train-page')stats.generatedExactRecords.add(id);
    if(type==='official-single-train-page'&&record.status==='verified'&&record.sourceUrl)stats.officialSingleTrainPageEvidence.add(id);
    if(type==='odpt-exact-published-destination'||type==='published-destination')stats.generatedPublishedDestinationRecords.add(id);
  }
}

const boundaryById=new Map((boundaries.boundaries||[]).map((row)=>[row.id,row]));
const operatorByRailway={};
for(const [slug,meta] of Object.entries(manifest.operators||{})){
  const operator=String(meta?.operator||'');
  if(!operator)continue;
  const entityFile=path.join(root,'data/transit',slug,'entities.json');
  if(!fs.existsSync(entityFile))continue;
  let entities={};
  try{entities=JSON.parse(fs.readFileSync(entityFile,'utf8'));}catch{continue;}
  for(const railway of entities.Railway||[]){
    const id=String(railway?.['owl:sameAs']||'');
    if(id)operatorByRailway[id]={slug,label:String(meta.label||slug),operator,timetableStatus:String(meta.timetableStatus||''),trainTimetables:Number(meta.trainTimetables||0)};
  }
}

const resultPairs=[];
for(const spec of PAIRS){
  const stats=pairStats.get(spec.id);
  const boundary=boundaryById.get(spec.id)||null;
  const odptResolved=stats.resolvedOdptLinks.size;
  const odptUnresolved=stats.unresolvedOdptReferences.size;
  const official=stats.officialSingleTrainPageEvidence.size;
  const authoritativeExact=odptResolved+official;
  const generated=stats.generatedExactRecords.size;
  resultPairs.push({
    id:spec.id,
    label:spec.label,
    fromRailway:spec.a,
    toRailway:spec.b,
    boundaryStatus:String(boundary?.status||'missing'),
    boundarySource:String(boundary?.source||''),
    authoritativeResolvedLinks:odptResolved,
    authoritativeUnresolvedReferences:odptUnresolved,
    officialSingleTrainPageEvidence:official,
    authoritativeExactEvidence:authoritativeExact,
    generatedExactThroughRecords:generated,
    generatedPublishedDestinationRecords:stats.generatedPublishedDestinationRecords.size,
    referenceDirections:stats.referenceDirections,
    exactIdentityReady:authoritativeExact>0&&generated>0,
    sourceA:operatorByRailway[spec.a]||null,
    sourceB:operatorByRailway[spec.b]||null,
  });
}

const importantRailways=[MM,TY,TSH,SSH,SM,SIZ,F,SY,SI,TJ];
const report={
  version:3,
  generatedAt:new Date().toISOString(),
  system:'Fukutoshin Line / former Line 13 through-service corridor including Minatomirai and Sotetsu branches',
  policy:{
    runtimeInference:false,
    timeGapMayEstablishTrainIdentity:false,
    trainNumberMayEstablishTrainIdentity:false,
    publishedDestinationAloneMayEstablishIdentity:false,
    singlePublishedOneTrainPageWithAdjacentBoundaryStopsMayEstablishIdentity:true,
  },
  sourceIdentityRecords:rows.length,
  relevantIdentityRecords:Object.fromEntries(importantRailways.map((id)=>[id,railwayCounts[id]||0])),
  pairs:resultPairs,
  summary:{
    boundaryPairs:resultPairs.length,
    verifiedBoundaries:resultPairs.filter((row)=>row.boundaryStatus==='verified').length,
    exactIdentityReadyPairs:resultPairs.filter((row)=>row.exactIdentityReady).length,
    resolvedAuthoritativeLinks:resultPairs.reduce((sum,row)=>sum+row.authoritativeResolvedLinks,0),
    unresolvedAuthoritativeReferences:resultPairs.reduce((sum,row)=>sum+row.authoritativeUnresolvedReferences,0),
    officialSingleTrainPageEvidence:resultPairs.reduce((sum,row)=>sum+row.officialSingleTrainPageEvidence,0),
    authoritativeExactEvidence:resultPairs.reduce((sum,row)=>sum+row.authoritativeExactEvidence,0),
    generatedExactThroughRecords:resultPairs.reduce((sum,row)=>sum+row.generatedExactThroughRecords,0),
    complete:resultPairs.every((row)=>row.boundaryStatus==='verified'&&row.exactIdentityReady),
  },
};

writeJson('data/transit/fukutoshin/identity-coverage-report.json',report);
console.log(JSON.stringify(report.summary,null,2));
for(const row of resultPairs){
  console.log(`${row.label}: boundary=${row.boundaryStatus} odpt=${row.authoritativeResolvedLinks} unresolved=${row.authoritativeUnresolvedReferences} officialPage=${row.officialSingleTrainPageEvidence} generated=${row.generatedExactThroughRecords} ready=${row.exactIdentityReady}`);
}
