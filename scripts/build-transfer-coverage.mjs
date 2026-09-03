import fs from 'node:fs';
import path from 'node:path';

const root=process.cwd();
const transit=path.join(root,'data','transit');
const read=name=>JSON.parse(fs.readFileSync(path.join(transit,name),'utf8'));
const candidates=read('transfer-candidates.json');
const rules=read('transfer-rules.json');
const blocks=fs.existsSync(path.join(transit,'transfer-blocks.json'))?read('transfer-blocks.json'):{blockedStationPairs:[]};

function pair(a,b){return [String(a||''),String(b||'')].sort().join('\u0001');}
function stationPair(a,b){return pair(a,b);}
const blockedStationPairs=new Set((blocks.blockedStationPairs||[]).map(value=>{
  const parts=String(value).split('\u0001');
  return stationPair(parts[0],parts[1]);
}));

const coveredExact=new Set();
for(const rule of rules.rules||[]){
  coveredExact.add([
    stationPair(rule.fromStation,rule.toStation),
    pair(rule.fromRailway,rule.toRailway)
  ].join('\u0002'));
}

function candidateState(row){
  const railwayPair=pair(row.railwayA,row.railwayB);
  const stationPairs=[];
  for(const a of row.stationIdsA||[])for(const b of row.stationIdsB||[])stationPairs.push(stationPair(a,b));
  const explicit=(row.sources||[]).includes('connecting-station');
  const blocked=!explicit&&stationPairs.length>0&&stationPairs.every(key=>blockedStationPairs.has(key));
  const covered=stationPairs.some(key=>coveredExact.has([key,railwayPair].join('\u0002')));
  return blocked?'blocked':covered?'curated':'uncurated';
}
function compact(row){return{
  railwayA:row.railwayA,railwayAName:row.railwayAName,railwayB:row.railwayB,railwayBName:row.railwayBName,
  sameOperator:row.sameOperator,distanceMeters:row.distanceMeters,fallbackMinutes:row.fallbackMinutes,sources:row.sources
};}

const rows=(candidates.candidates||[]).map(row=>({...row,state:candidateState(row)}));
const places=new Map();
for(const row of rows){
  if(!places.has(row.placeLabel))places.set(row.placeLabel,{place:row.placeLabel,total:0,curated:0,uncurated:0,blocked:0,crossOperatorUncurated:0,railways:new Set()});
  const p=places.get(row.placeLabel);p.total++;p[row.state]++;
  if(row.state==='uncurated'&&!row.sameOperator)p.crossOperatorUncurated++;
  p.railways.add(row.railwayAName);p.railways.add(row.railwayBName);
}
const placeRows=[...places.values()].map(p=>({
  place:p.place,totalPairs:p.total,curatedPairs:p.curated,uncuratedPairs:p.uncurated,blockedPairs:p.blocked,
  crossOperatorUncuratedPairs:p.crossOperatorUncurated,railwayCount:p.railways.size,
  priorityScore:p.uncurated+p.crossOperatorUncurated*1.5
})).sort((a,b)=>b.priorityScore-a.priorityScore||b.uncuratedPairs-a.uncuratedPairs||a.place.localeCompare(b.place,'ja'));

const summary={
  candidatePairs:rows.length,
  curatedPairs:rows.filter(r=>r.state==='curated').length,
  uncuratedPairs:rows.filter(r=>r.state==='uncurated').length,
  blockedPairs:rows.filter(r=>r.state==='blocked').length,
  curatedSourceRules:(rules.rules||[]).length,
  transferPlaces:new Set(rows.map(r=>r.placeLabel)).size
};
const priorityDetails=placeRows.slice(0,30).map(place=>({
  ...place,
  crossOperatorPairs:rows.filter(r=>r.state==='uncurated'&&r.placeLabel===place.place&&!r.sameOperator).map(compact),
  sameOperatorPairs:rows.filter(r=>r.state==='uncurated'&&r.placeLabel===place.place&&r.sameOperator).map(compact)
}));
const output={
  generatedAt:new Date().toISOString(),
  candidateGeneratedAt:candidates.generatedAt||null,
  rulesGeneratedAt:rules.generatedAt||null,
  methodology:'Candidate railway pairs are matched against resolved exact transfer rules. False same-name/nearby station pairs are classified as blocked unless ODPT explicitly declares connectingStation.',
  summary,
  priorityPlaces:placeRows.slice(0,100),
  priorityDetails,
  uncurated:rows.filter(r=>r.state==='uncurated').map(r=>({place:r.placeLabel,...compact(r)}))
};
fs.writeFileSync(path.join(transit,'transfer-coverage.json'),JSON.stringify(output,null,2)+'\n');
console.log(JSON.stringify(summary));
console.log('Top priorities:',placeRows.slice(0,15).map(p=>`${p.place}:${p.uncuratedPairs}`).join(', '));
