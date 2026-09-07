'use strict';
const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const Core=require('../route-core.js');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const network=read('data/transit/keisei/timetables/official-network.json');
const model=Core.createModel(['toei','keikyu','keisei','hokuso','shibayama'].map(s=>read(`data/transit/${s}/entities.json`)));
const element={addEventListener(){},value:'',disabled:false};
const context={document:{getElementById:()=>element},window:{RoutePlannerCore:Core},console,
  Map,Set,URLSearchParams,Date,location:{search:''},history:{replaceState(){}}};
vm.createContext(context);
let source=fs.readFileSync('route.js','utf8');
const end='  load();\n})();';
assert.ok(source.endsWith(end+'\n')||source.endsWith(end));
source=source.replace(end,'  window.testApi={direct:directNetworkTimedItinerary,setModel:function(m){model=m;}};\n})();');
vm.runInContext(source,context);
const api=context.window.testApi;api.setModel(model);
const counts={Hokuso:0,Shibayama:0};
for(const trip of network.trips){
  const rails=new Set(trip[4].flat().map(i=>network.railways[i]));
  const operators=Object.keys(counts).filter(op=>rails.has(`manual.Railway:${op}.${op}`));
  if(!operators.length)continue;
  const cal=network.calendars[trip[0]],service=(cal==='weekday'||cal==='odpt.Calendar:Weekday')?'weekday':'holiday';
  const one=Object.assign({},network,{trips:[trip]});
  const first=trip[3][0],last=trip[3].at(-1),departure=first[2]??first[1],arrival=last[1]??last[2];
  const a={nodes:[network.stations[first[0]]]},b={nodes:[network.stations[last[0]]]};
  const timed=api.direct(a,b,{__networks:[{data:one}]},departure,service);
  assert.ok(timed,`northern journey not found: ${trip[2]}`);
  assert.equal(timed.transfers,0);assert.equal(timed.departure,departure);assert.equal(timed.arrival,arrival);
  assert.equal(api.direct(a,b,{__networks:[{data:one}]},departure,service==='weekday'?'holiday':'weekday'),null);
  assert.equal(api.direct(b,a,{__networks:[{data:one}]},departure,service),null);
  for(const op of operators)counts[op]++;
}
assert.equal(counts.Hokuso,870);assert.equal(counts.Shibayama,185);
const supplement=read('data/transit/hokuso/timetables/official-local-supplement.json');
const line=read('data/transit/hokuso/timetables/official-complete-hokuso.json');
for(const trip of supplement.trips){
  const service=supplement.calendars[trip[0]],first=trip[3][0],last=trip[3].at(-1);
  const a={nodes:[supplement.stations[first[0]]]},b={nodes:[supplement.stations[last[0]]]};
  const one=Object.assign({},supplement,{trips:[trip]});
  const timed=api.direct(a,b,{__networks:[{data:one}]},first[2],service);
  assert.ok(timed);assert.equal(timed.transfers,0);assert.equal(timed.arrival,last[1]);
  assert.equal(api.direct(a,b,{__networks:[{data:one}]},first[2],service==='weekday'?'holiday':'weekday'),null);
  const path=model.shortestPath(a,b);
  const ordinary=model.timedItinerary(path,{'manual.Railway:Hokuso.Hokuso':line},first[2],service,5);
  assert.ok(ordinary,'new local train must work in the per-line engine, not just direct-network fallback');
  assert.equal(ordinary.departure,first[2]);assert.equal(ordinary.arrival,last[1]);
}
assert.equal(supplement.trips.length,3);
console.log(`Northern exact route publications verified: ${JSON.stringify(counts)}`);
