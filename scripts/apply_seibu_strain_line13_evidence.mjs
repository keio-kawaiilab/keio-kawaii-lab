#!/usr/bin/env node
import fs from 'node:fs';

const evidenceFile='data/transit/line8-line13/seibu-strain-line13-columns.json';
const tripsFile='data/transit/through-service-trips.json';
const coverageFile='data/transit/through-service-coverage.json';
const readJson=(file)=>JSON.parse(fs.readFileSync(file,'utf8'));
const writeJson=(file,value)=>fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n','utf8');
const evidence=readJson(evidenceFile),trips=readJson(tripsFile),coverage=readJson(coverageFile);
const p=evidence.identityPolicy||{};
if(p.sameOfficialPrintedColumnMayEstablishIdentity!==true||p.verifiedUniqueFamilyPathMayProjectInternalBoundaries!==true)throw new Error('S-TRAIN exact printed-column route-span policy missing');
if(p.timeProximityMayEstablishIdentity!==false||p.trainNumberAloneMayEstablishIdentity!==false||p.destinationAloneMayEstablishIdentity!==false)throw new Error('Unsafe S-TRAIN identity inference enabled');
const allowed=new Map([
  ['seibuyurakucho-ikebukuro-nerima',new Set(['odpt.Railway:Seibu.SeibuYurakucho|odpt.Railway:Seibu.Ikebukuro','odpt.Railway:Seibu.Ikebukuro|odpt.Railway:Seibu.SeibuYurakucho'])],
  ['seibu-ikebukuro-seibuchichibu-agano',new Set(['odpt.Railway:Seibu.Ikebukuro|odpt.Railway:Seibu.SeibuChichibu','odpt.Railway:Seibu.SeibuChichibu|odpt.Railway:Seibu.Ikebukuro'])],
]);
const recordMap=new Map((trips.records||[]).map(row=>[String(row.id||''),row]));let added=0;const byBoundary={};
for(const row of evidence.evidence||[]){
  if(row.identityEvidence!=='official-same-printed-column-route-span'||row.status!=='verified'||row.corridor!=='line13'||row.service!=='S-TRAIN')throw new Error('Unexpected S-TRAIN evidence row');
  if(!String(row.sourceUrl||'').startsWith('https://www.seiburailway.jp/railway/reservedtrain/file/'))throw new Error('Unexpected S-TRAIN source URL');
  const bid=String(row.canonicalBoundaryId||''),from=String(row.fromRailway||''),to=String(row.toRailway||'');
  if(!allowed.get(bid)?.has(`${from}|${to}`))throw new Error(`Unexpected S-TRAIN boundary pair ${bid}: ${from} -> ${to}`);
  const mp=row.matchPolicy||{};if(mp.sameOfficialPrintedColumnRequired!==true||mp.publishedFukutoshinSpecificStationRequired!==true||mp.publishedSeibuChichibuStationRequired!==true||mp.verifiedUniqueFamilyPathRequired!==true)throw new Error(`Incomplete S-TRAIN proof policy: ${bid}`);
  const id=String(row.id||'');if(!id)throw new Error('S-TRAIN evidence id missing');
  const record={id,identityKey:id,identityType:'official-same-printed-column',status:'verified',corridor:'line13',service:'S-TRAIN',fromRailway:from,toRailway:to,routeRailways:[from,to],transitions:[{fromRailway:from,toRailway:to,boundaryStation:String(row.boundaryStation||'')}],classification:'through',canonicalBoundaryId:bid,sourceUrl:String(row.sourceUrl||''),pdfPage:Number(row.pdfPage||1),publishedColumnLabel:String(row.publishedColumnLabel||''),publishedTimes:row.publishedTimes||{},publishedRouteMarkers:row.publishedRouteMarkers||[],evidence:'official-same-printed-column+verified-unique-through-family-route-span',matchPolicy:mp,runtimeRule:{requiredMatch:['identityKey','fromRailway','toRailway']}};
  byBoundary[bid]=(byBoundary[bid]||0)+1;if(!recordMap.has(id)){recordMap.set(id,record);added++;}
}
for(const bid of allowed.keys())if(!(byBoundary[bid]>0))throw new Error(`No S-TRAIN evidence generated for ${bid}`);
trips.version=Math.max(Number(trips.version)||0,10);trips.policy={...(trips.policy||{}),runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,genericBoundaryChaining:false};trips.records=[...recordMap.values()].sort((a,b)=>String(a.id||'').localeCompare(String(b.id||'')));trips.seibuStrainLine13Evidence={sourceFile:evidenceFile,sourceUrl:evidence.sourceUrl,sourceGeneratedAt:evidence.generatedAt,addedRecords:added,boundaries:byBoundary};writeJson(tripsFile,trips);
coverage.version=Math.max(Number(coverage.version)||0,10);coverage.summary={...(coverage.summary||{}),throughRecords:trips.records.length};coverage.seibuStrainLine13Evidence={sourceFile:evidenceFile,addedRecords:added,boundaries:byBoundary};writeJson(coverageFile,coverage);
console.log(JSON.stringify({inputRecords:(evidence.evidence||[]).length,addedRecords:added,boundaries:byBoundary,totalThroughRecords:trips.records.length},null,2));
