'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const page = fs.readFileSync(process.argv[2] || 'schedule.html', 'utf8');
const payload = JSON.parse(fs.readFileSync(process.argv[3] || 'data/live-events.json', 'utf8'));
const snapshot = JSON.parse(page.match(/<script id="snapshot-data"[^>]*>([\s\S]*?)<\/script>/)[1]);
const inline = [...page.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m => m[1]).find(s => s.includes('function prepare(raw)'));
const exported = inline.replace(/\}\)\(\);\s*$/, `globalThis.api={prepare,providerId,effectiveBand,performanceModels,renderCards,
  show:function(raw,day,group){events=prepare(raw);start=p(day);selected=group;render();return performanceModels(events.filter(e=>match(e,selected)&&scopeMatch(e)))},
  clock:function(day){now=moment(day+'T12:00',false);today=p(day);initial=today;start=today}};})();`);
function element() {
  return {children:[],appendChild(x){this.children.push(x)},setAttribute(){},
    classList:{add(){},remove(){},toggle(){}},style:{},innerHTML:'',textContent:''};
}
async function harness(failFetch) {
  const nodes = new Map();
  const get = id => {if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
  get('snapshot-data').textContent=JSON.stringify(snapshot);
  const context={console,Date,encodeURIComponent,setTimeout(){},
    document:{getElementById:get,createElement:element,querySelector(){return null},querySelectorAll(){return []}},
    window:{matchMedia(){return {matches:false}}},
    fetch(){return failFetch?Promise.reject(new Error('offline')):Promise.resolve({ok:true,json:()=>Promise.resolve(payload)})}};
  vm.runInNewContext(exported,context);
  await new Promise(resolve=>setImmediate(resolve));
  return {api:context.api,get};
}

async function main(){
 const targets=JSON.parse(fs.readFileSync('data/verified-general-sales.json','utf8')).observations.filter(r=>r.eventDate>=new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Tokyo'}));
 for(const offline of [false,true]){
  const h=await harness(offline);h.api.clock('2026-09-14');
  for(const raw of [snapshot.events,payload.publicEvents]){
   for(const row of targets){
    const models=h.api.show(raw,'2026-09-14',row.group);
    const matches=models.filter(m=>m.group===row.group&&m.date===row.eventDate&&m.startTime===row.startTime);
    assert.equal(matches.length,1,'exactly one performance '+row.id);
    const sale=matches[0].offers.find(o=>o.url===row.offer.url&&o.applyStart===row.offer.applyStart);
    assert(sale,'missing sale '+row.id);
    const html=h.get('cards').innerHTML;
    const cards=html.match(/<article[\s\S]*?<\/article>/g)||[];
    if((sale.event||sale).applicationStatus==='sold_out'){
      assert.equal(h.api.effectiveBand(sale.event||sale),null,'sold-out general sale band remains '+row.id);
      assert(!html.includes(row.offer.url.replace(/&/g,'&amp;')), 'sold-out application still visible '+row.id);
      continue;
    }
    const card=cards.find(c=>c.includes(row.offer.url.replace(/&/g,'&amp;'))&&c.includes('開演 '+row.startTime));
    assert(card,'missing rendered sale '+row.id);
    assert(card.includes((sale.event||sale).applicationStatus==='sold_out'?'予定枚数終了':'受付中'));
   }
  }
 }
 console.log('Verified general sales: five exact performances, snapshot/latest/offline, open/sold-out display passed');
}
main().catch(e=>{console.error(e);process.exitCode=1});
