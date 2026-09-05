#!/usr/bin/env node
import fs from 'node:fs';
import crypto from 'node:crypto';

const evidenceFile='data/transit/fukutoshin/seibu-official-linked-through-trains.json';
const tripsFile='data/transit/through-service-trips.json';
const coverageFile='data/transit/through-service-coverage.json';
const digest=(value)=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex').slice(0,20);
const readJson=(file)=>JSON.parse(fs.readFileSync(file,'utf8'));
const writeJson=(file,value)=>fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n','utf8');

if(!fs.existsSync(evidenceFile)){
  console.log('No current Fukutoshin official one-train evidence file; leaving DB unchanged.');
  process.exit(0);
}

const evidence=readJson(evidenceFile);
const trips=readJson(tripsFile);
const coverage=readJson(coverageFile);
const policy=evidence.identityPolicy||{};
if(policy.singlePublishedOneTrainPageMayEstablishIdentity!==true)throw new Error('Evidence must explicitly allow one published train page as identity proof');
if(policy.boundaryRequiresAdjacentPublishedStopsOnSameTrainPage!==true)throw new Error('Evidence must require adjacent boundary stops on the same train page');
if(policy.timeProximityMayEstablishIdentity!==false)throw new Error('Time proximity must not establish train identity');
if(policy.trainNumberAloneMayEstablishIdentity!==false)throw new Error('Train number alone must not establish train identity');
if(policy.destinationAloneMayEstablishIdentity!==false)throw new Error('Destination alone must not establish train identity');

const MM='manual.Railway:YokohamaMinatomirai.Minatomirai';
const TY='odpt.Railway:Tokyu.Toyoko';
const F='odpt.Railway:TokyoMetro.Fukutoshin';
const SY='odpt.Railway:Seibu.SeibuYurakucho';

const SPECS={
  'seibu-metro-kotake-mukaihara':{
    canonicalId:'fukutoshin-seibuyurakucho-kotakemukaihara',
    station:'小竹向原',
    patterns:[
      {stops:['新桜台','小竹向原','千川'],from:SY,to:F},
      {stops:['千川','小竹向原','新桜台'],from:F,to:SY},
    ],
  },
  'metro-tokyu-shibuya':{
    canonicalId:'toyoko-fukutoshin-shibuya',
    station:'渋谷',
    patterns:[
      {stops:['明治神宮前','渋谷','代官山'],from:F,to:TY},
      {stops:['代官山','渋谷','明治神宮前'],from:TY,to:F},
    ],
  },
  'tokyu-minatomirai-yokohama':{
    canonicalId:'minatomirai-toyoko-yokohama',
    station:'横浜',
    patterns:[
      {stops:['反町','横浜','新高島'],from:TY,to:MM},
      {stops:['新高島','横浜','反町'],from:MM,to:TY},
    ],
  },
};

function includesAdjacent(names,pattern){
  for(let i=0;i+pattern.length<=names.length;i++){
    if(pattern.every((name,j)=>names[i+j]===name))return true;
  }
  return false;
}

const rows=Array.isArray(evidence.authoritativeThroughTrains)?evidence.authoritativeThroughTrains:[];
const recordMap=new Map((trips.records||[]).map((row)=>[String(row.id||''),row]));
let added=0;
const byBoundary={};

for(const row of rows){
  if(row.identityEvidence!=='single-published-one-train-page')throw new Error('Unexpected identity evidence type in current Line 13 evidence');
  const sourceUrl=String(row.url||'');
  if(!sourceUrl.startsWith('https://seibu.ekitan.com/norikae/timetable/onetraintimetable/'))throw new Error(`Unexpected one-train source URL: ${sourceUrl}`);
  const params=row.sourceParameters||{};
  for(const key of ['tx','sf','date','time','dw'])if(!String(params[key]??''))throw new Error(`Missing source parameter ${key}: ${sourceUrl}`);
  const names=(row.stops||[]).map((stop)=>String(stop.station||''));
  if(names.length<3)throw new Error(`One-train page has too few published stops: ${sourceUrl}`);

  for(const boundaryId of row.boundaries||[]){
    const spec=SPECS[boundaryId];
    if(!spec)continue;
    const matched=spec.patterns.find((candidate)=>includesAdjacent(names,candidate.stops));
    if(!matched)throw new Error(`Claimed boundary is not adjacent on the published train page: ${boundaryId} ${sourceUrl}`);
    const identityKey=`official-one-train:${digest([sourceUrl,boundaryId,matched.stops])}`;
    const record={
      id:identityKey,
      identityKey,
      identityType:'official-single-train-page',
      status:'verified',
      fromRailway:matched.from,
      toRailway:matched.to,
      routeRailways:[matched.from,matched.to],
      transitions:[{fromRailway:matched.from,toRailway:matched.to,boundaryStation:spec.station}],
      classification:'through',
      canonicalBoundaryId:spec.canonicalId,
      sourceUrl,
      sourceParameters:{tx:String(params.tx),sf:String(params.sf),date:String(params.date),time:String(params.time),dw:String(params.dw)},
      publishedBoundaryStops:matched.stops,
      evidence:'single-published-one-train-page+adjacent-published-boundary-stops',
      runtimeRule:{requiredMatch:['identityKey','fromRailway','toRailway']},
    };
    byBoundary[spec.canonicalId]=(byBoundary[spec.canonicalId]||0)+1;
    if(!recordMap.has(identityKey)){
      recordMap.set(identityKey,record);
      added++;
    }
  }
}

trips.version=Math.max(Number(trips.version)||0,4);
trips.policy={...(trips.policy||{}),runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,genericBoundaryChaining:false};
trips.records=[...recordMap.values()].sort((a,b)=>String(a.id||'').localeCompare(String(b.id||'')));
trips.officialOneTrainEvidence={file:evidenceFile,generatedAt:String(evidence.generatedAt||''),source:String(evidence.source||''),records:added,boundaries:byBoundary};
writeJson(tripsFile,trips);

coverage.version=Math.max(Number(coverage.version)||0,4);
coverage.summary={...(coverage.summary||{}),throughRecords:trips.records.length,officialSingleTrainPageThroughRecords:trips.records.filter((row)=>row.identityType==='official-single-train-page').length};
coverage.officialOneTrainEvidence={sourceFile:evidenceFile,sourceGeneratedAt:String(evidence.generatedAt||''),inputTrainPages:rows.length,addedRecords:added,boundaries:byBoundary};
writeJson(coverageFile,coverage);

console.log(JSON.stringify({inputTrainPages:rows.length,addedRecords:added,boundaries:byBoundary,totalThroughRecords:trips.records.length},null,2));
