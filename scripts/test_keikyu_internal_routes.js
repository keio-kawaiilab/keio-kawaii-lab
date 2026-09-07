'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const Core=require('../route-core.js');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const network=read('data/transit/keikyu/timetables/official-internal-network.json');
const entities=read('data/transit/keikyu/entities.json');
const model=Core.createModel([entities]);
const element={addEventListener(){},value:'',disabled:false};
const context={document:{getElementById:()=>element},window:{RoutePlannerCore:Core},console,
               Map,Set,URLSearchParams,Date,location:{search:''},history:{replaceState(){}}};
vm.createContext(context);
let source=fs.readFileSync('route.js','utf8');
const end='  load();\n})();';
assert.ok(source.endsWith(end+'\n')||source.endsWith(end),'route test seam moved');
source=source.replace(end,'  window.testApi={networkTrip:networkTrip,direct:directNetworkTimedItinerary,setModel:function(m){model=m;}};\n})();');
vm.runInContext(source,context);
const api=context.window.testApi;api.setModel(model);

let tested=0;const calendars=new Set(),directions=new Set();
for(const trip of network.trips){
  const path=[];
  for(const links of trip[4])for(const i of links){if(path.at(-1)!==network.railways[i])path.push(network.railways[i]);}
  if(path.length<2)continue;
  const service=trip[0]===0?'weekday':'holiday';calendars.add(service);
  for(let i=0;i<path.length-1;i++)directions.add(path[i]+'>'+path[i+1]);
  const one=Object.assign({},network,{trips:[trip]});
  const first=trip[3][0],last=trip[3].at(-1);
  const departure=first[2]??first[1],arrival=last[1]??last[2];
  const a={nodes:[network.stations[first[0]]]},b={nodes:[network.stations[last[0]]]};
  const timed=api.direct(a,b,{__networks:[{data:one}]},departure,service);
  assert.ok(timed,'official direct journey not found: '+trip[5]);
  assert.equal(timed.transfers,0);assert.equal(timed.departure,departure);assert.equal(timed.arrival,arrival);
  assert.equal(api.direct(a,b,{__networks:[{data:one}]},departure,service==='weekday'?'holiday':'weekday'),null);
  assert.equal(api.direct(b,a,{__networks:[{data:one}]},departure,service),null,'a through identity must not reverse a train');
  tested++;
}
assert.equal(tested,1368);assert.equal(calendars.size,2);assert.equal(directions.size,6);

const suffix=s=>network.stations.find(id=>id.endsWith('.'+s));
for(const service of ['weekday','holiday']){
  assert.equal(api.networkTrip(network,[suffix('ZushiHayama')],[suffix('Misakiguchi')],180,service,null),null,
               'Zushi and Kurihama must not acquire a fictitious direct train');
  assert.equal(api.networkTrip(network,[suffix('Uraga')],[suffix('Misakiguchi')],180,service,null),null,
               'the Uraga branch requires a change for Kurihama');
}
const runtime=read('data/transit-v2/runtime-same-train.json').edges;
const official=runtime.filter(e=>e[0].startsWith('tt:keikyu-official:')&&e[1].startsWith('tt:keikyu-official:'));
assert.equal(official.length,1590);
for(const [a,b]of official)assert.equal(a.split(':').slice(0,3).join(':'),b.split(':').slice(0,3).join(':'),'different physical groups joined');
console.log(`Keikyu route checks passed: ${tested} direct journeys, six directions, both calendars, ${official.length} exact runtime links`);
