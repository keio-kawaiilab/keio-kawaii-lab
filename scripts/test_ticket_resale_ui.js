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
