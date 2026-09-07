'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const Core=require('../route-core.js');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const network=read('data/transit/toei/timetables/official-through-network.json');
const model=Core.createModel(['toei','keikyu','keisei','hokuso','shibayama'].map(s=>read(`data/transit/${s}/entities.json`)));
const element={addEventListener(){},value:'',disabled:false};
const context={document:{getElementById:()=>element},window:{RoutePlannerCore:Core},console,
               Map,Set,URLSearchParams,Date,location:{search:''},history:{replaceState(){}}};
vm.createContext(context);
let source=fs.readFileSync('route.js','utf8');
const end='  load();\n})();';
assert.ok(source.endsWith(end+'\n')||source.endsWith(end),'route test seam moved');
source=source.replace(end,'  window.testApi={direct:directNetworkTimedItinerary,setModel:function(m){model=m;}};\n})();');
vm.runInContext(source,context);
const api=context.window.testApi;api.setModel(model);
let tested=0, twoBoundaries=0;
const directions=new Set();
for(const trip of network.trips){
  const service=trip[0]===0?'weekday':'holiday';
  const path=[];
  for(const links of trip[4])for(const i of links)if(path.at(-1)!==network.railways[i])path.push(network.railways[i]);
  for(let i=0;i<path.length-1;i++){
    if(path[i].includes('Toei.Asakusa')||path[i+1].includes('Toei.Asakusa'))directions.add(service+':'+path[i]+'>'+path[i+1]);
  }
  if(path.some(r=>r.includes('Keikyu.'))&&path.some(r=>r.includes('Keisei.')))twoBoundaries++;
  const one=Object.assign({},network,{trips:[trip]});
  const first=trip[3][0],last=trip[3].at(-1);
  const departure=first[2]??first[1],arrival=last[1]??last[2];
  const a={nodes:[network.stations[first[0]]]},b={nodes:[network.stations[last[0]]]};
  const timed=api.direct(a,b,{__networks:[{data:one}]},departure,service);
  assert.ok(timed,'complete Asakusa journey not found: '+trip[5]);
  assert.equal(timed.transfers,0);assert.equal(timed.departure,departure);assert.equal(timed.arrival,arrival);
  assert.equal(api.direct(a,b,{__networks:[{data:one}]},departure,service==='weekday'?'holiday':'weekday'),null);
  assert.equal(api.direct(b,a,{__networks:[{data:one}]},departure,service),null,'a train cannot run backwards');
  tested++;
}
assert.equal(tested,1260);assert.equal(twoBoundaries,613);assert.equal(directions.size,8);
console.log(`Asakusa route checks passed: ${tested} exact journeys, ${twoBoundaries} across both boundaries, eight calendar/direction cases`);
