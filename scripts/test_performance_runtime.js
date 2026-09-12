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
const days='08-29 08-30 09-04 09-09 09-10 09-19 10-02 10-04 10-08 10-09 10-26 10-27 10-29 11-10 11-12 11-17 11-19 11-24 11-26 11-30 12-01 12-08 12-09'.split(' ').map(s=>'2026-'+s);
const today=new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Tokyo'});
const expected=days.filter(day=>day>=today);
function assertRendered(h, label) {
  for(const day of expected) assert(h.get('cards').innerHTML.includes('>'+day.replace(/-0?/g,'/')+'（'),label+': missing rendered date '+day);
}
async function main(){
  for(const offline of [false,true]){
    const h=await harness(offline);
    assertRendered(h,offline?'offline snapshot':'latest JSON');
    for(const [label,raw] of [['snapshot',snapshot.events],['latest',payload.publicEvents||payload.events]]){
      const models=h.api.show(raw,today,'CANDY TUNE');
      const tourDays=new Set(models.filter(m=>m.group==='CANDY TUNE'&&/JAPAN TOUR 2026/.test(m.title)).map(m=>m.date));
      for(const day of expected) assert(tourDays.has(day),label+': missing CANDY TUNE model '+day);
      assertRendered(h,label+' CANDY filter');
      for(const day of expected){
        h.get('calendar').children=[];
        h.api.show(raw,day,'CANDY TUNE');
        const marks=h.get('calendar').children.flatMap(w=>w.children).filter(e=>(e.className||'').includes('performance'));
        assert(marks.length>0,label+': no live calendar marks at '+day);
      }
    }
  }
  const h=await harness(true);h.api.clock('2099-09-12');
  const official='https://candytune.asobisystem.com/feature/test-tour';
  const pia='https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=12345';
  function show(day,time='18:00') {return {id:'show-'+day+'-'+time,entityType:'performance',group:'CANDY TUNE',eventScope:'kawaii-lab',title:'CANDY TUNE JAPAN TOUR 2099',eventDate:day,startTime:time,venue:'Hall',ticketType:'複数受付',url:official,urls:[official,pia],primarySource:'official',offers:[
    {sourceRowId:'fc-'+day,provider:'official',ticketType:'FC先行',url:official,applyStart:'2099-07-01T12:00',applyEnd:'2099-07-10T23:59'},
    {sourceRowId:'pia-'+day,provider:'pia',ticketType:'プレリザーブ',url:pia,applyStart:'2099-08-01T12:00',applyEnd:'2099-08-10T23:59'},
    {sourceRowId:'resale-'+day,provider:'official',ticketType:'公式リセール',url:official,applyStart:'2099-09-17T10:00',applyEnd:'2099-09-18T23:59'}]};}
  const input=[show('2099-09-19'),show('2099-09-20'),show('2099-09-19','14:00')];
  const before=JSON.stringify(input);const prepared=h.api.prepare(input);
  assert.strictEqual(JSON.stringify(input),before,'prepare mutated canonical source data');
  assert.strictEqual(h.api.performanceModels(prepared).length,3,'same lot collapsed distinct dates or matinee');
  assert(prepared.filter(e=>e.canonicalRuntimeRole==='performance').every(e=>!e.applyEnd&&e.ticketType==='現在受付なし'));
  const fc=prepared.find(e=>e.ticketType==='FC先行');assert.strictEqual(h.api.providerId(fc),'official');
  assert(!fc.urls.includes(pia),'FC offer inherited an unrelated Pia URL');
  assert.strictEqual(h.api.effectiveBand(fc),null,'ended FC still has an active band');
  assert(h.api.effectiveBand(prepared.find(e=>e.ticketType==='公式リセール')),'upcoming resale band disappeared');
  const model=h.api.performanceModels(prepared).find(m=>m.date==='2099-09-19'&&m.startTime==='18:00');
  assert.strictEqual(model.offers.length,3,'ticket history was lost');
  h.api.renderCards(prepared);assert(h.get('cards').innerHTML.includes('受付終了'),'ended reception label missing');
  assert(h.get('cards').innerHTML.includes('受付予定'),'future reception label missing');
  h.api.clock('2099-09-19');assert.strictEqual(h.api.performanceModels(h.api.prepare(input)).length,3,'show vanished on performance day');
  h.api.clock('2099-09-20');assert.strictEqual(h.api.performanceModels(h.api.prepare(input)).length,1,'past performances not removed');
  console.log('Performance runtime passed: '+expected.length+' upcoming CANDY TUNE dates after prepare/render, snapshot/latest/offline, FC/history/resale and date boundaries');
}
main().catch(error=>{console.error(error);process.exitCode=1});
