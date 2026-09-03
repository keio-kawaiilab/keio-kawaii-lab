import fs from 'node:fs';
import path from 'node:path';

const root=process.cwd();
const transit=path.join(root,'data','transit');
const candidates=JSON.parse(fs.readFileSync(path.join(transit,'transfer-candidates.json'),'utf8'));
const baseSources=JSON.parse(fs.readFileSync(path.join(transit,'transfer-rule-sources.json'),'utf8'));
const sourceDocs=[{file:'transfer-rule-sources.json',data:baseSources}];
const batchDir=path.join(transit,'transfer-rule-sources.d');
if(fs.existsSync(batchDir)){
  for(const file of fs.readdirSync(batchDir).filter(name=>name.endsWith('.json')).sort()){
    sourceDocs.push({file:`transfer-rule-sources.d/${file}`,data:JSON.parse(fs.readFileSync(path.join(batchDir,file),'utf8'))});
  }
}
const sourceEntries=[];
for(const doc of sourceDocs){
  const defaults=doc.data.defaults||baseSources.defaults||{};
  for(const rule of doc.data.rules||[])sourceEntries.push({source:rule,defaults,file:doc.file});
}
const output=[];

function hasRailwayIds(rule){return Boolean(rule&&rule.railwayA&&rule.railwayB);}
function samePair(row,rule){
  if(hasRailwayIds(rule)){
    return (row.railwayA===rule.railwayA&&row.railwayB===rule.railwayB)||
      (row.railwayA===rule.railwayB&&row.railwayB===rule.railwayA);
  }
  return (row.railwayAName===rule.railwayAName&&row.railwayBName===rule.railwayBName)||
    (row.railwayAName===rule.railwayBName&&row.railwayBName===rule.railwayAName);
}
function sourceAIsRowA(row,source){
  return hasRailwayIds(source)?row.railwayA===source.railwayA:row.railwayAName===source.railwayAName;
}
function sourceLabel(source,side){return String(source[`${side}Name`]||source[side]||'');}
function placeDiagnostics(place){
  const rows=(candidates.candidates||[]).filter(row=>row.placeLabel===place);
  const railways=new Map();
  for(const row of rows){railways.set(row.railwayA,row.railwayAName);railways.set(row.railwayB,row.railwayBName);}
  return [...railways.entries()].map(([id,name])=>`${name}=${id}`).sort().join(', ');
}

for(const entry of sourceEntries){
  const source=entry.source,defaults=entry.defaults;
  const matches=(candidates.candidates||[]).filter(row=>row.placeLabel===source.place&&samePair(row,source));
  if(matches.length!==1){
    throw new Error(`${entry.file}: ${source.place} ${sourceLabel(source,'railwayA')} / ${sourceLabel(source,'railwayB')}: expected 1 candidate, got ${matches.length}. Available railways at place: ${placeDiagnostics(source.place)}`);
  }
  const row=matches[0];
  const aIsRowA=sourceAIsRowA(row,source);
  const fromRailway=aIsRowA?row.railwayA:row.railwayB;
  const toRailway=aIsRowA?row.railwayB:row.railwayA;
  const fromStations=aIsRowA?row.stationIdsA:row.stationIdsB;
  const toStations=aIsRowA?row.stationIdsB:row.stationIdsA;
  const minutes=Number(source.minutes);
  if(!Number.isFinite(minutes)||minutes<0)throw new Error(`Invalid minutes for ${source.place}`);
  for(const fromStation of fromStations){
    for(const toStation of toStations){
      output.push({
        id:String(source.id||`${source.place}-${sourceLabel(source,'railwayA')}-${sourceLabel(source,'railwayB')}`),
        fromStation,
        toStation,
        fromRailway,
        toRailway,
        minutes,
        bidirectional:source.bidirectional??defaults.bidirectional??true,
        ...(source.reverseMinutes==null?{}:{reverseMinutes:Number(source.reverseMinutes)}),
        label:String(source.label??defaults.label??''),
        source:String(source.source||''),
        sourceType:String(source.sourceType??defaults.sourceType??''),
        verifiedAt:String(source.verifiedAt??defaults.verifiedAt??'')
      });
    }
  }
}

const seen=new Set();
for(const rule of output){
  const key=[rule.fromStation,rule.toStation,rule.fromRailway,rule.toRailway].join('\u0001');
  if(seen.has(key))throw new Error(`Duplicate transfer rule: ${rule.id}`);
  seen.add(key);
}

const payload={
  version:1,
  generatedAt:new Date().toISOString(),
  sourceCandidatesGeneratedAt:candidates.generatedAt||null,
  sourceFiles:sourceDocs.map(doc=>doc.file),
  description:'Curated station/railway-specific transfer times. Generated from transfer-rule source files and resolved against transfer-candidates.json.',
  rules:output
};
fs.writeFileSync(path.join(transit,'transfer-rules.json'),JSON.stringify(payload,null,2)+'\n');
console.log(JSON.stringify({sourceFiles:sourceDocs.length,sourceRules:sourceEntries.length,resolvedRules:output.length}));