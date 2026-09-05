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
const Y_WAKOSHI='odpt.Station:TokyoMetro.Yurakucho.Wakoshi';
const T_WAKOSHI='odpt.Station:Tobu.Tojo.Wakoshi';
const TOBU_PREFIX='odpt.Station:Tobu.Tojo.';
const Y_PREFIX='odpt.Station:TokyoMetro.Yurakucho.';
const BOUNDARY='yurakucho-tojo-wakoshi';

const identity=readJson(identityFile);
const trips=readJson(tripsFile);
const coverage=readJson(coverageFile);
if(identity?.policy?.runtimeInference!==false||identity?.policy?.timeGapMayEstablishTrainIdentity!==false||identity?.policy?.trainNumberMayEstablishTrainIdentity!==false)throw new Error('ODPT identity sidecar must remain fail-closed');

const metroRows=(identity.records||[]).filter(row=>row&&row.railway===Y&&row.timetableId);
const tobuRows=(identity.records||[]).filter(row=>row&&row.railway===TJ&&row.timetableId);
const recordMap=new Map((trips.records||[]).map(row=>[String(row.id||''),row]));
const evidence=[];
const counts={tobuToYurakucho:0,yurakuchoToTobu:0,metroSource:0,tobuSource:0};
const stationOf=(stop)=>String(stop?.station||'');
const filtered=(values,prefix)=>(Array.isArray(values)?values:[]).map(String).filter(value=>value.startsWith(prefix));

// Outbound: the exact Tokyo Metro Yurakucho TrainTimetable segment ends at
// Wakoshi and the same record explicitly publishes a Tobu Tojo destination.
for(const row of metroRows){
  const last=stationOf(row.lastStop);
  const destinations=filtered(row.destination,TOBU_PREFIX);
  if(last!==Y_WAKOSHI||!destinations.length)continue;
  evidence.push({row,direction:'yurakucho-to-tobu',externalStations:destinations,fromRailway:Y,toRailway:TJ,boundaryEndpoint:Y_WAKOSHI,endpointRole:'lastStop',sourceSide:'metro'});
  counts.yurakuchoToTobu++;counts.metroSource++;
}

// Inbound: Metro's sidecar does not expose the reciprocal external origin for
// current Line 8 trains. Tobu's exact TrainTimetable does: its segment ends at
// Tobu Wakoshi and the same record explicitly publishes a Yurakucho destination.
// This is a two-sided exact-endpoint proof, not a clock-time or train-number join.
for(const row of tobuRows){
  const last=stationOf(row.lastStop);
  const destinations=filtered(row.destination,Y_PREFIX);
  if(last!==T_WAKOSHI||!destinations.length)continue;
  evidence.push({row,direction:'tobu-to-yurakucho',externalStations:destinations,fromRailway:TJ,toRailway:Y,boundaryEndpoint:T_WAKOSHI,endpointRole:'lastStop',sourceSide:'tobu'});
  counts.tobuToYurakucho++;counts.tobuSource++;
}

if(counts.tobuToYurakucho<1||counts.yurakuchoToTobu<1)throw new Error(`Bidirectional exact Yurakucho-Tobu Wakoshi endpoint evidence missing: ${JSON.stringify(counts)}`);

let added=0;
for(const item of evidence){
  const row=item.row;
  const identityKey=`odpt-endpoint-y:${digest([row.timetableId,item.direction,item.externalStations,item.boundaryEndpoint,item.sourceSide])}`;
  const record={
    id:identityKey,identityKey,identityType:'odpt-explicit-boundary-endpoint',status:'verified',corridor:'line8',
    sourceOperator:row.sourceOperator||(item.sourceSide==='tobu'?'tobu':'tokyometro'),sourceSide:item.sourceSide,
    sourceTimetableId:row.timetableId,sourceTrainId:row.trainId||'',calendars:row.calendars||[],trainType:row.trainType||'',trainNumber:row.trainNumber||'',
    fromRailway:item.fromRailway,toRailway:item.toRailway,routeRailways:[item.fromRailway,item.toRailway],
    transitions:[{fromRailway:item.fromRailway,toRailway:item.toRailway,boundaryStation:item.boundaryEndpoint}],classification:'through',canonicalBoundaryId:BOUNDARY,boundaryEndpoint:item.boundaryEndpoint,
    externalOriginStations:[],externalDestinationStations:item.externalStations,
    exactEndpointRole:item.endpointRole,
    evidence:'same-odpt-train-timetable+explicit-other-operator-destination+exact-wakoshi-boundary-endpoint',
    matchPolicy:{sameTrainTimetableRecordRequired:true,exactBoundaryEndpointRequired:true,explicitOtherOperatorStationRequired:true,twoSidedSourceRecordsAllowed:true,destinationAloneMayEstablishIdentity:false,originAloneMayEstablishIdentity:false,timeProximityAloneMayEstablishIdentity:false,trainNumberAloneMayEstablishIdentity:false},
    runtimeRule:{requiredMatch:['identityKey','fromRailway','toRailway']},
  };
  if(!recordMap.has(identityKey)){recordMap.set(identityKey,record);added++;}
}
trips.version=Math.max(Number(trips.version)||0,8);
trips.policy={...(trips.policy||{}),runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,genericBoundaryChaining:false};
trips.records=[...recordMap.values()].sort((a,b)=>String(a.id||'').localeCompare(String(b.id||'')));
trips.yurakuchoWakoshiEndpointEvidence={sourceFile:identityFile,boundaryId:BOUNDARY,evidenceRecords:evidence.length,addedRecords:added,directions:counts,policy:{sameTrainTimetableRecordRequired:true,exactBoundaryEndpointRequired:true,twoSidedSourceRecordsAllowed:true,destinationAloneMayEstablishIdentity:false,timeProximityAloneMayEstablishIdentity:false,trainNumberAloneMayEstablishIdentity:false}};
writeJson(tripsFile,trips);
coverage.version=Math.max(Number(coverage.version)||0,8);
coverage.summary={...(coverage.summary||{}),throughRecords:trips.records.length,odptExplicitBoundaryEndpointThroughRecords:trips.records.filter(row=>row.identityType==='odpt-explicit-boundary-endpoint').length};
coverage.yurakuchoWakoshiEndpointEvidence={sourceFile:identityFile,boundaryId:BOUNDARY,evidenceRecords:evidence.length,addedRecords:added,directions:counts};
writeJson(coverageFile,coverage);
console.log(JSON.stringify({sourceMetroRecords:metroRows.length,sourceTobuRecords:tobuRows.length,evidenceRecords:evidence.length,addedRecords:added,directions:counts,totalThroughRecords:trips.records.length},null,2));
