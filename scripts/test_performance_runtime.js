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
  const available=prepared.find(e=>e.ticketType==='公式リセール');
  assert.strictEqual(h.api.effectiveBand({...available,applicationStatus:'sold_out'}),null,'sold-out reception still has an application band');
  assert(h.api.effectiveBand({...available,applicationStatus:'open'}),'available reception lost its band');

  const online={id:'online-benefit',group:'CANDY TUNE',eventScope:'kawaii-lab',eventCategory:'online-benefit',applicationDisplayMode:'offers',title:'CANDY TUNE オンライン特典会',eventDate:'2099-09-19',venue:'オンライン（SUKISUKI）',ticketType:'複数受付',url:official,urls:[official],primarySource:'official',offers:[
    {sourceRowId:'online-lottery',provider:'sukisuki',ticketType:'オンライン特典会・抽選販売',url:'https://sukisuki-shop.com/goods/lottery',applyStart:'2099-09-01T21:00',applyEnd:'2099-09-10T23:59'},
    {sourceRowId:'online-first-come',provider:'sukisuki',ticketType:'オンライン特典会・先着販売',url:'https://sukisuki-shop.com/goods/first-come',applyStart:'2099-09-18T20:00',applyEnd:'2099-09-19T17:00'}]};
  const onlinePrepared=h.api.prepare([online]);
  assert.strictEqual(onlinePrepared.filter(e=>e.canonicalRuntimeRole==='performance').length,1,'online benefit parent was not retained as one event');
  assert.strictEqual(onlinePrepared.filter(e=>e.canonicalRuntimeRole==='offer').length,2,'online benefit child receptions were not expanded');
  const onlineModel=h.api.performanceModels(onlinePrepared)[0];
  assert(onlineModel.online,'online benefit was not rendered as an online event');
  assert.strictEqual(onlineModel.offers.length,2,'online benefit receptions disappeared from the event card');
  h.api.renderCards(onlinePrepared);
  assert(h.get('cards').innerHTML.includes('オンライン特典会・先着販売'),'active online benefit reception is missing from the event card');

  const joint={id:'joint-benefit',entityType:'special-event',group:'KAWAII LAB.合同',participants:['CUTIE STREET','MORE STAR'],displayTitle:'CUTIE STREET／MORE STAR 大特典会',eventCategory:'large-benefit',eventScope:'kawaii-lab',applicationDisplayMode:'offers',title:'1stアルバム発売記念！CUTIE STREET/MORE STAR大特典会を開催決定！',eventDate:'2099-09-19',startTime:'11:20',venue:'神奈川県 パシフィコ横浜 展示ホールD',url:official,offers:[
    {sourceRowId:'cutie-hmv',sourceGroup:'CUTIE STREET',provider:'hmv',ticketType:'対象商品予約',url:'https://img.hmv.co.jp/cont/online/cutielandevent_lp/',applyStart:'2099-09-18T21:00',applyEnd:'2099-09-20T23:59'},
    {sourceRowId:'more-hmv',sourceGroup:'MORE STAR',provider:'hmv',ticketType:'対象商品予約',url:'https://img.hmv.co.jp/cont/online/morestarevent_lp/',applyStart:'2099-09-18T21:00',applyEnd:'2099-09-20T23:59'}]};
  const jointPrepared=h.api.prepare([joint]);
  const jointModel=h.api.performanceModels(jointPrepared)[0];
  assert.strictEqual(jointModel.title,joint.displayTitle,'canonical display title was ignored');
  assert.strictEqual(jointModel.offers.length,2,'same-provider joint offers were collapsed');
  h.api.renderCards(jointPrepared);
  assert(h.get('cards').innerHTML.includes('cutielandevent_lp'),'CUTIE STREET HMV reception is missing');
  assert(h.get('cards').innerHTML.includes('morestarevent_lp'),'MORE STAR HMV reception is missing');
  assert(h.get('cards').innerHTML.includes('CUTIE STREET / HMV'),'CUTIE STREET HMV label is ambiguous');
  assert(h.get('cards').innerHTML.includes('MORE STAR / HMV'),'MORE STAR HMV label is ambiguous');

  const sameDaySpecial={id:'same-day-special',entityType:'special-event',group:'CUTIE STREET',eventCategory:'large-benefit',eventScope:'kawaii-lab',title:'大特典会 in 大阪',eventDate:'2099-09-19',venue:'大阪府 某所※後日詳細発表',url:'https://cutiestreet.asobisystem.com/live_information/special'};
  const festivalOfficial={id:'festival-official',entityType:'performance',group:'CUTIE STREET',eventScope:'external',title:'HIROSHIMA CONTI-NeW FeS 2099',eventDate:'2099-09-19',eventDates:['2099-09-19'],startTime:'11:30',venue:'広島県 広島グリーンアリーナ',schedule:[{date:'2099-09-19',startTime:'11:30',venue:'広島県 広島グリーンアリーナ'}],url:'https://cutiestreet.asobisystem.com/live_information/festival'};
  const festivalTicket={id:'festival-ticket',group:'CUTIE STREET',eventScope:'external',title:'HIROSHIMA CONTI-NeW FeS 2099',eventDate:'2099-09-19',venue:'広島グリーンアリーナ',primarySource:'eplus',ticketProvider:'eplus',ticketType:'一般発売',applyStart:'2099-09-01T12:00',applyEnd:'2099-09-18T20:00',url:'https://eplus.jp/festival'};
  const sameDayPrepared=h.api.prepare([sameDaySpecial,festivalOfficial,festivalTicket]);
  const repairedFestival=sameDayPrepared.find(e=>e.id==='festival-ticket');
  assert.strictEqual(repairedFestival.venue,'広島県 広島グリーンアリーナ','same-day special event contaminated the festival venue');
  assert.strictEqual(repairedFestival.schedule[0].startTime,'11:30','same-day special event prevented the official festival time match');
  const festivalModel=h.api.performanceModels(sameDayPrepared).find(m=>/HIROSHIMA CONTI-NeW/.test(m.title));
  assert.strictEqual(festivalModel.venue,'広島県 広島グリーンアリーナ','festival card inherited the same-day special-event venue');

  const model=h.api.performanceModels(prepared).find(m=>m.date==='2099-09-19'&&m.startTime==='18:00');
  assert.strictEqual(model.offers.length,3,'ticket history was lost');
  h.api.renderCards(prepared);assert(!h.get('cards').innerHTML.includes('受付終了'),'ended reception leaked into application cards');
  assert(h.get('cards').innerHTML.includes('受付予定'),'future reception label missing');
  h.api.clock('2099-09-19');assert.strictEqual(h.api.performanceModels(h.api.prepare(input)).length,3,'show vanished on performance day');
  h.api.clock('2099-09-20');assert.strictEqual(h.api.performanceModels(h.api.prepare(input)).length,1,'past performances not removed');
  console.log('Performance runtime passed: '+expected.length+' upcoming CANDY TUNE dates after prepare/render, snapshot/latest/offline, FC/history/resale and date boundaries');
}
main().catch(error=>{console.error(error);process.exitCode=1});
