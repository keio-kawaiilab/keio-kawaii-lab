import fs from 'node:fs';
import path from 'node:path';

const transit=path.join(process.cwd(),'data','transit');
const candidates=JSON.parse(fs.readFileSync(path.join(transit,'transfer-candidates.json'),'utf8'));
const sources=JSON.parse(fs.readFileSync(path.join(transit,'transfer-block-sources.json'),'utf8'));

function pairMatches(row,block){
  return (row.railwayA===block.railwayA&&row.railwayB===block.railwayB)||
    (row.railwayA===block.railwayB&&row.railwayB===block.railwayA);
}
function stationPairKey(a,b){return a<b?`${a}\u0001${b}`:`${b}\u0001${a}`;}

const keyToMeta=new Map();
for(const block of sources.blocks||[]){
  const matches=(candidates.candidates||[]).filter(row=>row.placeLabel===block.place&&pairMatches(row,block));
  if(matches.length!==1)throw new Error(`${block.id}: expected 1 transfer candidate, got ${matches.length}`);
  const row=matches[0];
  if(!Array.isArray(row.sources)||!row.sources.includes('same-place-group'))throw new Error(`${block.id}: candidate is not a heuristic same-place transfer`);
  const aIsA=row.railwayA===block.railwayA;
  const stationIdsA=aIsA?row.stationIdsA:row.stationIdsB;
  const stationIdsB=aIsA?row.stationIdsB:row.stationIdsA;
  for(const stationA of stationIdsA||[]){
    for(const stationB of stationIdsB||[]){
      const key=stationPairKey(stationA,stationB);
      const previous=keyToMeta.get(key);
      const metadata={
        id:String(block.id||''),
        place:String(block.place||''),
        stationA,
        stationB,
        railwayA:String(block.railwayA||''),
        railwayB:String(block.railwayB||''),
        reason:String(block.reason||''),
        source:String(block.source||''),
        ...(block.correctConnectionSource?{correctConnectionSource:String(block.correctConnectionSource)}:{})
      };
      if(previous&&previous.id!==metadata.id)throw new Error(`Duplicate blocked station pair from ${previous.id} and ${metadata.id}`);
      keyToMeta.set(key,metadata);
    }
  }
}

const entries=[...keyToMeta.entries()].sort((a,b)=>a[0].localeCompare(b[0]));
const payload={
  version:1,
  generatedAt:new Date().toISOString(),
  sourceCandidatesGeneratedAt:candidates.generatedAt||null,
  verifiedAt:sources.verifiedAt||null,
  description:'Station pairs excluded only from the route planner same-name/nearby heuristic. Explicit connectingStation links are unaffected.',
  blockedStationPairs:entries.map(([key])=>key),
  blocks:entries.map(([,meta])=>meta)
};
fs.writeFileSync(path.join(transit,'transfer-blocks.json'),JSON.stringify(payload,null,2)+'\n');
console.log(JSON.stringify({sourceBlocks:(sources.blocks||[]).length,blockedStationPairs:entries.length}));
