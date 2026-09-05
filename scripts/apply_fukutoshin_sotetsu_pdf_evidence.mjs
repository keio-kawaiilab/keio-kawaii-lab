#!/usr/bin/env node
import fs from 'node:fs';
import crypto from 'node:crypto';

const evidenceFile='data/transit/fukutoshin/sotetsu-official-line13-columns.json';
const tripsFile='data/transit/through-service-trips.json';
const coverageFile='data/transit/through-service-coverage.json';
const readJson=(file)=>JSON.parse(fs.readFileSync(file,'utf8'));
const writeJson=(file,value)=>fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n','utf8');
const digest=(value)=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex').slice(0,24);

if(!fs.existsSync(evidenceFile)){
  console.log('No Sotetsu official Line 13 PDF evidence file; leaving DB unchanged.');
  process.exit(0);
}

const evidence=readJson(evidenceFile);
const trips=readJson(tripsFile);
const coverage=readJson(coverageFile);
const policy=evidence.identityPolicy||{};
if(policy.officialSamePrintedColumnMayEstablishIdentity!==true)throw new Error('Sotetsu evidence must explicitly require an official same printed column');
if(policy.exactPrintedStationTimesRequired!==true)throw new Error('Sotetsu evidence must require exact printed station times');
if(policy.timeProximityMayEstablishIdentity!==false)throw new Error('Time proximity must not establish Sotetsu train identity');
if(policy.trainNumberAloneMayEstablishIdentity!==false)throw new Error('Train number alone must not establish Sotetsu train identity');
if(policy.destinationAloneMayEstablishIdentity!==false)throw new Error('Destination alone must not establish Sotetsu train identity');
if(policy.stationTimetableRowAloneMayEstablishIdentity!==false)throw new Error('A station row alone must not establish Sotetsu train identity');

const SPECS={
  'toyoko-tokyushinyokohama-hiyoshi':{
    station:'日吉',
    railways:new Set(['odpt.Railway:Tokyu.Toyoko','odpt.Railway:Tokyu.TokyuShinYokohama']),
    patterns:[['自由が丘','日吉','新綱島'],['新綱島','日吉','自由が丘']],
  },
  'tokyushinyokohama-sotetsushinyokohama-shinyokohama':{
    station:'新横浜',
    railways:new Set(['odpt.Railway:Tokyu.TokyuShinYokohama','odpt.Railway:Sotetsu.SotetsuShinYokohama']),
    patterns:[['新綱島','新横浜','羽沢横浜国大'],['羽沢横浜国大','新横浜','新綱島']],
  },
};
const same=(a,b)=>Array.isArray(a)&&a.length===b.length&&b.every((v,i)=>String(a[i])===v);

const rows=Array.isArray(evidence.authoritativeColumns)?evidence.authoritativeColumns:[];
const recordMap=new Map((trips.records||[]).map((row)=>[String(row.id||''),row]));
const byBoundary={};
let added=0;

for(const row of rows){
  if(row.identityEvidence!=='official-same-printed-column')throw new Error('Unexpected Sotetsu evidence type');
  if(row.status!=='verified')throw new Error('Only verified Sotetsu column evidence may enter production DB');
  const boundaryId=String(row.canonicalBoundaryId||'');
  const spec=SPECS[boundaryId];
  if(!spec)throw new Error(`Unexpected Sotetsu Line 13 boundary: ${boundaryId}`);
  const fromRailway=String(row.fromRailway||'');
  const toRailway=String(row.toRailway||'');
  if(fromRailway===toRailway||!spec.railways.has(fromRailway)||!spec.railways.has(toRailway))throw new Error(`Wrong railway pair for ${boundaryId}`);
  const sourceUrl=String(row.sourceUrl||'');
  if(!sourceUrl.startsWith('https://cdn.sotetsu.co.jp/'))throw new Error(`Unexpected Sotetsu PDF source: ${sourceUrl}`);
  const pdfPage=Number(row.pdfPage);
  const columnX=Number(row.columnX);
  if(!Number.isInteger(pdfPage)||pdfPage<2)throw new Error(`Missing valid PDF page for ${boundaryId}`);
  if(!(columnX>0))throw new Error(`Missing valid printed column X for ${boundaryId}`);
  const stops=(row.publishedBoundaryStops||[]).map(String);
  if(!spec.patterns.some((pattern)=>same(stops,pattern)))throw new Error(`Exact boundary station pattern missing for ${boundaryId}`);
  const mp=row.matchPolicy||{};
  if(mp.officialSamePrintedColumnRequired!==true||mp.exactPrintedStationTimesRequired!==true)throw new Error(`Sotetsu column evidence lacks strict positive requirements for ${boundaryId}`);
  if(mp.timeProximityAloneMayEstablishIdentity!==false||mp.trainNumberAloneMayEstablishIdentity!==false||mp.destinationAloneMayEstablishIdentity!==false)throw new Error(`Sotetsu column evidence weakens fail-closed identity rules for ${boundaryId}`);
  const printedTimes=row.printedTimes||{};
  for(const stop of stops)if(!String(printedTimes[stop]||''))throw new Error(`Missing exact printed time for ${stop} on ${boundaryId}`);

  const identityKey=String(row.id||'')||`sotetsu-column:${digest([sourceUrl,pdfPage,columnX,boundaryId,stops,printedTimes])}`;
  const record={
    id:identityKey,
    identityKey,
    identityType:'official-same-printed-column',
    status:'verified',
    fromRailway,
    toRailway,
    routeRailways:[fromRailway,toRailway],
    transitions:[{fromRailway,toRailway,boundaryStation:spec.station}],
    classification:'through',
    canonicalBoundaryId:boundaryId,
    sourceUrl,
    pdfPage,
    columnX,
    columnTolerance:Number(row.columnTolerance)||0,
    calendar:String(row.calendar||''),
    direction:String(row.direction||''),
    publishedBoundaryStops:stops,
    printedTimes,
    evidence:'operator-official-full-train-timetable+same-printed-column+exact-station-times',
    matchPolicy:{
      officialSamePrintedColumnRequired:true,
      exactPrintedStationTimesRequired:true,
      timeProximityAloneMayEstablishIdentity:false,
      trainNumberAloneMayEstablishIdentity:false,
      destinationAloneMayEstablishIdentity:false,
    },
    runtimeRule:{requiredMatch:['identityKey','fromRailway','toRailway']},
  };
  byBoundary[boundaryId]=(byBoundary[boundaryId]||0)+1;
  if(!recordMap.has(identityKey)){
    recordMap.set(identityKey,record);
    added++;
  }
}

trips.version=Math.max(Number(trips.version)||0,5);
trips.policy={...(trips.policy||{}),runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,genericBoundaryChaining:false};
trips.records=[...recordMap.values()].sort((a,b)=>String(a.id||'').localeCompare(String(b.id||'')));
trips.sotetsuOfficialColumnEvidence={file:evidenceFile,generatedAt:String(evidence.generatedAt||''),source:String(evidence.source||''),records:added,boundaries:byBoundary};
writeJson(tripsFile,trips);

coverage.version=Math.max(Number(coverage.version)||0,5);
coverage.summary={...(coverage.summary||{}),throughRecords:trips.records.length,officialSamePrintedColumnThroughRecords:trips.records.filter((row)=>row.identityType==='official-same-printed-column').length};
coverage.sotetsuOfficialColumnEvidence={sourceFile:evidenceFile,sourceGeneratedAt:String(evidence.generatedAt||''),inputColumns:rows.length,addedRecords:added,boundaries:byBoundary};
writeJson(coverageFile,coverage);

console.log(JSON.stringify({inputColumns:rows.length,addedRecords:added,boundaries:byBoundary,totalThroughRecords:trips.records.length},null,2));
