const fs=require('fs');
const path=require('path');
const core=require('../route-core.js');

const readJson=(file)=>JSON.parse(fs.readFileSync(path.join(__dirname,'..',file),'utf8'));
const slugs=['tokyu','tokyo-metro','seibu'];
const payloads=slugs.map(slug=>readJson(`data/transit/${slug}/entities.json`));
const model=core.createModel(payloads);

const railways=[
  'odpt.Railway:Tokyu.Toyoko',
  'odpt.Railway:TokyoMetro.Fukutoshin',
  'odpt.Railway:Seibu.SeibuYurakucho',
  'odpt.Railway:Seibu.Ikebukuro'
];
const slugForRailway={
  'odpt.Railway:Tokyu.Toyoko':'tokyu',
  'odpt.Railway:TokyoMetro.Fukutoshin':'tokyo-metro',
  'odpt.Railway:Seibu.SeibuYurakucho':'seibu',
  'odpt.Railway:Seibu.Ikebukuro':'seibu'
};
const tables={};
for(const railway of railways){
  const slug=slugForRailway[railway];
  const index=readJson(`data/transit/${slug}/timetable-index.json`);
  const info=index.lines[railway];
  if(!info||!info.file)throw new Error(`No timetable index for ${railway}`);
  tables[railway]=readJson(`data/transit/${slug}/${info.file}`);
}

const origin=model.resolveInput('横浜').group;
const destination=model.resolveInput('小手指').group;
if(!origin||!destination)throw new Error('Could not resolve Yokohama/Kotesashi');
const candidates=model.candidatePaths(origin,destination,{allowedRailways:railways,limit:8});
const expected=railways.join('|');
const route=candidates.find(candidate=>model.segmentsFrom(candidate).map(segment=>segment.railway).join('|')===expected);
if(!route){
  const actual=candidates.map(candidate=>model.segmentsFrom(candidate).map(segment=>segment.railway).join(' > '));
  throw new Error(`Expected Toyoko > Fukutoshin > SeibuYurakucho > Ikebukuro path not found. Candidates: ${actual.join(' / ')}`);
}

const toyoko=tables['odpt.Railway:Tokyu.Toyoko'];
const originId='odpt.Station:Tokyu.Toyoko.Yokohama';
const destinationId='odpt.Station:Seibu.Ikebukuro.Kotesashi';
const stationIndex=toyoko.stations.indexOf(originId);
const destinationIndex=toyoko.destinations.indexOf(destinationId);
if(stationIndex<0||destinationIndex<0)throw new Error('Toyoko timetable does not contain Yokohama/Kotesashi destination data');

const departures=[];
for(const board of toyoko.boards||[]){
  if(!Array.isArray(board)||board[0]!==stationIndex)continue;
  for(const row of board[3]||[]){
    if(Number(row[2])!==destinationIndex)continue;
    const minute=Number(row[0]);
    if(!Number.isFinite(minute))continue;
    const calendar=String(toyoko.calendars[board[1]]||'').toLowerCase();
    const service=calendar.includes('weekday')||calendar.includes('平日')?'weekday':'holiday';
    departures.push({minute,service});
  }
}
if(!departures.length)throw new Error('No Yokohama -> Kotesashi departure found in current Toyoko timetable');
departures.sort((a,b)=>a.minute-b.minute);

let success=null;
const failures=[];
for(const departure of departures.slice(0,30)){
  const timed=model.timedItinerary(route,tables,departure.minute,departure.service,5);
  if(timed&&timed.transfers===0){success={departure,timed};break;}
  failures.push({departure,transfers:timed&&timed.transfers,segments:timed&&timed.segments&&timed.segments.map(s=>({railway:s.railway,departure:s.departure,arrival:s.arrival,destination:s.destination,through:s.throughFromPrevious}))});
}
if(!success)throw new Error(`No real Toyoko -> Kotesashi through itinerary was recognized. Sample failures: ${JSON.stringify(failures.slice(0,3))}`);

console.log(JSON.stringify({
  result:'real cross-operator through-service test passed',
  departure:success.departure,
  transfers:success.timed.transfers,
  segments:success.timed.segments.map(segment=>({railway:segment.railway,departure:segment.departure,arrival:segment.arrival,destination:segment.destination,through:!!segment.throughFromPrevious}))
},null,2));
