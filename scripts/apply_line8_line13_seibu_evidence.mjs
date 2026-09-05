#!/usr/bin/env node
import fs from 'node:fs';
import crypto from 'node:crypto';

const evidenceFile='data/transit/line8-line13/seibu-official-exact-through-trains.json';
const tripsFile='data/transit/through-service-trips.json';
const coverageFile='data/transit/through-service-coverage.json';
const readJson=(file)=>JSON.parse(fs.readFileSync(file,'utf8'));
const writeJson=(file,value)=>fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n','utf8');
const digest=(value)=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex').slice(0,20);

const Y='odpt.Railway:TokyoMetro.Yurakucho',F='odpt.Railway:TokyoMetro.Fukutoshin',SY='odpt.Railway:Seibu.SeibuYurakucho',SI='odpt.Railway:Seibu.Ikebukuro',SC='odpt.Railway:Seibu.SeibuChichibu',TY='odpt.Railway:Tokyu.Toyoko',MM='manual.Railway:YokohamaMinatomirai.Minatomirai';
const SPECS={
  'yurakucho-seibu-kotake-mukaihara':{canonicalId:'yurakucho-seibuyurakucho-kotakemukaihara',station:'小竹向原',corridor:'line8',requiredBranch:'yurakucho',pair:[Y,SY]},
  'fukutoshin-seibu-kotake-mukaihara':{canonicalId:'fukutoshin-seibuyurakucho-kotakemukaihara',station:'小竹向原',corridor:'line13',requiredBranch:'fukutoshin',pair:[F,SY]},
  'seibuyurakucho-ikebukuro-nerima':{canonicalId:'seibuyurakucho-ikebukuro-nerima',station:'練馬',corridorFromBranch:true,pair:[SY,SI]},
  'seibu-ikebukuro-seibuchichibu-agano':{canonicalId:'seibu-ikebukuro-seibuchichibu-agano',station:'吾野',corridor:'line13',requiredBranch:'fukutoshin',pair:[SI,SC]},
  'metro-tokyu-shibuya':{canonicalId:'toyoko-fukutoshin-shibuya',station:'渋谷',corridor:'line13',requiredBranch:'fukutoshin',pair:[F,TY],patterns:[{stops:['明治神宮前','渋谷','代官山'],from:F,to:TY},{stops:['明治神宮前〈原宿〉','渋谷','代官山'],from:F,to:TY},{stops:['代官山','渋谷','明治神宮前'],from:TY,to:F},{stops:['代官山','渋谷','明治神宮前〈原宿〉'],from:TY,to:F}]},
  'tokyu-minatomirai-yokohama':{canonicalId:'minatomirai-toyoko-yokohama',station:'横浜',corridor:'line13',requiredBranch:'fukutoshin',pair:[TY,MM],patterns:[{stops:['反町','横浜','新高島'],from:TY,to:MM},{stops:['新高島','横浜','反町'],from:MM,to:TY}]},
};
function includesAdjacent(names,pattern){for(let i=0;i+pattern.length<=names.length;i++)if(pattern.every((name,j)=>names[i+j]===name))return true;return false;}
function samePair(a,b,pair){return (a===pair[0]&&b===pair[1])||(a===pair[1]&&b===pair[0]);}

const evidence=readJson(evidenceFile),trips=readJson(tripsFile),coverage=readJson(coverageFile),p=evidence.identityPolicy||{};
if(p.singlePublishedOneTrainPageMayEstablishIdentity!==true||p.samePublishedTrainPageWithVerifiedUniqueRouteSpanMayEstablishInternalBoundary!==true)throw new Error('Published route-span identity policy missing');
if(p.metroLineRequiresPublishedRouteSpecificStation!==true||p.ambiguousMetroBranchMayEstablishLineIdentity!==false)throw new Error('Metro branch separation policy missing');
if(p.timeProximityMayEstablishIdentity!==false||p.trainNumberAloneMayEstablishIdentity!==false||p.destinationAloneMayEstablishIdentity!==false)throw new Error('Unsafe identity inference enabled');

const recordMap=new Map((trips.records||[]).map(row=>[String(row.id||''),row]));
const byBoundary={},byCorridor={line8:0,line13:0};let added=0;
for(const row of evidence.authoritativeThroughTrains||[]){
  if(row.identityEvidence!=='single-published-one-train-page')throw new Error('Unexpected evidence type');
  const sourceUrl=String(row.url||'');if(!sourceUrl.startsWith('https://seibu.ekitan.com/norikae/timetable/onetraintimetable/'))throw new Error(`Unexpected source URL: ${sourceUrl}`);
  const branch=String(row.metroBranch||'');if(branch==='conflict')throw new Error(`Conflicting Metro branch: ${sourceUrl}`);
  const params=row.sourceParameters||{};for(const key of ['tx','sf','date','time','dw'])if(!String(params[key]??''))throw new Error(`Missing ${key}: ${sourceUrl}`);
  const names=(row.stops||[]).map(stop=>String(stop.station||''));const proofs=row.boundaryProofs||{};

  for(const boundaryId of row.boundaries||[]){
    const spec=SPECS[boundaryId];if(!spec)continue;
    if(spec.requiredBranch&&branch!==spec.requiredBranch)throw new Error(`Wrong Metro branch for ${boundaryId}: ${branch}`);
    let corridor=spec.corridor||'';if(spec.corridorFromBranch){if(branch==='yurakucho')corridor='line8';else if(branch==='fukutoshin')corridor='line13';else continue;}
    const proof=proofs[boundaryId]||{};let from='',to='',publishedMarkers=[],proofType=String(proof.proofType||'');
    if(proofType==='same-published-one-train-page+verified-unique-route-span'){
      from=String(proof.fromRailway||'');to=String(proof.toRailway||'');publishedMarkers=(proof.publishedSideMarkers||[]).map(String);
      if(proof.verifiedUniqueRouteSpanRequired!==true||proof.adjacentPublishedBoundaryStopsRequired!==false)throw new Error(`Malformed route-span proof: ${boundaryId}`);
      if(!samePair(from,to,spec.pair))throw new Error(`Route-span railway pair mismatch: ${boundaryId} ${from} ${to}`);
      if(publishedMarkers.length<2||publishedMarkers.some(name=>!names.includes(name)))throw new Error(`Published route-span markers missing: ${boundaryId}`);
    }else if(proofType==='same-published-one-train-page+adjacent-published-boundary-stops'){
      const matched=(spec.patterns||[]).find(candidate=>includesAdjacent(names,candidate.stops));if(!matched)throw new Error(`Adjacent boundary proof missing: ${boundaryId}`);
      from=matched.from;to=matched.to;publishedMarkers=matched.stops;
    }else throw new Error(`Unknown or missing boundary proof: ${boundaryId} ${proofType}`);

    const identityKey=`official-one-train:${digest([sourceUrl,boundaryId,branch,proofType,publishedMarkers,from,to])}`;
    const record={id:identityKey,identityKey,identityType:'official-single-train-page',status:'verified',corridor,metroBranch:branch,fromRailway:from,toRailway:to,routeRailways:[from,to],transitions:[{fromRailway:from,toRailway:to,boundaryStation:spec.station}],classification:'through',canonicalBoundaryId:spec.canonicalId,sourceUrl,sourceParameters:{tx:String(params.tx),sf:String(params.sf),date:String(params.date),time:String(params.time),dw:String(params.dw)},metroBranchPublishedMarkers:row.metroBranchPublishedMarkers||[],publishedRouteMarkers:publishedMarkers,evidence:proofType,matchPolicy:{samePublishedTrainPageRequired:true,publishedRouteSpecificMetroMarkerRequired:Boolean(spec.requiredBranch||spec.corridorFromBranch),verifiedUniqueRouteSpanRequired:proofType.includes('route-span'),timeProximityAloneMayEstablishIdentity:false,trainNumberAloneMayEstablishIdentity:false,destinationAloneMayEstablishIdentity:false},runtimeRule:{requiredMatch:['identityKey','fromRailway','toRailway']}};
    byBoundary[spec.canonicalId]=(byBoundary[spec.canonicalId]||0)+1;if(corridor)byCorridor[corridor]=(byCorridor[corridor]||0)+1;if(!recordMap.has(identityKey)){recordMap.set(identityKey,record);added++;}
  }
}
trips.version=Math.max(Number(trips.version)||0,9);trips.policy={...(trips.policy||{}),runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,genericBoundaryChaining:false};trips.records=[...recordMap.values()].sort((a,b)=>String(a.id||'').localeCompare(String(b.id||'')));trips.line8Line13SeibuEvidence={file:evidenceFile,generatedAt:String(evidence.generatedAt||''),records:added,boundaries:byBoundary,corridors:byCorridor};writeJson(tripsFile,trips);
coverage.version=Math.max(Number(coverage.version)||0,9);coverage.summary={...(coverage.summary||{}),throughRecords:trips.records.length,officialSingleTrainPageThroughRecords:trips.records.filter(row=>row.identityType==='official-single-train-page').length};coverage.line8Line13SeibuEvidence={sourceFile:evidenceFile,inputTrainPages:(evidence.authoritativeThroughTrains||[]).length,addedRecords:added,boundaries:byBoundary,corridors:byCorridor};writeJson(coverageFile,coverage);
console.log(JSON.stringify({inputTrainPages:(evidence.authoritativeThroughTrains||[]).length,addedRecords:added,boundaries:byBoundary,corridors:byCorridor,totalThroughRecords:trips.records.length},null,2));
