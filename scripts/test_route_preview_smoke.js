'use strict';
const fs=require('fs');
const path=require('path');
const Core=require(process.cwd()+'/route-core.js');
global.RoutePlannerCore=Core;
require(process.cwd()+'/preview/transfer-guide/route-diversity.js');

const manifest=JSON.parse(fs.readFileSync('data/transit/manifest.json','utf8'));
const entities=[];
const indices=new Map();
const allowed=[];
let declaredLines=0;
for(const [slug,info] of Object.entries(manifest.operators||{})){
  if(!info||info.status!=='ok') continue;
  const base=path.join('data','transit',slug);
  const entityPath=path.join(base,'entities.json');
  const indexPath=path.join(base,'timetable-index.json');
  if(fs.existsSync(entityPath)) entities.push(JSON.parse(fs.readFileSync(entityPath,'utf8')));
  if(fs.existsSync(indexPath)){
    const index=JSON.parse(fs.readFileSync(indexPath,'utf8'));
    for(const [railway,row] of Object.entries(index.lines||{})){
      if(!row||!row.file) continue;
      indices.set(railway,{base,row});
      allowed.push(railway);
    }
  }
  declaredLines+=Number(info.timetableLines)||0;
}
if(declaredLines<120) throw new Error(`unexpected timetable coverage: ${declaredLines}`);
const model=Core.createModel(entities);
if(model.stations.length<500) throw new Error(`unexpected station coverage: ${model.stations.length}`);

const previewSource=fs.readFileSync('preview/transfer-guide/preview.js','utf8');
const compareSource=fs.readFileSync('preview/transfer-guide/preview-compare.js','utf8');
const indexSource=fs.readFileSync('preview/transfer-guide/index.html','utf8');
if(!previewSource.includes('limit:24')) throw new Error('preview path limit is not 24');
if(!previewSource.includes('choices.slice(0,12)')) throw new Error('preview display limit is not 12');
if(!previewSource.includes('attempt<3')) throw new Error('preview does not collect multiple departures per path');
if(!previewSource.includes('diversifyChoices(sortChoices(choices))')) throw new Error('preview caps choices before diversity selection');
if(!previewSource.includes('routeCorridorKey')) throw new Error('preview has no corridor-level diversity selection');
if(!indexSource.includes('route-diversity.js')) throw new Error('diversity search layer is not loaded by preview');
if(!compareSource.includes('byFamily')||!compareSource.includes('同系統の別案')) throw new Error('comparison does not prioritize route families');

function loadTable(railway){
  const entry=indices.get(railway);
  if(!entry) return null;
  const filename=path.join(entry.base,entry.row.file);
  if(!fs.existsSync(filename)) throw new Error(`timetable file missing: ${filename}`);
  return JSON.parse(fs.readFileSync(filename,'utf8'));
}
function resolvePair(from,to){
  const a=model.resolveInput(from),b=model.resolveInput(to);
  if(!a.group||!b.group) throw new Error(`station resolution failed: ${from} -> ${to}`);
  return {a,b};
}
function findTimed(from,to,earliest,service){
  const {a,b}=resolvePair(from,to);
  const paths=model.candidatePaths(a.group,b.group,{allowedRailways:allowed,limit:24});
  if(!paths.length) throw new Error(`candidate path missing: ${from} -> ${to}`);
  for(const candidate of paths){
    const tables={};
    for(const segment of model.segmentsFrom(candidate)){
      if(!(segment.railway in tables)) tables[segment.railway]=loadTable(segment.railway);
    }
    const timed=model.timedItinerary(candidate,tables,earliest,service,5);
    if(timed&&Number.isFinite(timed.departure)&&Number.isFinite(timed.arrival)&&timed.arrival>timed.departure){
      return {timed,path:candidate};
    }
  }
  throw new Error(`timed route missing: ${from} -> ${to}`);
}
function family(path){
  const ids=[];
  for(const segment of model.segmentsFrom(path)){
    if(segment.railway&&ids[ids.length-1]!==segment.railway) ids.push(segment.railway);
  }
  return ids.join('>');
}
function familyLabels(path){return model.segmentsFrom(path).map(s=>s.label||s.railway).join(' → ');}

const cases=[
  ['横浜','元町・中華街',600,'weekday'],
  ['元町・中華街','横浜',600,'holiday'],
  ['渋谷','みなとみらい',600,'weekday'],
  ['新宿','横浜',600,'weekday'],
];
for(const row of cases){
  const [from,to,minute,service]=row;
  const result=findTimed(from,to,minute,service);
  console.log(`${service} ${from}->${to}: ${result.timed.departure}->${result.timed.arrival}, transfers=${result.timed.transfers}`);
}

// A well-connected pair should expose several structurally different paths.
{
  const {a,b}=resolvePair('武蔵小杉','池袋');
  const paths=model.candidatePaths(a.group,b.group,{allowedRailways:allowed,limit:24});
  const families=new Set(paths.map(family));
  console.log(`武蔵小杉->池袋 candidate paths: ${paths.length}, families: ${families.size}`);
  if(families.size<3) throw new Error(`route-family repertoire still too small: ${families.size} families`);
}

// The preview keeps later trains on the same path available internally.
{
  const {a,b}=resolvePair('横浜','元町・中華街');
  const paths=model.candidatePaths(a.group,b.group,{allowedRailways:allowed,limit:24});
  let departures=[];
  for(const candidate of paths){
    const tables={};
    for(const segment of model.segmentsFrom(candidate)){
      if(!(segment.railway in tables)) tables[segment.railway]=loadTable(segment.railway);
    }
    let cursor=600;
    departures=[];
    for(let attempt=0;attempt<3;attempt++){
      const timed=model.timedItinerary(candidate,tables,cursor,'weekday',5);
      if(!timed) break;
      departures.push(timed.departure);
      cursor=timed.departure+1;
    }
    if(departures.length>=3) break;
  }
  console.log(`横浜->元町・中華街 successive departures: ${departures.join(', ')}`);
  if(departures.length<3) throw new Error('could not obtain three successive departure choices');
  if(!(departures[0]<departures[1]&&departures[1]<departures[2])) throw new Error('successive departure choices are not strictly increasing');
}

// Regression for the route-family problem discussed during development:
// Yashio -> Hiyoshi must not be limited to Kita-senju/Minami-senju/Akihabara variants of one trunk.
{
  const {a,b}=resolvePair('八潮','日吉');
  const paths=model.candidatePaths(a.group,b.group,{allowedRailways:allowed,limit:24});
  const families=[];
  const seen=new Set();
  paths.forEach(p=>{const key=family(p);if(!seen.has(key)){seen.add(key);families.push(familyLabels(p));}});
  console.log(`八潮->日吉 candidate paths: ${paths.length}, route families: ${families.length}`);
  families.slice(0,8).forEach((value,index)=>console.log(`  family${index+1}: ${value}`));
  if(paths.length<=8) throw new Error(`diversity layer did not expand beyond legacy 8-path cap: ${paths.length}`);
  if(families.length<4) throw new Error(`Yashio -> Hiyoshi still over-concentrated: only ${families.length} route families`);
}

console.log(`coverage: ${declaredLines} lines, ${model.stations.length} station groups`);
