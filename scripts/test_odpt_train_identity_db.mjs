import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const repoRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const script=path.join(repoRoot,'scripts','enrich-through-service-db.mjs');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'through-identity-'));
const write=(file,value)=>{const full=path.join(tmp,file);fs.mkdirSync(path.dirname(full),{recursive:true});fs.writeFileSync(full,JSON.stringify(value,null,2)+'\n');};

const A='odpt.Railway:Test.A';
const B='odpt.Railway:Test.B';
const X='odpt.Railway:Test.X';
const D='odpt.Station:Test.B.D';

write('data/transit/a/entities.json',{
  Station:[{'owl:sameAs':D,'odpt:railway':[B]}],
  Railway:[
    {'owl:sameAs':A,'odpt:stationOrder':[]},
    {'owl:sameAs':B,'odpt:stationOrder':[{'odpt:station':D}]}
  ]
});
write('data/transit/through-service-families.json',{
  version:1,
  policy:{runtimeInference:false,timeGapMayEstablishTrainIdentity:false,genericBoundaryChaining:false},
  families:[{id:'test-a-b',status:'verified',paths:[[A,B]],sourceUrls:['https://example.invalid/official']}]
});
write('data/transit/through-service-trips.json',{
  version:2,
  generatedAt:'2026-09-04T00:00:00Z',
  policy:{runtimeInference:false,timeGapMayEstablishTrainIdentity:false,genericBoundaryChaining:false},
  records:[]
});
write('data/transit/through-service-coverage.json',{version:2,generatedAt:'2026-09-04T00:00:00Z',summary:{throughRecords:0}});
write('data/transit/odpt-train-identities.json',{
  version:1,
  generatedAt:'2026-09-04T00:00:00Z',
  policy:{runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,authoritativeLinks:['odpt:previousTrainTimetable','odpt:nextTrainTimetable']},
  records:[
    {timetableId:'tt:A1',sourceOperator:'a',railway:A,trainId:'train:1',trainNumber:'100',calendars:['weekday'],nextTrainTimetables:['tt:B1'],previousTrainTimetables:[],destination:[],externalDestination:false,lastStop:{station:'odpt.Station:Test.A.Border'}},
    {timetableId:'tt:B1',sourceOperator:'b',railway:B,trainId:'train:1',trainNumber:'100',calendars:['weekday'],nextTrainTimetables:[],previousTrainTimetables:['tt:A1'],destination:[D],externalDestination:false,firstStop:{station:'odpt.Station:Test.B.Border'}},
    // Same train number alone must never establish identity.
    {timetableId:'tt:A-number-only',sourceOperator:'a',railway:A,trainId:'',trainNumber:'777',calendars:['weekday'],nextTrainTimetables:[],previousTrainTimetables:[],destination:[],externalDestination:false},
    {timetableId:'tt:B-number-only',sourceOperator:'b',railway:B,trainId:'',trainNumber:'777',calendars:['weekday'],nextTrainTimetables:[],previousTrainTimetables:[],destination:[],externalDestination:false},
    // Published external destination + verified service family is allowed.
    {timetableId:'tt:A-destination',sourceOperator:'a',railway:A,trainId:'train:2',trainNumber:'200',calendars:['weekday'],nextTrainTimetables:[],previousTrainTimetables:[],destination:[D],externalDestination:true},
    // Even an authoritative ODPT link is not promoted through an unverified family.
    {timetableId:'tt:A-unknown',sourceOperator:'a',railway:A,trainId:'train:3',trainNumber:'300',calendars:['weekday'],nextTrainTimetables:['tt:X1'],previousTrainTimetables:[],destination:[],externalDestination:false},
    {timetableId:'tt:X1',sourceOperator:'x',railway:X,trainId:'train:3',trainNumber:'300',calendars:['weekday'],nextTrainTimetables:[],previousTrainTimetables:['tt:A-unknown'],destination:[],externalDestination:false}
  ]
});

const result=spawnSync(process.execPath,[script],{cwd:tmp,encoding:'utf8'});
if(result.status!==0)throw new Error(`enricher failed\n${result.stdout}\n${result.stderr}`);
const db=JSON.parse(fs.readFileSync(path.join(tmp,'data/transit/through-service-trips.json'),'utf8'));
const coverage=JSON.parse(fs.readFileSync(path.join(tmp,'data/transit/through-service-coverage.json'),'utf8'));

const links=db.records.filter((row)=>row.identityType==='odpt-train-timetable-link');
const destinations=db.records.filter((row)=>row.identityType==='odpt-exact-published-destination');
if(links.length!==1)throw new Error(`Expected one verified exact ODPT link, got ${links.length}`);
if(links[0].sourceTimetableId!=='tt:A1'||links[0].targetTimetableId!=='tt:B1')throw new Error('Wrong exact-link record');
if(destinations.length!==1||destinations[0].sourceTimetableId!=='tt:A-destination')throw new Error('Published-destination evidence was not classified correctly');
if(db.records.some((row)=>String(row.id).includes('number-only')))throw new Error('Train number was incorrectly used as identity');
if(db.records.some((row)=>row.targetTimetableId==='tt:X1'))throw new Error('Unverified family was incorrectly promoted to through service');
if(db.policy.trainNumberMayEstablishTrainIdentity!==false)throw new Error('train-number identity policy must be false');
if((coverage.summary.odptIdentityUnresolved||0)<1)throw new Error('Unverified authoritative link should appear in unresolved coverage');

console.log('ODPT train-identity through-service DB test passed');
