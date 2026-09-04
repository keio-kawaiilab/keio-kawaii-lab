import fs from 'node:fs';
import path from 'node:path';

const root=process.cwd();
const transit=path.join(root,'data','transit');
const candidates=JSON.parse(fs.readFileSync(path.join(transit,'transfer-candidates.json'),'utf8'));
const blockPayload=fs.existsSync(path.join(transit,'transfer-blocks.json'))
  ?JSON.parse(fs.readFileSync(path.join(transit,'transfer-blocks.json'),'utf8'))
  :{blockedStationPairs:[]};
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
const explicitlyResolvedCandidates=new Set();

function stationPairKey(a,b){return [String(a||''),String(b||'')].sort().join('\u0001');}
const blockedStationPairs=new Set((blockPayload.blockedStationPairs||[]).map(value=>{
  const parts=String(value).split('\u0001');
  return stationPairKey(parts[0],parts[1]);
}));
function candidateIsBlocked(row){
  if((row.sources||[]).includes('connecting-station'))return false;
  const pairs=[];
  for(const a of row.stationIdsA||[])for(const b of row.stationIdsB||[])pairs.push(stationPairKey(a,b));
  return pairs.length>0&&pairs.every(key=>blockedStationPairs.has(key));
}
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
function candidateKey(row){
  return [String(row.placeKey||row.placeLabel||''),...([String(row.railwayA||''),String(row.railwayB||'')].sort())].join('\u0001');
}
function pushResolvedRule({id,fromRailway,toRailway,fromStations,toStations,minutes,bidirectional=true,reverseMinutes,label='',source='',sourceType='',verifiedAt=''}){
  for(const fromStation of fromStations||[]){
    for(const toStation of toStations||[]){
      output.push({
        id:String(id||''),
        fromStation,
        toStation,
        fromRailway,
        toRailway,
        minutes,
        bidirectional,
        ...(reverseMinutes==null?{}:{reverseMinutes:Number(reverseMinutes)}),
        label:String(label||''),
        source:String(source||''),
        sourceType:String(sourceType||''),
        verifiedAt:String(verifiedAt||'')
      });
    }
  }
}

for(const entry of sourceEntries){
  const source=entry.source,defaults=entry.defaults;
  const matches=(candidates.candidates||[]).filter(row=>row.placeLabel===source.place&&samePair(row,source));
  if(matches.length!==1){
    throw new Error(`${entry.file}: ${source.place} ${sourceLabel(source,'railwayA')} / ${sourceLabel(source,'railwayB')}: expected 1 candidate, got ${matches.length}. Available railways at place: ${placeDiagnostics(source.place)}`);
  }
  const row=matches[0];
  explicitlyResolvedCandidates.add(candidateKey(row));
  const aIsRowA=sourceAIsRowA(row,source);
  const fromRailway=aIsRowA?row.railwayA:row.railwayB;
  const toRailway=aIsRowA?row.railwayB:row.railwayA;
  const fromStations=aIsRowA?row.stationIdsA:row.stationIdsB;
  const toStations=aIsRowA?row.stationIdsB:row.stationIdsA;
  const minutes=Number(source.minutes);
  if(!Number.isFinite(minutes)||minutes<0)throw new Error(`Invalid minutes for ${source.place}`);
  pushResolvedRule({
    id:String(source.id||`${source.place}-${sourceLabel(source,'railwayA')}-${sourceLabel(source,'railwayB')}`),
    fromRailway,toRailway,fromStations,toStations,minutes,
    bidirectional:source.bidirectional??defaults.bidirectional??true,
    reverseMinutes:source.reverseMinutes,
    label:String(source.label??defaults.label??''),
    source:String(source.source||''),
    sourceType:String(source.sourceType??defaults.sourceType??''),
    verifiedAt:String(source.verifiedAt??defaults.verifiedAt??'')
  });
}

let fallbackCandidatePairs=0;
for(const row of candidates.candidates||[]){
  if(explicitlyResolvedCandidates.has(candidateKey(row))||candidateIsBlocked(row))continue;
  const minutes=Number(row.fallbackMinutes);
  if(!Number.isFinite(minutes)||minutes<0)throw new Error(`Invalid fallbackMinutes for ${row.placeLabel}`);
  fallbackCandidatePairs++;
  pushResolvedRule({
    id:`fallback-${row.placeLabel}-${row.railwayAName}-${row.railwayBName}`,
    fromRailway:row.railwayA,
    toRailway:row.railwayB,
    fromStations:row.stationIdsA,
    toStations:row.stationIdsB,
    minutes,
    bidirectional:true,
    label:'暫定・安全側乗換',
    source:'data/transit/transfer-candidates.json',
    sourceType:'fallbackMinutes（駅間距離・接続関係から生成した安全側の暫定値。外部標準時間が登録されると自動的に置換）',
    verifiedAt:''
  });
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
  description:'Station/railway-specific transfer times. Explicit curated rules are preferred; any remaining unblocked candidate pair receives a conservative fallbackMinutes rule until an external standard time is added.',
  fallbackCandidatePairs,
  rules:output
};
fs.writeFileSync(path.join(transit,'transfer-rules.json'),JSON.stringify(payload,null,2)+'\n');
console.log(JSON.stringify({sourceFiles:sourceDocs.length,sourceRules:sourceEntries.length,fallbackCandidatePairs,resolvedRules:output.length}));
