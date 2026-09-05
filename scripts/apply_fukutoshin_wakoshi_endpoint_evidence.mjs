#!/usr/bin/env node
import fs from 'node:fs';
import crypto from 'node:crypto';

const identityFile='data/transit/odpt-train-identities.json';
const tripsFile='data/transit/through-service-trips.json';
const coverageFile='data/transit/through-service-coverage.json';
const readJson=(file)=>JSON.parse(fs.readFileSync(file,'utf8'));
const writeJson=(file,value)=>fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n','utf8');
const digest=(value)=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex').slice(0,24);

const F='odpt.Railway:TokyoMetro.Fukutoshin';
const TJ='odpt.Railway:Tobu.Tojo';
const WAKOSHI='odpt.Station:TokyoMetro.Fukutoshin.Wakoshi';
const TOBU_PREFIX='odpt.Station:Tobu.Tojo.';
const BOUNDARY='fukutoshin-tojo-wakoshi';

const identity=readJson(identityFile);
const trips=readJson(tripsFile);
const coverage=readJson(coverageFile);

if(identity?.policy?.runtimeInference!==false)throw new Error('Identity sidecar must forbid runtime inference');
if(identity?.policy?.timeGapMayEstablishTrainIdentity!==false)throw new Error('Time gaps must not establish train identity');
if(identity?.policy?.trainNumberMayEstablishTrainIdentity!==false)throw new Error('Train numbers must not establish train identity');

const rows=(identity.records||[]).filter(row=>row&&row.railway===F&&row.timetableId);
const recordMap=new Map((trips.records||[]).map(row=>[String(row.id||''),row]));
const evidence=[];
const counts={tobuToFukutoshin:0,fukutoshinToTobu:0};

const stationOf=(stop)=>String(stop?.station||'');
const tobuStations=(values)=>(Array.isArray(values)?values:[]).map(String).filter(value=>value.startsWith(TOBU_PREFIX));

for(const row of rows){
  const first=stationOf(row.firstStop);
  const last=stationOf(row.lastStop);
  const origins=tobuStations(row.origin);
  const destinations=tobuStations(row.destination);

  // Exact inbound proof: this exact Tokyo Metro TrainTimetable says the train
  // originates at a Tobu Tojo station, while its Metro timetable segment starts
  // at Wakoshi. No clock-time, train-number, or destination similarity is used.
  if(first===WAKOSHI&&origins.length){
    evidence.push({row,direction:'tobu-to-fukutoshin',externalStations:origins,fromRailway:TJ,toRailway:F});
    counts.tobuToFukutoshin++;
  }

  // Exact outbound proof: this exact Tokyo Metro TrainTimetable says its Metro
  // timetable segment ends at Wakoshi and its published destination is a Tobu
  // Tojo station. Destination by itself is insufficient; the exact boundary
  // endpoint on the same TrainTimetable record is mandatory.
  if(last===WAKOSHI&&destinations.length){
    evidence.push({row,direction:'fukutoshin-to-tobu',externalStations:destinations,fromRailway:F,toRailway:TJ});
    counts.fukutoshinToTobu++;
  }
}

if(!evidence.length)throw new Error('No exact Wakoshi endpoint evidence found');
if(counts.tobuToFukutoshin<1)throw new Error('No exact Tobu -> Fukutoshin Wakoshi endpoint evidence found');
if(counts.fukutoshinToTobu<1)throw new Error('No exact Fukutoshin -> Tobu Wakoshi endpoint evidence found');

let added=0;
for(const item of evidence){
  const row=item.row;
  const identityKey=`odpt-endpoint:${digest([row.timetableId,item.direction,item.externalStations,WAKOSHI])}`;
  const record={
    id:identityKey,
    identityKey,
    identityType:'odpt-explicit-boundary-endpoint',
    status:'verified',
    sourceOperator:row.sourceOperator||'tokyometro',
    sourceTimetableId:row.timetableId,
    sourceTrainId:row.trainId||'',
    calendars:row.calendars||[],
    trainType:row.trainType||'',
    trainNumber:row.trainNumber||'',
    fromRailway:item.fromRailway,
    toRailway:item.toRailway,
    routeRailways:[item.fromRailway,item.toRailway],
    transitions:[{fromRailway:item.fromRailway,toRailway:item.toRailway,boundaryStation:WAKOSHI}],
    classification:'through',
    canonicalBoundaryId:BOUNDARY,
    boundaryEndpoint:WAKOSHI,
    externalOriginStations:item.direction==='tobu-to-fukutoshin'?item.externalStations:[],
    externalDestinationStations:item.direction==='fukutoshin-to-tobu'?item.externalStations:[],
    exactEndpointRole:item.direction==='tobu-to-fukutoshin'?'firstStop':'lastStop',
    evidence:'same-odpt-train-timetable+explicit-tobu-origin-or-destination+exact-wakoshi-boundary-endpoint',
    matchPolicy:{
      sameTrainTimetableRecordRequired:true,
      exactBoundaryEndpointRequired:true,
      explicitOtherOperatorStationRequired:true,
      destinationAloneMayEstablishIdentity:false,
      originAloneMayEstablishIdentity:false,
      timeProximityAloneMayEstablishIdentity:false,
      trainNumberAloneMayEstablishIdentity:false,
    },
    runtimeRule:{requiredMatch:['identityKey','fromRailway','toRailway']},
  };
  if(!recordMap.has(identityKey)){
    recordMap.set(identityKey,record);
    added++;
  }
}

trips.version=Math.max(Number(trips.version)||0,6);
trips.policy={...(trips.policy||{}),runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,genericBoundaryChaining:false};
trips.records=[...recordMap.values()].sort((a,b)=>String(a.id||'').localeCompare(String(b.id||'')));
trips.wakoshiEndpointEvidence={
  sourceFile:identityFile,
  sourceGeneratedAt:String(identity.generatedAt||''),
  boundaryId:BOUNDARY,
  evidenceRecords:evidence.length,
  addedRecords:added,
  directions:counts,
  policy:{
    sameTrainTimetableRecordRequired:true,
    exactBoundaryEndpointRequired:true,
    destinationAloneMayEstablishIdentity:false,
    timeProximityAloneMayEstablishIdentity:false,
    trainNumberAloneMayEstablishIdentity:false,
  },
};
writeJson(tripsFile,trips);

coverage.version=Math.max(Number(coverage.version)||0,6);
coverage.summary={...(coverage.summary||{}),throughRecords:trips.records.length,odptExplicitBoundaryEndpointThroughRecords:trips.records.filter(row=>row.identityType==='odpt-explicit-boundary-endpoint').length};
coverage.wakoshiEndpointEvidence={sourceFile:identityFile,sourceGeneratedAt:String(identity.generatedAt||''),boundaryId:BOUNDARY,evidenceRecords:evidence.length,addedRecords:added,directions:counts};
writeJson(coverageFile,coverage);

console.log(JSON.stringify({sourceMetroRecords:rows.length,evidenceRecords:evidence.length,addedRecords:added,directions:counts,totalThroughRecords:trips.records.length},null,2));
