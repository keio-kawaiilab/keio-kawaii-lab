import fs from 'node:fs';
import path from 'node:path';

const root=process.cwd();
const transit=path.join(root,'data','transit');
const candidates=JSON.parse(fs.readFileSync(path.join(transit,'transfer-candidates.json'),'utf8'));
const sources=JSON.parse(fs.readFileSync(path.join(transit,'transfer-rule-sources.json'),'utf8'));
const defaults=sources.defaults||{};
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
function sourceLabel(source,side){
  return String(source[`${side}Name`]||source[side]||'');
}

for(const source of sources.rules||[]){
  const matches=(candidates.candidates||[]).filter(row=>row.placeLabel===source.place&&samePair(row,source));
  if(matches.length!==1)throw new Error(`${source.place} ${sourceLabel(source,'railwayA')} / ${sourceLabel(source,'railwayB')}: expected 1 candidate, got ${matches.length}`);
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
  description:'Curated station/railway-specific transfer times. Generated from transfer-rule-sources.json and resolved against transfer-candidates.json.',
  rules:output
};
fs.writeFileSync(path.join(transit,'transfer-rules.json'),JSON.stringify(payload,null,2)+'\n');
console.log(JSON.stringify({sourceRules:(sources.rules||[]).length,resolvedRules:output.length}));
