#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const root=process.cwd();
const readJson=(file)=>JSON.parse(fs.readFileSync(path.join(root,file),'utf8'));
const writeJson=(file,value)=>{const target=path.join(root,file);fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,JSON.stringify(value,null,2)+'\n','utf8');};

const MM='manual.Railway:YokohamaMinatomirai.Minatomirai';
const TY='odpt.Railway:Tokyu.Toyoko';
const TSH='odpt.Railway:Tokyu.TokyuShinYokohama';
const SSH='odpt.Railway:Sotetsu.SotetsuShinYokohama';
const SM='odpt.Railway:Sotetsu.Main';
const SIZ='odpt.Railway:Sotetsu.Izumino';
const F='odpt.Railway:TokyoMetro.Fukutoshin';
const Y='odpt.Railway:TokyoMetro.Yurakucho';
const SY='odpt.Railway:Seibu.SeibuYurakucho';
const SI='odpt.Railway:Seibu.Ikebukuro';
const SC='odpt.Railway:Seibu.SeibuChichibu';
const TJ='odpt.Railway:Tobu.Tojo';

const LINE13=[
  {id:'minatomirai-toyoko-yokohama',label:'みなとみらい線↔東急東横線（横浜）',a:MM,b:TY},
  {id:'toyoko-tokyushinyokohama-hiyoshi',label:'東急東横線↔東急新横浜線（日吉）',a:TY,b:TSH},
  {id:'tokyushinyokohama-sotetsushinyokohama-shinyokohama',label:'東急新横浜線↔相鉄新横浜線（新横浜）',a:TSH,b:SSH},
  {id:'sotetsushinyokohama-main-nishiya',label:'相鉄新横浜線↔相鉄本線（西谷）',a:SSH,b:SM},
  {id:'sotetsu-main-izumino-futamatagawa',label:'相鉄本線↔相鉄いずみ野線（二俣川）',a:SM,b:SIZ},
  {id:'toyoko-fukutoshin-shibuya',label:'東急東横線↔副都心線（渋谷）',a:TY,b:F},
  {id:'fukutoshin-seibuyurakucho-kotakemukaihara',label:'副都心線↔西武有楽町線（小竹向原）',a:F,b:SY},
  {id:'seibuyurakucho-ikebukuro-nerima',label:'西武有楽町線↔西武池袋線（練馬）',a:SY,b:SI,requiredCorridor:'line13'},
  {id:'seibu-ikebukuro-seibuchichibu-agano',label:'西武池袋線↔西武秩父線（吾野/S-TRAIN）',a:SI,b:SC,requiredCorridor:'line13'},
  {id:'fukutoshin-tojo-wakoshi',label:'副都心線↔東武東上線（和光市）',a:F,b:TJ},
];
const LINE8=[
  {id:'yurakucho-seibuyurakucho-kotakemukaihara',label:'有楽町線↔西武有楽町線（小竹向原）',a:Y,b:SY,requiredCorridor:'line8'},
  {id:'seibuyurakucho-ikebukuro-nerima',label:'西武有楽町線↔西武池袋線（練馬）',a:SY,b:SI,requiredCorridor:'line8'},
  {id:'yurakucho-tojo-wakoshi',label:'有楽町線↔東武東上線（和光市）',a:Y,b:TJ,requiredCorridor:'line8'},
];
const exactTypes=new Set(['odpt-train-timetable-link','train-timetable-network','official-single-train-page','official-same-printed-column','odpt-explicit-boundary-endpoint']);
const identities=readJson('data/transit/odpt-train-identities.json');
const through=readJson('data/transit/through-service-trips.json');
const boundaries=readJson('data/transit/through-service-boundaries.json');
if(identities.policy?.runtimeInference!==false||identities.policy?.timeGapMayEstablishTrainIdentity!==false||identities.policy?.trainNumberMayEstablishTrainIdentity!==false)throw new Error('Identity sidecar must remain fail-closed');
if(through.policy?.runtimeInference!==false||through.policy?.timeGapMayEstablishTrainIdentity!==false||through.policy?.trainNumberMayEstablishTrainIdentity!==false||through.policy?.genericBoundaryChaining!==false)throw new Error('Through DB must remain fail-closed');

const identityRows=Array.isArray(identities.records)?identities.records:[];
const byTimetable=new Map(identityRows.map(row=>[String(row.timetableId||''),row]).filter(([id])=>id));
const boundaryById=new Map((boundaries.boundaries||[]).map(row=>[String(row.id||''),row]));
const pairKey=(a,b)=>[String(a||''),String(b||'')].sort().join('|');
function railwayFromTimetableId(id){const text=String(id||'');const prefix='odpt.TrainTimetable:';if(!text.startsWith(prefix))return '';const parts=text.slice(prefix.length).split('.');return parts.length>=2?`odpt.Railway:${parts[0]}.${parts[1]}`:'';}
function directionForPair(row,p){
  const route=Array.isArray(row.routeRailways)?row.routeRailways.map(String):[];
  for(let i=0;i+1<route.length;i++){if(route[i]===p.a&&route[i+1]===p.b)return 'ab';if(route[i]===p.b&&route[i+1]===p.a)return 'ba';}
  const from=String(row.fromRailway||''),to=String(row.toRailway||'');
  if(from===p.a&&to===p.b)return 'ab';if(from===p.b&&to===p.a)return 'ba';return '';
}
function recordEligible(row,p){if(p.requiredCorridor&&String(row.corridor||'')!==p.requiredCorridor)return false;return Boolean(directionForPair(row,p));}

function buildReport(system,pairs,version){
  const pairMap=new Map(pairs.map(p=>[pairKey(p.a,p.b),p]));
  const stats=new Map(pairs.map(p=>[p.id,{resolvedRefs:new Set(),unresolvedRefs:new Set(),generated:new Set(),official:new Set(),endpoint:new Set(),ab:0,ba:0,other:0,types:{}}]));
  function inspectRef(source,targetId){
    const sourceRailway=String(source.railway||'');const target=byTimetable.get(String(targetId||''));const targetRailway=target?String(target.railway||''):railwayFromTimetableId(targetId);
    const p=pairMap.get(pairKey(sourceRailway,targetRailway));if(!p||p.requiredCorridor)return;
    const s=stats.get(p.id);const sig=[String(source.timetableId||''),String(targetId||'')].sort().join('↔');(target?s.resolvedRefs:s.unresolvedRefs).add(sig);
  }
  for(const row of identityRows){for(const id of row.previousTrainTimetables||[])inspectRef(row,id);for(const id of row.nextTrainTimetables||[])inspectRef(row,id);}
  for(const row of through.records||[]){
    const type=String(row.identityType||row.evidenceType||'');if(!exactTypes.has(type))continue;
    for(const p of pairs){
      const explicit=String(row.canonicalBoundaryId||'')===p.id;
      const direction=recordEligible(row,p)?directionForPair(row,p):'';
      if(!direction){if(explicit&&(!p.requiredCorridor||String(row.corridor||'')===p.requiredCorridor))stats.get(p.id).other++;continue;}
      const s=stats.get(p.id);const id=String(row.identityKey||row.id||JSON.stringify(row));s.generated.add(id);s[direction]++;s.types[type]=(s.types[type]||0)+1;
      if((type==='official-single-train-page'||type==='official-same-printed-column')&&row.status==='verified')s.official.add(id);
      if(type==='odpt-explicit-boundary-endpoint'&&row.status==='verified')s.endpoint.add(id);
    }
  }
  const result=pairs.map(p=>{
    const s=stats.get(p.id);const boundary=boundaryById.get(p.id)||null;const bidirectional=s.ab>0&&s.ba>0&&s.other===0;
    const authoritativeExact=s.resolvedRefs.size+s.official.size+s.endpoint.size;
    return {id:p.id,label:p.label,fromRailway:p.a,toRailway:p.b,requiredCorridor:p.requiredCorridor||'',boundaryStatus:String(boundary?.status||'missing'),boundarySource:String(boundary?.source||''),authoritativeResolvedLinks:s.resolvedRefs.size,authoritativeUnresolvedReferences:s.unresolvedRefs.size,officialPublishedTrainEvidence:s.official.size,explicitBoundaryEndpointEvidence:s.endpoint.size,authoritativeExactEvidence:authoritativeExact,generatedExactThroughRecords:s.generated.size,directions:{ab:s.ab,ba:s.ba,other:s.other},exactBidirectional:bidirectional,exactIdentityReady:String(boundary?.status||'')==='verified'&&authoritativeExact>0&&s.generated.size>0&&bidirectional,evidenceTypes:s.types};
  });
  return {version,generatedAt:new Date().toISOString(),system,policy:{runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,publishedDestinationAloneMayEstablishIdentity:false,ambiguousMetroBranchMayEstablishLineIdentity:false,bidirectionalExactEvidenceRequired:true},sourceIdentityRecords:identityRows.length,pairs:result,summary:{boundaryPairs:result.length,verifiedBoundaries:result.filter(r=>r.boundaryStatus==='verified').length,exactIdentityReadyPairs:result.filter(r=>r.exactIdentityReady).length,resolvedAuthoritativeLinks:result.reduce((n,r)=>n+r.authoritativeResolvedLinks,0),unresolvedAuthoritativeReferences:result.reduce((n,r)=>n+r.authoritativeUnresolvedReferences,0),officialPublishedTrainEvidence:result.reduce((n,r)=>n+r.officialPublishedTrainEvidence,0),explicitBoundaryEndpointEvidence:result.reduce((n,r)=>n+r.explicitBoundaryEndpointEvidence,0),authoritativeExactEvidence:result.reduce((n,r)=>n+r.authoritativeExactEvidence,0),generatedExactThroughRecords:result.reduce((n,r)=>n+r.generatedExactThroughRecords,0),complete:result.every(r=>r.exactIdentityReady)}};
}

const line13=buildReport('Fukutoshin Line / former Line 13 full through-service corridor including Seibu Ikebukuro/Chichibu and Sotetsu branches',LINE13,5);
const line8=buildReport('Yurakucho Line / former Line 8 through-service corridor to Tobu Tojo and Seibu Yurakucho/Ikebukuro',LINE8,1);
writeJson('data/transit/fukutoshin/identity-coverage-report.json',line13);
writeJson('data/transit/line8/identity-coverage-report.json',line8);
for(const [name,report] of [['LINE13',line13],['LINE8',line8]]){console.log(name,JSON.stringify(report.summary,null,2));for(const row of report.pairs)console.log(`${name} ${row.label}: boundary=${row.boundaryStatus} exact=${row.authoritativeExactEvidence} generated=${row.generatedExactThroughRecords} directions=${row.directions.ab}/${row.directions.ba}/${row.directions.other} ready=${row.exactIdentityReady}`);}
