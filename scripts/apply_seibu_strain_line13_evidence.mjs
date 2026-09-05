#!/usr/bin/env node
import fs from 'node:fs';

const evidenceFile='data/transit/line8-line13/seibu-strain-line13-columns.json';
const tripsFile='data/transit/through-service-trips.json';
const coverageFile='data/transit/through-service-coverage.json';
const readJson=(file)=>JSON.parse(fs.readFileSync(file,'utf8'));
const writeJson=(file,value)=>fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n','utf8');
const evidence=readJson(evidenceFile),trips=readJson(tripsFile),coverage=readJson(coverageFile);
const p=evidence.identityPolicy||{};
if(p.sameOfficialPrintedColumnMayEstablishIdentity!==true||p.reviewedSourceHashRequired!==true||p.verifiedUniqueFamilyPathMayProjectInternalBoundaries!==true)throw new Error('S-TRAIN hash-guarded printed-column policy missing');
if(p.timeProximityMayEstablishIdentity!==false||p.trainNumberAloneMayEstablishIdentity!==false||p.destinationAloneMayEstablishIdentity!==false)throw new Error('Unsafe S-TRAIN identity inference enabled');
if(evidence.sourceSha256!=='d04ba82847797557e5ca22e5bc3a7f70eff18204f02a2fc017eaa3a131d8c66d')throw new Error('Unexpected S-TRAIN source snapshot');

const pairs={
  'seibu-ikebukuro-seibuchichibu-agano':['odpt.Railway:Seibu.Ikebukuro','odpt.Railway:Seibu.SeibuChichibu'],
  'seibuyurakucho-ikebukuro-nerima':['odpt.Railway:Seibu.SeibuYurakucho','odpt.Railway:Seibu.Ikebukuro'],
  'fukutoshin-seibuyurakucho-kotakemukaihara':['odpt.Railway:TokyoMetro.Fukutoshin','odpt.Railway:Seibu.SeibuYurakucho'],
  'toyoko-fukutoshin-shibuya':['odpt.Railway:Tokyu.Toyoko','odpt.Railway:TokyoMetro.Fukutoshin'],
  'minatomirai-toyoko-yokohama':['manual.Railway:YokohamaMinatomirai.Minatomirai','odpt.Railway:Tokyu.Toyoko'],
};
const samePair=(a,b,p)=>Boolean(p)&&((a===p[0]&&b===p[1])||(a===p[1]&&b===p[0]));
const recordMap=new Map((trips.records||[]).map(row=>[String(row.id||''),row]));
let added=0;const byBoundary={},directions={};
for(const row of evidence.evidence||[]){
  if(row.identityEvidence!=='official-same-printed-column-route-span'||row.status!=='verified'||row.corridor!=='line13'||row.service!=='S-TRAIN')throw new Error('Unexpected S-TRAIN evidence row');
  if(row.reviewMode!=='manual-visual-review-hash-guarded'||row.sourceSha256!==evidence.sourceSha256)throw new Error('S-TRAIN reviewed source guard missing');
  if(!String(row.sourceUrl||'').startsWith('https://www.seiburailway.jp/railway/reservedtrain/file/'))throw new Error('Unexpected S-TRAIN source URL');
  const bid=String(row.canonicalBoundaryId||''),from=String(row.fromRailway||''),to=String(row.toRailway||'');
  if(!samePair(from,to,pairs[bid]))throw new Error(`Unexpected S-TRAIN boundary pair ${bid}: ${from} -> ${to}`);
  const mp=row.matchPolicy||{};
  if(mp.sameOfficialPrintedColumnRequired!==true||mp.reviewedSourceHashRequired!==true||mp.publishedFukutoshinSpecificStationRequired!==true||mp.publishedSeibuChichibuStationRequired!==true||mp.verifiedUniqueFamilyPathRequired!==true)throw new Error(`Incomplete S-TRAIN proof policy: ${bid}`);
  if(mp.timeProximityAloneMayEstablishIdentity!==false||mp.trainNumberAloneMayEstablishIdentity!==false||mp.destinationAloneMayEstablishIdentity!==false)throw new Error(`Unsafe S-TRAIN row policy: ${bid}`);
  const id=String(row.id||'');if(!id)throw new Error('S-TRAIN evidence id missing');
  const record={id,identityKey:id,identityType:'official-same-printed-column',status:'verified',corridor:'line13',service:'S-TRAIN',fromRailway:from,toRailway:to,routeRailways:[from,to],transitions:[{fromRailway:from,toRailway:to,boundaryStation:String(row.boundaryStation||'')}],classification:'through',canonicalBoundaryId:bid,sourceUrl:String(row.sourceUrl||''),sourceSha256:String(row.sourceSha256||''),sourceRevision:String(row.sourceRevision||''),reviewMode:String(row.reviewMode||''),pdfPage:Number(row.pdfPage||1),publishedColumnLabel:String(row.publishedColumnLabel||''),publishedTimes:row.publishedTimes||{},publishedRouteMarkers:row.publishedRouteMarkers||[],evidence:'official-same-printed-column+reviewed-source-hash+verified-unique-through-family-route-span',matchPolicy:mp,runtimeRule:{requiredMatch:['identityKey','fromRailway','toRailway']}};
  byBoundary[bid]=(byBoundary[bid]||0)+1;directions[bid]??={};directions[bid][String(row.direction||'')]=(directions[bid][String(row.direction||'')]||0)+1;
  if(!recordMap.has(id)){recordMap.set(id,record);added++;}
}
for(const bid of Object.keys(pairs)){
  const d=directions[bid]||{};
  if(d['chichibu-to-fukutoshin']!==1||d['fukutoshin-to-chichibu']!==1)throw new Error(`S-TRAIN boundary is not exactly bidirectional: ${bid} ${JSON.stringify(d)}`);
}
trips.version=Math.max(Number(trips.version)||0,11);trips.policy={...(trips.policy||{}),runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,genericBoundaryChaining:false};trips.records=[...recordMap.values()].sort((a,b)=>String(a.id||'').localeCompare(String(b.id||'')));trips.seibuStrainLine13Evidence={sourceFile:evidenceFile,sourceUrl:evidence.sourceUrl,sourceSha256:evidence.sourceSha256,sourceGeneratedAt:evidence.generatedAt,addedRecords:added,boundaries:byBoundary,directions};writeJson(tripsFile,trips);
coverage.version=Math.max(Number(coverage.version)||0,11);coverage.summary={...(coverage.summary||{}),throughRecords:trips.records.length};coverage.seibuStrainLine13Evidence={sourceFile:evidenceFile,sourceSha256:evidence.sourceSha256,addedRecords:added,boundaries:byBoundary,directions};writeJson(coverageFile,coverage);
console.log(JSON.stringify({inputRecords:(evidence.evidence||[]).length,addedRecords:added,boundaries:byBoundary,directions,totalThroughRecords:trips.records.length},null,2));
