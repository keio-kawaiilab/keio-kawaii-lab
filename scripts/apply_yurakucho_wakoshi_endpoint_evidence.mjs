#!/usr/bin/env node
import fs from 'node:fs';
import crypto from 'node:crypto';

const identityFile='data/transit/odpt-train-identities.json';
const tripsFile='data/transit/through-service-trips.json';
const coverageFile='data/transit/through-service-coverage.json';
const readJson=(file)=>JSON.parse(fs.readFileSync(file,'utf8'));
const writeJson=(file,value)=>fs.writeFileSync(file,JSON.stringify(value,null,2)+'\n','utf8');
const digest=(value)=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex').slice(0,24);

const Y='odpt.Railway:TokyoMetro.Yurakucho';
const TJ='odpt.Railway:Tobu.Tojo';
const WAKOSHI='odpt.Station:TokyoMetro.Yurakucho.Wakoshi';
const TOBU_PREFIX='odpt.Station:Tobu.Tojo.';
const BOUNDARY='yurakucho-tojo-wakoshi';

const identity=readJson(identityFile);
const trips=readJson(tripsFile);
const coverage=readJson(coverageFile);
if(identity?.policy?.runtimeInference!==false||identity?.policy?.timeGapMayEstablishTrainIdentity!==false||identity?.policy?.trainNumberMayEstablishTrainIdentity!==false)throw new Error('ODPT identity sidecar must remain fail-closed');

const rows=(identity.records||[]).filter(row=>row&&row.railway===Y&&row.timetableId);
const recordMap=new Map((trips.records||[]).map(row=>[String(row.id||''),row]));
const evidence=[];
const counts={tobuToYurakucho:0,yurakuchoToTobu:0};
const stationOf=(stop)=>String(stop?.station||'');
const tobuStations=(values)=>(Array.isArray(values)?values:[]).map(String).filter(value=>value.startsWith(TOBU_PREFIX));

for(const row of rows){
  const first=stationOf(row.firstStop);
  const last=stationOf(row.lastStop);
  const origins=tobuStations(row.origin);
  const destinations=tobuStations(row.destination);
  if(first===WAKOSHI&&origins.length){evidence.push({row,direction:'tobu-to-yurakucho',externalStations:origins,fromRailway:TJ,toRailway:Y});counts.tobuToYurakucho++;}
  if(last===WAKOSHI&&destinations.length){evidence.push({row,direction:'yurakucho-to-tobu',externalStations:destinations,fromRailway:Y,toRailway:TJ});counts.yurakuchoToTobu++;}
}
if(counts.tobuToYurakucho<1||counts.yurakuchoToTobu<1)throw new Error(`Bidirectional exact Yurakucho-Tobu Wakoshi endpoint evidence missing: ${JSON.stringify(counts)}`);

let added=0;
for(const item of evidence){
  const row=item.row;
  const identityKey=`odpt-endpoint-y:${digest([row.timetableId,item.direction,item.externalStations,WAKOSHI])}`;
  const record={
    id:identityKey,identityKey,identityType:'odpt-explicit-boundary-endpoint',status:'verified',corridor:'line8',
    sourceOperator:row.sourceOperator||'tokyometro',sourceTimetableId:row.timetableId,sourceTrainId:row.trainId||'',calendars:row.calendars||[],trainType:row.trainType||'',trainNumber:row.trainNumber||'',
    fromRailway:item.fromRailway,toRailway:item.toRailway,routeRailways:[item.fromRailway,item.toRailway],
    transitions:[{fromRailway:item.fromRailway,toRailway:item.toRailway,boundaryStation:WAKOSHI}],classification:'through',canonicalBoundaryId:BOUNDARY,boundaryEndpoint:WAKOSHI,
    externalOriginStations:item.direction==='tobu-to-yurakucho'?item.externalStations:[],externalDestinationStations:item.direction==='yurakucho-to-tobu'?item.externalStations:[],
    exactEndpointRole:item.direction==='tobu-to-yurakucho'?'firstStop':'lastStop',
    evidence:'same-odpt-train-timetable+explicit-tobu-origin-or-destination+exact-yurakucho-wakoshi-boundary-endpoint',
    matchPolicy:{sameTrainTimetableRecordRequired:true,exactBoundaryEndpointRequired:true,explicitOtherOperatorStationRequired:true,destinationAloneMayEstablishIdentity:false,originAloneMayEstablishIdentity:false,timeProximityAloneMayEstablishIdentity:false,trainNumberAloneMayEstablishIdentity:false},
    runtimeRule:{requiredMatch:['identityKey','fromRailway','toRailway']},
  };
  if(!recordMap.has(identityKey)){recordMap.set(identityKey,record);added++;}
}
trips.version=Math.max(Number(trips.version)||0,7);
trips.policy={...(trips.policy||{}),runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,genericBoundaryChaining:false};
trips.records=[...recordMap.values()].sort((a,b)=>String(a.id||'').localeCompare(String(b.id||'')));
trips.yurakuchoWakoshiEndpointEvidence={sourceFile:identityFile,boundaryId:BOUNDARY,evidenceRecords:evidence.length,addedRecords:added,directions:counts,policy:{sameTrainTimetableRecordRequired:true,exactBoundaryEndpointRequired:true,destinationAloneMayEstablishIdentity:false,timeProximityAloneMayEstablishIdentity:false,trainNumberAloneMayEstablishIdentity:false}};
writeJson(tripsFile,trips);
coverage.version=Math.max(Number(coverage.version)||0,7);
coverage.summary={...(coverage.summary||{}),throughRecords:trips.records.length,odptExplicitBoundaryEndpointThroughRecords:trips.records.filter(row=>row.identityType==='odpt-explicit-boundary-endpoint').length};
coverage.yurakuchoWakoshiEndpointEvidence={sourceFile:identityFile,boundaryId:BOUNDARY,evidenceRecords:evidence.length,addedRecords:added,directions:counts};
writeJson(coverageFile,coverage);
console.log(JSON.stringify({sourceMetroRecords:rows.length,evidenceRecords:evidence.length,addedRecords:added,directions:counts,totalThroughRecords:trips.records.length},null,2));
