'use strict';
const fs=require('fs'), vm=require('vm'), assert=require('assert');
let code=fs.readFileSync('ticket-flow.js','utf8');
code=code.slice(0,code.indexOf('  var historyRequest='))+`globalThis.flowTest={show(history,card){historyAvailable=true;flowRowsByGroupDate=buildIndex(history);return flowHtml(safeRowsForCard(card));},curate:curatedHistoryRows}};})();`;
const context={document:{getElementById(){return {};}}};
vm.runInNewContext(code,context);
const history=JSON.parse(fs.readFileSync('data/ticket-history.json','utf8'));
const card={getAttribute(name){return name==='data-group'?'CUTIE STREET':'CUTIE STREET|2026-09-23|17:00';},querySelector(selector){return selector==='h3'?{textContent:'🎤 【CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-】'}:null;}};
const html=context.flowTest.show(history,card);
assert(html.includes('一般発売（当日引換券）'),'Yokohama general sale missing from history without visible application options');
assert(html.includes('eventCd=2635331&amp;rlsCd=001'),'verified source missing');
assert(html.includes('予定枚数終了'),'sold out history shown as available');
assert(html.includes('9/12 10:00 〜 9/22 23:59'),'verified window missing');
console.log('Yokohama general-sale history renders independently of hidden application options');

const oneoffs=JSON.parse(fs.readFileSync('data/ticket-history-backfill-oneoffs.json','utf8'));
const curated=context.flowTest.curate(oneoffs);
for(const day of ['2026-12-12','2026-12-13']){
  const christmasCard={
    getAttribute(name){return name==='data-group'?'KAWAII LAB.合同':'KAWAII LAB.合同|'+day+'|17:00';},
    querySelector(selector){return selector==='h3'?{textContent:'🎤 KAWAII LAB. Christmas SESSION 2026'}:null;}
  };
  const flow=context.flowTest.show({entries:curated},christmasCard);
  assert(flow.includes('プレリザーブ2次')&&flow.includes('9/4 18:00 〜 9/13 23:59'),'September presale missing: '+day);
  assert(flow.includes('プレリザーブ3次')&&flow.includes('10/21 18:00 〜 10/25 23:59'),'October presale missing: '+day);
  assert(flow.includes('7/11 19:30 〜 7/20 23:59'),'FC presale missing: '+day);
  assert(!flow.includes('プレリザーブ（初回）'),'unverified August sale unexpectedly published');
}
console.log('Christmas session fallback history: both dates validated');
