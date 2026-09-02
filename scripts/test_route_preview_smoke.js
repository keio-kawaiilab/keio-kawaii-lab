'use strict';
const fs=require('fs');
const path=require('path');
const Core=require(process.cwd()+'/route-core.js');

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
if(!previewSource.includes('limit:24')) throw new Error('preview path limit is not 24');
if(!previewSource.includes('choices.slice(0,12)')) throw new Error('preview display limit is not 12');
if(!previewSource.includes('attempt<3')) throw new Error('preview does not collect multiple departures per path');

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
  console.log(`武蔵小杉->池袋 candidate paths: ${paths.length}`);
  if(paths.length<4) throw new Error(`route repertoire still too small: ${paths.length} paths`);
}

// The preview now keeps later trains on the same path as separate comparison choices.
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

console.log(`coverage: ${declaredLines} lines, ${model.stations.length} station groups`);
