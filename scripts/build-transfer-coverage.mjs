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
function isFallbackRule(rule){
  return String(rule&&rule.sourceType||'').includes('fallbackMinutes')||String(rule&&rule.label||'').includes('暫定・安全側');
}
const blockedStationPairs=new Set((blocks.blockedStationPairs||[]).map(value=>{
  const parts=String(value).split('\u0001');
  return stationPair(parts[0],parts[1]);
}));

const coveredExact=new Map();
for(const rule of rules.rules||[]){
  const key=[stationPair(rule.fromStation,rule.toStation),pair(rule.fromRailway,rule.toRailway)].join('\u0002');
  const state=isFallbackRule(rule)?'fallback':'curated';
  if(!coveredExact.has(key)||state==='curated')coveredExact.set(key,state);
}

function candidateState(row){
  const railwayPair=pair(row.railwayA,row.railwayB);
  const stationPairs=[];
  for(const a of row.stationIdsA||[])for(const b of row.stationIdsB||[])stationPairs.push(stationPair(a,b));
  const explicit=(row.sources||[]).includes('connecting-station');
  const blocked=!explicit&&stationPairs.length>0&&stationPairs.every(key=>blockedStationPairs.has(key));
  if(blocked)return 'blocked';
  const states=stationPairs.map(key=>coveredExact.get([key,railwayPair].join('\u0002'))).filter(Boolean);
  if(states.includes('curated'))return 'curated';
  if(states.includes('fallback'))return 'fallback';
  return 'uncurated';
}
function compact(row){return{
  railwayA:row.railwayA,railwayAName:row.railwayAName,railwayB:row.railwayB,railwayBName:row.railwayBName,
  sameOperator:row.sameOperator,distanceMeters:row.distanceMeters,fallbackMinutes:row.fallbackMinutes,sources:row.sources
};}

const rows=(candidates.candidates||[]).map(row=>({...row,state:candidateState(row)}));
const places=new Map();
for(const row of rows){
  if(!places.has(row.placeLabel))places.set(row.placeLabel,{place:row.placeLabel,total:0,curated:0,fallback:0,uncurated:0,blocked:0,crossOperatorUncurated:0,railways:new Set()});
  const p=places.get(row.placeLabel);p.total++;p[row.state]++;
  if(row.state==='uncurated'&&!row.sameOperator)p.crossOperatorUncurated++;
  p.railways.add(row.railwayAName);p.railways.add(row.railwayBName);
}
const placeRows=[...places.values()].map(p=>({
  place:p.place,totalPairs:p.total,curatedPairs:p.curated,fallbackPairs:p.fallback,uncuratedPairs:p.uncurated,blockedPairs:p.blocked,
  crossOperatorUncuratedPairs:p.crossOperatorUncurated,railwayCount:p.railways.size,
  priorityScore:p.uncurated+p.crossOperatorUncurated*1.5
})).sort((a,b)=>b.priorityScore-a.priorityScore||b.uncuratedPairs-a.uncuratedPairs||b.fallbackPairs-a.fallbackPairs||a.place.localeCompare(b.place,'ja'));

const generatedRules=rules.rules||[];
const summary={
  candidatePairs:rows.length,
  curatedPairs:rows.filter(r=>r.state==='curated').length,
  fallbackPairs:rows.filter(r=>r.state==='fallback').length,
  uncuratedPairs:rows.filter(r=>r.state==='uncurated').length,
  blockedPairs:rows.filter(r=>r.state==='blocked').length,
  curatedSourceRules:generatedRules.filter(rule=>!isFallbackRule(rule)).length,
  fallbackGeneratedRules:generatedRules.filter(isFallbackRule).length,
  transferPlaces:new Set(rows.map(r=>r.placeLabel)).size
};
const priorityDetails=placeRows.filter(place=>place.uncuratedPairs>0).slice(0,30).map(place=>({
  ...place,
  crossOperatorPairs:rows.filter(r=>r.state==='uncurated'&&r.placeLabel===place.place&&!r.sameOperator).map(compact),
  sameOperatorPairs:rows.filter(r=>r.state==='uncurated'&&r.placeLabel===place.place&&r.sameOperator).map(compact)
}));
const output={
  generatedAt:new Date().toISOString(),
  candidateGeneratedAt:candidates.generatedAt||null,
  rulesGeneratedAt:rules.generatedAt||null,
  methodology:'Candidate railway pairs are classified as curated when backed by an explicit transfer rule, fallback when covered by conservative fallbackMinutes, blocked for false same-name/nearby links, and uncurated only when no usable rule exists.',
  summary,
  priorityPlaces:placeRows.slice(0,100),
  priorityDetails,
  uncurated:rows.filter(r=>r.state==='uncurated').map(r=>({place:r.placeLabel,...compact(r)})),
  fallback:rows.filter(r=>r.state==='fallback').map(r=>({place:r.placeLabel,...compact(r)}))
};
fs.writeFileSync(path.join(transit,'transfer-coverage.json'),JSON.stringify(output,null,2)+'\n');
console.log(JSON.stringify(summary));
console.log('Top priorities:',placeRows.filter(p=>p.uncuratedPairs>0).slice(0,15).map(p=>`${p.place}:${p.uncuratedPairs}`).join(', ')||'none');
