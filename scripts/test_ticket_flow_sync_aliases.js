'use strict';
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('ticket-flow-sync.js', 'utf8');
const code = source.slice(0, source.indexOf('  function run(){')) +
  'globalThis.testFlowSync={dedupeTimeline,semanticKey};})();';
const context = {
  URL,
  location:{href:'https://keio-kawaiilab.github.io/keio-kawaii-lab/schedule.html'},
  document:{getElementById(){return {};}}
};
vm.runInNewContext(code,context);

function step(title,period,url,isCurrent=false) {
  const classes = new Set(isCurrent?['current']:[]);
  return {
    title,period,url,removed:false,
    classList:{contains(name){return classes.has(name);},add(name){classes.add(name);}},
    querySelector(selector){
      if(selector==='.step-title')return{textContent:title};
      if(selector==='.period')return{textContent:period};
      if(selector==='.flow-source[href]')return url?{href:url}:null;
      return null;
    },
    remove(){this.removed=true;}
  };
}
function dedupe(rows){
  const timeline={querySelectorAll(selector){
    assert.strictEqual(selector,'.step');
    return rows.filter(row=>!row.removed);
  }};
  context.testFlowSync.dedupeTimeline(timeline);
  return rows.filter(row=>!row.removed);
}
const period='10/20 12:00 〜 10/27 23:59';
const link='https://fruitszipper.asobisystem.com/news/detail/201';
let generic=step('FC先行',period,link,true);
let named=step('FRUITS ZIPPER FC先行',period,link);
let out=dedupe([generic,named]);
assert.strictEqual(out.length,1);
assert.strictEqual(out[0],named);
assert(named.classList.contains('current'),'preserve live application state when replacing alias');

out=dedupe([
  step('FRUITS ZIPPER FC先行',period,link),
  step('KAWAII LAB. FC先行',period,link)
]);
assert.strictEqual(out.length,2,'distinct named fanclubs must not disappear');

out=dedupe([
  step('FC先行',period,link),
  step('FC先行',period,'https://fruitszipper.asobisystem.com/news/detail/202')
]);
assert.strictEqual(out.length,2,'different application URLs must survive');

out=dedupe([
  step('FC先行',period,link),
  step('FRUITS ZIPPER FC先行','10/28 12:00 〜 11/1 23:59',link)
]);
assert.strictEqual(out.length,2,'different reception rounds must survive');

out=dedupe([
  step('FC先行',period,link),
  step('FRUITS ZIPPER FC先行',period,link+'?utm_source=x')
]);
assert.strictEqual(out.length,1,'tracking parameters must not duplicate one signup');

console.log('FC signup alias dedupe, distinct fanclubs, URLs, rounds and active state passed');
