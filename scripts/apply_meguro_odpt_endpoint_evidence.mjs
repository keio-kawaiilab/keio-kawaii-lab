#!/usr/bin/env node
import fs from 'node:fs';
import crypto from 'node:crypto';

const identityFile='data/transit/odpt-train-identities.json',tripsFile='data/transit/through-service-trips.json',coverageFile='data/transit/through-service-coverage.json';
const read=(f)=>JSON.parse(fs.readFileSync(f,'utf8')),write=(f,v)=>fs.writeFileSync(f,JSON.stringify(v,null,2)+'\n');
const dig=(v)=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex').slice(0,24);
const N='odpt.Railway:TokyoMetro.Namboku',M='odpt.Railway:Toei.Mita',TM='odpt.Railway:Tokyu.Meguro',SR='odpt.Railway:SaitamaRailway.SaitamaRailway';
const NM='odpt.Station:TokyoMetro.Namboku.Meguro',MM='odpt.Station:Toei.Mita.Meguro',AK='odpt.Station:TokyoMetro.Namboku.AkabaneIwabuchi';
const TOKYU_PREFIXES=['odpt.Station:Tokyu.Meguro.','odpt.Station:Tokyu.TokyuShinYokohama.','odpt.Station:Sotetsu.'];const SR_PREFIX='odpt.Station:SaitamaRailway.SaitamaRailway.';
const arr=(v)=>Array.isArray(v)?v.map(String):[],station=(x)=>String(x?.station||'');
const external=(r,prefixes,field)=>arr(r[field]).filter(x=>prefixes.some(p=>x.startsWith(p)));
const identities=read(identityFile),trips=read(tripsFile),coverage=read(coverageFile);
if(identities?.policy?.runtimeInference!==false||identities?.policy?.timeGapMayEstablishTrainIdentity!==false||identities?.policy?.trainNumberMayEstablishTrainIdentity!==false)throw new Error('Identity sidecar must remain fail-closed');
const rows=identities.records||[],out=[],counts={meguroNamboku:{tokyuToNamboku:0,nambokuToTokyu:0},meguroMita:{tokyuToMita:0,mitaToTokyu:0},nambokuSaitama:{saitamaToNamboku:0,nambokuToSaitama:0}};
function push(row,boundary,fromRailway,toRailway,boundaryEndpoint,endpointRole,externalStations,direction){out.push({row,boundary,fromRailway,toRailway,boundaryEndpoint,endpointRole,externalStations,direction});}
for(const r of rows){
 if(r.railway===N){
  const first=station(r.firstStop),last=station(r.lastStop),origTok=external(r,TOKYU_PREFIXES,'origin'),destTok=external(r,TOKYU_PREFIXES,'destination'),origSR=arr(r.origin).filter(x=>x.startsWith(SR_PREFIX)),destSR=arr(r.destination).filter(x=>x.startsWith(SR_PREFIX));
  if(first===NM&&origTok.length){push(r,'meguro-namboku-meguro',TM,N,NM,'firstStop',origTok,'tokyu-to-namboku');counts.meguroNamboku.tokyuToNamboku++;}
  if(last===NM&&destTok.length){push(r,'meguro-namboku-meguro',N,TM,NM,'lastStop',destTok,'namboku-to-tokyu');counts.meguroNamboku.nambokuToTokyu++;}
  if(first===AK&&origSR.length){push(r,'namboku-saitamarailway-akabaneiwabuchi',SR,N,AK,'firstStop',origSR,'saitama-to-namboku');counts.nambokuSaitama.saitamaToNamboku++;}
  if(last===AK&&destSR.length){push(r,'namboku-saitamarailway-akabaneiwabuchi',N,SR,AK,'lastStop',destSR,'namboku-to-saitama');counts.nambokuSaitama.nambokuToSaitama++;}
 }
 if(r.railway===M){
  const first=station(r.firstStop),last=station(r.lastStop),origTok=external(r,TOKYU_PREFIXES,'origin'),destTok=external(r,TOKYU_PREFIXES,'destination');
  if(first===MM&&origTok.length){push(r,'meguro-mita-meguro',TM,M,MM,'firstStop',origTok,'tokyu-to-mita');counts.meguroMita.tokyuToMita++;}
  if(last===MM&&destTok.length){push(r,'meguro-mita-meguro',M,TM,MM,'lastStop',destTok,'mita-to-tokyu');counts.meguroMita.mitaToTokyu++;}
 }
}
if(!(counts.meguroNamboku.tokyuToNamboku>0&&counts.meguroNamboku.nambokuToTokyu>0))throw new Error(`Namboku-Meguro ODPT endpoint evidence incomplete ${JSON.stringify(counts.meguroNamboku)}`);
if(!(counts.nambokuSaitama.saitamaToNamboku>0&&counts.nambokuSaitama.nambokuToSaitama>0))throw new Error(`Namboku-Saitama ODPT endpoint evidence incomplete ${JSON.stringify(counts.nambokuSaitama)}`);
if(!(counts.meguroMita.mitaToTokyu>0))throw new Error(`No Mita->Tokyu exact endpoint evidence ${JSON.stringify(counts.meguroMita)}`);
const map=new Map((trips.records||[]).map(r=>[String(r.id||''),r]));let added=0;const byBoundary={};
for(const e of out){
 const r=e.row,id=`meguro-endpoint:${dig([r.timetableId,e.boundary,e.direction,e.externalStations,e.boundaryEndpoint])}`;
 const rec={id,identityKey:id,identityType:'odpt-explicit-boundary-endpoint',status:'verified',corridor:'meguro',sourceOperator:r.sourceOperator||'',sourceTimetableId:r.timetableId,sourceTrainId:r.trainId||'',calendars:r.calendars||[],trainType:r.trainType||'',trainNumber:r.trainNumber||'',fromRailway:e.fromRailway,toRailway:e.toRailway,routeRailways:[e.fromRailway,e.toRailway],transitions:[{fromRailway:e.fromRailway,toRailway:e.toRailway,boundaryStation:e.boundaryEndpoint}],classification:'through',canonicalBoundaryId:e.boundary,boundaryEndpoint:e.boundaryEndpoint,externalStations:e.externalStations,exactEndpointRole:e.endpointRole,evidence:'same-odpt-train-timetable+explicit-other-operator-station+exact-boundary-endpoint',matchPolicy:{sameTrainTimetableRecordRequired:true,exactBoundaryEndpointRequired:true,explicitOtherOperatorStationRequired:true,destinationAloneMayEstablishIdentity:false,originAloneMayEstablishIdentity:false,timeProximityAloneMayEstablishIdentity:false,trainNumberAloneMayEstablishIdentity:false},runtimeRule:{requiredMatch:['identityKey','fromRailway','toRailway']}};
 byBoundary[e.boundary]=(byBoundary[e.boundary]||0)+1;if(!map.has(id)){map.set(id,rec);added++;}
}
trips.version=Math.max(Number(trips.version)||0,9);trips.policy={...(trips.policy||{}),runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,genericBoundaryChaining:false};trips.records=[...map.values()].sort((a,b)=>String(a.id||'').localeCompare(String(b.id||'')));trips.meguroEndpointEvidence={sourceFile:identityFile,evidenceRecords:out.length,addedRecords:added,boundaries:byBoundary,directions:counts,policy:{sameTrainTimetableRecordRequired:true,exactBoundaryEndpointRequired:true,destinationAloneMayEstablishIdentity:false,originAloneMayEstablishIdentity:false,timeProximityAloneMayEstablishIdentity:false,trainNumberAloneMayEstablishIdentity:false}};write(tripsFile,trips);
coverage.version=Math.max(Number(coverage.version)||0,9);coverage.summary={...(coverage.summary||{}),throughRecords:trips.records.length,odptExplicitBoundaryEndpointThroughRecords:trips.records.filter(r=>r.identityType==='odpt-explicit-boundary-endpoint').length};coverage.meguroEndpointEvidence={evidenceRecords:out.length,addedRecords:added,boundaries:byBoundary,directions:counts};write(coverageFile,coverage);
console.log(JSON.stringify({sourceNamboku:rows.filter(r=>r.railway===N).length,sourceMita:rows.filter(r=>r.railway===M).length,evidenceRecords:out.length,addedRecords:added,boundaries:byBoundary,directions:counts,totalThroughRecords:trips.records.length},null,2));
