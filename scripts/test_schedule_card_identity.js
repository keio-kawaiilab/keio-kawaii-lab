'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync('schedule-card-dedupe-v2.js','utf8');
const head=code.slice(0,code.indexOf('  function provider(option)'))+
  'globalThis.identityTest={cardIdentity};})();';
const context={document:{getElementById(){return {};}}};
vm.runInNewContext(head,context);
function card(venue,time='19:00'){
  return {
    getAttribute(name){return name==='data-group'?'SWEET STEADY':'';},
    querySelector(selector){
      if(selector==='.performance-date')return{textContent:'2026/10/26'};
      if(selector==='.meta')return{textContent:'開演 '+time};
      if(selector==='.meta a.venue-link')return{textContent:venue};
      return null;
    }
  };
}
const key=context.identityTest.cardIdentity;
assert.strictEqual(key(card('SGC HALL ARIAKE')),key(card('SGCホール有明')));
assert.notStrictEqual(key(card('SGC HALL ARIAKE')),key(card('Zepp Haneda')));
assert.notStrictEqual(key(card('SGC HALL ARIAKE','19:00')),key(card('SGC HALL ARIAKE','21:00')));
console.log('Browser card identity keeps venues/times distinct and unifies SGC venue aliases');
