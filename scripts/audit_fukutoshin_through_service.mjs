#!/usr/bin/env node
import fs from 'node:fs';

const readJson=(file)=>JSON.parse(fs.readFileSync(file,'utf8'));
const MM='manual.Railway:YokohamaMinatomirai.Minatomirai';
const TY='odpt.Railway:Tokyu.Toyoko';
const TSH='odpt.Railway:Tokyu.TokyuShinYokohama';
const SSH='odpt.Railway:Sotetsu.SotetsuShinYokohama';
const SM='odpt.Railway:Sotetsu.Main';
const SIZ='odpt.Railway:Sotetsu.Izumino';
const F='odpt.Railway:TokyoMetro.Fukutoshin';
const SI='odpt.Railway:Seibu.SeibuYurakucho';
const TJ='odpt.Railway:Tobu.Tojo';

const PAIRS=[
  {id:'minatomirai-toyoko-yokohama',label:'みなとみらい線↔東急東横線（横浜）',a:MM,b:TY,patterns:[['反町','横浜','新高島'],['新高島','横浜','反町']]},
  {id:'toyoko-tokyushinyokohama-hiyoshi',label:'東急東横線↔東急新横浜線（日吉）',a:TY,b:TSH,patterns:[['自由が丘','日吉','新綱島'],['新綱島','日吉','自由が丘']]},
  {id:'tokyushinyokohama-sotetsushinyokohama-shinyokohama',label:'東急新横浜線↔相鉄新横浜線（新横浜）',a:TSH,b:SSH,patterns:[['新綱島','新横浜','羽沢横浜国大'],['羽沢横浜国大','新横浜','新綱島']]},
  {id:'sotetsushinyokohama-main-nishiya',label:'相鉄新横浜線↔相鉄本線（西谷）',a:SSH,b:SM,patterns:[]},
  {id:'sotetsu-main-izumino-futamatagawa',label:'相鉄本線↔相鉄いずみ野線（二俣川）',a:SM,b:SIZ,patterns:[]},
  {id:'toyoko-fukutoshin-shibuya',label:'東急東横線↔副都心線（渋谷）',a:TY,b:F,patterns:[['明治神宮前','渋谷','代官山'],['代官山','渋谷','明治神宮前']]},
  {id:'fukutoshin-seibuyurakucho-kotakemukaihara',label:'副都心線↔西武有楽町線（小竹向原）',a:F,b:SI,patterns:[['新桜台','小竹向原','千川'],['千川','小竹向原','新桜台']]},
  {id:'fukutoshin-tojo-wakoshi',label:'副都心線↔東武東上線（和光市）',a:F,b:TJ,patterns:[]},
];
const pairKey=(a,b)=>[String(a||''),String(b||'')].sort().join('|');
const wanted=new Map(PAIRS.map((row)=>[pairKey(row.a,row.b),row]));
const identities=readJson('data/transit/odpt-train-identities.json');
const through=readJson('data/transit/through-service-trips.json');
const boundaries=readJson('data/transit/through-service-boundaries.json');

if(identities?.policy?.runtimeInference!==false)throw new Error('Identity sidecar must forbid runtime inference');
if(identities?.policy?.timeGapMayEstablishTrainIdentity!==false)throw new Error('Identity sidecar must forbid time-gap identity inference');
if(identities?.policy?.trainNumberMayEstablishTrainIdentity!==false)throw new Error('Identity sidecar must forbid train-number identity inference');
if(through?.policy?.runtimeInference!==false||through?.policy?.timeGapMayEstablishTrainIdentity!==false||through?.policy?.trainNumberMayEstablishTrainIdentity!==false)throw new Error('Generated DB must preserve strict train identity policy');

const rows=Array.isArray(identities.records)?identities.records:[];
const byId=new Map();
for(const row of rows)for(const id of [row.timetableId,row.id,row.canonicalId,row['owl:sameAs']].filter(Boolean))byId.set(String(id),row);
const odptLinks=new Map(PAIRS.map((row)=>[row.id,new Set()]));
for(const source of rows){
  for(const targetId of [...(source.previousTrainTimetables||[]),...(source.nextTrainTimetables||[])]){
    const target=byId.get(String(targetId));
    if(!target)continue;
    const spec=wanted.get(pairKey(source.railway,target.railway));
    if(!spec)continue;
    const sourceId=String(source.timetableId||source.id||'');
    const targetCanonical=String(target.timetableId||target.id||targetId);
    if(sourceId&&targetCanonical)odptLinks.get(spec.id).add([sourceId,targetCanonical].sort().join('↔'));
  }
}

function recordMentionsPair(row,spec){
  const route=Array.isArray(row.routeRailways)?row.routeRailways:[];
  for(let i=0;i+1<route.length;i++)if(pairKey(route[i],route[i+1])===pairKey(spec.a,spec.b))return true;
  return pairKey(row.fromRailway,row.toRailway)===pairKey(spec.a,spec.b);
}
const exactType=(row)=>String(row.identityType||row.evidenceType||'');
const samePattern=(value,patterns)=>patterns.some((pattern)=>Array.isArray(value)&&value.length===pattern.length&&pattern.every((name,i)=>String(value[i])===name));

const generated=new Map(PAIRS.map((row)=>[row.id,new Set()]));
const officialEvidence=new Map(PAIRS.map((row)=>[row.id,new Set()]));
for(const row of through.records||[]){
  const type=exactType(row);
  if(!['odpt-train-timetable-link','train-timetable-network','official-single-train-page','official-same-printed-column'].includes(type))continue;
  for(const spec of PAIRS){
    if(!recordMentionsPair(row,spec))continue;
    const id=String(row.identityKey||row.id||'');
    if(!id)throw new Error(`Exact record lacks identity key on ${spec.label}`);
    if(type==='official-single-train-page'){
      if(row.status!=='verified'||String(row.canonicalBoundaryId||'')!==spec.id)continue;
      if(!String(row.sourceUrl||'').startsWith('https://'))throw new Error(`Official page record lacks source URL on ${spec.label}`);
      for(const key of ['tx','sf','date','time','dw'])if(!String(row.sourceParameters?.[key]??''))throw new Error(`Official page record lacks ${key} on ${spec.label}`);
      if(spec.patterns.length&&!samePattern(row.publishedBoundaryStops,spec.patterns))throw new Error(`Official page record lacks exact adjacent boundary stops on ${spec.label}`);
      const required=row.runtimeRule?.requiredMatch||[];
      for(const field of ['identityKey','fromRailway','toRailway'])if(!required.includes(field))throw new Error(`Official page record lacks ${field} runtime guard on ${spec.label}`);
      officialEvidence.get(spec.id).add(id);
    }else if(type==='official-same-printed-column'){
      if(row.status!=='verified'||String(row.canonicalBoundaryId||'')!==spec.id)continue;
      if(!String(row.sourceUrl||'').startsWith('https://cdn.sotetsu.co.jp/'))throw new Error(`Unexpected official column source on ${spec.label}`);
      if(!Number.isInteger(Number(row.pdfPage))||Number(row.pdfPage)<2)throw new Error(`Official column record lacks PDF page on ${spec.label}`);
      if(!(Number(row.columnX)>0))throw new Error(`Official column record lacks column X on ${spec.label}`);
      if(spec.patterns.length&&!samePattern(row.publishedBoundaryStops,spec.patterns))throw new Error(`Official column record lacks exact boundary pattern on ${spec.label}`);
      if(row.matchPolicy?.officialSamePrintedColumnRequired!==true||row.matchPolicy?.exactPrintedStationTimesRequired!==true)throw new Error(`Official column record lacks strict same-column requirements on ${spec.label}`);
      if(row.matchPolicy?.timeProximityAloneMayEstablishIdentity!==false||row.matchPolicy?.trainNumberAloneMayEstablishIdentity!==false||row.matchPolicy?.destinationAloneMayEstablishIdentity!==false)throw new Error(`Official column record weakens identity policy on ${spec.label}`);
      const required=row.runtimeRule?.requiredMatch||[];
      for(const field of ['identityKey','fromRailway','toRailway'])if(!required.includes(field))throw new Error(`Official column record lacks ${field} runtime guard on ${spec.label}`);
      officialEvidence.get(spec.id).add(id);
    }else if(type==='odpt-train-timetable-link'){
      if(!String(row.sourceTimetableId||'')||!String(row.targetTimetableId||''))throw new Error(`ODPT exact record lacks source/target timetable ids on ${spec.label}`);
    }
    generated.get(spec.id).add(id);
  }
}

const boundaryById=new Map((boundaries.boundaries||[]).map((row)=>[row.id,row]));
const summary={identityRecords:rows.length,generatedThroughRecords:(through.records||[]).length,boundaries:{}};
const missing=[];
for(const spec of PAIRS){
  const boundary=boundaryById.get(spec.id);
  if(!boundary)throw new Error(`Missing boundary: ${spec.id}`);
  if(boundary.status!=='verified'||boundary.bidirectional!==true)throw new Error(`Boundary is not verified bidirectional: ${spec.id}`);
  if(!boundary.source)throw new Error(`Verified boundary has no official source: ${spec.id}`);
  const odpt=odptLinks.get(spec.id).size;
  const official=officialEvidence.get(spec.id).size;
  const exact=generated.get(spec.id).size;
  const authoritative=odpt+official;
  summary.boundaries[spec.id]={label:spec.label,authoritativeOdptLinks:odpt,officialExactEvidence:official,authoritativeExactEvidence:authoritative,generatedExactThroughRecords:exact};
  if(authoritative<1||exact<1)missing.push(spec.label);
}

console.log('Fukutoshin through-service identity evidence audit');
console.log(JSON.stringify(summary,null,2));
if(missing.length)throw new Error(`Authoritative exact same-train identity is still missing for: ${missing.join(' / ')}`);
console.log('Fukutoshin exact through-service audit passed for all eight corridor boundaries');
