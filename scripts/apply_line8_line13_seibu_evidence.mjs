#!/usr/bin/env node
import fs from 'node:fs';
import crypto from 'node:crypto';

const evidenceFile='data/transit/line8-line13/seibu-official-exact-through-trains.json';
const tripsFile='data/transit/through-service-trips.json';
const coverageFile='data/transit/through-service-coverage.json';
const readJson=(file)=>JSON.parse(fs.readFileSync(file,'utf8'));
const writeJson=(file,value)=>fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n','utf8');
const digest=(value)=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex').slice(0,20);

const Y='odpt.Railway:TokyoMetro.Yurakucho';
const F='odpt.Railway:TokyoMetro.Fukutoshin';
const SY='odpt.Railway:Seibu.SeibuYurakucho';
const SI='odpt.Railway:Seibu.Ikebukuro';
const SC='odpt.Railway:Seibu.SeibuChichibu';
const TY='odpt.Railway:Tokyu.Toyoko';
const MM='manual.Railway:YokohamaMinatomirai.Minatomirai';

const SPECS={
  'yurakucho-seibu-kotake-mukaihara':{
    canonicalId:'yurakucho-seibuyurakucho-kotakemukaihara',station:'小竹向原',corridor:'line8',requiredBranch:'yurakucho',
    patterns:[{stops:['新桜台','小竹向原','千川'],from:SY,to:Y},{stops:['千川','小竹向原','新桜台'],from:Y,to:SY}],
  },
  'fukutoshin-seibu-kotake-mukaihara':{
    canonicalId:'fukutoshin-seibuyurakucho-kotakemukaihara',station:'小竹向原',corridor:'line13',requiredBranch:'fukutoshin',
    patterns:[{stops:['新桜台','小竹向原','千川'],from:SY,to:F},{stops:['千川','小竹向原','新桜台'],from:F,to:SY}],
  },
  'seibuyurakucho-ikebukuro-nerima':{
    canonicalId:'seibuyurakucho-ikebukuro-nerima',station:'練馬',corridorFromBranch:true,
    patterns:[{stops:['新桜台','練馬','中村橋'],from:SY,to:SI},{stops:['中村橋','練馬','新桜台'],from:SI,to:SY}],
  },
  'seibu-ikebukuro-seibuchichibu-agano':{
    canonicalId:'seibu-ikebukuro-seibuchichibu-agano',station:'吾野',corridor:'line13',requiredBranch:'fukutoshin',
    patterns:[{stops:['東吾野','吾野','西吾野'],from:SI,to:SC},{stops:['西吾野','吾野','東吾野'],from:SC,to:SI}],
  },
  'metro-tokyu-shibuya':{
    canonicalId:'toyoko-fukutoshin-shibuya',station:'渋谷',corridor:'line13',requiredBranch:'fukutoshin',
    patterns:[
      {stops:['明治神宮前','渋谷','代官山'],from:F,to:TY},{stops:['明治神宮前〈原宿〉','渋谷','代官山'],from:F,to:TY},
      {stops:['代官山','渋谷','明治神宮前'],from:TY,to:F},{stops:['代官山','渋谷','明治神宮前〈原宿〉'],from:TY,to:F},
    ],
  },
  'tokyu-minatomirai-yokohama':{
    canonicalId:'minatomirai-toyoko-yokohama',station:'横浜',corridor:'line13',requiredBranch:'fukutoshin',
    patterns:[{stops:['反町','横浜','新高島'],from:TY,to:MM},{stops:['新高島','横浜','反町'],from:MM,to:TY}],
  },
};

function includesAdjacent(names,pattern){
  for(let i=0;i+pattern.length<=names.length;i++)if(pattern.every((name,j)=>names[i+j]===name))return true;
  return false;
}

const evidence=readJson(evidenceFile);
const trips=readJson(tripsFile);
const coverage=readJson(coverageFile);
const p=evidence.identityPolicy||{};
if(p.singlePublishedOneTrainPageMayEstablishIdentity!==true||p.boundaryRequiresAdjacentPublishedStopsOnSameTrainPage!==true)throw new Error('Published one-train exact identity policy missing');
if(p.metroLineRequiresPublishedRouteSpecificStation!==true||p.ambiguousMetroBranchMayEstablishLineIdentity!==false)throw new Error('Metro branch separation policy missing');
if(p.timeProximityMayEstablishIdentity!==false||p.trainNumberAloneMayEstablishIdentity!==false||p.destinationAloneMayEstablishIdentity!==false)throw new Error('Unsafe identity inference enabled');

const recordMap=new Map((trips.records||[]).map(row=>[String(row.id||''),row]));
const byBoundary={};
const byCorridor={line8:0,line13:0};
let added=0;
for(const row of evidence.authoritativeThroughTrains||[]){
  if(row.identityEvidence!=='single-published-one-train-page')throw new Error('Unexpected evidence type');
  const sourceUrl=String(row.url||'');
  if(!sourceUrl.startsWith('https://seibu.ekitan.com/norikae/timetable/onetraintimetable/'))throw new Error(`Unexpected source URL: ${sourceUrl}`);
  const branch=String(row.metroBranch||'');
  if(branch==='conflict')throw new Error(`Conflicting Metro branch: ${sourceUrl}`);
  const params=row.sourceParameters||{};
  for(const key of ['tx','sf','date','time','dw'])if(!String(params[key]??''))throw new Error(`Missing ${key}: ${sourceUrl}`);
  const names=(row.stops||[]).map(stop=>String(stop.station||''));

  for(const boundaryId of row.boundaries||[]){
    const spec=SPECS[boundaryId];
    if(!spec)continue;
    if(spec.requiredBranch&&branch!==spec.requiredBranch)throw new Error(`Wrong Metro branch for ${boundaryId}: ${branch} ${sourceUrl}`);
    let corridor=spec.corridor||'';
    if(spec.corridorFromBranch){
      if(branch==='yurakucho')corridor='line8';
      else if(branch==='fukutoshin')corridor='line13';
      else continue;
    }
    const matched=spec.patterns.find(candidate=>includesAdjacent(names,candidate.stops));
    if(!matched)throw new Error(`Boundary not adjacent on one-train page: ${boundaryId} ${sourceUrl}`);
    const identityKey=`official-one-train:${digest([sourceUrl,boundaryId,branch,matched.stops])}`;
    const record={
      id:identityKey,identityKey,identityType:'official-single-train-page',status:'verified',
      corridor,metroBranch:branch,fromRailway:matched.from,toRailway:matched.to,routeRailways:[matched.from,matched.to],
      transitions:[{fromRailway:matched.from,toRailway:matched.to,boundaryStation:spec.station}],classification:'through',
      canonicalBoundaryId:spec.canonicalId,sourceUrl,
      sourceParameters:{tx:String(params.tx),sf:String(params.sf),date:String(params.date),time:String(params.time),dw:String(params.dw)},
      metroBranchPublishedMarkers:row.metroBranchPublishedMarkers||[],publishedBoundaryStops:matched.stops,
      evidence:'single-published-one-train-page+published-route-specific-metro-marker+adjacent-published-boundary-stops',
      matchPolicy:{samePublishedTrainPageRequired:true,publishedRouteSpecificMetroMarkerRequired:true,adjacentBoundaryStopsRequired:true,timeProximityAloneMayEstablishIdentity:false,trainNumberAloneMayEstablishIdentity:false,destinationAloneMayEstablishIdentity:false},
      runtimeRule:{requiredMatch:['identityKey','fromRailway','toRailway']},
    };
    byBoundary[spec.canonicalId]=(byBoundary[spec.canonicalId]||0)+1;
    if(corridor)byCorridor[corridor]=(byCorridor[corridor]||0)+1;
    if(!recordMap.has(identityKey)){recordMap.set(identityKey,record);added++;}
  }
}

trips.version=Math.max(Number(trips.version)||0,7);
trips.policy={...(trips.policy||{}),runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,genericBoundaryChaining:false};
trips.records=[...recordMap.values()].sort((a,b)=>String(a.id||'').localeCompare(String(b.id||'')));
trips.line8Line13SeibuEvidence={file:evidenceFile,generatedAt:String(evidence.generatedAt||''),records:added,boundaries:byBoundary,corridors:byCorridor};
writeJson(tripsFile,trips);
coverage.version=Math.max(Number(coverage.version)||0,7);
coverage.summary={...(coverage.summary||{}),throughRecords:trips.records.length,officialSingleTrainPageThroughRecords:trips.records.filter(row=>row.identityType==='official-single-train-page').length};
coverage.line8Line13SeibuEvidence={sourceFile:evidenceFile,inputTrainPages:(evidence.authoritativeThroughTrains||[]).length,addedRecords:added,boundaries:byBoundary,corridors:byCorridor};
writeJson(coverageFile,coverage);
console.log(JSON.stringify({inputTrainPages:(evidence.authoritativeThroughTrains||[]).length,addedRecords:added,boundaries:byBoundary,corridors:byCorridor,totalThroughRecords:trips.records.length},null,2));
