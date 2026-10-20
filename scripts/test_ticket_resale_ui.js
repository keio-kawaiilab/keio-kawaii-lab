'use strict';
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('ticket-resale-ui.js', 'utf8');
const code = source.slice(0, source.indexOf('  var queued=')) +
  'globalThis.testResale={isResaleText,decorateOption};})();';
const context = {document:{getElementById(){return {};},querySelector(){return {};}}};
vm.runInNewContext(code, context);
for (const title of ['プリセール', 'プリセール（先着先行）', 'presale', 'Presale tickets', 'FC先行']) {
  assert.strictEqual(context.testResale.isResaleText(title), false, title);
  const option = {querySelector(selector){return selector==='.ticket-copy b'?{textContent:title}:null;},
    classList:{add(){throw Error('presale must not be decorated as resale');}}};
  context.testResale.decorateOption(option);
}
for (const title of ['リセール', '公式リセール', 'ticket resale', 'RESALE']) {
  assert.strictEqual(context.testResale.isResaleText(title), true, title);
}
console.log('Presale is not reclassified as resale; legitimate resale labels remain recognized');
const version = fs.readFileSync('going-highlight-soften.js', 'utf8').match(/var version="(\d+)"/)[1];
assert(fs.readFileSync('train-status.js', 'utf8').includes('going-highlight-soften.js?v='+version));
assert(fs.readFileSync('scripts/build_schedule_snapshot.py', 'utf8').includes('train-status.js?v='+version));
assert(fs.readFileSync('.github/workflows/update-resale-fast.yml', 'utf8').includes('version = "'+version+'"'));
console.log('Resale cache version is consistent through loader, generator and recurring publisher');
